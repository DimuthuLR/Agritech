"""
Simple MQTT listener for debugging. Subscribes to agritech/# and prints
every message. Runs forever — Ctrl+C to quit.
"""
import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Connected. Subscribed to agritech/#. Waiting for messages...")
        client.subscribe("agritech/#")
    else:
        print(f"Connect failed rc={rc}")


def on_message(client, userdata, msg):
    print(f"\n--- MESSAGE ---")
    print(f"  topic:   {msg.topic}")
    print(f"  payload: {msg.payload.decode()}")


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("localhost", 1883)
    client.loop_forever()


if __name__ == "__main__":
    main()