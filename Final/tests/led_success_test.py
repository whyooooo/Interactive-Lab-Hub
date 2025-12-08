#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LED + 语音通过测试脚本

用途：复现“绿色脉冲 8 秒 → 播放通过语音 → 绿灯常亮”流程。
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import subprocess
import threading
import time

try:
    from gpiozero import RGBLED
except ImportError as exc:
    print(f"未找到 gpiozero，请运行 'python3 -m pip install gpiozero'。具体错误: {exc}")
    sys.exit(1)

try:
    import pyttsx3
except ImportError as exc:
    pyttsx3 = None
    PYTTSX3_IMPORT_ERROR = exc
else:
    PYTTSX3_IMPORT_ERROR = None


LED_PINS = {"red": 21, "green": 20, "blue": 26}
LED_ACTIVE_HIGH = True
SUCCESS_TEXT = "Dose verification passed. You may take your pills now."


def send_voice_prompt(text: str, voice: str = "en", speed: str = "150"):
    """与 smart_pillbox 中的语音逻辑保持一致，优先使用 espeak。"""

    def _try_espeak() -> bool:
        try:
            subprocess.Popen(
                ["espeak", "-s", speed, "-v", voice, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"Voice prompt sent via espeak: {text}")
            return True
        except FileNotFoundError:
            print("⚠️ espeak 未安装，将尝试 pyttsx3。请运行 'sudo apt install espeak'.")
        except Exception as exc:
            print(f"⚠️ espeak 播放失败 ({exc})，尝试 pyttsx3。")
        return False

    if _try_espeak():
        return

    if _speak_with_pyttsx3(text, voice=voice, speed=speed):
        return

    print("✗ 语音提示失败：不存在可用的 TTS 后端。")


def _speak_with_pyttsx3(text: str, voice: str = "en", speed: str = "150") -> bool:
    if pyttsx3 is None:
        if 'PYTTSX3_IMPORT_ERROR' in globals() and PYTTSX3_IMPORT_ERROR:
            print(f"⚠️ pyttsx3 未安装，无法作为语音后备方案 ({PYTTSX3_IMPORT_ERROR})。")
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
            print(f"⚠️ pyttsx3 语音播放失败: {exc}")

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


def pulse_green(led: RGBLED, duration: float = 8.0, period: float = 0.4) -> None:
    """绿色脉冲闪烁以模拟处理中状态。"""
    deadline = time.monotonic() + max(0.0, duration)
    state_on = False
    while time.monotonic() < deadline:
        led.color = (1.0, 0.1, 0.0) if state_on else (0.0, 0.0, 0.0)
        state_on = not state_on
        time.sleep(max(0.05, period / 2))
    led.off()


def hold_green(led: RGBLED) -> None:
    """绿灯常亮直到用户终止。"""
    led.color = (0.0, 0.9, 0.0)
    print("→ 绿灯已常亮，按 Ctrl+C 结束测试。")
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
    print("绿色脉冲 → 语音通过 → 绿灯常亮 测试脚本")
    print("硬件: RGB LED (GPIO21/20/26)")
    print("语音: espeak / pyttsx3 (与 smart_pillbox 一致的逻辑)")
    print("=" * 52)

    try:
        print("→ 开始绿色脉冲 8 秒...")
        pulse_green(led, duration=8.0, period=0.4)
        send_voice_prompt(SUCCESS_TEXT, voice="en", speed="140")
        hold_green(led)
    finally:
        led.off()
        led.close()


if __name__ == "__main__":
    main()


