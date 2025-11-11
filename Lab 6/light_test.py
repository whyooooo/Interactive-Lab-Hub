import sounddevice as sd
import numpy as np
import cv2, time, threading, json, paho.mqtt.client as mqtt
from PIL import Image, ImageDraw, ImageFont

# ===== Try to import mini PiTFT driver =====
try:
    from adafruit_rgb_display import st7789
    import digitalio, board, busio
    USE_TFT = True
except ImportError:
    print("[WARN] Adafruit PiTFT not found, fallback to OpenCV window display.")
    USE_TFT = False

# ===== MQTT Configuration =====
BROKER = "farlab.infosci.cornell.edu"
PORT = 1883
USER, PW = "idd", "device@theFarm"
DEVICE_ID = "pi_01"

TOPIC_CMD = f"IDD/hall/smartlight/cmd/{DEVICE_ID}"
TOPIC_STATUS = f"IDD/hall/smartlight/status/{DEVICE_ID}"
TOPIC_EVENT = f"IDD/hall/smartlight/event/{DEVICE_ID}"

# ===== Parameter Initialization =====
params = {
    "mode": "auto",
    "sound_thresh": 300,
    "motion_thresh": 8/255.0,
    "timeout": 120
}
state = {
    "on": False,
    "last_on": 0,
    "no_motion": 0,
    "last_trigger": None,
    "reset_prev": False,
    "countdown_active": False
}

# ===== MQTT Initialization =====
client = mqtt.Client()
client.username_pw_set(USER, PW)
client.connect(BROKER, PORT, 60)
def publish(topic, data):
    client.publish(topic, json.dumps(data), qos=1)

# ===== mini PiTFT Screen Initialization =====
if USE_TFT:
    # SPI interface initialization
    spi = board.SPI()
    dc = digitalio.DigitalInOut(board.D25)
    cs = digitalio.DigitalInOut(board.CE0)
    rst = digitalio.DigitalInOut(board.D24)
    disp = st7789.ST7789(
        spi,
        cs=cs,
        dc=dc,
        rst=rst,
        baudrate=80_000_000,
        width=240,
        height=240,
        rotation=180,
        x_offset=0,
        y_offset=80,
    )
else:
    cv2.namedWindow("LightSim", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("LightSim", 240, 240)

font = ImageFont.load_default()
lock = threading.Lock()

# ===== Screen Display Function =====
def show_screen(color=(255,255,255), text=None, text_color=(0,0,0)):
    """Display color block and text on PiTFT"""
    with lock:
        img = Image.new("RGB", (240,240), color)
        if text:
            draw = ImageDraw.Draw(img)
            w, h = draw.textsize(text, font=font)
            draw.text(((240-w)/2, (240-h)/2), text, fill=text_color, font=font)
        if USE_TFT:
            disp.image(img)
        else:
            cv2.imshow("LightSim", np.array(img))
            cv2.waitKey(1)

# ===== Countdown Thread =====
def countdown_thread():
    """Trigger countdown after vision detects stillness twice"""
    state["countdown_active"] = True
    for t in range(10, 0, -1):
        if t > 3:
            show_screen(color=(255,255,255), text=f"{t}s", text_color=(0,0,0))
        else:
            show_screen(color=(255,255,255), text=f"{t}s", text_color=(255,0,0))
        time.sleep(1)
    show_screen(color=(0,0,0))
    state["countdown_active"] = False
    turn_light(False)

# ===== Light Control Function =====
def turn_light(on):
    if state["on"] != on:
        state["on"] = on
        state["last_on"] = time.monotonic()
        state["no_motion"] = 0
        state["reset_prev"] = True
        action = "ON" if on else "OFF"
        print(f"[{time.strftime('%H:%M:%S')}] Light -> {action}")
        if on:
            show_screen(color=(255,255,255))
        else:
            show_screen(color=(0,0,0))
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
                if state["no_motion"] == 2 and not state["countdown_active"]:
                    threading.Thread(target=countdown_thread, daemon=True).start()

        prev = gray
        if state["on"] and time.monotonic() - state["last_on"] > params["timeout"]:
            turn_light(False)
        time.sleep(10)

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

# ===== Start All Threads =====
threading.Thread(target=sound_loop, daemon=True).start()
threading.Thread(target=vision_loop, daemon=True).start()
threading.Thread(target=status_loop, daemon=True).start()

while True:
    time.sleep(1)
