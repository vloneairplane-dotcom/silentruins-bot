#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 تست خودکار موتور تشخیص درخت
===============================

یه «صحنه‌ی بازی» مصنوعی می‌سازه (پس‌زمینه + چند درخت با سایز/جای تصادفی + چند
سنگ و بوته که نباید با درخت اشتباه گرفته بشن)، بعد موتور رو امتحان می‌کنه:

    python selftest.py            # تست کامل
    python selftest.py --save     # علاوه بر تست، tree.png و screen.png هم می‌سازه

اگه همه‌ی تست‌ها PASS بشن، یعنی هم قالب‌خوانی، هم جست‌وجوی چندمقیاسه، هم NMS
درست کار می‌کنن و می‌شه به ربات برای کلیک کردن اعتماد کرد.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from matcher import draw_matches, find_all, find_best, iou, parse_scales  # noqa: E402

RNG = np.random.default_rng(1403)
TREE_W, TREE_H = 72, 96


# ─────────────────────── ساخت صحنه‌ی آزمایشی ───────────────────────


def make_tree_sprite(w: int = TREE_W, h: int = TREE_H) -> np.ndarray:
    """یه درخت کارتونی با بافت: تنه‌ی قهوه‌ای + سه لایه تاج سبز + نویز."""
    img = np.zeros((h, w, 3), np.uint8)

    # تنه
    trunk_x0, trunk_x1 = int(w * 0.42), int(w * 0.58)
    cv2.rectangle(img, (trunk_x0, int(h * 0.60)), (trunk_x1, h - 1), (60, 82, 120), -1)  # BGR قهوه‌ای
    cv2.line(img, (trunk_x0, int(h * 0.72)), (trunk_x0 + 3, h - 6), (45, 62, 95), 1)

    # تاج: سه مثلث روی هم
    layers = [(0.62, 0.30), (0.42, 0.18), (0.24, 0.06)]
    for base_y, top_y in layers:
        pts = np.array(
            [
                [int(w * 0.50), int(h * top_y)],
                [int(w * 0.06), int(h * base_y)],
                [int(w * 0.94), int(h * base_y)],
            ],
            np.int32,
        )
        cv2.fillPoly(img, [pts], (54, 132, 66))  # سبز
        cv2.polylines(img, [pts], True, (34, 92, 44), 2)

    # بافت برگ: چند لکه‌ی روشن/تیره
    mask = (img[:, :, 1] > 60).astype(np.uint8)
    for _ in range(160):
        y, x = int(RNG.integers(0, h)), int(RNG.integers(0, w))
        if not mask[y, x]:
            continue
        delta = int(RNG.integers(-26, 27))
        img[y, x] = np.clip(img[y, x].astype(int) + delta, 0, 255).astype(np.uint8)

    # یه ذره نویز، مثل اسپرایت‌های واقعی
    noise = RNG.integers(-4, 5, img.shape, dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def make_background(w: int = 1600, h: int = 900) -> np.ndarray:
    """آسمون گرادیانی + چمن + ابر و سنگ — تا تطبیق سخت‌تر بشه."""
    bg = np.zeros((h, w, 3), np.uint8)
    for y in range(h):
        t = y / h
        bg[y, :] = (
            int(210 * (1 - t) + 95 * t),   # B
            int(160 * (1 - t) + 140 * t),  # G
            int(120 * (1 - t) + 70 * t),   # R
        )
    grass_y = int(h * 0.62)
    cv2.rectangle(bg, (0, grass_y), (w, h), (70, 120, 60), -1)
    for _ in range(600):
        y, x = int(RNG.integers(grass_y, h)), int(RNG.integers(0, w))
        bg[y, x] = np.clip(bg[y, x].astype(int) + int(RNG.integers(-18, 19)), 0, 255).astype(np.uint8)

    for _ in range(7):  # ابر
        cx, cy = int(RNG.integers(0, w)), int(RNG.integers(20, grass_y // 2))
        cv2.ellipse(bg, (cx, cy), (int(RNG.integers(60, 130)), int(RNG.integers(18, 34))), 0, 0, 360,
                    (235, 238, 240), -1)
    for _ in range(14):  # سنگ (نباید درخت تشخیص داده شه)
        cx, cy = int(RNG.integers(0, w)), int(RNG.integers(grass_y, h))
        axes = (int(RNG.integers(14, 34)), int(RNG.integers(10, 22)))
        grey = int(RNG.integers(85, 150))
        cv2.ellipse(bg, (cx, cy), axes, int(RNG.integers(0, 180)), 0, 360, (grey, grey + 6, grey + 10), -1)
    return bg


def make_scene(count: int = 5, scales: Tuple[float, ...] = (0.9, 1.0, 1.125)):
    """یه صحنه با چند درخت در سایزهای مختلف + لیست جای دقیق‌شون."""
    sprite = make_tree_sprite()
    screen = make_background()
    h, w = screen.shape[:2]
    placed: List[Tuple[int, int, int, int, float]] = []

    for _ in range(count):
        scale = float(RNG.choice(list(scales)))
        # مثل خود موتور: round (نه int) — وگرنه لبه‌ها یک پیکسل می‌خوره و تست بی‌انصاف می‌شه
        tw, th = int(round(TREE_W * scale)), int(round(TREE_H * scale))
        # همون درون‌یابی‌ای که موتور تشخیص استفاده می‌کنه (وگرنه تست بی‌انصاف می‌شه)
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        tree = cv2.resize(sprite, (tw, th), interpolation=interp)
        for _try in range(60):
            x = int(RNG.integers(0, w - tw))
            y = int(RNG.integers(int(h * 0.30), h - th))
            if all(abs(x - px) > tw + 10 or abs(y - py) > th + 10 for px, py, _, _, _ in placed):
                screen[y:y + th, x:x + tw] = tree
                placed.append((x, y, tw, th, scale))
                break
    return screen, sprite, placed


# ─────────────────────────── تست‌ها ───────────────────────────


class Results:
    def __init__(self) -> None:
        self.ok = 0
        self.fail = 0

    def check(self, name: str, cond: bool, extra: str = "") -> None:
        if cond:
            self.ok += 1
            print(f"  ✅ PASS  {name}")
        else:
            self.fail += 1
            print(f"  ❌ FAIL  {name}  {extra}")


def test_parse_scales(r: Results) -> None:
    print("\n🧩 تست parse_scales")
    r.check("تک‌عدد", parse_scales("1.0") == [1.0])
    r.check("لیست", parse_scales("0.9,1.0,1.1") == [0.9, 1.0, 1.1])
    r.check("بازه", parse_scales("0.8:1.2:0.2") == [0.8, 1.0, 1.2], str(parse_scales("0.8:1.2:0.2")))
    r.check("خالی→1.0", parse_scales(None) == [1.0])


def test_iou(r: Results) -> None:
    print("\n🧩 تست iou (هم‌پوشانی)")
    from matcher import Match

    a = Match(0, 0, 10, 10, 0.9)
    r.check("کاملاً روی هم = 1", abs(iou(a, Match(0, 0, 10, 10, 0.8)) - 1.0) < 1e-6)
    r.check("بی‌ربط = 0", iou(a, Match(50, 50, 10, 10, 0.8)) == 0.0)
    r.check("نصفه = ~0.33", abs(iou(a, Match(5, 0, 10, 10, 0.8)) - 1 / 3) < 0.02)


def test_detection(r: Results, save: bool) -> None:
    print("\n🌳 تست تشخیص درخت روی صحنه‌ی مصنوعی")
    screen, sprite, placed = make_scene(count=5, scales=(0.9, 1.025, 1.15))
    debug_dir = HERE / "debug"
    debug_dir.mkdir(exist_ok=True)

    if save:
        cv2.imwrite(str(HERE / "tree.png"), sprite)
        cv2.imwrite(str(HERE / "screen.png"), screen)
        print(f"  💾 tree.png و screen.png ساخته شد ({TREE_W}×{TREE_H})")

    found = find_all(screen, sprite, threshold=0.80, scales=parse_scales("0.9:1.15:0.125"))
    print(f"  🔎 {len(placed)} درخت کاشته شد • {len(found)} تطابق پیدا شد")
    for m in sorted(found, key=lambda m: (m.x, m.y)):
        print(f"      ({m.center[0]:>5},{m.center[1]:>5})  {m.score * 100:5.1f}%  x{m.scale:g}")

    # ۱) تعداد
    r.check(f"تعداد درخت‌ها درست ({len(placed)})", len(found) == len(placed),
            f"(شد {len(found)})")

    # ۲) هر درخت واقعی یه تطابق نزدیک داره
    missed = []
    for (x, y, tw, th, _s) in placed:
        cx, cy = x + tw // 2, y + th // 2
        near = [m for m in found if abs(m.center[0] - cx) <= 5 and abs(m.center[1] - cy) <= 5]
        if not near:
            missed.append((cx, cy))
    r.check("همه‌ی درخت‌ها پیدا شدن (±۵ پیکسل)", not missed, f"گم‌شده‌ها: {missed}")

    # ۳) هیچ تطابق اضافی/غلطی نیست
    false_pos = []
    for m in found:
        cx, cy = m.center
        if not any(
            abs(cx - (x + tw // 2)) <= 8 and abs(cy - (y + th // 2)) <= 8
            for (x, y, tw, th, _s) in placed
        ):
            false_pos.append((cx, cy, round(m.score, 3)))
    r.check("هیچ درخت اشتباهی تشخیص داده نشد", not false_pos, f"اضافی‌ها: {false_pos}")

    # ۴) کیفیت تطبیق
    r.check("کیفیت تطبیق‌ها ≥ ۹۵٪", all(m.score >= 0.95 for m in found),
            f"کمترین: {min((m.score for m in found), default=0):.3f}")

    # ۵) مقیاس‌های خارج از شبکه‌ی جست‌وجو هم پیدا شن (تست حافظه‌ی اغماض)
    print("\n  🎚 صحنه‌ی دوم: درخت‌هایی با سایز تصادفیِ خارج از شبکه")
    screen2, sprite2, placed2 = make_scene(count=6, scales=(0.94, 1.03, 1.12))
    found2 = find_all(screen2, sprite2, threshold=0.70, scales=parse_scales("0.85:1.2:0.05"))
    hit = 0
    for (x, y, tw, th, _s) in placed2:
        cx, cy = x + tw // 2, y + th // 2
        if any(abs(m.center[0] - cx) <= 6 and abs(m.center[1] - cy) <= 6 for m in found2):
            hit += 1
    print(f"      {hit}/{len(placed2)} درخت با سایز غیردقیق پیدا شد ({len(found2)} تطابق)")
    r.check("روی سایزهای غیردقیق، حداقل ۸۰٪ یادآوری داره", hit >= int(0.8 * len(placed2)),
            f"{hit} از {len(placed2)}")

    # ۶) حالت خاکستری هم کار کنه
    gray_found = find_all(screen, sprite, threshold=0.80, scales=[1.0], use_gray=True)
    r.check("حالت سیاه‌وسفید هم درخت پیدا می‌کنه", len(gray_found) >= 1, f"(شد {len(gray_found)})")

    # ۷) find_best
    best = find_best(screen, sprite, threshold=0.80, scales=["0.9:1.15:0.125"])
    r.check("find_best بهترین رو می‌ده", best is not None and best.score >= 0.9)

    # ۸) آستانه‌ی بالا → درخت‌های با سایز متفاوت کمتر پیدا می‌شن (منطق آستانه سالمه)
    strict = find_all(screen, sprite, threshold=0.995, scales=[1.0])
    r.check("آستانه‌ی سخت‌گیرانه تعداد رو کم می‌کنه", len(strict) <= len(found))

    # ۹) عکس دیباگ
    out = debug_dir / "selftest_found.png"
    cv2.imwrite(str(out), draw_matches(screen, found))
    r.check("عکس دیباگ ساخته شد", out.exists() and out.stat().st_size > 1000, str(out))

    # ۱۰) بدون درخت واقعی → تشخیص اشتباه نکن
    empty = make_background()
    none_found = find_all(empty, sprite, threshold=0.80, scales=parse_scales("0.9:1.15:0.125"))
    r.check("روی صفحه‌ی بدون درخت، تشخیص اشتباه نمی‌ده", len(none_found) == 0,
            f"(شد {len(none_found)})")

    return screen, sprite


def test_cli_dry_run(r: Results, screen: np.ndarray, sprite: np.ndarray) -> None:
    """تست کامل: خود اسکریپت ربات با --screen-file --dry-run --once اجرا شه."""
    print("\n🤖 تست اجرای خود ربات (بدون هیچ کلیکی)")
    tmp = HERE / "debug"
    tmp.mkdir(exist_ok=True)
    (tmp / "_t_screen.png").write_bytes(cv2.imencode(".png", screen)[1].tobytes())
    (tmp / "_t_tree.png").write_bytes(cv2.imencode(".png", sprite)[1].tobytes())

    cmd = [
        sys.executable, str(HERE / "tree_auto_clicker.py"),
        "--template", str(tmp / "_t_tree.png"),
        "--screen-file", str(tmp / "_t_screen.png"),
        "--dry-run", "--once", "--threshold", "0.8",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    r.check("ربات بدون خطا اجرا شد", proc.returncode == 0, f"کد {proc.returncode}\n{out[-1500:]}")
    r.check("درخت‌ها رو گزارش کرد", "درخت پیدا شد" in out, out[-600:])
    r.check("تأیید کرد که کلیکی نکرده", "هیچ کلیکی انجام نشد" in out)
    r.check("فایل debug/found.png ساخته شد", (tmp / "found.png").exists())
    print("\n  ── خروجی ربات ──")
    for line in out.strip().splitlines()[-12:]:
        print("   " + line)

    # تمیزکاری
    for f in ("_t_screen.png", "_t_tree.png"):
        p = tmp / f
        if p.exists():
            p.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description="تست خودکار موتور تشخیص درخت")
    ap.add_argument("--save", action="store_true", help="tree.png و screen.png نمونه رو هم ذخیره کن")
    ap.add_argument("--no-cli", action="store_true", help="تست اجرای ربات رو انجام نده")
    args = ap.parse_args()

    print("=" * 60)
    print("🧪 تست Tree Auto-Clicker")
    print("=" * 60)

    r = Results()
    test_parse_scales(r)
    test_iou(r)
    screen, sprite = test_detection(r, args.save)
    if not args.no_cli:
        test_cli_dry_run(r, screen, sprite)

    print("\n" + "=" * 60)
    total = r.ok + r.fail
    if r.fail == 0:
        print(f"🎉 همه‌ی {total} تست PASS شد — موتور تشخیص سالمه.")
        print("   قدم بعدی: python tree_auto_clicker.py --pick   (درخت رو با ماوس انتخاب کن)")
        return 0
    print(f"⚠️  {r.fail} از {total} تست FAIL شد.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
