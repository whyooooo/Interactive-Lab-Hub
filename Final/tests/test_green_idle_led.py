#!/usr/bin/env python3
"""
Scenario: Drive the RGB LED exactly as smart_pillbox does and keep it solid green.

Hardware required:
- Same RGB LED wiring as the main project (GPIO 21/20/26 by default)
- gpiozero installed.

Steps:
1. Run this script on the Pi with the LED connected.
2. It instantiates smart_pillbox.LEDAnimator (same pins, same PWM config).
3. The LED blinks green briefly (idle), then stays solid green (success mode) until Ctrl+C.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smart_pillbox import LEDAnimator


def main():
    try:
        led = LEDAnimator()
    except Exception as exc:
        print(f"✗ Failed to initialize LEDAnimator: {exc}")
        print("Ensure gpiozero is installed and RGB LED wiring matches smart_pillbox.py.")
        sys.exit(1)

    print("✓ LEDAnimator ready. Green blink (idle) for 3 seconds...")
    led.set_mode("idle")
    time.sleep(3)

    print("Switching to solid green (success mode). Press Ctrl+C to stop.")
    led.set_mode("success")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping LED test.")
    finally:
        led.shutdown()
        print("LED turned off and GPIO released.")


if __name__ == "__main__":
    main()


