# -*- coding: utf-8 -*-
"""
mqtt_listener.py
Windows XP + Python 3.4 compatible
paho-mqtt 1.3.1
"""

import subprocess
import logging
import ssl
import time
import os
import paho.mqtt.client as mqtt

# =========================
# CONFIG — edita estos valores
# =========================
MQTT_HOST  = "ef5003dc4f0742d693f4d47946133d80.s1.eu.hivemq.cloud"
MQTT_PORT  = 8883
MQTT_USER  = "magic"
MQTT_PASS  = "4v4ld3zJROamisr"
MQTT_TOPIC = "radar/control"

PYTHON3    = r"C:\Python34\python.exe"
SCRIPT_ON  = r"C:\Documents and Settings\radar\My Documents\app_python\app_on.py"
SCRIPT_OFF = r"C:\Documents and Settings\radar\My Documents\app_python\app_off.py"

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
# ESTADO — evita ejecuciones dobles
# =========================
ultimo_comando = None

# =========================
# CALLBACKS
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
        client.subscribe(MQTT_TOPIC, qos=1)
        log.info("Suscrito al topic: {0}".format(MQTT_TOPIC))
    else:
        log.error("No se pudo conectar al broker")


def on_message(client, userdata, msg):
    global ultimo_comando
    payload = msg.payload.decode("utf-8").strip().upper()
    log.info("Mensaje recibido | topic: {0} | payload: {1}".format(msg.topic, payload))

    if payload == ultimo_comando:
        log.warning("Comando '{0}' repetido, ignorando ejecucion doble".format(payload))
        return

    if payload == "ON":
        ultimo_comando = "ON"
        log.info("Ejecutando app_on.py...")
        ejecutar_script(SCRIPT_ON)

    elif payload == "OFF":
        ultimo_comando = "OFF"
        log.info("Ejecutando app_off.py...")
        ejecutar_script(SCRIPT_OFF)

    else:
        log.warning("Payload desconocido: '{0}' ignorado".format(payload))


def on_disconnect(client, userdata, rc):
    log.warning("Desconectado del broker (rc={0})".format(rc))


# =========================
# EJECUTAR SCRIPT
# =========================
def ejecutar_script(script_path):
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
# SSL CONTEXT — compatible con XP + Python 3.4
# =========================
def crear_ssl_context():
    # ssl.PROTOCOL_TLS no existe en 3.4, se usa PROTOCOL_SSLv23
    ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    ctx.verify_mode = ssl.CERT_NONE   # XP no tiene CA bundle actualizado
    return ctx


# =========================
# CLIENTE MQTT
# =========================
def iniciar_cliente():
    client = mqtt.Client(client_id="radar_listener", clean_session=True)
    client.username_pw_set(MQTT_USER, MQTT_PASS)

    ssl_ctx = crear_ssl_context()
    client.tls_set_context(ssl_ctx)

    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    return client


# =========================
# MAIN — con reconexion automatica
# =========================
if __name__ == "__main__":
    log.info("=" * 50)
    log.info("MQTT Listener iniciado")
    log.info("Broker: {0}:{1}".format(MQTT_HOST, MQTT_PORT))
    log.info("Topic:  {0}".format(MQTT_TOPIC))
    log.info("=" * 50)

    client = iniciar_cliente()

    while True:
        try:
            log.info("Conectando al broker...")
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_forever()
        except Exception as e:
            log.error("Error de conexion: {0}".format(str(e)))
            log.info("Reintentando en 10 segundos...")
            time.sleep(10)