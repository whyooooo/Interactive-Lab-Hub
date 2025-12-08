#!/usr/bin/env python3
"""
Scenario 2: noon arrives and the scheduled dose is still incomplete.
The script freezes the clock at 12:05, invokes the smart_pillbox reminder,
and exits immediately once the voice prompt fires.
"""

import sys
from pathlib import Path
from datetime import datetime as real_datetime, time as dtime
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


class DummyButton:
    def is_button_pressed(self):
        return False


class DummyTouchDetector:
    def get_box_state(self):
        return "locked"


def _build_fixed_datetime(hour: int, minute: int, second: int = 0):
    class _Fixed(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2024, 1, 1, hour, minute, second, tzinfo=tz)

    return _Fixed


def _setup_tester():
    dummy_button = DummyButton()
    dummy_touch = DummyTouchDetector()
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

    tester = smart_pillbox.ButtonCameraTester(prescriptions=[])
    tester._set_led_mode = lambda mode, hold_seconds=0.0: print(f"[LED] mode={mode} hold={hold_seconds}s")

    def _speak_with_audio(text, voice="en"):
        print(f"[VOICE] {text}")
        smart_pillbox.send_voice_prompt(text, voice=voice)

    tester._speak = _speak_with_audio
    tester.doses_taken = 0
    tester.dose_target = 1
    tester.noon_reminder_sent = False

    return tester, _cleanup


def main():
    original_window_end = smart_pillbox.DOSE_WINDOW_END
    smart_pillbox.DOSE_WINDOW_END = dtime(12, 0)
    tester, cleanup = _setup_tester()
    try:
        print("=== Noon reminder (should prompt immediately) ===")
        fake_datetime = _build_fixed_datetime(12, 5)
        with mock.patch.object(smart_pillbox, "datetime", fake_datetime):
            tester._check_noon_reminder()

        if tester.noon_reminder_sent:
            print("WARNING: Noon reminder triggered; instruct the user to take medication now.")
            return
        print("Reminder not triggered; please double-check the configuration.")
    finally:
        smart_pillbox.DOSE_WINDOW_END = original_window_end
        cleanup()


if __name__ == "__main__":
    main()

