#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Pillbox Demo (Mock Ollama)
--------------------------------
Variant of smart_pillbox_demo.py that still captures real photos and
drives the RGB LED / touch workflow, but skips the actual Ollama call.

After each capture, the user manually inputs the detected counts for
red/blue/green pills so the rest of the workflow can continue.
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from smart_pillbox_demo import SmartPillboxDemo


class SmartPillboxDemoMockAI(SmartPillboxDemo):
    """Real capture, fake AI analysis."""

    CANCEL_WORDS = {"skip", "cancel", "exit"}

    def __init__(self):
        super().__init__()
        print("ℹ️ Mock AI mode: photos are captured, but Ollama calls are simulated.")

    def _announce_capture_counts(self, capture_counts):
        super()._announce_capture_counts(capture_counts)
        time.sleep(6.0)

    def analyze_with_ollama(self, image_path: Path):
        """Bypass the real HTTP call and ask the operator for counts."""
        print(f"📸 Pretending to send {image_path.name} to Ollama (network skipped).")
        manual_counts = self._prompt_manual_counts()
        if manual_counts is None:
            print("✗ Capture skipped: no counts were provided.")
            return None

        pills = [
            {"color": color, "count": manual_counts[color]}
            for color in self.COLORS_TRACKED
            if manual_counts[color] > 0
        ]

        result = {
            "pills": pills,
            "image_path": str(image_path),
            "model": "mock-ollama",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        print("✓ Fake Ollama response ready.")
        return result

    def _prompt_manual_counts(self) -> Optional[Dict[str, int]]:
        """Collect per-color counts from stdin; return None to skip capture."""
        print("Enter detected pill counts (Enter = 0, 'skip' to abort this capture).")
        counts: Dict[str, int] = {}
        for color in self.COLORS_TRACKED:
            while True:
                raw = input(f"  {color.upper()} pills: ").strip().lower()
                if raw in self.CANCEL_WORDS:
                    return None
                if not raw:
                    counts[color] = 0
                    break
                try:
                    value = int(raw)
                except ValueError:
                    print("Please enter an integer >= 0.")
                    continue
                if value < 0:
                    print("Negative values are not allowed.")
                    continue
                counts[color] = value
                break
        return counts


def main():
    try:
        demo = SmartPillboxDemoMockAI()
    except Exception as exc:
        print(f"Initialization failed: {exc}")
        sys.exit(1)
    demo.run()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()


