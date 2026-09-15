# -*- coding: utf-8 -*-
"""
موتور تشخیص «درخت» روی تصویر — Template Matching
=================================================

این فایل هیچ وابستگی‌ای به ماوس/کیبورد/نمایشگر نداره؛ فقط یه تصویر می‌گیره
(اسکرین‌شات صفحه) و یه قالب درخت (همون عکسی که کاربر با --pick بریده)،
و مختصات همه‌ی درخت‌های موجود روی صفحه رو برمی‌گردونه.

    ┌───────────── اسکرین‌شات صفحه ─────────────┐
    │   🌳        🌳            🌳              │   ← قالب درخت (tree.png)
    │                                           │      اینجا دنبالش می‌گردیم
    └───────────────────────────────────────────┘

قابلیت‌ها:
  • چند مقیاس (اگه بازی زوم/سایز اسپرایت‌ها رو عوض کنه بازم پیدا می‌کنه)
  • NMS — جلوگیری از این‌که یه درخت چند بار شمرده بشه
  • مقاوم به NaN (اگه پیکسل‌های قالب یکنواخت باشن)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple, Union

import cv2
import numpy as np


# ───────────────────────────── داده ─────────────────────────────


@dataclass(frozen=True)
class Match:
    """یک درختِ پیدا‌شده روی تصویر."""

    x: int
    y: int
    w: int
    h: int
    score: float
    scale: float = 1.0

    @property
    def center(self) -> Tuple[int, int]:
        """نقطه‌ای که باید روش کلیک بشه."""
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def box(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    def as_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "score": round(float(self.score), 4),
            "scale": round(float(self.scale), 3),
            "center": {"x": self.center[0], "y": self.center[1]},
        }

    def __str__(self) -> str:  # pragma: no cover
        return f"({self.center[0]},{self.center[1]}) {self.score * 100:.1f}% x{self.scale:g}"


# ───────────────────────────── ابزارها ─────────────────────────────


def parse_scales(spec: Union[str, Sequence[float], None]) -> List[float]:
    """
    مقیاس‌ها رو از رشته‌ی کاربر می‌سازه.

        "1.0"            → [1.0]
        "0.9,1.0,1.1"    → [0.9, 1.0, 1.1]
        "0.8:1.25:0.15"  → [0.8, 0.95, 1.1, 1.25]   (از:تا:گام)
    """
    if spec is None:
        return [1.0]
    if isinstance(spec, (list, tuple)):
        # هر عضو می‌تونه عدد باشه یا خودش یه بازه ("0.9:1.15:0.1")
        out: List[float] = []
        for item in spec:
            out.extend(parse_scales(item))
        return out or [1.0]

    spec = str(spec).strip()
    if not spec:
        return [1.0]

    if ":" in spec:
        parts = [float(p) for p in spec.split(":")]
        if len(parts) != 3:
            raise ValueError("فرمت مقیاس باید مثل 0.8:1.25:0.15 باشه (از:تا:گام)")
        start, end, step = parts
        if step <= 0 or end < start:
            raise ValueError("بازه‌ی مقیاس نامعتبره")
        out, cur = [], start
        while cur <= end + 1e-9:
            out.append(round(cur, 4))
            cur += step
        if end not in out:
            out.append(round(end, 4))
        return out

    return [float(p) for p in spec.replace(" ", "").split(",") if p] or [1.0]


def iou(a: Match, b: Match) -> float:
    """نسبت هم‌پوشانی دو کادر (0 = بی‌ربط، 1 = کاملاً روی هم)."""
    ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
    bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = a.w * a.h + b.w * b.h - inter
    return float(inter) / float(union) if union else 0.0


def _nms(matches: List[Match], overlap: float, max_results: int) -> List[Match]:
    """Non-Maximum Suppression: از هر خوشه‌ی روی‌هم‌افتاده فقط بهترین می‌مونه."""
    kept: List[Match] = []
    for m in sorted(matches, key=lambda m: m.score, reverse=True):
        if all(iou(m, k) <= overlap for k in kept):
            kept.append(m)
        if len(kept) >= max_results:
            break
    return kept


def _match_method(template: np.ndarray) -> int:
    """قالبِ یکنواخت (مثل یه مربع تک‌رنگ) با CCOEFF نتیجه‌ی NaN می‌ده → عوضش می‌کنیم."""
    if template.size == 0:
        return cv2.TM_CCOEFF_NORMED
    if float(template.std()) < 1.0:
        return cv2.TM_CCORR_NORMED
    return cv2.TM_CCOEFF_NORMED


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ───────────────────────────── تشخیص ─────────────────────────────


def find_all(
    screen: np.ndarray,
    template: np.ndarray,
    threshold: float = 0.80,
    scales: Union[str, Sequence[float], None] = (1.0,),
    max_results: int = 25,
    nms_overlap: float = 0.35,
    use_gray: bool = False,
    offset: Tuple[int, int] = (0, 0),
) -> List[Match]:
    """
    همه‌ی جاهایی که شبیه «قالب درخت» هستن رو برمی‌گردونه.

    screen     : تصویر صفحه (BGR یا خاکستری)
    template   : تصویر درخت (BGR یا خاکستری)
    threshold  : آستانه‌ی شباهت 0..1 (پیش‌فرض 0.80 — کمتر = حساس‌تر)
    scales     : مقیاس‌هایی که امتحان می‌شن (ببین parse_scales)
    offset     : اگه فقط یه تکه از صفحه رو فرستادی، مختصاتش نسبت به کل صفحه ست شه
    """
    if screen is None or template is None:
        return []
    if screen.size == 0 or template.size == 0:
        return []

    src = screen
    tpl_src = template

    if use_gray or screen.ndim == 2 or template.ndim == 2:
        src = to_gray(screen)
        tpl_src = to_gray(template)

    sh, sw = src.shape[:2]
    th0, tw0 = tpl_src.shape[:2]
    if th0 < 4 or tw0 < 4:
        raise ValueError("قالب خیلی کوچیکه — حداقل ۴×۴ پیکسل لازمه")

    th_norm = max(0.0, min(1.0, float(threshold)))
    method = _match_method(tpl_src)
    found: List[Match] = []

    for scale in parse_scales(scales):
        tw, th = int(round(tw0 * scale)), int(round(th0 * scale))
        if tw < 4 or th < 4 or tw > sw or th > sh:
            continue
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        tpl = cv2.resize(tpl_src, (tw, th), interpolation=interp) if (tw, th) != (tw0, th0) else tpl_src

        res = cv2.matchTemplate(src, tpl, method)
        res = np.nan_to_num(res, nan=-1.0, posinf=1.0, neginf=-1.0)

        ys, xs = np.where(res >= th_norm)
        for x, y in zip(xs.tolist(), ys.tolist()):
            found.append(
                Match(
                    x=int(x) + offset[0],
                    y=int(y) + offset[1],
                    w=int(tw),
                    h=int(th),
                    score=float(res[y, x]),
                    scale=float(scale),
                )
            )

    return _nms(found, overlap=nms_overlap, max_results=max_results)


def find_best(screen: np.ndarray, template: np.ndarray, **kwargs) -> Match | None:
    """فقط بهترین تطابق (یا None)."""
    res = find_all(screen, template, max_results=1, **kwargs)
    return res[0] if res else None


def draw_matches(
    screen: np.ndarray,
    matches: Iterable[Match],
    color: Tuple[int, int, int] = (0, 0, 255),
    thickness: int = 3,
    labels: bool = True,
) -> np.ndarray:
    """یه کپی از تصویر با کادر دور درخت‌های پیدا‌شده — برای تست بدون کلیک."""
    out = screen.copy()
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    for i, m in enumerate(matches, 1):
        cv2.rectangle(out, (m.x, m.y), (m.x + m.w, m.y + m.h), color, thickness)
        cx, cy = m.center
        cv2.drawMarker(out, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 18, 2)
        if labels:
            text = f"{i}: {m.score * 100:.0f}%"
            cv2.putText(
                out, text, (m.x, max(18, m.y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA,
            )
    return out


def save_debug_image(path, screen: np.ndarray, matches: Iterable[Match]) -> None:
    """ذخیره‌ی تصویرِ دیباگ (برای وقتی می‌خوای ببینی ربات چی می‌بینه)."""
    img = draw_matches(screen, matches)
    # windows-safe: مسیر فارسی → با imencode می‌نویسیم
    ok, buf = cv2.imencode(".png", img)
    if ok:
        with open(path, "wb") as f:
            f.write(buf.tobytes())
