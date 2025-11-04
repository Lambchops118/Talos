# Part of TALOS
# Monkey Butler Device Operations System

#

import machine, time
import uasyncio as asyncio
from   mqtt_as  import MQTTClient, config

WIFI_SSID     = '...'
WIFI_PASS     = '...'
BROKER        = '192.168.1.160'
TOPIC_PREFIX  = b'quad_pump/'
STATUS_PREFIX = b'status/'
RUN_SECONDS   = 8
PINS          = {n: machine.Pin(n, machine.Pin.OUT) for n in (16,17,18,19)}

config['ssid']      = WIFI_SSID
config['wifi_pw']   = WIFI_PASS
config['server']    = BROKER
config['client_id'] = 'pico-w-client'
config['will']      = (b'status/online', b'0', True, 1)

async def publish_state(client, pin): # Publish the current state of the pump (on/off)
    await client.publish(
        STATUS_PREFIX + str(pin).encode(),
        b"1" if PINS[pin].value() else b"0",
        retain = True,
        qos    = 1 
        )

async def run_pump(client, pin, seconds): # Run the pump for a specified number of seconds
    PINS[pin].value(1)
    await publish_state(client, pin)
    await asyncio.sleep(seconds)
    PINS[pin].value(0)
    await publish_state(client, pin)

async def messages(client): # Handle incoming MQTT messages
    async for topic, msg, retained in client.queue:
        try:
            pin = int(topic.split(b'/')[-1])
            if pin not in PINS: continue
            txt = msg.decode()
            if txt.startswith('1'):
                seconds = RUN_SECONDS # Defined at top
                if ':' in txt:
                    seconds = max(1, min(3600, int(txt.split(':',1)[1])))
                asyncio.create_task(run_pump(client, pin, seconds)) #fire-and-forget. Does not block message handling
            elif txt == '0':
                PINS[pin].value(0)
                await publish_state(client, pin)
        except Exception as e:
            print("msg err:", e)

async def main(): # Main entry point
    client = MQTTClient(config)
    await client.connect()
    await client.publish(b'status/online', b'1', retain = True, qos = 1)

    for pin in PINS:
        await client.subscribe(TOPIC_PREFIX + str(pin).encode(), 1)
    asyncio.create_task(messages(client)) #This handles incoming messages

    while True: # Keep the main task alive
        await asyncio.sleep(3600)

try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()