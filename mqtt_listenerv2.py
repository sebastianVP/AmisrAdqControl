# -*- coding: utf-8 -*-
"""
mqtt_listener.py  v3.0
Windows XP + Python 3.4 compatible
paho-mqtt 1.3.1

Cambios v3.0 respecto a v2.0:
  - Importa status_amisr (mismo directorio) como modulo.
  - El driver de Firefox se abre UNA SOLA VEZ en __main__ y se
    pasa a leer_parametros() via variable global driver_selenium.
  - leer_parametros() llama a status_amisr.obtener_estado(driver)
    y construye el dict que loop_parametros() publica via MQTT.
  - El dict publicado incluye status_rf, status_mode, status_array
    y array_activo (el campo mas importante para la app movil).
  - Si el driver falla (None), el listener arranca igual y solo
    omite la publicacion de parametros hasta que se recupere.
"""

import threading
import logging
import ssl
import time
import json

import paho.mqtt.client as mqtt

# Importar como modulo — ambos archivos deben estar en el mismo directorio.
# Si status_amisr.py no existe o Selenium no esta instalado, se captura
# el ImportError y el listener funciona sin lectura web (degradado).
try:
    import status_amisr
    SELENIUM_DISPONIBLE = True
except ImportError as _ie:
    SELENIUM_DISPONIBLE = False
    logging.getLogger(__name__).warning(
        "status_amisr no disponible: {0}. Parametros no se publicaran.".format(str(_ie)))

# =========================
# CONFIG MQTT
# =========================
MQTT_HOST  = "ef5003dc4f0742d693f4d47946133d80.s1.eu.hivemq.cloud"
MQTT_PORT  = 8883
MQTT_USER  = "magic"
MQTT_PASS  = "4v4ld3zJROamisr"

TOPIC_CONTROL    = "radar/control"      # Recibe: ON / OFF
TOPIC_STATUS     = "radar/status"       # Publica: ON / OFF (confirmacion)
TOPIC_PARAMETROS = "radar/parametros"   # Publica: JSON con estado del radar

PYTHON3    = r"C:\Python34\python.exe"
SCRIPT_ON  = r"C:\Documents and Settings\radar\My Documents\app_python\app_on.py"
SCRIPT_OFF = r"C:\Documents and Settings\radar\My Documents\app_python\app_off.py"

# Segundos entre cada lectura de parametros via Selenium
INTERVALO_PARAMETROS = 5

# =========================
# LOGGER
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("mqtt_listener.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# =========================
# ESTADO GLOBAL
# =========================
ultimo_comando  = None    # Evita ejecuciones dobles del mismo comando
radar_encendido = False   # Controla el loop de publicacion de parametros
cliente_global  = None    # Referencia al cliente MQTT para publicar desde hilos

# Driver de Selenium: se inicializa en __main__ y se reutiliza en cada
# llamada a leer_parametros(). No se abre/cierra por ciclo.
driver_selenium = None


# =========================
# LECTURA DE PARAMETROS
# -------------------------
# Justificacion del diseno:
#   - Recibe driver_selenium (global) en lugar de abrirlo aqui porque
#     abrir Firefox cuesta ~5-10 s y loop_parametros() llama a esta
#     funcion cada INTERVALO_PARAMETROS segundos.
#   - Llama a status_amisr.obtener_estado() que es la unica funcion
#     que sabe como navegar la pagina y leer los <li>.
#   - Retorna None si la lectura falla para que loop_parametros()
#     no publique datos invalidos al broker.
# =========================
def leer_parametros():
    """
    Retorna un dict con el estado actual del radar leido via Selenium,
    o None si la lectura no es posible.

    Claves del dict retornado (coinciden con lo que espera la app movil):
        "status_rf"    -> str,  ej. "RF: 151.0 KW"
        "status_mode"  -> str,  ej. "Mode: ISR_lBeam_oblique_10ms_25"
        "status_array" -> str,  ej. "Array: online (tx)"
        "array_activo" -> bool, True si el arreglo esta transmitiendo

    La app movil muestra status_rf como "potencia", status_array como
    indicador principal de actividad, y status_mode como modo de operacion.
    """
    global driver_selenium

    # Caso 1: Selenium no esta instalado o status_amisr no se importo
    if not SELENIUM_DISPONIBLE:
        log.debug("leer_parametros: Selenium no disponible, retornando None")
        return None

    # Caso 2: El driver no fue inicializado o cerro por error
    if driver_selenium is None:
        log.warning("leer_parametros: driver_selenium es None, intentando reabrir...")
        driver_selenium = status_amisr.abrir_driver()
        if driver_selenium is None:
            log.error("leer_parametros: no se pudo reabrir Firefox")
            return None

    # Llamada a status_amisr — aqui ocurre el scraping real
    estado = status_amisr.obtener_estado(driver_selenium)

    # Caso 3: La lectura de la pagina fallo (timeout, pagina caida, etc.)
    if not estado["ok"]:
        log.error("leer_parametros: obtener_estado fallo -> {0}".format(estado["error"]))
        # Si el driver se corrompio (ej. Firefox cerro inesperadamente),
        # lo marcamos None para que el proximo ciclo intente reabrirlo.
        if "WebDriverException" in (estado["error"] or ""):
            log.warning("leer_parametros: driver posiblemente invalido, reseteando")
            driver_selenium = None
        return None

    # Construccion del dict final que se publicara como JSON en MQTT.
    # Solo se incluyen los campos que la app movil conoce y espera.
    datos = {
        "status_rf":    estado["status_rf"],     # texto completo del RF
        "status_mode":  estado["status_mode"],   # modo de operacion
        "status_array": estado["status_array"],  # texto del array
        "array_activo": estado["array_activo"],  # bool — el mas importante
    }

    log.info("leer_parametros OK -> array_activo={0}".format(datos["array_activo"]))
    return datos


# =========================
# PUBLICAR ESTADO (radar/status)
# =========================
def publicar_estado(client, estado):
    """Publica 'ON' o 'OFF' en radar/status con retain=True."""
    try:
        result = client.publish(TOPIC_STATUS, estado, qos=1, retain=True)
        if result.rc == 0:
            log.info("Publicado en {0}: {1}".format(TOPIC_STATUS, estado))
        else:
            log.warning("Fallo al publicar estado (rc={0})".format(result.rc))
    except Exception as e:
        log.error("publicar_estado: {0}".format(str(e)))


# =========================
# LOOP DE PARAMETROS
# -------------------------
# Justificacion del threading:
#   client.loop_forever() bloquea el hilo principal. Este hilo daemon
#   corre en paralelo y publica los parametros periodicamente.
#   Es daemon=True para que no impida el cierre del proceso.
# =========================
def loop_parametros(client):
    global radar_encendido
    log.info("Loop de parametros iniciado (intervalo={0}s)".format(INTERVALO_PARAMETROS))

    while True:
        if radar_encendido:
            datos = leer_parametros()
            if datos is not None:
                try:
                    payload = json.dumps(datos)
                    result = client.publish(TOPIC_PARAMETROS, payload, qos=0)
                    if result.rc == 0:
                        log.info("Parametros publicados: {0}".format(payload))
                    else:
                        log.warning("Fallo al publicar parametros (rc={0})".format(result.rc))
                except Exception as e:
                    log.error("loop_parametros publish: {0}".format(str(e)))
            else:
                log.debug("leer_parametros retorno None, no se publica este ciclo")
        time.sleep(INTERVALO_PARAMETROS)


# =========================
# EJECUTAR SCRIPT  (sin cambios desde v1.0)
# =========================
def ejecutar_script(script_path):
    import subprocess
    try:
        proceso = subprocess.Popen(
            [PYTHON3, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        for line in proceso.stdout:
            log.info("  [script] {0}".format(line.rstrip()))
        proceso.wait()
        log.info("Script finalizado con codigo: {0}".format(proceso.returncode))
    except Exception as e:
        log.error("Error ejecutando script: {0}".format(str(e)))


# =========================
# CALLBACKS MQTT  (sin cambios desde v2.0)
# =========================
def on_connect(client, userdata, flags, rc):
    codigos = {
        0: "Conexion exitosa",
        1: "Version MQTT incorrecta",
        2: "ID de cliente invalido",
        3: "Broker no disponible",
        4: "Usuario/contrasena incorrectos",
        5: "No autorizado"
    }
    log.info("on_connect rc={0} | {1}".format(rc, codigos.get(rc, "Desconocido")))
    if rc == 0:
        client.subscribe(TOPIC_CONTROL, qos=1)
        log.info("Suscrito al topic: {0}".format(TOPIC_CONTROL))
    else:
        log.error("No se pudo conectar al broker")


def on_message(client, userdata, msg):
    global ultimo_comando, radar_encendido
    payload = msg.payload.decode("utf-8").strip().upper()
    log.info("Mensaje recibido | topic: {0} | payload: {1}".format(
        msg.topic, payload))

    if payload == ultimo_comando:
        log.warning("Comando '{0}' repetido, ignorando ejecucion doble".format(payload))
        return

    if payload == "ON":
        ultimo_comando  = "ON"
        log.info("Ejecutando app_on.py...")
        ejecutar_script(SCRIPT_ON)
        radar_encendido = True
        publicar_estado(client, "ON")

    elif payload == "OFF":
        ultimo_comando  = "OFF"
        log.info("Ejecutando app_off.py...")
        radar_encendido = False
        ejecutar_script(SCRIPT_OFF)
        publicar_estado(client, "OFF")

    else:
        log.warning("Payload desconocido: '{0}' ignorado".format(payload))


def on_disconnect(client, userdata, rc):
    log.warning("Desconectado del broker (rc={0})".format(rc))


# =========================
# SSL CONTEXT  (sin cambios desde v1.0)
# =========================
def crear_ssl_context():
    ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# =========================
# CLIENTE MQTT
# =========================
def iniciar_cliente():
    client = mqtt.Client(client_id="radar_listener", clean_session=True)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set_context(crear_ssl_context())
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect
    return client


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    log.info("=" * 50)
    log.info("MQTT Listener v3.0 iniciado")
    log.info("Broker   : {0}:{1}".format(MQTT_HOST, MQTT_PORT))
    log.info("Suscribe : {0}".format(TOPIC_CONTROL))
    log.info("Publica  : {0}  {1}".format(TOPIC_STATUS, TOPIC_PARAMETROS))
    log.info("Selenium : {0}".format("disponible" if SELENIUM_DISPONIBLE else "NO disponible"))
    log.info("=" * 50)

    # Abrir Firefox una sola vez antes de entrar al loop MQTT.
    # Si falla, el listener arranca igual pero sin publicar parametros.
    if SELENIUM_DISPONIBLE:
        driver_selenium = status_amisr.abrir_driver()
        if driver_selenium is None:
            log.warning("Firefox no pudo abrirse. Parametros no se publicaran.")
    else:
        driver_selenium = None

    cliente_global = iniciar_cliente()

    # Hilo de parametros: daemon, corre mientras el proceso este vivo
    hilo_params = threading.Thread(
        target=loop_parametros,
        args=(cliente_global,)
    )
    hilo_params.daemon = True
    hilo_params.start()

    # Loop principal con reconexion automatica (igual que v1.0 y v2.0)
    while True:
        try:
            log.info("Conectando al broker...")
            cliente_global.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            cliente_global.loop_forever()
        except Exception as e:
            log.error("Error de conexion: {0}".format(str(e)))
            log.info("Reintentando en 10 segundos...")
            time.sleep(10)