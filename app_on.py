# -*- coding: utf-8 -*-

import sys
import time
import subprocess
import threading

from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary

# =========================
# LOGGER SEGURO PARA XP
# =========================
class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open("consola.log", "w")

    def write(self, message):
        try:
            self.terminal.write(message)
        except:
            pass
        try:
            self.log.write(message.encode('ascii', 'ignore').decode('ascii'))
        except:
            pass

    def flush(self):
        pass

sys.stdout = Logger()
sys.stderr = sys.stdout

# =========================
# CONFIGURACIÃ“N
# =========================
firefox_path = r"C:\firefox45\firefox.exe"
python_exe25 = r"C:\Python25\python.exe"

script_path = r"C:\Documents and Settings\radar\Desktop\scripts\attenuate_radar2.py"
url = "http://dtc0:9000/"

print("==============================")
print("INICIO: " + time.ctime())

# =========================
# PASO 1: Abrir navegador
# =========================
print("Paso 1: Configurando Firefox")

binary = FirefoxBinary(firefox_path)

print("Paso 2: Abriendo navegador con Selenium...")

try:
    driver = webdriver.Firefox(firefox_binary=binary)
    print("Paso 3: Navegador abierto correctamente")

    driver.get(url)
    print("Paso 4: PÃ¡gina AMISR cargada")

except Exception as e:
    print("ERROR al abrir navegador:")
    print(str(e))
    sys.exit(1)

# =========================
# PASO 2: Ejecutar script en paralelo
# =========================
print("Paso 5: Ejecutando script de atenuaciÃ³n...")

process = subprocess.Popen(
    [python_exe25, "-u", script_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True
)

# =========================
# FUNCIÃ“N PARA LEER OUTPUT Y SINCRONIZAR
# =========================
def monitor_proceso(proc, driver):
    boton_presionado = False

    for line in proc.stdout:
        print(line, end='')

        # ðŸ”¥ DETECCIÃ“N CLAVE (sincronizaciÃ³n exacta)
        if "starting steady time" in line and not boton_presionado:
            print(">>> MOMENTO EXACTO DETECTADO <<<")

            try:
                # pequeÃ±a espera para asegurar que el DOM estÃ© listo
                time.sleep(2)

                button = driver.find_element_by_id("ext-gen146")
                button.click()

                print(">>> BOTÃ“N 'Manual' PRESIONADO AUTOMÃTICAMENTE <<<")
                boton_presionado = True

            except Exception as e:
                print("ERROR al presionar botÃ³n:")
                print(str(e))

# =========================
# LANZAR HILO DE MONITOREO
# =========================
thread = threading.Thread(target=monitor_proceso, args=(process, driver))
thread.daemon = True
thread.start()

print("Script ejecutÃ¡ndose y monitoreado en tiempo real...")

# =========================
# ESPERAR A QUE TERMINE EL PROCESO
# =========================
process.wait()

print("Proceso de atenuaciÃ³n finalizado")

# =========================
# CERRAR NAVEGADOR
# =========================
print("Cerrando navegador...")

try:
    driver.quit()
    print("Navegador cerrado correctamente")
except Exception as e:
    print("Error al cerrar navegador:")
    print(str(e))

# =========================
# FIN
# =========================
print("FIN: " + time.ctime())
print("==============================")