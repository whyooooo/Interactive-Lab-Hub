#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal "press button → capture photo" probe inspired by smart_pillbox.

Use it to iterate quickly on camera framing without the full voice/touch/prompt flow.
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
import time
from datetime import datetime
from pathlib import Path

try:
    import cv2
except ImportError as exc:
    cv2 = None
    CV2_IMPORT_ERROR = exc
else:
    CV2_IMPORT_ERROR = None

try:
    import qwiic_button
except ImportError as exc:
    qwiic_button = None
    QWIIC_IMPORT_ERROR = exc
else:
    QWIIC_IMPORT_ERROR = None


CONFIG_PATH = Path(__file__).with_name("pillbox_config.json")
IMAGE_DIR = Path(__file__).with_name("pillbox_images")
DEBOUNCE_SECONDS = 0.35

CAMERA_DEFAULT = {
    "index": 0,
    "width": 1280,
    "height": 720,
    "fps": 30,
    "warmup_seconds": 2.0,
    "warmup_frames": 30,
}


def ensure_dependencies():
    if qwiic_button is None:
        raise ImportError(
            "未安装 sparkfun-qwiic-button（python -m pip install sparkfun-qwiic-button） "
            f"或 I2C 模块不可用: {QWIIC_IMPORT_ERROR}"
        )
    if cv2 is None:
        raise ImportError(
            "未安装 OpenCV-python（python -m pip install opencv-python）: "
            f"{CV2_IMPORT_ERROR}"
        )


def load_camera_config():
    cfg = CAMERA_DEFAULT.copy()
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as fh:
                raw = json.load(fh) or {}
                cfg.update(raw.get("camera", {}))
        except Exception as exc:
            print(f"⚠️ 无法读取 pillbox_config.json，改用默认相机设置: {exc}")
    return cfg


def init_button():
    button = qwiic_button.QwiicButton()
    if not button.begin():
        raise RuntimeError("Qwiic Button 初始化失败，请检查 I2C 接线和地址。")
    print("✓ Qwiic Button 已连接，等待按压触发拍照...")
    return button


def open_capture_device(camera_index):
    preferred_backend = getattr(cv2, "CAP_V4L2", None)
    candidates = []
    if preferred_backend is not None:
        candidates.append(("V4L2", preferred_backend))
    candidates.append(("DEFAULT", None))

    for name, backend in candidates:
        cap = (
            cv2.VideoCapture(camera_index, backend)
            if backend is not None
            else cv2.VideoCapture(camera_index)
        )
        if cap.isOpened():
            return cap, name
        cap.release()
    return None, None


def capture_photo(camera_cfg):
    cap, backend_name = open_capture_device(camera_cfg["index"])
    if cap is None:
        print("✗ 无法打开相机，请确认 /dev/video* 权限或摄像头连接。")
        return None

    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_cfg["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_cfg["height"])
        target_fps = int(camera_cfg.get("fps", 30))
        if target_fps > 0:
            cap.set(cv2.CAP_PROP_FPS, target_fps)

        warmup_seconds = float(camera_cfg.get("warmup_seconds", 0))
        warmup_frames = int(camera_cfg.get("warmup_frames", 0))
        if warmup_seconds > 0:
            print(f"  · 预热 {warmup_seconds:.1f}s（保持 pillbox 姿态不动）")
            time.sleep(max(0.0, warmup_seconds))
        for _ in range(max(0, warmup_frames)):
            cap.read()

        success, frame = cap.read()
        if not success:
            print("✗ 拍照失败，未读取到帧。")
            return None

        IMAGE_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        photo_path = IMAGE_DIR / f"button_capture_{timestamp}.jpg"
        if not cv2.imwrite(str(photo_path), frame):
            print("✗ 无法写入图片，请检查磁盘可写权限。")
            return None

        brightness = float(frame.mean())
        reported_fps = cap.get(cv2.CAP_PROP_FPS) or target_fps
        print(f"✓ 已保存 {photo_path} | 后端 {backend_name} | FPS≈{reported_fps:.1f} | 亮度均值 {brightness:.1f}")
        if brightness < 15:
            print("  ⚠️ 画面较暗，可尝试增加补光或延长预热。")
        return photo_path
    finally:
        cap.release()


def print_banner(camera_cfg):
    print("=" * 58)
    print("按钮拍照定位测试")
    print("将药盒摆到目标位置，按下按钮即可截取一张 720p 图像。")
    print(f"相机 #{camera_cfg['index']} @ {camera_cfg['width']}x{camera_cfg['height']} | 结果保存在 pillbox_images/")
    print("Ctrl+C 退出；每次按键前请等待 LED/按钮完全弹起。")
    print("=" * 58)


def loop_until_exit(button, camera_cfg):
    last_press = 0.0
    try:
        while True:
            if button.is_button_pressed():
                now = time.monotonic()
                if now - last_press < DEBOUNCE_SECONDS:
                    time.sleep(0.05)
                    continue
                while button.is_button_pressed():
                    time.sleep(0.02)
                last_press = now
                print("→ 接收到按键，开始拍照...")
                capture_photo(camera_cfg)
                print("→ 拍照完成，调整摆放后可再次按键。")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n已退出测试，谢谢使用。")


def main():
    try:
        ensure_dependencies()
        camera_cfg = load_camera_config()
        button = init_button()
    except Exception as exc:
        print(f"初始化失败: {exc}")
        sys.exit(1)

    print_banner(camera_cfg)
    loop_until_exit(button, camera_cfg)


if __name__ == "__main__":
    main()

