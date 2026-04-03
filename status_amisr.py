# -*- coding: utf-8 -*-
"""
status_amisr.py  v2.0
Recupera el estado del radar AMISR-14 via Selenium.

CAMBIO v2.0 respecto a v1.0:
  Se agrego la funcion publica obtener_estado(driver) que retorna
  un dict listo para ser publicado por mqtt_listener.py.
  El bloque __main__ queda para pruebas manuales independientes.

Compatible: Python 3.4 + Selenium 2.53.6 + Firefox 45 ESR / Windows XP
"""

import sys
import time
import logging

from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.common.exceptions import NoSuchElementException, WebDriverException

# =========================
# CONFIGURACION
# =========================
FIREFOX_PATH = r"C:\firefox45\firefox.exe"
URL_RADAR    = "http://firewall.amisr.net/monitor"


# Segundos que se espera a que ExtJS termine de renderizar el ledlist.
# ExtJS construye el DOM dinamicamente; sin este sleep los find_element
# devuelven NoSuchElementException aunque la pagina este cargada.
ESPERA_CARGA = 5

# =========================
# LOGGER — seguro para XP
# =========================
class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open("status_amisr.log", "w")

    def write(self, message):
        try:
            self.terminal.write(message)
        except Exception:
            pass
        try:
            self.log.write(message.encode("ascii", "ignore").decode("ascii"))
        except Exception:
            pass

    def flush(self):
        pass

# Solo redirigir stdout cuando se ejecuta como script principal.
# Si se importa como modulo, el logger del modulo padre (mqtt_listener)
# ya esta activo y no hay que sobreescribir sys.stdout.
if __name__ == "__main__":
    sys.stdout = Logger()
    sys.stderr = sys.stdout

log = logging.getLogger(__name__)

# =========================
# HELPER INTERNO
# =========================
def _clase_activa(clase):
    """
    Convierte el atributo class del <li> a booleano.
    Valores activos observados en la pagina: "on", "true".
    Cualquier otro valor (None, "off", cadena vacia) = inactivo.
    """
    if clase is None:
        return False
    return clase.strip().lower() in ("on", "true")


# =========================
# FUNCION PUBLICA PRINCIPAL
# =========================
def obtener_estado(driver):
    """
    Navega a la pagina del radar y lee los tres elementos de estado.

    Parametros:
        driver -- instancia de webdriver.Firefox ya abierta y reutilizable.
                  Se recibe desde afuera para NO abrir/cerrar el navegador
                  en cada llamada (abrir Firefox tarda ~5-10 s).

    Retorna:
        dict con las claves:
            "status_rf"     -> texto leido, ej. "RF: 151.0 KW"   (str o None)
            "status_mode"   -> texto leido, ej. "Mode: ISR_..."   (str o None)
            "status_array"  -> texto leido, ej. "Array: online"   (str o None)
            "array_activo"  -> True si class=="on", False en caso contrario (bool)
            "ok"            -> True si la lectura fue exitosa      (bool)
            "error"         -> mensaje de error o None             (str o None)

        Cuando "ok" es False, los campos de texto pueden ser None.
        mqtt_listener.py debe chequear ["ok"] antes de publicar.

    Justificacion de las claves:
        - "status_rf", "status_mode", "status_array" mapean 1:1 con los IDs
          del HTML observados en la imagen (<li id="status-rf"> etc.).
        - "array_activo" es el campo mas importante segun el requerimiento:
          indica si el arreglo esta transmitiendo (class="on") o no.
        - "ok" permite al caller distinguir entre "array apagado" (ok=True,
          array_activo=False) y "no se pudo leer la pagina" (ok=False).
    """
    resultado = {
        "status_rf":    None,
        "status_mode":  None,
        "status_array": None,
        "array_activo": False,
        "ok":           False,
        "error":        None,
    }

    try:
        log.info("Navegando a: {0}".format(URL_RADAR))
        driver.get(URL_RADAR)

        # Espera fija para que ExtJS renderice el <ul id="status-list">
        log.info("Esperando {0}s a que cargue el DOM (ExtJS)...".format(ESPERA_CARGA))
        time.sleep(ESPERA_CARGA)

        # --- status-rf ---
        try:
            el = driver.find_element_by_id("status-rf")
            resultado["status_rf"] = el.text.strip()
            log.info("status-rf   -> '{0}' (class='{1}')".format(
                resultado["status_rf"], el.get_attribute("class")))
        except NoSuchElementException:
            log.warning("Elemento 'status-rf' no encontrado")

        # --- status-mode ---
        try:
            el = driver.find_element_by_id("status-mode")
            resultado["status_mode"] = el.text.strip()
            log.info("status-mode -> '{0}' (class='{1}')".format(
                resultado["status_mode"], el.get_attribute("class")))
        except NoSuchElementException:
            log.warning("Elemento 'status-mode' no encontrado")

        # --- status-array (el mas importante) ---
        try:
            el = driver.find_element_by_id("status-array")
            clase = el.get_attribute("class")
            resultado["status_array"] = el.text.strip()
            resultado["array_activo"] = _clase_activa(clase)
            log.info("status-array-> '{0}' (class='{1}') -> array_activo={2}".format(
                resultado["status_array"], clase, resultado["array_activo"]))
        except NoSuchElementException:
            log.warning("Elemento 'status-array' no encontrado")

        resultado["ok"] = True

    except WebDriverException as e:
        resultado["error"] = "WebDriverException: {0}".format(str(e))
        log.error(resultado["error"])

    except Exception as e:
        resultado["error"] = "Error inesperado: {0}".format(str(e))
        log.error(resultado["error"])

    return resultado


# =========================
# GESTION DEL DRIVER
# (usadas por __main__ y por mqtt_listener al arrancar)
# =========================
def abrir_driver():
    """
    Abre Firefox y retorna la instancia del driver.
    Retorna None si falla — el caller debe manejar este caso.

    Se llama UNA SOLA VEZ al inicio del proceso (en mqtt_listener.py
    dentro del bloque __main__, antes del loop de reconexion MQTT).
    No se llama dentro de leer_parametros() para no pagar el costo
    de arrancar Firefox en cada ciclo de 5 segundos.
    """
    try:
        log.info("Abriendo Firefox: {0}".format(FIREFOX_PATH))
        binary = FirefoxBinary(FIREFOX_PATH)
        driver = webdriver.Firefox(firefox_binary=binary)
        log.info("Firefox abierto correctamente")
        return driver
    except Exception as e:
        log.error("No se pudo abrir Firefox: {0}".format(str(e)))
        return None


def cerrar_driver(driver):
    """Cierra Firefox sin propagar excepciones."""
    try:
        driver.quit()
        log.info("Firefox cerrado")
    except Exception as e:
        log.warning("Error al cerrar Firefox: {0}".format(str(e)))


# =========================
# MAIN — prueba manual independiente
# =========================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    print("=" * 50)
    print("status_amisr.py  INICIO: " + time.ctime())
    print("=" * 50)

    driver = abrir_driver()
    if driver is None:
        print("ERROR: No se pudo abrir el navegador")
        sys.exit(1)

    estado = obtener_estado(driver)

    cerrar_driver(driver)

    print("")
    print("=" * 50)
    print("RESULTADO:")
    for clave, valor in estado.items():
        print("  {0}: {1}".format(clave, valor))
    print("=" * 50)
    print("FIN: " + time.ctime())

    if not estado["ok"]:
        sys.exit(1)