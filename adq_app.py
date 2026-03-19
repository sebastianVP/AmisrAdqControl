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
# CONFIGURACIÓN
# =========================
firefox_path = r"C:\firefox45\firefox.exe"
python_exe = r"C:\Python34\python.exe"
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
    print("Paso 4: Página AMISR cargada")

except Exception as e:
    print("ERROR al abrir navegador:")
    print(str(e))
    sys.exit(1)

# =========================
# PASO 2: Ejecutar script en paralelo
# =========================
print("Paso 5: Ejecutando script de atenuación...")

process = subprocess.Popen(
    [python_exe25, "-u", script_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True
)

def print_output(proc):
    for line in proc.stdout:
        print(line, end='')

thread = threading.Thread(target=print_output, args=(process,))
thread.daemon = True
thread.start()

print("Script ejecutándose en paralelo")

# =========================
# PASO 3: Esperar 70 segundos (desde inicio)
# =========================
print("Paso 6: Esperando 70 segundos...")
time.sleep(70)

# =========================
# PASO 4: Presionar botón Manual
# =========================
print("Paso 7: Intentando presionar botón Manual...")

try:
    time.sleep(5)  # pequeña espera para asegurar carga

    button = driver.find_element_by_id("ext-gen146")
    button.click()

    print("Paso 8: Botón 'Manual' presionado correctamente")

except Exception as e:
    print("ERROR al presionar botón:")
    print(str(e))

# =========================
# FIN
# =========================
print("FIN: " + time.ctime())
print("==============================")