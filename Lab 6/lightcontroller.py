import paho.mqtt.client as mqtt
import json, time, threading

# ===== MQTT CONFIGURATION =====
BROKER = "farlab.infosci.cornell.edu"
PORT = 1883
USER, PW = "idd", "device@theFarm"

# ===== MQTT TOPICS =====
TOPIC_STATUS = "IDD/hall/smartlight/status/#"   # Receive all device status updates
TOPIC_EVENT  = "IDD/hall/smartlight/event/#"    # Receive all device event logs
TOPIC_CMD    = "IDD/hall/smartlight/cmd/"       # Command topic prefix for sending control messages

# ===== DEVICE STATE CACHE =====
devices = {}   # {device_id: {mode, light_on, sound_thresh, ...}}

client = mqtt.Client()
client.username_pw_set(USER, PW)

# ===== MQTT CALLBACK =====
def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    topic = msg.topic

    if "status" in topic:
        dev_id = data.get("device_id", "unknown")
        devices[dev_id] = data
        print(f"[STATUS] {dev_id}: mode={data['mode']} | "
              f"light={'ON' if data['light_on'] else 'OFF'} | "
              f"sound_thresh={data['sound_thresh']} | motion_thresh={data['motion_thresh']}")

    elif "event" in topic:
        dev_id = data.get("device_id", "unknown")
        etype  = data.get("type")
        print(f"[EVENT] {dev_id}: {etype} -> {data}")

    else:
        print(f"[MQTT] {topic} -> {data}")

client.on_message = on_message

# ===== MQTT CONNECTION THREAD =====
def mqtt_loop():
    client.connect(BROKER, PORT, 60)
    client.subscribe(TOPIC_STATUS)
    client.subscribe(TOPIC_EVENT)
    client.loop_forever()

# ===== COMMAND FUNCTIONS =====
def send_command(dev, cmd_dict):
    topic = TOPIC_CMD + dev
    client.publish(topic, json.dumps(cmd_dict), qos=1)
    print(f"[CMD] Sent to {dev}: {cmd_dict}")

def broadcast(cmd_dict):
    for dev in list(devices.keys()):
        send_command(dev, cmd_dict)

# ===== USER INTERFACE (COMMAND LINE) =====
def cli_loop():
    time.sleep(2)
    print("\n=== Central Controller Menu ===")
    print("1. View all device statuses")
    print("2. Adjust sound threshold for a specific device")
    print("3. Group control (all ON / all OFF)")
    print("4. Broadcast parameters (sound/motion thresholds)")
    print("5. Change device mode (auto / always_on / always_off)")
    print("q. Quit")
    print("===============================\n")

    while True:
        cmd = input("Enter command number: ").strip()

        if cmd == "1":
            if not devices:
                print("No devices detected yet.")
            for dev, d in devices.items():
                print(f"{dev} -> mode={d['mode']} | "
                      f"light={'ON' if d['light_on'] else 'OFF'} | "
                      f"sound={d['sound_thresh']} | motion={d['motion_thresh']}")

        elif cmd == "2":
            dev = input("Enter device ID (e.g., pi_01): ").strip()
            val = float(input("New sound_thresh value: "))
            send_command(dev, {"sound_thresh": val})

        elif cmd == "3":
            sub = input("Enter 'all_on' or 'all_off': ").strip()
            if sub == "all_on":
                broadcast({"mode": "always_on"})
            elif sub == "all_off":
                broadcast({"mode": "always_off"})
            else:
                print("Invalid input.")

        elif cmd == "4":
            s = float(input("New sound_thresh: "))
            m = float(input("New motion_thresh: "))
            broadcast({"sound_thresh": s, "motion_thresh": m})

        elif cmd == "5":
            dev = input("Enter device ID: ").strip()
            mode = input("Enter mode (auto / always_on / always_off): ").strip()
            send_command(dev, {"mode": mode})

        elif cmd.lower() == "q":
            print("Exiting controller...")
            client.disconnect()
            break

        else:
            print("Invalid command, please try again.")

# ===== START THREADS =====
threading.Thread(target=mqtt_loop, daemon=True).start()
cli_loop()
