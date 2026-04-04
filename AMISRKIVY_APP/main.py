# -*- coding: utf-8 -*-
"""
RADAR AMISR-14 — Control Interface v3.0
Instituto Geofísico del Perú

Mejoras v3.0:
  - Pantalla de login con registro de usuarios autorizados
  - Panel de parámetros (potencia, corriente, voltaje) — solo visible cuando ON
  - Log de actividad con timestamps
  - Animación de transición entre pantallas
  - Arquitectura escalable (ScreenManager)
  - MQTT robusto con reconexión automática
"""

import ssl
import threading
import time
import hashlib
import json
import os
from datetime import datetime

import paho.mqtt.client as mqtt
import certifi

# ---- TECLADO: parche directo a config.ini -------------------------
# Kivy 2.3 en Linux/SDL2 lee ~/.kivy/config.ini al arrancar y ese
# valor sobreescribe cualquier Config.set posterior. La unica forma
# garantizada de forzar keyboard_mode antes de que Window se cree
# es modificar el archivo antes de importar kivy.app.
#
# keyboard_mode 'system' = el SO maneja el teclado (correcto en desktop).
# keyboard_mode 'single' = Kivy lo maneja internamente; en SDL2/Linux no
# solicita el foco al compositor y los TextInput no reciben teclas.
import configparser
_kivy_cfg_path = os.path.join(os.path.expanduser('~'), '.kivy', 'config.ini')
if os.path.exists(_kivy_cfg_path):
    _cfg = configparser.ConfigParser()
    _cfg.read(_kivy_cfg_path)
    if not _cfg.has_section('kivy'):
        _cfg.add_section('kivy')
    _cfg.set('kivy', 'keyboard_mode', 'system')
    with open(_kivy_cfg_path, 'w') as _f:
        _cfg.write(_f)
# -------------------------------------------------------------------

from kivy.config import Config
Config.set('kivy', 'keyboard_mode', 'system')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.metrics import dp
from kivy.properties import StringProperty

# ============================================================
# CONFIGURACIÓN MQTT
# ============================================================
MQTT_HOST  = "ef5003dc4f0742d693f4d47946133d80.s1.eu.hivemq.cloud"
MQTT_PORT  = 8883
MQTT_USER  = "magic"
MQTT_PASS  = "4v4ld3zJROamisr"
MQTT_TOPIC_CONTROL = "radar/control"
MQTT_TOPIC_STATUS  = "radar/status"      # El radar publica ON/OFF aquí
MQTT_TOPIC_PARAMS  = "radar/parametros"  # JSON: {"status_rf":..., "status_mode":..., "status_array":..., "array_activo":...}

# ============================================================
# GESTIÓN DE USUARIOS — Archivo local JSON
# ============================================================
USERS_FILE = "usuarios_autorizados.json"

# Usuarios iniciales (contraseñas hasheadas con SHA-256)
DEFAULT_USERS = {
    "admin":    hashlib.sha256("admin123".encode()).hexdigest(),
    "operador": hashlib.sha256("radar2024".encode()).hexdigest(),
    "igp":      hashlib.sha256("amisr14".encode()).hexdigest(),
}

def cargar_usuarios():
    """Carga usuarios desde JSON o crea el archivo con defaults."""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    # Crear con defaults
    guardar_usuarios(DEFAULT_USERS)
    return dict(DEFAULT_USERS)

def guardar_usuarios(usuarios: dict):
    """Persiste el diccionario de usuarios en JSON."""
    with open(USERS_FILE, "w") as f:
        json.dump(usuarios, f, indent=2)

def hash_pass(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_usuario(usuarios: dict, user: str, password: str) -> bool:
    """True si el usuario existe y la contraseña es correcta."""
    return usuarios.get(user.strip().lower()) == hash_pass(password)

def agregar_usuario(usuarios: dict, user: str, password: str):
    """Agrega o actualiza un usuario."""
    usuarios[user.strip().lower()] = hash_pass(password)
    guardar_usuarios(usuarios)

def eliminar_usuario(usuarios: dict, user: str):
    """Elimina un usuario si existe."""
    if user in usuarios:
        del usuarios[user]
        guardar_usuarios(usuarios)

# ============================================================
# CLIENTE MQTT
# ============================================================
class MQTTClient:
    def __init__(self, callback_estado, callback_radar_status, callback_parametros):
        self.callback_estado        = callback_estado
        self.callback_radar_status  = callback_radar_status
        self.callback_parametros    = callback_parametros
        self.conectado              = False
        self._intentando            = False

        self.client = mqtt.Client(client_id="radar_app_v3")
        self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.tls_set(ca_certs=certifi.where(), tls_version=ssl.PROTOCOL_TLS)
        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message    = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        self.conectado    = (rc == 0)
        self._intentando  = False
        if rc == 0:
            # Suscribirse a topics de estado y parámetros
            client.subscribe([(MQTT_TOPIC_STATUS, 1), (MQTT_TOPIC_PARAMS, 1)])
            Clock.schedule_once(
                lambda dt: self.callback_estado("Conectado al broker", True))
        else:
            Clock.schedule_once(
                lambda dt: self.callback_estado(f"Error conexión (rc={rc})", False))

    def _on_disconnect(self, client, userdata, rc):
        self.conectado = False
        Clock.schedule_once(
            lambda dt: self.callback_estado("Desconectado", False))
        # Reintentar reconexión después de 5 s
        if rc != 0:
            Clock.schedule_once(lambda dt: self.reconectar(), 5)

    def _on_message(self, client, userdata, msg):
        """Procesa mensajes recibidos de los topics suscritos."""
        try:
            payload = msg.payload.decode("utf-8").strip()
            topic   = msg.topic

            if topic == MQTT_TOPIC_STATUS:
                Clock.schedule_once(
                    lambda dt: self.callback_radar_status(payload))

            elif topic == MQTT_TOPIC_PARAMS:
                data = json.loads(payload)
                Clock.schedule_once(
                    lambda dt: self.callback_parametros(data))
        except Exception as e:
            print(f"[MQTT] Error procesando mensaje: {e}")

    def conectar(self):
        if self._intentando:
            return
        self._intentando = True
        def hilo():
            try:
                self.client.connect(MQTT_HOST, MQTT_PORT, 60)
                self.client.loop_forever()
            except Exception as e:
                self._intentando = False
                Clock.schedule_once(
                    lambda dt: self.callback_estado(f"Error: {e}", False))
        threading.Thread(target=hilo, daemon=True).start()

    def reconectar(self):
        if not self.conectado and not self._intentando:
            self._intentando = True
            def hilo():
                try:
                    self.client.reconnect()
                except Exception:
                    self._intentando = False
                    Clock.schedule_once(lambda dt: self.conectar(), 5)
            threading.Thread(target=hilo, daemon=True).start()

    def publicar(self, topic: str, mensaje: str) -> bool:
        if self.conectado:
            result = self.client.publish(topic, mensaje, qos=1, retain=True)
            return result.rc == 0
        return False

# ============================================================
# PANTALLA DE LOGIN — teclado en pantalla
# ============================================================
class LoginScreen(BoxLayout):
    """
    Pantalla de login con teclado en pantalla propio.
    No usa TextInput para evitar dependencia del teclado del SO,
    que en Kivy 2.3 / Linux SDL2 no funciona en modo 'single'.

    Flujo:
      - campo_activo indica cual campo recibe las pulsaciones ('user'/'pass')
      - activar_campo(campo) cambia el campo activo
      - tecla(char) agrega/borra el caracter en el campo activo
      - _actualizar_displays() refresca los labels de usuario y password
    """

    # Kivy Property para que el canvas.before de los botones-campo
    # reaccione al cambio de campo activo
    campo_activo = StringProperty('user')

    def __init__(self, usuarios: dict, callback_login_ok, **kwargs):
        self._val_user = ""   # valor interno del campo usuario
        self._val_pass = ""   # valor interno del campo password
        self.usuarios        = usuarios
        self.callback_login_ok = callback_login_ok
        super().__init__(**kwargs)

    def activar_campo(self, campo: str):
        """Selecciona qué campo recibe el input del teclado."""
        self.campo_activo = campo
        self.ids.lbl_login_error.text = ""

    def tecla(self, char: str):
        """Procesa una pulsacion del teclado en pantalla."""
        if self.campo_activo == 'user':
            if char == '<<':
                self._val_user = self._val_user[:-1]
            elif char == 'CLR':
                self._val_user = ""
            else:
                self._val_user += char
        else:
            if char == '<<':
                self._val_pass = self._val_pass[:-1]
            elif char == 'CLR':
                self._val_pass = ""
            else:
                self._val_pass += char
        self._actualizar_displays()

    def _actualizar_displays(self):
        """Refresca los labels que muestran usuario y password."""
        # Usuario: se muestra tal cual
        u = self._val_user
        self.ids.campo_user.text = u if u else "  toca para escribir..."

        # Password: enmascarar con asteriscos
        p = self._val_pass
        self.ids.campo_pass.text = "*" * len(p) if p else "  toca para escribir..."

    def intentar_login(self):
        user  = self._val_user.strip().lower()
        passw = self._val_pass

        if not user or not passw:
            self._error("Complete usuario y clave")
            return

        if verificar_usuario(self.usuarios, user, passw):
            self.ids.lbl_login_error.text = ""
            # Limpiar campos para proxima sesion
            self._val_user = ""
            self._val_pass = ""
            self._actualizar_displays()
            self.callback_login_ok(user)
        else:
            self._error("Usuario o clave incorrectos")
            self._val_pass = ""
            self._actualizar_displays()

    def _error(self, msg: str):
        self.ids.lbl_login_error.text = msg
        Clock.schedule_once(
            lambda dt: setattr(self.ids.lbl_login_error, 'text', ''), 3)


# ============================================================
# PANTALLA PRINCIPAL (DASHBOARD)
# ============================================================
class RadarLayout(BoxLayout):
    """Widget principal del dashboard de control."""

    def __init__(self, mqtt_client: MQTTClient, **kwargs):
        # mqtt debe asignarse ANTES de super().__init__() porque Kivy
        # dispara on_kv_post durante la construccion del widget, y ese
        # metodo ya necesita acceder a self.mqtt.
        self.mqtt            = mqtt_client
        self.radar_encendido = False
        self._log_lines      = []
        super().__init__(**kwargs)

    def on_kv_post(self, base_widget):
        """Se llama cuando el KV ya terminó de construir el árbol."""
        # Registrar callbacks del MQTT en este layout
        self.mqtt.callback_estado       = self.actualizar_broker
        self.mqtt.callback_radar_status = self.actualizar_estado_radar
        self.mqtt.callback_parametros   = self.actualizar_parametros

    def set_usuario(self, usuario: str):
        """Muestra el nombre del usuario logueado."""
        self.ids.lbl_usuario_activo.text = f"Usuario: {usuario.upper()}"

    # ------ Callbacks MQTT ------

    def actualizar_broker(self, texto: str, conectado: bool):
        self.ids.lbl_broker.text = texto
        if conectado:
            self.ids.lbl_broker.color = (0.0, 0.85, 0.68, 1)
        else:
            self.ids.lbl_broker.color = (0.95, 0.35, 0.35, 1)
        self._agregar_log(f"Broker: {texto}")

    def actualizar_estado_radar(self, estado: str):
        """Recibe 'ON' u 'OFF' desde el topic radar/status."""
        estado = estado.upper().strip()
        if estado == "ON":
            self.radar_encendido = True
            self.ids.lbl_radar_estado.text  = "ON"
            self.ids.lbl_radar_estado.color = (0.0, 0.9, 0.6, 1)
            self._mostrar_parametros(True)
        else:
            self.radar_encendido = False
            self.ids.lbl_radar_estado.text  = "OFF"
            self.ids.lbl_radar_estado.color = (0.72, 0.18, 0.18, 1)
            self._mostrar_parametros(False)
        self._agregar_log(f"Estado radar → {estado}")

    def actualizar_parametros(self, data: dict):
        """
        Recibe dict publicado por mqtt_listener/status_amisr con claves:
          status_rf    -> str,  ej. "RF: 151.0 KW"
          status_mode  -> str,  ej. "Mode: ISR_lBeam_oblique_10ms_25"
          status_array -> str,  ej. "Array: online (tx)"
          array_activo -> bool, True si el arreglo esta transmitiendo
        Cada clave es opcional: si no viene en el dict se ignora sin error.
        """
        if "status_rf" in data and data["status_rf"] is not None:
            self.ids.lbl_potencia.text = data["status_rf"]
        if "status_mode" in data and data["status_mode"] is not None:
            self.ids.lbl_corriente.text = data["status_mode"]
        if "status_array" in data and data["status_array"] is not None:
            self.ids.lbl_voltaje.text = data["status_array"]

        # array_activo es el campo mas importante: controla el color del
        # label de status_array para destacar visualmente si esta ON u OFF.
        if "array_activo" in data:
            if data["array_activo"]:
                self.ids.lbl_voltaje.color = (0.0, 0.9, 0.6, 1)    # verde - activo
            else:
                self.ids.lbl_voltaje.color = (0.95, 0.35, 0.35, 1)  # rojo  - inactivo

        ahora = datetime.now().strftime("%H:%M:%S")
        self.ids.lbl_ultima_act.text = "Ultima actualizacion: " + ahora

    # ------ Acciones de botones ------

    def encender(self):
        if self.mqtt.publicar(MQTT_TOPIC_CONTROL, "ON"):
            self.ids.lbl_estado.text  = "▶  Comando ENCENDIDO enviado"
            self.ids.lbl_estado.color = (0.0, 0.85, 0.68, 1)
            self._agregar_log("Comando → ENCENDER")
        else:
            self.ids.lbl_estado.text  = "✕  Sin conexión MQTT"
            self.ids.lbl_estado.color = (0.95, 0.35, 0.35, 1)
            self._agregar_log("Fallo: ENCENDER (sin conexión)")

    def apagar(self):
        if self.mqtt.publicar(MQTT_TOPIC_CONTROL, "OFF"):
            self.ids.lbl_estado.text  = "■  Comando APAGADO enviado"
            self.ids.lbl_estado.color = (1.0, 0.65, 0.15, 1)
            self._agregar_log("Comando → APAGAR")
        else:
            self.ids.lbl_estado.text  = "✕  Sin conexión MQTT"
            self.ids.lbl_estado.color = (0.95, 0.35, 0.35, 1)
            self._agregar_log("Fallo: APAGAR (sin conexión)")

    def cerrar_sesion(self):
        self._agregar_log("Sesión cerrada")
        App.get_running_app().ir_a_login()

    # ------ Helpers ------

    def _mostrar_parametros(self, mostrar: bool):
        """Anima la aparición/desaparición del panel de parámetros."""
        panel = self.ids.panel_parametros
        if mostrar:
            panel.opacity = 0
            panel.height  = dp(222)  # 22 titulo + 3x52 filas + 3x8 spacing + 20 timestamp
            anim = Animation(opacity=1, duration=0.4)
            anim.start(panel)
        else:
            anim = Animation(opacity=0, duration=0.3)
            anim.bind(on_complete=lambda *a: setattr(panel, 'height', dp(0)))
            anim.start(panel)
            # Limpiar valores con los textos por defecto de cada campo
            self.ids.lbl_potencia.text   = "— RF"
            self.ids.lbl_corriente.text  = "— Mode"
            self.ids.lbl_voltaje.text    = "— Array"
            self.ids.lbl_voltaje.color   = (0.4, 0.7, 1.0, 1)  # color neutro al limpiar
            self.ids.lbl_ultima_act.text = "Ultima actualizacion: —"

    def _agregar_log(self, mensaje: str):
        ahora = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append(f"[{ahora}] {mensaje}")
        # Mantener últimas 30 líneas
        if len(self._log_lines) > 30:
            self._log_lines = self._log_lines[-30:]
        self.ids.lbl_log.text = "\n".join(reversed(self._log_lines))


# ============================================================
# SCREENS para el ScreenManager
# ============================================================
class LoginScreenWrapper(Screen):
    def __init__(self, login_widget, **kwargs):
        super().__init__(**kwargs)
        self.add_widget(login_widget)
        self.login_widget = login_widget


class DashboardScreenWrapper(Screen):
    def __init__(self, radar_widget, **kwargs):
        super().__init__(**kwargs)
        self.add_widget(radar_widget)
        self.radar_widget = radar_widget


# ============================================================
# APP PRINCIPAL
# ============================================================
class RadarApp(App):
    def build(self):
        self.title = "Radar AMISR-14"

        # Cargar usuarios
        self.usuarios = cargar_usuarios()

        # Cliente MQTT (callbacks vacíos por ahora, se asignan al crear el dashboard)
        self.mqtt_client = MQTTClient(
            callback_estado        = self._dummy,
            callback_radar_status  = self._dummy,
            callback_parametros    = self._dummy,
        )

        # Construir pantallas
        self.login_widget   = LoginScreen(
            usuarios          = self.usuarios,
            callback_login_ok = self.ir_a_dashboard,
        )
        self.radar_widget   = RadarLayout(mqtt_client=self.mqtt_client)

        self.screen_login     = LoginScreenWrapper(self.login_widget,  name="login")
        self.screen_dashboard = DashboardScreenWrapper(self.radar_widget, name="dashboard")

        # ScreenManager
        self.sm = ScreenManager(transition=FadeTransition(duration=0.3))
        self.sm.add_widget(self.screen_login)
        self.sm.add_widget(self.screen_dashboard)
        self.sm.current = "login"

        # Iniciar conexión MQTT al arrancar
        self.mqtt_client.conectar()

        return self.sm

    # ------ Navegación ------

    def ir_a_dashboard(self, usuario: str):
        self.sm.current = "dashboard"
        # Esperar a que KV post esté listo antes de llamar set_usuario
        Clock.schedule_once(lambda dt: self.radar_widget.set_usuario(usuario), 0.1)

    def ir_a_login(self):
        self.sm.current = "login"

    def _dummy(self, *args, **kwargs):
        pass


if __name__ == "__main__":
    RadarApp().run()