# This runs on the MQTT pi because its connected to the TV with HDMI.
# Subscribes to the MQTT broker and sends CEC commands to the TV.

import paho.mqtt.client as mqtt
import subprocess

BROKER = "localhost"
TOPIC  = "tv_display/wake_status"

CEC_CLIENT_CMD = "cec-client -s -d 1"

def send_cec(cmd: str) -> int:
    full_cmd = f'echo "{cmd}" | {CEC_CLIENT_CMD}'
    result   = subprocess.run(full_cmd, shell=True)
    print(f"[DEBUG] Running: {full_cmd}")
    return result.returncode

def tv_power_on():
    send_cec("on 0")

def tv_power_off():
    send_cec("standby 0")

def switch_to_pi_input(): #Pi is responsible for MQTT broker and CEC program.
    send_cec("as")

def switch_to_server_pc_input(): #Server PC is responsible for Monkey Butler core.
    send_cec("2.0.0.0")

def on_message(client, userdata, msg):
    payload = msg.payload.decode().strip()
    print(f"Received message: {payload}")

    if payload == "0":
        tv_power_off()
    elif payload == "1":
        tv_power_on()

def main():    
    client = mqtt.Client()
    client.on_message = on_message

    client.connect(BROKER, 1883, 60)
    client.subscribe(TOPIC)

    print(f"Subscribed to {TOPIC}, waiting for messages...")
    client.loop_forever()

if __name__ == "__main__":
    main()