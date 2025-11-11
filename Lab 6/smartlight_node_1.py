import sounddevice as sd
import numpy as np
import cv2, time, threading, json, paho.mqtt.client as mqtt
from gpiozero import RGBLED                     # Added
import atexit                                   # Added

# ===== GPIO LED Initialization =====
# Note: Based on wiring: GPIO17=red, GPIO16=green, GPIO26=blue, common anode module
led = RGBLED(red=17, green=16, blue=26, active_high=True)
led.color = (1, 1, 1)                           # Turn on white light at startup
atexit.register(lambda: led.off())              # Automatically turn off LED on program exit

# ===== MQTT Configuration =====
BROKER = "farlab.infosci.cornell.edu"
PORT = 1883
USER, PW = "idd", "device@theFarm"
DEVICE_ID = "pi_02"

TOPIC_CMD = f"IDD/hall/smartlight/cmd/{DEVICE_ID}"
TOPIC_STATUS = f"IDD/hall/smartlight/status/{DEVICE_ID}"
TOPIC_EVENT = f"IDD/hall/smartlight/event/{DEVICE_ID}"

# ===== Parameter Initialization =====
params = {
    "mode": "auto",                # "auto" | "always_on" | "always_off"
    "sound_thresh": 500,           # Sound threshold (higher = less sensitive)
    "motion_thresh": 8/255.0,      # Visual frame difference threshold
    "timeout": 120                 # Maximum light-on duration (seconds)
}

# Add reset_prev flag for vision thread to discard old frames
state = {
    "on": False,
    "last_on": 0,
    "no_motion": 0,
    "last_trigger": None,
    "reset_prev": False
}

# ===== MQTT Initialization =====
client = mqtt.Client()
client.username_pw_set(USER, PW)
client.connect(BROKER, PORT, 60)

def publish(topic, data):
    client.publish(topic, json.dumps(data), qos=1)

# ===== Light Control Function =====
def turn_light(on):
    """Turn light on/off, clear motion count and vision cache"""
    if state["on"] != on:
        state["on"] = on
        state["last_on"] = time.monotonic()
        state["no_motion"] = 0
        state["reset_prev"] = True

        # Synchronously control physical LED
        if on:
            led.color = (1, 0, 0)   # White light on
        else:
            led.color = (0, 1, 0)
            time.sleep(1)
            led.color = (0, 0, 1)
            time.sleep(1)
            led.off()               # Turn off light

        action = "ON" if on else "OFF"
        print(f"[{time.strftime('%H:%M:%S')}] Light -> {action}")
        publish(TOPIC_EVENT, {
            "device_id": DEVICE_ID,
            "type": "light_change",
            "on": on,
            "timestamp": int(time.time())
        })

# ===== Sound Detection Thread =====
def sound_loop():
    with sd.InputStream(samplerate=16000, channels=1, blocksize=3200, dtype='int16') as s:
        last_trigger = 0
        while True:
            data, _ = s.read(3200)
            rms = np.sqrt(np.mean(data.astype(np.float32)**2))
            if params["mode"] == "auto":
                if rms > params["sound_thresh"] and time.monotonic() - last_trigger > 3:
                    print(f"[sound] RMS={rms:.3f} -> Trigger")
                    state["no_motion"] = 0
                    turn_light(True)
                    state["last_trigger"] = "sound"
                    publish(TOPIC_EVENT, {
                        "device_id": DEVICE_ID,
                        "type": "sound_detected",
                        "value": float(rms),
                        "timestamp": int(time.time())
                    })
                    last_trigger = time.monotonic()
            time.sleep(0.1)

# ===== Vision Detection Thread =====
def vision_loop():
    cap = cv2.VideoCapture(0)
    prev = None
    while True:
        if params["mode"] != "auto":
            time.sleep(1)
            continue

        ret, frame = cap.read()
        if not ret:
            continue

        if state.get("reset_prev"):
            prev = None
            state["reset_prev"] = False

        gray = cv2.cvtColor(cv2.resize(frame, (320,240)), cv2.COLOR_BGR2GRAY)

        if prev is not None and state["on"]:
            diff = np.mean(np.abs(gray.astype(float) - prev.astype(float))) / 255.0
            print(f"[vision] diff={diff:.4f}")
            if diff > params["motion_thresh"]:
                state["no_motion"] = 0
                state["last_trigger"] = "motion"
            else:
                state["no_motion"] += 1
                print(f"  no_motion_count = {state['no_motion']}")
            if state["no_motion"] >= 2:
                turn_light(False)

        prev = gray

        if state["on"] and time.monotonic() - state["last_on"] > params["timeout"]:
            turn_light(False)

        time.sleep(5)

# ===== Status Reporting Thread =====
def status_loop():
    while True:
        publish(TOPIC_STATUS, {
            "device_id": DEVICE_ID,
            "mode": params["mode"],
            "light_on": state["on"],
            "sound_thresh": params["sound_thresh"],
            "motion_thresh": params["motion_thresh"],
            "last_trigger": state["last_trigger"],
            "timestamp": int(time.time())
        })
        time.sleep(10)

# ===== Receive Controller Commands =====
def on_msg(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print(f"[MQTT cmd] {data}")
    params.update({k: v for k, v in data.items() if k in params})
    if "mode" in data:
        if data["mode"] == "always_on":
            turn_light(True)
        elif data["mode"] == "always_off":
            turn_light(False)
    publish(TOPIC_EVENT, {
        "device_id": DEVICE_ID,
        "type": "param_update",
        "params": params,
        "timestamp": int(time.time())
    })

client.on_message = on_msg
client.subscribe(TOPIC_CMD, qos=1)
client.loop_start()

# ===== Start Threads =====
threading.Thread(target=sound_loop, daemon=True).start()
threading.Thread(target=vision_loop, daemon=True).start()
threading.Thread(target=status_loop, daemon=True).start()

while True:
    time.sleep(1)
