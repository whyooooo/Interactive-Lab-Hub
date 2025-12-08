#!/usr/bin/env python3
"""
Scenario 1: the lid is opened outside the 8:00–12:00 dose window.
Steps:
1. Wait for initialization to finish, then type 'y' and press Enter.
2. 按下下一次回车即可立即触发“窗口外”语音与红灯闪烁（无需真实开盖）。
"""

import sys
import time
import types
from pathlib import Path
from datetime import datetime as real_datetime
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import cv2  # type: ignore
except ModuleNotFoundError:
    class _Cv2Stub:
        CAP_V4L2 = None
        CAP_PROP_FRAME_WIDTH = 3
        CAP_PROP_FRAME_HEIGHT = 4
        CAP_PROP_FPS = 5

        def VideoCapture(self, *_, **__):
            raise RuntimeError("cv2 stub active: camera unavailable in tests.")

        def imwrite(self, *_, **__):
            raise RuntimeError("cv2 stub active: cannot write images in tests.")

    sys.modules["cv2"] = _Cv2Stub()

import smart_pillbox  # noqa: E402

try:
    from gpiozero import RGBLED  # type: ignore
except ImportError as exc:
    RGBLED = None
    GPIOZERO_IMPORT_ERROR = exc
else:
    GPIOZERO_IMPORT_ERROR = None

LED_PINS = {"red": 21, "green": 20, "blue": 26}
LED_ACTIVE_HIGH = True
ALERT_TEXT = "Box opened outside the 8 AM to noon window, please close it now!"


def _wait_for_confirmation():
    while True:
        answer = input("Init ready. Type 'y' then Enter to simulate an early lid opening: ").strip().lower()
        if answer in {"y", "yes"}:
            return
        if answer in {"n", "no", ""}:
            print("Aborted by user.")
            sys.exit(0)
        print("Please respond with y/yes or n/no.")


class DummyButton:
    def is_button_pressed(self):
        return False


class DummyTouchDetector:
    def get_box_state(self):
        return "locked"


def _init_led():
    if RGBLED is None:
        if GPIOZERO_IMPORT_ERROR:
            print(f"ℹ️ gpiozero 未安装，红灯闪烁将跳过 ({GPIOZERO_IMPORT_ERROR}).")
        else:
            print("ℹ️ gpiozero 未安装，红灯闪烁将跳过。")
        return None
    try:
        led = RGBLED(
            red=LED_PINS["red"],
            green=LED_PINS["green"],
            blue=LED_PINS["blue"],
            active_high=LED_ACTIVE_HIGH,
            pwm=True,
        )
        return led
    except Exception as exc:
        print(f"⚠️ 红灯初始化失败：{exc}")
        return None


def _blink_red(led: RGBLED, duration: float = 4.0, period: float = 0.3):
    deadline = time.monotonic() + max(0.0, duration)
    state_on = False
    while time.monotonic() < deadline:
        led.color = (1.0, 0.0, 0.0) if state_on else (0.0, 0.0, 0.0)
        state_on = not state_on
        time.sleep(max(0.05, period / 2))
    led.off()


def _build_fixed_datetime(hour: int, minute: int, second: int = 0):
    class _Fixed(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2024, 1, 1, hour, minute, second, tzinfo=tz)

    return _Fixed


def _setup_tester():
    dummy_button = DummyButton()
    dummy_touch = DummyTouchDetector()
    led = _init_led()
    patchers = [
        mock.patch.object(
            smart_pillbox.ButtonCameraTester,
            "_init_button",
            return_value=dummy_button,
        ),
        mock.patch.object(
            smart_pillbox.ButtonCameraTester,
            "_init_touch_detector",
            return_value=dummy_touch,
        ),
        mock.patch.object(
            smart_pillbox.ButtonCameraTester,
            "_init_status_led",
            return_value=None,
        ),
    ]
    for p in patchers:
        p.start()

    def _cleanup():
        for p in reversed(patchers):
            p.stop()
        if led:
            led.off()
            led.close()

    tester = smart_pillbox.ButtonCameraTester(prescriptions=[])

    def _set_led_mode(mode, hold_seconds=0.0):
        print(f"[LED] mode={mode} hold={hold_seconds}s")
        if not led:
            return
        if mode in {"failure", "alert"}:
            _blink_red(led, duration=hold_seconds or 4.0)
        elif mode == "off":
            led.off()

    tester._set_led_mode = _set_led_mode

    def _speak_with_audio(text, voice="en"):
        # 覆盖语音内容为指定提醒文案
        print(f"[VOICE] {ALERT_TEXT}")
        smart_pillbox.send_voice_prompt(ALERT_TEXT, voice=voice)

    def _custom_alert(self):
        _speak_with_audio(ALERT_TEXT, voice="en")
        self._set_led_mode("failure", hold_seconds=4.0)

    tester._speak = _speak_with_audio
    tester._alert_outside_window = types.MethodType(_custom_alert, tester)

    return tester, _cleanup


def _trigger_alert_on_keypress(tester):
    input("Press Enter once more to trigger the outside-window alert: ")
    fake_datetime = _build_fixed_datetime(7, 5)
    with mock.patch.object(smart_pillbox, "datetime", fake_datetime):
        tester._alert_outside_window()


def main():
    tester, cleanup = _setup_tester()
    try:
        print("=== Opening outside the window (should raise an error) ===")
        _wait_for_confirmation()
        _trigger_alert_on_keypress(tester)
        print("WARNING: Lid was opened outside the 8:00-noon window; red LED should be flashing.")
    finally:
        cleanup()


if __name__ == "__main__":
    main()

