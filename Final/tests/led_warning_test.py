#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LED + 语音预警测试脚本

用途：复现“黄色闪烁 10 秒 → 播放警示语音 → 红灯常亮”流程。
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import subprocess
import time

try:
    from gpiozero import RGBLED
except ImportError as exc:
    print(f"未找到 gpiozero，请运行 'python3 -m pip install gpiozero'。具体错误: {exc}")
    sys.exit(1)


LED_PINS = {"red": 21, "green": 20, "blue": 26}
LED_ACTIVE_HIGH = True
WARNING_TEXT = "pill color or quantity is incorrect. Please verify before taking any dose."


def speak_warning(text: str = WARNING_TEXT, voice: str = "en", speed: str = "150") -> None:
    """调用 espeak 播放提示，若缺失则仅打印文字。"""
    try:
        subprocess.run(
            ["espeak", "-s", speed, "-v", voice, text],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"✓ 语音提示已触发: {text}")
    except FileNotFoundError:
        print("⚠️ 未安装 espeak，已改为控制台提示。请运行 'sudo apt install espeak'.")
    except Exception as exc:
        print(f"⚠️ 语音播放失败: {exc}")


def blink_yellow(led: RGBLED, duration: float = 10.0, period: float = 0.5) -> None:
    """周期性闪烁黄色 (R+G)，便于在 pillbox 上模拟提示。"""
    deadline = time.monotonic() + max(0.0, duration)
    state_on = False
    while time.monotonic() < deadline:
        led.color = (1.0, 0.1, 0.0) if state_on else (0.0, 0.0, 0.0)
        state_on = not state_on
        time.sleep(max(0.05, period / 2))
    led.off()


def hold_red(led: RGBLED) -> None:
    """红灯常亮直到手动退出。"""
    led.color = (1.0, 0.0, 0.0)
    print("→ 红灯已常亮，按 Ctrl+C 结束测试。")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n已收到中断，关闭 LED。")


def main():
    led = RGBLED(
        red=LED_PINS["red"],
        green=LED_PINS["green"],
        blue=LED_PINS["blue"],
        active_high=LED_ACTIVE_HIGH,
        pwm=True,
    )
    print("=" * 52)
    print("黄色闪烁 → 语音 → 红灯常亮 测试脚本")
    print("硬件: RGB LED (GPIO21/20/26)")
    print("语音: espeak (若未安装则仅输出文字)")
    print("=" * 52)

    try:
        print("→ 开始黄色闪烁 10 秒...")
        blink_yellow(led, duration=10.0, period=0.5)
        speak_warning()
        hold_red(led)
    finally:
        led.off()
        led.close()


if __name__ == "__main__":
    main()

