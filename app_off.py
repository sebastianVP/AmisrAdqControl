# -*- coding: utf-8 -*-
# UBICACION C:\Documents and Settings\radar\My Documents\app_python
import sys
import time
import subprocess
import threading
from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary

# =========================
# LOGGER
# =========================
class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open("consola_off.log", "w")
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
# CONFIG
# =========================
firefox_path = r"C:\firefox45\firefox.exe"
python_exe25 = r"C:\Python25\python.exe"
script_path = r"C:\Documents and Settings\radar\Desktop\scripts\attenuate_radar2.py"
url = "http://dtc0:9000/"

print("==============================")
print("INICIO: " + time.ctime())

# =========================
# ABRIR NAVEGADOR
# =========================
binary = FirefoxBinary(firefox_path)
try:
    driver = webdriver.Firefox(firefox_binary=binary)
    print("Navegador abierto correctamente")
    driver.get(url)
    print("Página AMISR cargada")
except Exception as e:
    print("ERROR al abrir navegador:")
    print(str(e))
    sys.exit(1)

# =========================
# EJECUTAR ATENUADOR
# =========================
process = subprocess.Popen(
    [python_exe25, "-u", script_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True
)

# =========================
# MONITOREO + APAGADO
# =========================
def monitor_proceso(proc, driver):
    boton_presionado = False
    for line in proc.stdout:
        print(line, end='')
        if "starting steady time" in line and not boton_presionado:
            print(">>> MOMENTO EXACTO DETECTADO <<<")
            try:
                time.sleep(2)
                driver.find_element_by_id("ext-gen146").click()
                print(">>> BOTÓN Manual presionado <<<")
                time.sleep(7)
                driver.find_element_by_id("ext-gen223").click()
                print(">>> BOTÓN ext-gen223 presionado <<<")
                time.sleep(5)
                driver.find_element_by_id("ext-gen216").click()
                print(">>> BOTÓN ext-gen216 presionado <<<")
                time.sleep(3)
                driver.find_element_by_id("ext-gen209").click()
                print(">>> BOTÓN ext-gen209 presionado <<<")
                time.sleep(3)

                # =========================
                # BOTÓN ABORT
                # =========================
                driver.find_element_by_id("ext-gen202").click()
                print(">>> BOTÓN ext-gen202 (ABORT) presionado <<<")

                # =========================
                # MANEJO DEL POPUP (ALERT NATIVO O MODAL HTML)
                # =========================
                time.sleep(1)
                ok_presionado = False

                for i in range(5):
                    # --- CASO 1: Alert nativo del navegador ---
                    try:
                        alert = driver.switch_to.alert
                        texto_alert = alert.text
                        print(">>> ALERT DETECTADO: '{}' <<<".format(texto_alert))
                        alert.accept()   # .accept() = OK | .dismiss() = Cancel
                        print(">>> OK PRESIONADO EN ALERT NATIVO <<<")
                        ok_presionado = True
                        break
                    except Exception:
                        pass

                    # --- CASO 2: Modal HTML (botón dentro de la página) ---
                    try:
                        button_ok = driver.find_element_by_xpath(
                            "//button[normalize-space()='OK'] | "
                            "//button[normalize-space()='Ok'] | "
                            "//button[normalize-space()='Aceptar']"
                        )
                        button_ok.click()
                        print(">>> OK PRESIONADO EN MODAL HTML <<<")
                        ok_presionado = True
                        break
                    except Exception:
                        pass

                    print("  Intento {}/5 - popup aun no visible, esperando...".format(i + 1))
                    time.sleep(1)

                if not ok_presionado:
                    print(">>> ERROR: No se encontro popup OK tras 5 intentos <<<")

                time.sleep(6)
                time.sleep(2)
                print(">>> SECUENCIA DE APAGADO COMPLETADA <<<")
                boton_presionado = True

            except Exception as e:
                print("ERROR en secuencia de apagado:")
                print(str(e))

# =========================
# THREAD
# =========================
thread = threading.Thread(target=monitor_proceso, args=(process, driver))
thread.daemon = False
thread.start()
print("Monitoreando proceso en tiempo real...")

# =========================
# FINALIZACIÓN
# =========================
process.wait()
thread.join()
print("Proceso de atenuación finalizado")

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