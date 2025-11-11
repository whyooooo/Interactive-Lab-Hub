from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import json, time, socket

# ===== MQTT Configuration =====
BROKER = "farlab.infosci.cornell.edu"
PORT = 1883
USER, PW = "idd", "device@theFarm"
TOPIC_STATUS = "IDD/hall/smartlight/status/#"
TOPIC_EVENT  = "IDD/hall/smartlight/event/#"
TOPIC_CMD    = "IDD/hall/smartlight/cmd/"

# ===== Global State Cache =====
devices = {}

# ===== Flask Initialization =====
app = Flask(__name__)

# ===== Enable Stable Mode SocketIO (extended heartbeat) =====
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    ping_timeout=60,
    ping_interval=25
)

# ===== MQTT Initialization =====
client = mqtt.Client()
client.username_pw_set(USER, PW)

def on_connect(client, userdata, flags, rc):
    print(f"[MQTT] Connected to {BROKER} with result code {rc}")
    client.subscribe(TOPIC_STATUS)
    client.subscribe(TOPIC_EVENT)
    print(f"[MQTT] Subscribed to {TOPIC_STATUS} and {TOPIC_EVENT}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        dev_id = data.get("device_id", "unknown")

        if "status" in msg.topic:
            devices[dev_id] = data
            print(f"[STATUS] {dev_id}: mode={data['mode']} | "
                  f"light={'ON' if data['light_on'] else 'OFF'} | "
                  f"sound={data['sound_thresh']} | motion={data['motion_thresh']:.3f}")
            socketio.emit("update_status",
                          {"device_id": dev_id, "data": data})

        elif "event" in msg.topic:
            print(f"[EVENT] {dev_id}: {data}")
            socketio.emit("new_event",
                          {"device_id": dev_id, "event": data})

    except Exception as e:
        print("[ERROR] Failed to parse MQTT message:", e)
        print("  Raw payload:", msg.payload)

client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_start()

# ===== Flask Routes =====
@app.route("/")
def index():
    return render_template("dashboard.html", devices=devices)

@app.route("/set_param", methods=["POST"])
def set_param():
    data = request.json
    dev_id = data["device_id"]
    payload = data["payload"]
    topic = TOPIC_CMD + dev_id
    client.publish(topic, json.dumps(payload), qos=1)
    print(f"[CMD] Sent to {dev_id}: {payload}")
    socketio.emit("new_event",
                  {"device_id": dev_id, "event": {"type": "cmd_sent", "payload": payload}})
    return jsonify({"ok": True})

@app.route("/broadcast", methods=["POST"])
def broadcast():
    data = request.json
    for dev in list(devices.keys()):
        topic = TOPIC_CMD + dev
        client.publish(topic, json.dumps(data), qos=1)
        print(f"[BROADCAST] -> {dev}: {data}")
    socketio.emit("new_event",
                  {"device_id": "ALL", "event": {"type": "broadcast", "payload": data}})
    return jsonify({"ok": True, "msg": f"Broadcasted to {len(devices)} devices"})

# ===== Get Local IP Function =====
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# ===== Main Program Entry =====
if __name__ == "__main__":
    ip = get_local_ip()
    print("\nController Dashboard is running")
    print(f"Open Dashboard at: http://{ip}:5000\n")
    socketio.run(app, host="0.0.0.0", port=5000)
