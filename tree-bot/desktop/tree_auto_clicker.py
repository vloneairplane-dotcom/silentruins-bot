#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌳 Tree Auto-Clicker — بات قطع درخت (ویندوز / مک / لینوکس)
============================================================

هر N ثانیه (پیش‌فرض: هر ۵ ثانیه) صفحه رو نگاه می‌کنه، هر «درختی» که شبیه قالبِ
ذخیره‌شده باشه رو پیدا می‌کنه و روش کلیک می‌کنه. کلیکش هم کلیک واقعیِ ویندوزه
(pyautogui) — یعنی برای هر بازی‌ای کار می‌کنه، حتی بازی‌هایی که کلیک تقلبی جاوااسکریپت
رو قبول نمی‌کنن.

سه راه استفاده:

  1) انتخاب درخت با ماوس (پیشنهاد می‌شه):
        python tree_auto_clicker.py --pick --interval 5
     بعد از اجرا، با ماوس دور یه درختِ کامل مستطیل بکش → ذخیره می‌شه تو tree.png
     و از همون لحظه ربات شروع می‌کنه.

  2) با قالب آماده:
        python tree_auto_clicker.py --template tree.png --interval 5

  3) فقط تست، بدون هیچ کلیکی (خیلی مهم قبل از شروع):
        python tree_auto_clicker.py --template tree.png --dry-run --once
     یه عکس debug/found.png می‌سازه که کادرِ درخت‌های پیدا‌شده توش مشخصه.

  4) تست روی یه اسکرین‌شات ذخیره‌شده (بدون گرفتن صفحه‌ی زنده):
        python tree_auto_clicker.py --template tree.png --screen-file shot.png --dry-run --once

کلیدهای میان‌بر (سراسری، حتی وقتی پنجره‌ی بازی فعاله):
    F8  →  توقف/ادامه
    F9  →  خروج
            
کلیدهای میان‌بر اختیاری‌اند؛ اگه کتابخونه‌ش نصب نباشه، Ctrl+C کار می‌کنه.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from matcher import (  # noqa: E402
    Match,
    find_all,
    parse_scales,
    save_debug_image,
)

# ─────────────────────‌ کنسولِ ویندوز با فارسی/ایموجی ─────────────────────
try:  # pragma: no cover
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VERSION = "1.0.0"


# ══════════════════════════════ تنظیمات ══════════════════════════════


@dataclass
class Config:
    template: str = str(HERE / "tree.png")   # عکس درخت
    interval: float = 5.0                    # هر چند ثانیه یه دور (خواسته‌ی کاربر)
    threshold: float = 0.78                  # آستانه‌ی شباهت
    scales: str = "0.9:1.15:0.125"           # مقیاس‌های جست‌وجو (تک‌عدد = 1.0)
    region: Optional[List[int]] = None       # x,y,w,h — فقط این ناحیه از صفحه اسکن شه
    gray: bool = False                       # تطبیق سیاه‌وسفید (وقتی رنگ‌ها اذیت می‌کنن)
    jitter: int = 3                          # لرزش تصادفی پیکسلی نقطه‌ی کلیک (±)
    click_hold: float = 0.03                 # مدت نگه‌داشتن دکمه‌ی ماوس
    clicks_per_tree: int = 1                 # چند بار روی هر درخت کلیک شه
    click_gap: float = 0.15                  # فاصله بین کلیک‌های پشت‌سرهم
    max_trees: int = 0                       # حداکثر درخت در هر دور (0 = بی‌نهایت)
    move_duration: float = 0.05              # سرعت حرکت ماوس
    dry_run: bool = False                    # بدون کلیک واقعی — فقط تست
    debug_dir: str = str(HERE / "debug")
    log_path: str = str(HERE / "clicks.jsonl")
    start_paused: bool = False

    @classmethod
    def load(cls, path: Optional[Path]) -> "Config":
        cfg = cls()
        if path and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        return cfg

    def save(self, path: Path) -> None:
        payload = {k: v for k, v in self.__dict__.items()}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class State:
    running: bool = True
    paused: bool = False
    cycles: int = 0
    clicks: int = 0
    started: float = field(default_factory=time.time)


# ══════════════════════════ گرفتن تصویر صفحه ══════════════════════════


class ScreenGrabber:
    """
    اسکرین‌شات از صفحه — با mss (سریع) و در نبودش با pyautogui/Pillow.
    اگه region بدی، فقط همون تیکه گرفته می‌شه (هم سریع‌تره هم دقت بالاتر).
    """

    def __init__(self, region: Optional[Sequence[int]] = None, screen_file: Optional[str] = None):
        self.region = list(region) if region else None
        self.screen_file = screen_file
        self._sct = None
        self._mode = "file" if screen_file else None
        if screen_file:
            img = cv2.imread(str(screen_file), cv2.IMREAD_COLOR)
            if img is None:
                raise SystemExit(f"❌ این فایل تصویری خونده نشد: {screen_file}")
            self._file_img = img

    # ── انتخاب بهترین روش ──
    def _ensure(self) -> None:
        if self._mode or self.screen_file:
            return
        try:
            import mss  # type: ignore

            self._sct = mss.mss()
            self._mode = "mss"
        except Exception:
            self._mode = "pyautogui"

    @property
    def mode(self) -> str:
        self._ensure()
        return self._mode or "file"

    def grab(self) -> Tuple[np.ndarray, Tuple[int, int]]:
        """برمی‌گردونه: (تصویر BGR، آفستِ گوشه‌ی ناحیه نسبت به صفحه)"""
        if self.screen_file:
            return self._file_img.copy(), (0, 0)

        self._ensure()

        if self._mode == "mss":
            mon = self._region_dict()
            shot = self._sct.grab(mon)  # type: ignore[union-attr]
            arr = np.asarray(shot, dtype=np.uint8)
            img = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            return img, (int(mon["left"]), int(mon["top"]))

        # fallback: pyautogui
        import pyautogui  # type: ignore

        left, top, width, height = self._region_tuple()
        img = np.asarray(pyautogui.screenshot(region=(left, top, width, height)), dtype=np.uint8)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR), (left, top)

    def _region_tuple(self) -> Tuple[int, int, int, int]:
        if self.region:
            return int(self.region[0]), int(self.region[1]), int(self.region[2]), int(self.region[3])
        w, h = screen_size()
        return 0, 0, w, h

    def _region_dict(self) -> dict:
        left, top, width, height = self._region_tuple()
        return {"left": left, "top": top, "width": width, "height": height}


def screen_size() -> Tuple[int, int]:
    """اندازه‌ی کل دسکتاپ (همه‌ی مانیتور‌ها)."""
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            mon = sct.monitors[0]
            return int(mon["width"]), int(mon["height"])
    except Exception:
        pass
    try:
        import pyautogui  # type: ignore

        return int(pyautogui.size()[0]), int(pyautogui.size()[1])
    except Exception:
        return 1920, 1080


# ══════════════════════════════ کلیک ══════════════════════════════


class Clicker:
    """کلیک واقعیِ سیستم با pyautogui."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._gui = None
        if cfg.dry_run:
            return
        try:
            import pyautogui  # type: ignore

            pyautogui.FAILSAFE = True  # ماوس بره گوشه‌ی بالا-چپ → توقف اضطراری
            pyautogui.PAUSE = 0
            self._gui = pyautogui
        except Exception as exc:  # pragma: no cover
            raise SystemExit(
                "❌ pyautogui نصب نیست یا کار نمی‌کنه.\n"
                "   راه‌حل:  pip install pyautogui\n"
                f"   جزئیات: {exc}"
            )

    def click(self, x: int, y: int) -> None:
        if self._gui is None:
            return
        j = max(0, int(self.cfg.jitter))
        if j:
            x += random.randint(-j, j)
            y += random.randint(-j, j)
        self._gui.moveTo(int(x), int(y), duration=float(self.cfg.move_duration))
        self._gui.mouseDown()
        time.sleep(max(0.0, float(self.cfg.click_hold)))
        self._gui.mouseUp()

    def tap_tree(self, x: int, y: int) -> int:
        """چند کلیک پشت‌سرهم روی یه درخت (برای بازی‌هایی که یه ضربه‌ای نمی‌افتن)."""
        n = max(1, int(self.cfg.clicks_per_tree))
        for i in range(n):
            self.click(x, y)
            if i < n - 1:
                time.sleep(max(0.0, float(self.cfg.click_gap)))
        return n


# ═══════════════════ انتخاب درخت با کشیدن مستطیل ═══════════════════


def pick_template_with_mouse(out_path: Path, grabber: ScreenGrabber) -> bool:
    """
    یه پنجره‌ی تمام‌صفحه از اسکرین‌شات فعلی باز می‌کنه؛ با ماوس دور یه درخت
    مستطیل بکش. همون تیکه ذخیره می‌شه.  (بدون پنجره: با Win+Shift+S خودت ببر و --template بده)
    """
    try:
        import tkinter as tk
    except Exception:
        print("⚠️ tkinter روی این سیستم نیست — خودت با Win+Shift+S از یه درخت عکس بگیر و --template بده.")
        return False

    frame, off = grabber.grab()
    h, w = frame.shape[:2]
    print("🖱  با ماوس دور یه «درخت کامل» مستطیل بکش (بدون حاشیه‌ی اضافه).  Esc = انصراف")

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.geometry(f"{w}x{h}+{off[0]}+{off[1]}")

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    try:
        from PIL import Image, ImageTk  # type: ignore

        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
    except Exception:
        # بدون Pillow: PPM base64 (tkinter خودش PPM رو می‌خونه)
        import base64

        ppm = f"P6\n{w} {h}\n255\n".encode() + rgb.tobytes()
        photo = tk.PhotoImage(data=base64.b64encode(ppm))

    canvas = tk.Canvas(root, width=w, height=h, highlightthickness=0, cursor="crosshair")
    canvas.pack()
    canvas.create_image(0, 0, anchor="nw", image=photo)

    box = {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "id": None}
    done = {"ok": False}

    def on_press(ev):
        box["x0"], box["y0"] = ev.x, ev.y
        if box["id"] is not None:
            canvas.delete(box["id"])
        box["id"] = canvas.create_rectangle(ev.x, ev.y, ev.x, ev.y, outline="#00ff88", width=2, dash=(4, 3))

    def on_drag(ev):
        if box["id"] is not None:
            canvas.coords(box["id"], box["x0"], box["y0"], ev.x, ev.y)

    def on_release(ev):
        box["x1"], box["y1"] = ev.x, ev.y
        x0, x1 = sorted((box["x0"], box["x1"]))
        y0, y1 = sorted((box["y0"], box["y1"]))
        if (x1 - x0) < 6 or (y1 - y0) < 6:
            print("⚠️ خیلی کوچیک بود — یه بار دیگه بزرگ‌تر بکش.")
            return
        crop = frame[y0:y1, x0:x1]
        ok, buf = cv2.imencode(".png", crop)
        if ok:
            out_path.write_bytes(buf.tobytes())
            done["ok"] = True
            print(f"✅ قالب درخت ذخیره شد: {out_path}   ({x1 - x0}×{y1 - y0} پیکسل)")
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", lambda e: root.destroy())
    root.focus_force()
    root.mainloop()
    return done["ok"]


def capture_screenshot(path: Path, region: Optional[Sequence[int]] = None) -> None:
    """یه اسکرین‌شات کامل ذخیره می‌کنه (برای فرستادن به من یا تست)."""
    g = ScreenGrabber(region)
    frame, _ = g.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", frame)
    if not ok:
        raise SystemExit("❌ نتونستم عکس رو انکود کنم")
    path.write_bytes(buf.tobytes())
    print(f"📸 ذخیره شد: {path}  ({frame.shape[1]}×{frame.shape[0]})")


# ══════════════════════════ کلیدهای میان‌بر ══════════════════════════


def start_hotkeys(state: State) -> Optional[object]:
    """
    F8 = توقف/ادامه، F9 = خروج.  اگه هیچ کتابخونه‌ای نبود، فقط Ctrl+C.
    اول pynput (بدون نیاز به ادمین)، بعد keyboard.
    """
    try:
        from pynput import keyboard  # type: ignore

        def on_press(key):
            if key == keyboard.Key.f8:
                state.paused = not state.paused
                print("\n⏸  توقف" if state.paused else "\n▶️  ادامه")
            elif key == keyboard.Key.f9:
                state.running = False
                print("\n👋 خروج…")
                return False

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        return listener
    except Exception:
        pass

    try:
        import keyboard  # type: ignore

        keyboard.add_hotkey("f8", lambda: _toggle(state))
        keyboard.add_hotkey("f9", lambda: setattr(state, "running", False))
        return None
    except Exception:
        return None


def _toggle(state: State) -> None:
    state.paused = not state.paused
    print("\n⏸  توقف" if state.paused else "\n▶️  ادامه")


# ══════════════════════════════ حلقه‌ی اصلی ══════════════════════════════


def load_template(path: Path, gray: bool) -> np.ndarray:
    if not path.exists():
        raise SystemExit(
            f"❌ قالب درخت پیدا نشد: {path}\n"
            "   یا با --pick درخت رو انتخاب کن، یا با Win+Shift+S از یه درخت عکس بگیر\n"
            "   و بذارش کنار همین اسکریپت به اسم tree.png"
        )
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"❌ فایل قالب خونده نشد: {path}")
    if gray:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def detect(grabber: ScreenGrabber, template: np.ndarray, cfg: Config) -> Tuple[List[Match], np.ndarray]:
    """یه اسکرین‌شات می‌گیره و همه‌ی درخت‌های روی صفحه رو پیدا می‌کنه."""
    frame, off = grabber.grab()
    matches = find_all(
        frame,
        template,
        threshold=cfg.threshold,
        scales=parse_scales(cfg.scales),
        max_results=max(1, cfg.max_trees or 25),
        nms_overlap=0.35,
        use_gray=cfg.gray,
        offset=off,
    )
    return matches, frame


def log_click(path: Path, m: Match, count: int) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "x": m.center[0], "y": m.center[1],
                     "score": round(m.score, 4), "n": count},
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass


def run(args: argparse.Namespace) -> None:
    cfg: Config = Config.load(Path(args.config)) if args.config else Config()
    cfg.template = args.template or cfg.template
    cfg.interval = args.interval if args.interval is not None else cfg.interval
    cfg.threshold = args.threshold if args.threshold is not None else cfg.threshold
    cfg.scales = args.scales if args.scales is not None else cfg.scales
    cfg.dry_run = bool(args.dry_run)
    cfg.gray = bool(args.gray)
    cfg.jitter = args.jitter if args.jitter is not None else cfg.jitter
    cfg.clicks_per_tree = args.clicks_per_tree if args.clicks_per_tree is not None else cfg.clicks_per_tree
    cfg.max_trees = args.max_trees if args.max_trees is not None else cfg.max_trees
    if args.region:
        cfg.region = [int(v) for v in args.region.split(",")]

    debug_dir = Path(cfg.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)
    template_path = Path(cfg.template)

    grabber = ScreenGrabber(cfg.region, screen_file=args.screen_file)

    # --shoot: فقط عکس بگیر و برو
    if args.shoot:
        capture_screenshot(Path(args.shoot), cfg.region)
        return

    # --pick: انتخاب درخت با ماوس
    if args.pick:
        if not pick_template_with_mouse(template_path, ScreenGrabber(cfg.region)):
            raise SystemExit("قالبی ذخیره نشد.")

    template = load_template(template_path, cfg.gray)

    state = State(paused=bool(cfg.start_paused))
    clicker = Clicker(cfg)
    hotkeys = start_hotkeys(state)

    print("=" * 64)
    print(f"🌳 Tree Auto-Clicker v{VERSION}")
    print(f"   قالب درخت : {template_path.name}  ({template.shape[1]}×{template.shape[0]})")
    print(f"   هر چند ثانیه: {cfg.interval:g} ثانیه" + ("   (هر ۵ ثانیه = پیش‌فرض)" if cfg.interval == 5 else ""))
    print(f"   آستانه شباهت : {cfg.threshold:g}")
    print(f"   حالت         : {'🧪 تست (بدون کلیک)' if cfg.dry_run else '🖱  کلیک واقعی'}")
    print(f"   روش گرفتن صفحه: {grabber.mode}")
    print(f"   میان‌بر      : {'F8 توقف/ادامه • F9 خروج' if hotkeys or _has_keyboard_fallback() else 'Ctrl+C برای خروج'}")
    print("=" * 64)

    if not cfg.dry_run:
        print("⏳ ۳ ثانیه فرصت — پنجره‌ی بازی رو بیار جلو…")
        time.sleep(3)

    last_cycle = 0.0
    try:
        while state.running:
            if state.paused:
                time.sleep(0.2)
                continue

            t0 = time.time()
            matches, frame = detect(grabber, template, cfg)
            if cfg.max_trees:
                matches = matches[: cfg.max_trees]
            detect_ms = (time.time() - t0) * 1000
            state.cycles += 1

            stamp = time.strftime("%H:%M:%S")
            if matches:
                print(f"\n[{stamp}] دور {state.cycles}: 🌳 {len(matches)} درخت پیدا شد  (اسکن {detect_ms:.0f}ms)")
                for m in matches:
                    cx, cy = m.center
                    print(f"    ▸ ({cx:>5},{cy:>5})  شباهت {m.score * 100:5.1f}%")
            else:
                print(f"\n[{stamp}] دور {state.cycles}: درختی پیدا نشد  (اسکن {detect_ms:.0f}ms)")

            if cfg.dry_run:
                out = debug_dir / "found.png"
                save_debug_image(out, frame, matches)
                print(f"    🧪 تست: کادرها تو {out} ذخیره شد — هیچ کلیکی انجام نشد")
            else:
                for i, m in enumerate(matches, 1):
                    if not state.running or state.paused:
                        break
                    cx, cy = m.center
                    n = clicker.tap_tree(cx, cy)
                    state.clicks += n
                    log_click(Path(cfg.log_path), m, state.clicks)
                    print(f"    🪓 درخت {i}/{len(matches)} کلیک شد → ({cx},{cy})   مجموع کلیک: {state.clicks}")
                    if i < len(matches):
                        time.sleep(0.05)

            if args.once:
                break

            last_cycle = time.time()
            wait_until = last_cycle + float(cfg.interval)
            while state.running and time.time() < wait_until:
                if not state.paused and sys.stdout.isatty():
                    left = wait_until - time.time()
                    print(f"\r    ⏳ کلیک بعدی تا {left:4.1f} ثانیه… ", end="", flush=True)
                time.sleep(0.1)
            if sys.stdout.isatty():
                print("\r" + " " * 40 + "\r", end="")
    except KeyboardInterrupt:
        print("\n\n⛔️ با Ctrl+C متوقف شد.")
    finally:
        print(f"\n📊 خلاصه: {state.cycles} دور • {state.clicks} کلیک • {time.time() - state.started:.0f} ثانیه فعالیت")
        if not cfg.dry_run and state.clicks:
            print(f"   لاگ کلیک‌ها: {cfg.log_path}")


def _has_keyboard_fallback() -> bool:
    try:
        import keyboard  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


# ══════════════════════════════ آرگومان‌ها ══════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tree_auto_clicker",
        description="🌳 هر ۵ ثانیه درخت‌های روی صفحه رو پیدا می‌کنه و روشون کلیک می‌کنه.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "مثال‌ها:\n"
            "  python tree_auto_clicker.py --pick                 # انتخاب درخت با ماوس، بعد شروع\n"
            "  python tree_auto_clicker.py --template tree.png    # با قالب آماده، هر ۵ ثانیه\n"
            "  python tree_auto_clicker.py --dry-run --once       # فقط تست، بدون کلیک\n"
            "  python tree_auto_clicker.py --shoot shot.png       # گرفتن اسکرین‌شات\n"
        ),
    )
    p.add_argument("--pick", action="store_true", help="درخت رو با کشیدن مستطیل روی صفحه انتخاب کن")
    p.add_argument("--template", "-t", default=None, help="مسیر عکس درخت (پیش‌فرض: tree.png)")
    p.add_argument("--interval", "-i", type=float, default=None, help="هر چند ثانیه یه دور (پیش‌فرض ۵)")
    p.add_argument("--threshold", type=float, default=None, help="آستانه شباهت 0..1 (پیش‌فرض 0.78)")
    p.add_argument("--scales", default=None, help="مقیاس‌های جست‌وجو، مثل 0.8:1.25:0.15 یا 1.0")
    p.add_argument("--region", default=None, help="فقط این ناحیه اسکن شه: x,y,w,h")
    p.add_argument("--gray", action="store_true", help="تطبیق سیاه‌وسفید (مقاوم‌تر به تغییر رنگ)")
    p.add_argument("--jitter", type=int, default=None, help="لرزش تصادفی نقطه کلیک (پیکسل)")
    p.add_argument("--clicks-per-tree", type=int, default=None, help="چند کلیک روی هر درخت")
    p.add_argument("--max-trees", type=int, default=None, help="حداکثر چند درخت در هر دور")
    p.add_argument("--dry-run", action="store_true", help="تست بدون کلیک واقعی")
    p.add_argument("--once", action="store_true", help="فقط یه دور، بعد خروج")
    p.add_argument("--screen-file", default=None, help="به‌جای صفحه‌ی زنده، از این عکس بخون (برای تست)")
    p.add_argument("--shoot", default=None, help="یه اسکرین‌شات بگیر و ذخیره کن، بعد برو")
    p.add_argument("--config", default=None, help="فایل تنظیمات JSON")
    p.add_argument("--save-config", default=None, help="تنظیمات فعلی رو تو این فایل ذخیره کن")
    p.add_argument("--version", action="version", version=f"tree_auto_clicker {VERSION}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.save_config:
        cfg = Config.load(Path(args.config)) if args.config else Config()
        if args.template:
            cfg.template = args.template
        if args.interval is not None:
            cfg.interval = args.interval
        if args.threshold is not None:
            cfg.threshold = args.threshold
        cfg.save(Path(args.save_config))
        print(f"✅ تنظیمات ذخیره شد: {args.save_config}")
        return 0

    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
