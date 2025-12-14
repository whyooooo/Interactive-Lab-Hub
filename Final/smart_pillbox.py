#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwiic Button -> Camera Capture Smoke Test

Press the SparkFun Qwiic Button once to trigger a 720p capture via USB/Pi camera.
This verifies the most critical human-in-the-loop interaction path.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import base64
import json
import re
import subprocess
import time
import threading
from datetime import datetime, time as dtime
from pathlib import Path

import cv2

try:
    import qwiic_button
except ImportError as exc:  # keep the error message friendlier
    qwiic_button = None
    QWIIC_IMPORT_ERROR = exc
else:
    QWIIC_IMPORT_ERROR = None

try:
    import requests
except ImportError as exc:
    requests = None
    REQUESTS_IMPORT_ERROR = exc
else:
    REQUESTS_IMPORT_ERROR = None

try:
    import pyttsx3
except ImportError as exc:
    pyttsx3 = None
    PYTTSX3_IMPORT_ERROR = exc
else:
    PYTTSX3_IMPORT_ERROR = None

try:
    from gpiozero import RGBLED
except ImportError as exc:
    RGBLED = None
    GPIOZERO_IMPORT_ERROR = exc
else:
    GPIOZERO_IMPORT_ERROR = None

try:
    import board
    import busio
    import adafruit_mpr121
except ImportError as exc:
    board = busio = adafruit_mpr121 = None
    MPR121_IMPORT_ERROR = exc
else:
    MPR121_IMPORT_ERROR = None


CONFIG_PATH = Path(__file__).with_name("pillbox_config.json")
IMAGE_DIR = Path(__file__).with_name("pillbox_images")
COLOR_ALIAS_MAP = {
    "red": "red",
    "scarlet": "red",
    "crimson": "red",
    "green": "green",
    "lime": "green",
    "emerald": "green",
    "blue": "blue",
    "navy": "blue",
    "cyan": "blue",
    "yellow": "yellow",
    "gold": "yellow",
    "amber": "yellow",
    "white": "white",
    "ivory": "white",
    "pearl": "white",
    "black": "black",
    "charcoal": "black",
    "ebony": "black",
    "orange": "orange",
    "tangerine": "orange",
    "apricot": "orange",
    "pink": "pink",
    "rose": "pink",
    "magenta": "pink",
    "purple": "purple",
    "violet": "purple",
    "lavender": "purple",
    "brown": "brown",
    "chocolate": "brown",
    "tan": "brown"
}

def send_voice_prompt(text: str, voice: str = "en", speed: str = "150"):
    """Voice prompt helper with espeak primary and pyttsx3 fallback."""

    def _try_espeak():
        try:
            subprocess.Popen(
                ["espeak", "-s", speed, "-v", voice, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"Voice prompt sent via espeak: {text}")
            return True
        except FileNotFoundError:
            print("⚠️ espeak not found. Trying pyttsx3 fallback (install via 'sudo apt install espeak').")
        except Exception as exc:
            print(f"⚠️ espeak playback failed ({exc}). Trying pyttsx3 fallback.")
        return False

    if _try_espeak():
        return

    if _speak_with_pyttsx3(text, voice=voice, speed=speed):
        return

    print("✗ Voice prompt failed: no available TTS backend. Install espeak or 'pip install pyttsx3'.")


def _speak_with_pyttsx3(text: str, voice: str = "en", speed: str = "150") -> bool:
    if pyttsx3 is None:
        if PYTTSX3_IMPORT_ERROR:
            print(f"⚠️ pyttsx3 is not installed; speech fallback unavailable ({PYTTSX3_IMPORT_ERROR}). Run 'pip install pyttsx3'.")
        return False

    def _worker():
        try:
            engine = pyttsx3.init()
            try:
                rate = int(speed)
            except ValueError:
                rate = 150
            engine.setProperty("rate", max(80, min(rate, 300)))
            _assign_pyttsx3_voice(engine, voice)
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            print(f"⚠️ pyttsx3 voice playback failed: {exc}")

    threading.Thread(target=_worker, daemon=True).start()
    print(f"Voice prompt sent via pyttsx3 fallback: {text}")
    return True


def _assign_pyttsx3_voice(engine, target_voice: str):
    if not target_voice:
        return
    try:
        voices = engine.getProperty("voices") or []
    except Exception:
        return
    target = target_voice.lower()
    for candidate in voices:
        desc = " ".join(
            filter(
                None,
                [
                    getattr(candidate, "id", ""),
                    getattr(candidate, "name", ""),
                    " ".join(getattr(candidate, "languages", []) or []),
                ],
            )
        ).lower()
        if target in desc:
            try:
                engine.setProperty("voice", candidate.id)
            except Exception:
                pass
            return


LED_DEFAULT_PINS = {"red": 21, "green": 20, "blue": 26}
LED_DEFAULT_ACTIVE_HIGH = True
DOSE_WINDOW_START = dtime(8, 0)
DOSE_WINDOW_END = dtime(12, 0)
DOSE_TARGET_COUNT = 1
GLOBAL_TOUCH_DETECTOR = None


class PillboxTouchDetector:
    """Minimal MPR121 wrapper: both channel 0/1 touched → locked, otherwise unlocked."""

    def __init__(self):
        if None in (board, busio, adafruit_mpr121):
            raise ImportError(
                f"MPR121 dependency missing: {MPR121_IMPORT_ERROR or 'board/busio unavailable'}"
            )
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.mpr121 = adafruit_mpr121.MPR121(self.i2c)
        except Exception as exc:
            raise RuntimeError(f"MPR121 initialization failed: {exc}") from exc

    def get_box_state(self):
        try:
            touch_0 = bool(self.mpr121[0].value)
            touch_1 = bool(self.mpr121[1].value)
        except Exception as exc:
            print(f"Failed to read MPR121: {exc}")
            return "error"
        if touch_0 and touch_1:
            return "locked"
        return "unlocked"


def bootstrap_touch_detector():
    """Initialize touch detector ASAP so MPR121 is ready at program start."""
    global GLOBAL_TOUCH_DETECTOR
    if GLOBAL_TOUCH_DETECTOR is not None:
        return GLOBAL_TOUCH_DETECTOR
    if board is None or busio is None or adafruit_mpr121 is None:
        if MPR121_IMPORT_ERROR:
            print(f"ℹ️ MPR121 dependency unavailable ({MPR121_IMPORT_ERROR}).")
        return None
    try:
        GLOBAL_TOUCH_DETECTOR = PillboxTouchDetector()
        print("✓ Global touch detector initialized.")
    except Exception as exc:
        print(f"⚠️ Failed to initialize touch detector at startup: {exc}")
        GLOBAL_TOUCH_DETECTOR = None
    return GLOBAL_TOUCH_DETECTOR


bootstrap_touch_detector()


class LEDAnimator:
    """Background thread controlling RGB LED patterns."""

    MODES = {
        "idle": {"color": (0.0, 0.28, 0.0), "blink": True, "period": 0.9},
        # Matches the test_rgbtest.py ratio: red 1.0 / green 0.1 to avoid skewing green
        "processing": {"color": (1.0, 0.1, 0.0), "blink": True, "period": 0.3},
        "warning": {"color": (1.0, 0.75, 0.0), "blink": True, "period": 0.25},
        "alert": {"color": (1.0, 0.0, 0.0), "blink": False, "period": 0.0},
        "success": {"color": (0.0, 0.9, 0.0), "blink": False, "period": 0.0},
        "failure": {"color": (1.0, 0.0, 0.0), "blink": True, "period": 0.2},
        "off": {"color": (0.0, 0.0, 0.0), "blink": False, "period": 0.0},
    }

    def __init__(self, red_pin=LED_DEFAULT_PINS["red"], green_pin=LED_DEFAULT_PINS["green"],
                 blue_pin=LED_DEFAULT_PINS["blue"], active_high=LED_DEFAULT_ACTIVE_HIGH):
        if RGBLED is None:
            raise RuntimeError("gpiozero.RGBLED is not installed")

        self.led = RGBLED(
            red=red_pin,
            green=green_pin,
            blue=blue_pin,
            pwm=True,
            active_high=active_high
        )
        self.mode = "off"
        self._hold_until = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._phase_on = False
        self._last_toggle = 0.0
        self._current_color = (0.0, 0.0, 0.0)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.set_mode("idle")

    def set_mode(self, mode: str, hold_seconds: float = 0.0):
        target = mode if mode in self.MODES else "off"
        with self._lock:
            self.mode = target
            self._hold_until = time.monotonic() + hold_seconds if hold_seconds > 0 else 0.0
            self._phase_on = False
            self._last_toggle = 0.0

    def shutdown(self):
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        try:
            self.led.off()
            self.led.close()
        except Exception:
            pass

    def _loop(self):
        while not self._stop_event.is_set():
            with self._lock:
                mode = self.mode
                hold_until = self._hold_until

            now = time.monotonic()
            if hold_until and now >= hold_until and mode in {"success", "failure"}:
                self.set_mode("idle")
                continue

            config = self.MODES.get(mode, self.MODES["off"])
            if config["blink"]:
                period = max(0.05, config["period"])
                if now - self._last_toggle >= period:
                    self._last_toggle = now
                    self._phase_on = not self._phase_on
                    color = config["color"] if self._phase_on else (0.0, 0.0, 0.0)
                    self._apply_color(color)
            else:
                if (not self._phase_on) or (self._current_color != config["color"]):
                    self._phase_on = True
                    self._apply_color(config["color"])

            time.sleep(0.05)

    def _apply_color(self, color):
        try:
            self.led.color = color
            self._current_color = color
        except Exception:
            self._stop_event.set()

def normalize_color_input(raw_color: str) -> str:
    color = (raw_color or "").strip().lower()
    if not color:
        return ""
    return COLOR_ALIAS_MAP.get(color, color)


def prompt_user_prescription():
    print("=" * 62)
    print("Enter the pill color and quantity you need to take (example: red, 2).")
    print("Type 'done' when you have finished adding prescriptions. Press Ctrl+C to exit.")
    send_voice_prompt("Please enter pill color and quantity.")

    prescriptions = []
    while True:
        try:
            color_raw = input("Pill color (English, or 'done' to finish): ").strip()
        except EOFError:
            color_raw = ""
        except KeyboardInterrupt:
            print("\nInput cancelled by user.")
            raise

        if color_raw.lower() in {"done", "exit", "quit"}:
            if prescriptions:
                break
            print("Please enter at least one prescription before finishing.")
            continue

        color = normalize_color_input(color_raw)
        if not color:
            print("Color cannot be empty. Please enter again.")
            continue

        while True:
            try:
                count_raw = input("Quantity needed (integer, >=1): ").strip()
            except EOFError:
                count_raw = ""
            except KeyboardInterrupt:
                print("\nInput cancelled by user.")
                raise

            try:
                count = int(count_raw)
            except ValueError:
                print("Quantity must be an integer. Please enter again.")
                continue

            if count >= 1:
                break
            print("Quantity must be at least 1. Please enter again.")

        prescriptions.append({"color": color, "count": count})
        print(f"✓ Recorded target: {count} pill(s) of color {color}.")

        while True:
            more = input("Add another prescription? (y/N): ").strip().lower()
            if more in {"y", "yes"}:
                break
            if more in {"", "n", "no"}:
                print("Prescription intake complete.")
                return prescriptions
            print("Please respond with 'y' or 'n'.")

    print("Prescription intake complete.")
    return prescriptions


class ButtonCameraTester:
    """Minimal integration test connecting the Qwiic button with the camera."""

    def __init__(self, prescriptions=None):
        self.camera_config, self.vision_config = self._load_runtime_config()
        self.camera_index = int(self.camera_config.get("index", 0))
        self.target_fps = int(self.camera_config.get("fps", 30))
        self.warmup_seconds = float(self.camera_config.get("warmup_seconds", 2.0))
        self.warmup_frames = int(self.camera_config.get("warmup_frames", 30))
        self.analysis_enabled = bool(self.vision_config.get("enabled", True))
        self.image_dir = IMAGE_DIR
        self.image_dir.mkdir(exist_ok=True)

        self.touch_detector = self._init_touch_detector()
        self.last_touch_state = None
        self.button = self._init_button()
        self.status_led = self._init_status_led()
        self.last_press_ts = 0.0
        self.debounce = 0.4  # seconds
        self.capture_counter = 0
        self.prescription_targets = {}
        self.prescription_active = False
        self.dose_target = DOSE_TARGET_COUNT
        self.doses_taken = 0
        self.window_open = False
        self.noon_reminder_sent = False
        self.prompt_thread = None
        self.alert_latched = False

        self.set_prescriptions(prescriptions or [])
        if self.analysis_enabled and requests is None:
            print(f"⚠️ requests is not installed. Ollama analysis cannot be enabled ({REQUESTS_IMPORT_ERROR}).")
            self.analysis_enabled = False
        if self.analysis_enabled:
            print(f"✓ AI analysis enabled. Model: {self.vision_config.get('model')}")
        else:
            print("ℹ️ AI analysis disabled due to config or missing dependency.")
        if self.prescription_active and not self.analysis_enabled:
            print("⚠️ Prescription provided but AI analysis is disabled, so auto validation is unavailable.")

    def _load_runtime_config(self):
        camera_default = {
            "width": 1280,
            "height": 720,
            "index": 0,
            "fps": 30,
            "warmup_seconds": 2.0,
            "warmup_frames": 30
        }
        vision_default = {
            "enabled": True,
            "model": "moondream:latest",
            "endpoint": "http://localhost:11434/api/generate",
            "temperature": 0.1,
            "timeout": 120,
            "save_json": True,
            "max_pills": 8
        }
        raw_cfg = {}
        if CONFIG_PATH.exists():
            try:
                with CONFIG_PATH.open("r", encoding="utf-8") as f:
                    raw_cfg = json.load(f)
            except Exception as exc:
                print(f"⚠️ Failed to read pillbox_config.json. Falling back to defaults: {exc}")

        camera_cfg = camera_default.copy()
        camera_cfg.update(raw_cfg.get("camera", {}))

        vision_cfg = vision_default.copy()
        vision_cfg.update(raw_cfg.get("vision", {}))

        return camera_cfg, vision_cfg

    def _init_button(self):
        if qwiic_button is None:
            raise ImportError(
                "qwiic_button is not installed. Please run 'pip install sparkfun-qwiic-button' "
                f"({QWIIC_IMPORT_ERROR})"
            )
        button = qwiic_button.QwiicButton()
        if not button.begin():
            raise RuntimeError("Failed to initialize Qwiic button. Check I2C wiring and address.")
        print("✓ Qwiic button connected. Waiting for presses...")
        return button

    def _init_status_led(self):
        if RGBLED is None:
            if GPIOZERO_IMPORT_ERROR:
                print(f"ℹ️ gpiozero is not installed; RGB LED indicator disabled ({GPIOZERO_IMPORT_ERROR}).")
            else:
                print("ℹ️ RGB LED indicator not enabled.")
            return None
        try:
            controller = LEDAnimator()
        except Exception as exc:
            print(f"⚠️ RGB LED initialization failed: {exc}")
            return None
        print("✓ RGB LED indicator ready: green blink = idle, amber blink = processing, solid green = success, red fast blink = failure.")
        return controller

    def set_prescriptions(self, prescriptions):
        normalized = self._normalize_prescriptions(prescriptions or [])
        self.prescription_targets = normalized
        self.prescription_active = True
        summary = ", ".join(
            f"{count} pill(s) of {color}"
            for color, count in normalized.items()
        ) if normalized else "Custom intake (manual review)"
        print(f"🎯 Targets for this session: {summary}.")

    def _init_touch_detector(self):
        detector = bootstrap_touch_detector()
        if detector:
            print("✓ Touch detector ready (used to track lid state).")
        else:
            print("ℹ️ Touch detector not initialized.")
        return detector

    def _set_led_mode(self, mode: str, hold_seconds: float = 0.0):
        if not self.status_led:
            return
        if getattr(self, "alert_latched", False) and mode not in {"alert", "warning", "off"}:
            return
        try:
            self.status_led.set_mode(mode, hold_seconds=hold_seconds)
        except Exception as exc:
            print(f"⚠️ Failed to update LED state: {exc}")
            self._shutdown_led()

    def _shutdown_led(self):
        if not self.status_led:
            return
        try:
            self.status_led.shutdown()
        finally:
            self.status_led = None

    @staticmethod
    def _within_window(now_time: dtime, start: dtime, end: dtime) -> bool:
        if start <= end:
            return start <= now_time <= end
        return now_time >= start or now_time <= end

    def _within_dose_window(self, now_time=None) -> bool:
        now = now_time or datetime.now().time()
        return self._within_window(now, DOSE_WINDOW_START, DOSE_WINDOW_END)

    def _check_touch_state(self):
        if not self.touch_detector:
            return
        state = self.touch_detector.get_box_state()
        if not state or state == "error":
            return
        if state == self.last_touch_state:
            return
        self.last_touch_state = state
        print(f"[Touch] Box state -> {state}")
        now_time = datetime.now().time()
        if state == "locked":
            self.window_open = False
            return

        if not self._within_dose_window(now_time):
            self.window_open = False
            self._alert_outside_window()
            return
        if self.doses_taken >= self.dose_target:
            self._alert_extra_dose()
            return

        self.window_open = True
        self._queue_verification_prompts()
        self._set_led_mode("idle")

    def _alert_outside_window(self):
        self._set_led_mode("failure", hold_seconds=4.0)
        self._speak("Pillbox opened outside the 8 a.m. to noon window.", voice="en")

    def _alert_extra_dose(self):
        self._set_led_mode("failure", hold_seconds=4.0)
        self._speak("Dose already completed. Do not take extra pills.", voice="en")

    def _queue_verification_prompts(self):
        if self.prompt_thread and self.prompt_thread.is_alive():
            return

        def _worker():
            self._speak("Lid opened on schedule. You may verify now.", voice="en")
            time.sleep(4.0)
            self._speak("Press the button to verify your pills.", voice="en")

        self.prompt_thread = threading.Thread(target=_worker, daemon=True)
        self.prompt_thread.start()

    def _check_noon_reminder(self):
        if self.noon_reminder_sent:
            return
        now_time = datetime.now().time()
        if now_time >= DOSE_WINDOW_END:
            if self.doses_taken < self.dose_target:
                self._speak("It is noon. Please take your scheduled medication now.", voice="en")
                self._set_led_mode("failure", hold_seconds=5.0)
            self.noon_reminder_sent = True

    def capture_image(self):
        """Open the camera, capture a frame, and save it under pillbox_images."""
        backend = getattr(cv2, "CAP_V4L2", None)
        backend_used = None
        cap = None

        if backend is not None:
            cap = cv2.VideoCapture(self.camera_index, backend)
            backend_used = "V4L2"
        else:
            cap = cv2.VideoCapture(self.camera_index)
            backend_used = "DEFAULT"

        if not cap.isOpened():
            # Attempt to fall back to default backend.
            if backend is not None:
                cap.release()
                cap = cv2.VideoCapture(self.camera_index)
                backend_used = "DEFAULT"

        if not cap.isOpened():
            print("✗ Unable to open camera. Please check connections/permissions.")
            cap.release()
            return None

        print(f"Capturing with camera #{self.camera_index} via backend {backend_used}.")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.camera_config["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.camera_config["height"])
        if self.target_fps > 0:
            cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        reported_fps = cap.get(cv2.CAP_PROP_FPS) or self.target_fps
        print(f"Target FPS: {self.target_fps}fps, reported by camera: {reported_fps:.1f}fps.")

        warmup_time = max(0.0, self.warmup_seconds)
        warmup_frames = max(0, self.warmup_frames)
        if warmup_time > 0 or warmup_frames > 0:
            print(f"Camera warm-up: {warmup_time:.1f}s + {warmup_frames} frames (mirrors Lab5 approach).")
            if warmup_time > 0:
                time.sleep(warmup_time)
            for _ in range(warmup_frames):
                cap.read()

        ret, frame = cap.read()
        cap.release()

        if not ret:
            print("✗ Capture failed. Please try again.")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.image_dir / f"button_capture_{timestamp}.jpg"

        if cv2.imwrite(str(file_path), frame):
            mean_pixel = float(frame.mean())
            if mean_pixel < 15:
                print("⚠️ Frame brightness is very low. Check ambient light or extend warm-up.")
            return file_path

        print("✗ Failed to save photo. Check disk permissions.")
        return None

    def run(self):
        self._print_banner()
        self._set_led_mode("idle")
        try:
            while True:
                self._check_touch_state()
                self._check_noon_reminder()
                if self.button.is_button_pressed():
                    now = time.time()
                    if now - self.last_press_ts < self.debounce:
                        time.sleep(0.05)
                        continue

                    # Wait until release to avoid long-press double triggers.
                    while self.button.is_button_pressed():
                        time.sleep(0.02)

                    self.last_press_ts = now
                    if not self._within_dose_window():
                        self._alert_outside_window()
                        continue
                    if self.doses_taken >= self.dose_target:
                        self._alert_extra_dose()
                        continue
                    if not self.window_open:
                        self._speak("Please open the pillbox before verifying.", voice="en")
                        self._set_led_mode("failure", hold_seconds=2.0)
                        continue
                    if self.alert_latched:
                        self._set_led_mode("warning")
                        self.alert_latched = False
                    else:
                        self._set_led_mode("processing")
                    photo_path = self.capture_image()
                    led_success = False
                    validation_ok = False
                    if photo_path:
                        self.capture_counter += 1
                        print(f"✓ Capture #{self.capture_counter} saved at: {photo_path}")
                        analysis = self.analyze_with_ollama(photo_path)
                        if analysis:
                            self._handle_analysis_output(photo_path, analysis)
                            validation_ok = self._validate_prescription(analysis)
                        else:
                            validation_ok = not self.prescription_active
                        if validation_ok:
                            led_success = True
                            self.doses_taken += 1
                            self.window_open = False
                            if self.doses_taken >= self.dose_target:
                                self._speak("Dose completed for this window.", voice="en")
                        else:
                            led_success = False
                    else:
                        print("✗ Capture failed. Please inspect the camera/storage before pressing again.")
                        led_success = False

                    if led_success:
                        self._set_led_mode("success", hold_seconds=3.0)
                    else:
                        if self.alert_latched:
                            self._set_led_mode("alert")
                        else:
                            self._set_led_mode("failure", hold_seconds=3.0)

                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nTest stopped. Thank you for trying the workflow!")
        finally:
            self._set_led_mode("off")
            self._shutdown_led()

    @staticmethod
    def _print_banner():
        print("=" * 62)
        print("Qwiic Button -> Camera Capture Test")
        print("Press the button once to create a 720p photo under pillbox_images/.")
        print("If vision.enabled is true, Ollama will return JSON analysis automatically.")
        print("Press Ctrl+C to stop.")
        print("=" * 62)

    @staticmethod
    def _speak(text: str, voice: str = "en"):
        send_voice_prompt(text, voice=voice)

    # ---------- Ollama analysis ----------

    def analyze_with_ollama(self, image_path: Path):
        if not self.analysis_enabled:
            return None

        try:
            with image_path.open("rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as exc:
            print(f"✗ Failed to read image for AI analysis: {exc}")
            return None

        payload = {
            "model": self.vision_config.get("model", "moondream:latest"),
            "prompt": self._build_analysis_prompt(),
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": self.vision_config.get("temperature", 0.1)
            }
        }

        endpoint = self.vision_config.get("endpoint", "http://localhost:11434/api/generate")
        timeout = self.vision_config.get("timeout", 120)

        try:
            response = requests.post(endpoint, json=payload, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            print(f"✗ Ollama request failed: {exc}")
            return None

        if response.status_code != 200:
            print(f"✗ Ollama returned status {response.status_code}: {response.text[:200]}")
            return None

        raw_text = response.json().get("response", "").strip()
        print("---- Raw Ollama response (start) ----")
        print(raw_text)
        print("---- Raw Ollama response (end) ----")
        raw_log_path = image_path.with_suffix(".ollama_raw.txt")
        try:
            raw_log_path.write_text(raw_text, encoding="utf-8")
        except Exception as exc:
            print(f"⚠️ Failed to save raw Ollama response: {exc}")
        parsed = self._parse_analysis_json(raw_text)
        if not parsed:
            print("✗ Could not parse AI JSON response. Raw content follows:")
            print(raw_text)
            return None

        if isinstance(parsed, list):
            parsed = {"pills": parsed}

        normalized_pills = self._normalize_pills(parsed.get("pills", []))
        result = {
            "pills": normalized_pills,
            "image_path": str(image_path),
            "model": self.vision_config.get("model"),
            "timestamp": datetime.now().isoformat(timespec="seconds")
        }

        return result

    def _build_analysis_prompt(self) -> str:
        max_pills = int(self.vision_config.get("max_pills", 8))
        return f"""
You are a pill color/count inspector. Look at the image and output ONLY the JSON structure below, in English, with lowercase color names. No extra narration.
{{
  "pills": [
    {{
      "color": "",
      "count": integer
    }}
  ]
}}
Rules:
1. Group pills with the same color into one entry; at most {max_pills} entries.
2. If color is unclear, use "unknown".
3. If no pills are visible, return an empty list (no entries in "pills").
4. Return valid JSON only.
""".strip()

    def _parse_analysis_json(self, text: str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
        return None

    @staticmethod
    def _normalize_pills(pills):
        normalized = []
        entries = pills if isinstance(pills, list) else []
        for pill in entries:
            color = str(pill.get("color", "unknown")).strip().lower() or "unknown"
            try:
                count = int(pill.get("count", 0))
            except (ValueError, TypeError):
                count = 0
            normalized.append({
                "color": color,
                "count": max(count, 0)
            })
        return normalized

    @staticmethod
    def _normalize_prescriptions(prescriptions):
        targets = {}
        entries = prescriptions if isinstance(prescriptions, list) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            color = normalize_color_input(entry.get("color", ""))
            if not color:
                continue
            try:
                count = int(entry.get("count", 0))
            except (ValueError, TypeError):
                continue
            if count < 1:
                continue
            if color in targets:
                targets[color] += count
            else:
                targets[color] = count
        return targets

    def _validate_prescription(self, analysis: dict) -> bool:
        if not self.prescription_active:
            return True

        pills = analysis.get("pills") or []
        expected_map = self.prescription_targets
        detected_map = {}
        for pill in pills:
            color = pill.get("color")
            if not color:
                continue
            try:
                detected_map[color] = max(int(pill.get("count", 0)), 0)
            except (ValueError, TypeError):
                detected_map[color] = 0

        mismatches = []
        for color, expected in expected_map.items():
            actual = detected_map.get(color, 0)
            if actual != expected:
                mismatches.append(f"{color}: expected {expected}, got {actual}")

        unexpected = {
            color: count for color, count in detected_map.items()
            if color not in expected_map and count > 0
        }

        if not mismatches and not unexpected:
            summary = ", ".join(f"{count}x {color}" for color, count in expected_map.items())
            print(f"✓ Prescription satisfied: {summary}.")
            self._speak("You may take your pills now.", voice="en")
            return True

        if mismatches:
            print("✗ Prescription mismatches detected:")
            for issue in mismatches:
                print(f"  - {issue}")
        if unexpected:
            print("✗ Additional pill colors detected:")
            for color, count in unexpected.items():
                print(f"  - {color}: detected {count}")

        self._speak(
            "Warning: pill color or quantity is incorrect. Please verify before taking any dose.",
            voice="en"
        )
        self.alert_latched = True
        self._set_led_mode("alert")
        return False

    def _handle_analysis_output(self, photo_path: Path, analysis: dict):
        print("AI structured output:")
        print(json.dumps(analysis, ensure_ascii=False, indent=2))

        if not self.vision_config.get("save_json", True):
            return

        analysis_path = photo_path.with_suffix(".json")
        try:
            analysis_path.write_text(
                json.dumps(analysis, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print(f"✓ AI result saved to: {analysis_path}")
        except Exception as exc:
            print(f"⚠️ Failed to save AI analysis: {exc}")


def main():
    try:
        tester = ButtonCameraTester()
    except Exception as exc:
        print(f"Initialization failed: {exc}")
        sys.exit(1)

    prescriptions = prompt_user_prescription()
    tester.set_prescriptions(prescriptions)
    tester.run()


if __name__ == "__main__":
    main()



