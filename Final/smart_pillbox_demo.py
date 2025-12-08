#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Pillbox Demo
------------------
Lightweight variant of smart_pillbox:
- removes schedule/quantity validation logic
- keeps touch detection, camera capture, and AI color counting
- when the lid opens, LED blinks green and totals are spoken
- each capture announces per-color counts for this capture and for today
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import threading
import time
from datetime import datetime

from smart_pillbox import (
    ButtonCameraTester,
    normalize_color_input,
)


class SmartPillboxDemo(ButtonCameraTester):
    """Demo without schedule/prescription logic; focuses on touch + spoken color totals."""

    COLORS_TRACKED = ("red", "blue", "green")

    def __init__(self):
        # ButtonCameraTester.__init__ calls set_prescriptions; override early to make it a no-op.
        super().__init__(prescriptions=None)

        if not self.analysis_enabled:
            raise RuntimeError(
                "AI vision analysis disabled; smart_pillbox_demo cannot estimate pill colors/counts."
            )

        self.window_open = False
        self.daily_totals = {color: 0 for color in self.COLORS_TRACKED}
        self.daily_totals["overall"] = 0
        self._totals_date = datetime.now().date()
        self._touch_lock = threading.Lock()

        if not self.touch_detector:
            # Without a touch sensor we assume the lid stays open for easier software testing.
            print("⚠️ Touch sensor not detected; demo mode assumes the lid is already open.")
            self.window_open = True
            self._set_led_mode("idle")
        else:
            self._set_led_mode("idle")

    # --------- Override parent prescription logic to avoid manual input ---------
    def set_prescriptions(self, prescriptions):
        self.prescription_targets = {}
        self.prescription_active = False
        print("🎯 Demo mode: skipping prescription intake and only tracking color counts.")

    # --------- Main loop ---------
    def run(self):
        self._print_banner()
        self._set_led_mode("idle")
        try:
            while True:
                self._monitor_touch_state()
                self._process_button_event()
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nSmart Pillbox Demo stopped.")
        finally:
            self._set_led_mode("off")
            self._shutdown_led()

    def _print_banner(self):
        print("=" * 62)
        print("Smart Pillbox Demo")
        print("Lid open → green blink + spoken totals; button → capture + AI + spoken counts.")
        print("Requires Ollama (or compatible multimodal endpoint). Press Ctrl+C to exit.")
        print("=" * 62)

    # --------- Touch / lid logic ---------
    def _monitor_touch_state(self):
        if not self.touch_detector:
            return

        state = self.touch_detector.get_box_state()
        if not state or state == "error":
            return

        with self._touch_lock:
            if state == self.last_touch_state:
                return
            self.last_touch_state = state

        print(f"[Touch] Box state -> {state}")
        if state == "locked":
            self.window_open = False
            self._set_led_mode("idle")
        else:
            was_closed = not self.window_open
            self.window_open = True
            if was_closed:
                self._set_led_mode("idle")
                self._announce_daily_totals(prefix="Right now")

    # --------- Button / capture / AI analysis ---------
    def _process_button_event(self):
        if not self.button.is_button_pressed():
            return
        now = time.time()
        if now - self.last_press_ts < self.debounce:
            return

        while self.button.is_button_pressed():
            time.sleep(0.02)

        self.last_press_ts = now

        if not self.window_open:
            self._speak("Please open the pillbox before taking a photo.", voice="en")
            self._set_led_mode("failure", hold_seconds=2.0)
            return

        self._capture_and_report()

    def _capture_and_report(self):
        self._set_led_mode("processing")
        photo_path = self.capture_image()
        if not photo_path:
            self._speak("Capture failed. Check the camera and try again.", voice="en")
            self._set_led_mode("failure", hold_seconds=3.0)
            return

        self.capture_counter += 1
        print(f"✓ Capture #{self.capture_counter} saved at: {photo_path}")

        analysis = self.analyze_with_ollama(photo_path)
        if not analysis:
            self._speak("AI could not identify pill colors. Please try again.", voice="en")
            self._set_led_mode("failure", hold_seconds=3.0)
            return

        self._handle_analysis_output(photo_path, analysis)

        capture_counts = self._summarize_rgb_counts(analysis)
        self._announce_capture_counts(capture_counts)
        self._update_daily_totals(capture_counts)
        self._announce_daily_totals(prefix="Today in total")
        self._set_led_mode("success", hold_seconds=20.0)

    # --------- Counting / announcements ---------
    def _summarize_rgb_counts(self, analysis):
        summary = {color: 0 for color in self.COLORS_TRACKED}
        pills = analysis.get("pills") or []
        for pill in pills:
            color = normalize_color_input(pill.get("color", ""))
            try:
                count = max(int(pill.get("count", 0)), 0)
            except (ValueError, TypeError):
                count = 0
            if color in summary:
                summary[color] += count
        summary["overall"] = sum(summary.values())
        return summary

    def _announce_capture_counts(self, capture_counts):
        text = (
            f"This time you took {capture_counts['red']} red, {capture_counts['blue']} blue, "
            f"{capture_counts['green']} green pills, {capture_counts['overall']} total."
        )
        self._speak(text, voice="en")

    def _announce_daily_totals(self, prefix="Today in total"):
        self._ensure_daily_totals_reset()
        totals = self.daily_totals
        text = (
            f"{prefix} you have taken {totals['red']} red, {totals['blue']} blue, "
            f"{totals['green']} green pills, {totals['overall']} overall."
        )
        self._speak(text, voice="en")

    def _update_daily_totals(self, capture_counts):
        self._ensure_daily_totals_reset()
        for color in self.COLORS_TRACKED:
            self.daily_totals[color] += capture_counts[color]
        self.daily_totals["overall"] += capture_counts["overall"]

    def _ensure_daily_totals_reset(self):
        today = datetime.now().date()
        if today == self._totals_date:
            return
        self._totals_date = today
        for color in self.COLORS_TRACKED:
            self.daily_totals[color] = 0
        self.daily_totals["overall"] = 0
        print("ℹ️ New day detected; counters reset.")


def main():
    try:
        demo = SmartPillboxDemo()
    except Exception as exc:
        print(f"Initialization failed: {exc}")
        sys.exit(1)
    demo.run()


if __name__ == "__main__":
    main()


