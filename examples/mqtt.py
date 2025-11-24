from time import sleep
import weatherhat
from datetime import datetime
from gpiozero import CPUTemperature
import socket
import paho.mqtt.client as mqtt
import json
import subprocess

# Variables

sensor = weatherhat.WeatherHAT()
cpu = CPUTemperature()

cputemp_topic = "sensors/pi/cpu_temp"
temp_topic = "sensors/weather/temperature"
humidity_topic = "sensors/weather/humidity"
rel_hum_topic = "sensors/weather/relative_humidity"
pressure_topic = "sensors/weather/pressure"
dewpoint_topic = "sensors/weather/dewpoint"
light_topic = "sensors/weather/light"
wind_dir_topic = "sensors/weather/wind_direction"
wind_spd_topic = "sensors/weather/wind_speed"
rain_topic = "sensors/weather/rain"
rain_total_topic = "sensors/weather/rain_total"

mqtt_server = "mqtt.timfinn.dev"  # Replace with the IP or URI of the MQTT server you use
client_id = "weatherhat"


# We can compensate for the heat of the Pi and other environmental conditions using a simple offset.
# Change this number to adjust temperature compensation!
OFFSET = -7.5


#  Function Definitions

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe("$SYS/#")


def on_message(client, userdata, msg):
    print(msg.topic + " " + str(msg.payload))


def host_avail(hostname):
    try:
        socket.gethostbyname(hostname)
#        socket.gethostbyaddr(hostname)
        return True
    except OSError as exc:
        print(exc)
        return False


def send_payload(topic, data):
    payload = json.dumps(
        {
            topic:data
        }
    )
    client.publish(topic=topic, payload=payload, qos=0, retain=False)
#    print(f"sending {payload} to server")

def restart_wifi():
    subprocess.call(['sudo', 'ifconfig', 'wlan0', 'down'])
    sleep(5)
    subprocess.call(['sudo', 'ifconfig', 'wlan0', 'up'])

def check_connectivity():
    try:
        # Ping local router
        subprocess.check_call(['ping', '-c', '1', 'dradis.timfinn.dev'], 
                            stdout=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

#   Main Loop

while not host_avail(mqtt_server):
    print("Waiting for mqtt")
    sleep(2)

# Create an instance of the client.
client = mqtt.Client(client_id=client_id)
client.on_connect = on_connect
client.on_message = on_message
client.connect(host=mqtt_server, port=1883, keepalive=60)
client.loop_start()


# Read the BME280 and discard the initial nonsense readings
sensor.update(interval=10.0)
sensor.temperature_offset = OFFSET
temperature = sensor.temperature
humidity = sensor.relative_humidity
pressure = sensor.pressure
print("Discarding the first few BME280 readings...")
sleep(10.0)

# Read all the sensors and start sending data

while True:
    if host_avail(mqtt_server):
        try:
            sensor.update(interval=2.0)
        except Exception as e:
            print(e)

        wind_direction_cardinal = sensor.degrees_to_cardinal(sensor.wind_direction)

        temperature = sensor.temperature
        humidity = sensor.relative_humidity
        relative_humidity = sensor.relative_humidity
        pressure = sensor.pressure
        dewpoint = sensor.dewpoint
        light = sensor.lux
        wind_speed = sensor.wind_speed
        wind_direction = wind_direction_cardinal
        rain = sensor.rain
        rain_total = sensor.rain_total

        try:
            send_payload(cputemp_topic, cpu.temperature)
            send_payload(temp_topic, temperature)
            send_payload(humidity_topic, humidity)
            send_payload(rel_hum_topic, relative_humidity)
            send_payload(pressure_topic, pressure)
            send_payload(dewpoint_topic, dewpoint)
            send_payload(light_topic, light)
            send_payload(wind_dir_topic, wind_direction)
            send_payload(wind_spd_topic, wind_speed)
            send_payload(rain_topic, rain)
            send_payload(rain_total_topic, rain_total)
#            print('Data sent to broker')
        except Exception as e:
            print(e)

