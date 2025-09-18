# Part of TALOS
# Monkey Butler Device Operations System

# Main file in raspberry pi pico root folder along with simple.py. This will listen for a "1" on
# MQTT topics quad_waterer/{16, 17, 18, 19} and run the pump for 8 seconds when called. It will turn off the pin
# after 8 seconds. It will also listen for a "0" to turn off the pin immediately. It will publish the pin status
# to status/{16, 17, 18, 19} after any change. 


import network
import time
import machine
from   umqtt.simple import MQTTClient

# Configuration
WIFI_SSID         = 'Verizon_4VLXXY'
WIFI_PASSWORD     = 'artery4-fob-vim'
MQTT_BROKER       = '192.168.1.160'
MQTT_CLIENT_ID    = 'pico-w-client'
MQTT_TOPIC_PREFIX = b'quad_pump/'  # example:  waterer_pump/4  (1-4) 
CONTROL_TOPICS    = [MQTT_TOPIC_PREFIX + bytes(str(pin), 'utf-8') for pin in [16, 17, 18, 19]]

# Pin setup
PIN_NUMBERS       = [16, 17, 18, 19]
PINS              = {pin_num: machine.Pin(pin_num, machine.Pin.OUT) for pin_num in PIN_NUMBERS}

print('started')

# Wi-Fi connection
def connect_wifi():
    print("Connecting to wifi...")
    wlan = network.WLAN(network.STA_IF)
    print("wlan: " + str(wlan))
    wlan.active(True)
    if not wlan.isconnected():
        print("wlan not connected...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        print("WIFI_SSID: " + WIFI_SSID)
        print("WIFI_PASSWORD: " + WIFI_PASSWORD)
        while not wlan.isconnected():
            print("Sleeping...")
            time.sleep(0.5)
    print('Connected to Wi-Fi:', wlan.ifconfig())

# MQTT message callback
def mqtt_callback(topic, msg):
    try:
        pin_number = int(topic.decode().split('/')[-1])
        if pin_number in PINS:
            pin = PINS[pin_number]
            if msg == b'1':
                pin.value(1)
                time.sleep(8)   # RUN PUMP FOR 8 SECONDS
                pin.value(0)
            elif msg == b'0':
                pin.value(0)
            else:
                print(f"Invalid command: {msg}")
                return
            # Publish new status
            status_topic = b'status/' + bytes(str(pin_number), 'utf-8')
            print(status_topic)
            client.publish(status_topic, str(pin.value()))
    except Exception as e:
        print('Error handling message:', e)

# Connect Wi-Fi
connect_wifi()

# Setup MQTT
client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER)

print("MQTT_CLIENT_ID: " + MQTT_CLIENT_ID)
print("MQTT_BROKER: " + MQTT_BROKER)

client.set_callback(mqtt_callback)
client.connect()
for topic in CONTROL_TOPICS:
    client.subscribe(topic)
    print("Subscribed to: " + str(topic))

# Main loop
try:
    while True:
        client.check_msg()
        time.sleep(0.1)
except KeyboardInterrupt:
    client.disconnect()