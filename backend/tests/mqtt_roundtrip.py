"""
Self-contained MQTT round-trip test.

Subscribes to agritech/#, publishes a message, waits for it to arrive,
and reports success or failure. All in one process — no window juggling.
"""
import time

import paho.mqtt.client as mqtt


received: list[tuple[str, str]] = []


def on_message(client, userdata, msg):
    received.append((msg.topic, msg.payload.decode()))


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message

    print("Connecting to localhost:1883...")
    client.connect("localhost", 1883)
    client.loop_start()

    # Subscribe first, then wait for the SUBACK before publishing
    client.subscribe("agritech/#", qos=1)
    print("Subscribed to agritech/#")

    # Give the broker a moment to register the subscription
    time.sleep(0.5)

    topic = "agritech/roundtrip-test"
    payload = f"ping-{int(time.time())}"
    print(f"Publishing to {topic}: {payload}")

    info = client.publish(topic, payload, qos=1)
    info.wait_for_publish(timeout=5.0)

    # Wait up to 3 seconds for the message to come back
    for _ in range(30):
        if received:
            break
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()

    print()
    if received:
        print(f"✅ Received {len(received)} message(s):")
        for t, p in received:
            print(f"   {t}  →  {p}")
    else:
        print("❌ No message received. Pub/sub roundtrip failed.")


if __name__ == "__main__":
    main()