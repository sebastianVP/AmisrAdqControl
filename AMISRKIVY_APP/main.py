# -*- coding: utf-8 -*-

import ssl
import threading
import paho.mqtt.client as mqtt

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock

# =========================
# CONFIG MQTT (EDITAR)
# =========================
MQTT_HOST  = "ef5003dc4f0742d693f4d47946133d80.s1.eu.hivemq.cloud"
MQTT_PORT  = 8883
MQTT_USER  = "magic"
MQTT_PASS  = "4v4ld3zJROamisr"
MQTT_TOPIC = "radar/control"


# =========================
# CLIENTE MQTT
# =========================
class MQTTClient:
    def __init__(self, callback_estado):
        self.callback_estado = callback_estado
        self.client = mqtt.Client(client_id="radar_app")
        self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.tls_set(tls_version=ssl.PROTOCOL_TLS)

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

        self.conectado = False

    def on_connect(self, client, userdata, flags, rc):
        self.conectado = (rc == 0)

        if rc == 0:
            msg = "Conectado al broker"
        else:
            msg = f"Error conexión (rc={rc})"

        Clock.schedule_once(lambda dt: self.callback_estado(msg, self.conectado))

    def on_disconnect(self, client, userdata, rc):
        self.conectado = False
        Clock.schedule_once(lambda dt: self.callback_estado("Desconectado", False))

    def conectar(self):
        def hilo():
            try:
                self.client.connect(MQTT_HOST, MQTT_PORT, 60)
                self.client.loop_forever()
            except Exception as e:
                error_str = str(e)
                Clock.schedule_once(lambda dt: self.callback_estado(f"Error: {error_str }", False))

        threading.Thread(target=hilo, daemon=True).start()

    def publicar(self, mensaje):
        if self.conectado:
            result = self.client.publish(MQTT_TOPIC, mensaje, qos=1)
            return result.rc == 0
        return False


# =========================
# UI
# =========================
class RadarLayout(BoxLayout):

    def on_kv_post(self, base_widget):
        self.mqtt = MQTTClient(self.actualizar_broker)
        self.mqtt.conectar()

    def actualizar_broker(self, texto, conectado):
        self.ids.lbl_broker.text = texto
        if conectado:
            self.ids.lbl_broker.color = (0.2, 0.9, 0.4, 1)
        else:
            self.ids.lbl_broker.color = (1, 0.3, 0.3, 1)

    def encender(self):
        if self.mqtt.publicar("ON"):
            self.ids.lbl_estado.text = "Comando enviado: ENCENDIDO"
            self.ids.lbl_estado.color = (0.2, 0.9, 0.4, 1)
        else:
            self.ids.lbl_estado.text = "Error: sin conexión"
            self.ids.lbl_estado.color = (1, 0.3, 0.3, 1)

    def apagar(self):
        if self.mqtt.publicar("OFF"):
            self.ids.lbl_estado.text = "Comando enviado: APAGADO"
            self.ids.lbl_estado.color = (1, 0.5, 0.1, 1)
        else:
            self.ids.lbl_estado.text = "Error: sin conexión"
            self.ids.lbl_estado.color = (1, 0.3, 0.3, 1)


# =========================
# APP
# =========================
class RadarApp(App):
    def build(self):
        self.title = "Radar AMISR"
        return RadarLayout()


if __name__ == "__main__":
    RadarApp().run()