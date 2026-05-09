#!/usr/bin/env python3
"""
微信红包自动抢脚本 (macOS M4)
原理：定时截图 → OpenCV 模板匹配识别红包/开按钮 → PyAutoGUI 自动点击

依赖安装:
  pip3 install pyautogui opencv-python Pillow mss

使用前准备:
  1. 运行 python3 wechat_red_packet.py --capture 截取红包模板图片
  2. 确保微信窗口可见且在目标聊天框中
  3. 运行 python3 wechat_red_packet.py 开始监听
"""

import sys
import time
import os
import argparse
import threading
from datetime import datetime

try:
    import cv2
    import numpy as np
    import pyautogui
    import mss
    from PIL import Image, ImageGrab
except ImportError as e:
    print(f"[错误] 缺少依赖: {e}")
    print("请运行: pip3 install pyautogui opencv-python Pillow mss")
    sys.exit(1)

# ─────────────────────────────────────────────
# 配置区（可按需修改）
# ─────────────────────────────────────────────
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")  # 模板图片目录

# 模板文件路径
TEMPLATE_RED_PACKET = os.path.join(ASSETS_DIR, "red_packet.png")   # 红包气泡截图
TEMPLATE_KAI_BTN    = os.path.join(ASSETS_DIR, "kai_btn.png")   # "开" 按钮截图

SCAN_INTERVAL     = 0.01    # 扫描间隔（秒）
MATCH_THRESHOLD   = 0.75   # 模板匹配置信度阈值
CLICK_DELAY       = 0.03   # 点击后等待时间（秒）
KAI_WAIT          = 0.7    # 点击红包后等待"开"按钮出现的时间（秒）

# 监控区域（None = 全屏，也可指定 {"top":y, "left":x, "width":w, "height":h}）
MONITOR_REGION = None

# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


def ensure_assets_dir():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    log(f"模板目录: {ASSETS_DIR}")


def capture_screen(region=None) -> np.ndarray:
    """截取屏幕，返回 BGR numpy 数组（OpenCV 格式）"""
    with mss.mss() as sct:
        if region:
            monitor = region
        else:
            monitor = sct.monitors[1]  # 主显示器
        raw = sct.grab(monitor)
        img = np.array(raw)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def load_template(path: str) -> np.ndarray | None:
    if not os.path.exists(path):
        return None
    tmpl = cv2.imread(path, cv2.IMREAD_COLOR)
    return tmpl


def find_template(screen: np.ndarray, template: np.ndarray, threshold=MATCH_THRESHOLD):
    """
    在 screen 中寻找 template，返回最佳匹配中心坐标 (x, y) 或 None。
    支持多尺度匹配，适应 Retina / 不同 DPI。
    """
    best_val = 0
    best_loc = None
    best_scale = 1.0

    h, w = template.shape[:2]

    for scale in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]:
        resized = cv2.resize(template, (int(w * scale), int(h * scale)))
        if resized.shape[0] > screen.shape[0] or resized.shape[1] > screen.shape[1]:
            continue
        result = cv2.matchTemplate(screen, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_scale = scale

    if best_val >= threshold and best_loc is not None:
        rh, rw = int(h * best_scale), int(w * best_scale)
        cx = best_loc[0] + rw // 2
        cy = best_loc[1] + rh // 2
        return (cx, cy, best_val)
    return None


def click_at(x: int, y: int, double=False):
    """模拟鼠标点击，加入微小随机偏移模拟人类行为"""
    import random
    ox = random.randint(-3, 3)
    oy = random.randint(-3, 3)
    pyautogui.moveTo(x + ox, y + oy, duration=0.05)
    if double:
        pyautogui.doubleClick()
    else:
        pyautogui.click()


# ─────────────────────────────────────────────
# 模板截取工具（--capture 模式）
# ─────────────────────────────────────────────

def capture_template_interactive():
    """交互式截取模板图片"""
    ensure_assets_dir()
    print("\n=== 模板截取工具 ===")
    print("请按照提示操作，脚本将引导你截取所需模板图片\n")

    templates = [
        ("red_packet",  TEMPLATE_RED_PACKET,  "红包气泡（聊天列表中的红包消息）"),
        ("kai_btn",  TEMPLATE_KAI_BTN,  '"开" 按钮（点击红包后弹出的领取按钮）'),
    ]

    for name, path, desc in templates:
        if os.path.exists(path):
            ans = input(f"[{name}] 已存在，是否重新截取? (y/N): ").strip().lower()
            if ans != 'y':
                continue

        print(f"\n→ 准备截取: {desc}")
        print("  请在微信中找到对应元素，确保它在屏幕上可见")
        input("  按 Enter 开始截取（3 秒后截屏）...")
        print("  3...")
        time.sleep(1)
        print("  2...")
        time.sleep(1)
        print("  1...")
        time.sleep(1)

        # 截全屏让用户框选
        screen = ImageGrab.grab()
        tmp_path = os.path.join(ASSETS_DIR, f"_tmp_{name}.png")
        screen.save(tmp_path)

        print(f"  截图已保存至 {tmp_path}")
        print(f"  请用 Preview / 截图工具裁剪出 [{desc}] 区域")
        print(f"  并保存为: {path}")
        input("  完成后按 Enter 继续...\n")

        if os.path.exists(path):
            log(f"✅ {name} 模板已就绪: {path}")
        else:
            log(f"⚠️  {path} 不存在，跳过")

    print("\n模板准备完成！")
    print("运行 python3 wechat_red_packet.py 开始监听红包")


# ─────────────────────────────────────────────
# 主监听循环
# ─────────────────────────────────────────────

class RedPacketGrabber:
    def __init__(self):
        self.tmpl_red_packet = load_template(TEMPLATE_RED_PACKET)
        self.tmpl_kai        = load_template(TEMPLATE_KAI_BTN)
        self.last_grab_time = 0
        self.grab_count = 0
        self._running = True

    def check_templates(self):
        if self.tmpl_red_packet is None:
            log(f"❌ 红包模板不存在: {TEMPLATE_RED_PACKET}")
            log("   请先运行: python3 wechat_red_packet.py --capture")
            return False
        if self.tmpl_kai is None:
            log(f"❌ '开'按钮模板不存在: {TEMPLATE_KAI_BTN}")
            log("   请先运行: python3 wechat_red_packet.py --capture")
            return False
        log("✅ 模板加载成功")
        return True

    def try_grab(self, screen: np.ndarray) -> bool:
        """尝试识别并点击红包，返回是否成功抢了一个"""

        # 1. 寻找红包气泡
        result = find_template(screen, self.tmpl_red_packet)
        if result is None:
            return False

        hb_x, hb_y, conf = result
        log(f"🧧 发现红包！位置({hb_x}, {hb_y}) 置信度={conf:.3f}")

        # 2. 点击红包气泡
        click_at(hb_x, hb_y)
        log(f"   → 点击红包，等待 {KAI_WAIT}s ...")
        time.sleep(KAI_WAIT)

        # 3. 截新屏幕，寻找"开"按钮
        screen2 = capture_screen(MONITOR_REGION)
        kai_result = find_template(screen2, self.tmpl_kai)

        if kai_result is None:
            log("   → 未找到'开'按钮（可能已超时或非红包消息）")
            pyautogui.press('escape')
            return False

        kai_x, kai_y, kai_conf = kai_result
        log(f"   → 找到'开'按钮 ({kai_x}, {kai_y})，置信度={kai_conf:.3f}，点击！")
        click_at(kai_x, kai_y)
        time.sleep(CLICK_DELAY)

        self.grab_count += 1
        log(f"🎉 成功抢到红包！退出。")
        return True

    def run(self):
        if not self.check_templates():
            return

        log(f"🚀 开始监听红包（扫描间隔={SCAN_INTERVAL}s，阈值={MATCH_THRESHOLD}）")
        log("   按 Ctrl+C 停止")

        try:
            while self._running:
                screen = capture_screen(MONITOR_REGION)
                if self.try_grab(screen):
                    log("✅ 任务完成，退出程序")
                    return
                time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            log("\n⏹  已手动停止")

    def stop(self):
        self._running = False


# ─────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────

def main():
    global MATCH_THRESHOLD, SCAN_INTERVAL  # 必须在任何引用前声明

    parser = argparse.ArgumentParser(description="微信红包自动抢脚本 (macOS M4)")
    parser.add_argument("--capture", action="store_true",
                        help="进入模板截取模式，引导截取红包/开按钮图片")
    parser.add_argument("--threshold", type=float, default=MATCH_THRESHOLD,
                        help=f"匹配置信度阈值（默认 {MATCH_THRESHOLD}）")
    parser.add_argument("--interval", type=float, default=SCAN_INTERVAL,
                        help=f"扫描间隔秒数（默认 {SCAN_INTERVAL}）")
    args = parser.parse_args()

    MATCH_THRESHOLD = args.threshold
    SCAN_INTERVAL = args.interval

    if args.capture:
        capture_template_interactive()
    else:
        grabber = RedPacketGrabber()
        grabber.run()


if __name__ == "__main__":
    main()
