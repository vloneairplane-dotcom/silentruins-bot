// ==UserScript==
// @name         🌳 Tree Auto-Clicker (بات قطع درخت — وب)
// @namespace    https://github.com/silentruins/tree-bot
// @version      1.0.0
// @description  هر ۵ ثانیه درخت‌های روی کانواس بازی رو پیدا می‌کنه و روشون کلیک می‌کنه — با پنل فارسی، تشخیص تصویر و لاگ
// @author       silent ruins
// @match        *://*/*
// @grant        none
// @run-at       document-idle
// @noframes
// ==/UserScript==

/*
  ┌──────────────────────── استفاده ────────────────────────┐
  │ ۱) افزونه Tampermonkey (یا Violentmonkey) رو نصب کن     │
  │ ۲) این فایل رو باز کن → Tampermonkey → Install          │
  │ ۳) بازی رو باز کن؛ بالا-راست یه پنل 🌳 میاد             │
  │ ۴) دکمه‌ی «انتخاب درخت» رو بزن و با ماوس دور یه درختِ   │
  │    کامل مستطیل بکش (بدون حاشیه‌ی اضافه)                 │
  │ ۵) «شروع» — از این به بعد هر ۵ ثانیه خودش کلیک می‌کنه   │
  └─────────────────────────────────────────────────────────┘

  نکته‌ها:
   • «تست (بدون کلیک)» رو اول بزن تا ببینی درخت‌ها رو درست پیدا می‌کنه یا نه؛
     کادری که درست تشخیص داده با شماره و درصد شباهت روی صفحه کشیده می‌شه.
   • اگه بازی کلیک جاوااسکریپتی رو قبول نکرد، گزینه‌ی «حالت کلیک» رو
     بذار «لمس (موبایل)» یا «هر دو»، و «هدف کلیک» رو عوض کن.
   • برای بازی‌های دسکتاپیِ سنگین (یا بازی‌ای که ربات رو تشخیص می‌ده)
     نسخه‌ی پایتونیِ همین پروژه بهتره چون کلیکِ واقعیِ ویندوز می‌زنه.
*/

(function () {
  'use strict';

  /* =====================================================================
     ======================= TREEBOT-LIB START ============================
     =====  ریاضیِ خالص — بدون DOM، بدون canvas؛ قابل تست در Node  ========
     ===================================================================== */

  const TreeBotLib = (() => {
    /** خاکستری‌سازی از داده‌ی RGBA (خروجی getImageData) */
    function toGray(width, height, data) {
      const g = new Float32Array(width * height);
      for (let i = 0, p = 0; i < g.length; i++, p += 4) {
        g[i] = 0.299 * data[p] + 0.587 * data[p + 1] + 0.114 * data[p + 2];
      }
      return { w: width, h: height, g };
    }

    /** برشِ خاکستری */
    function cropGray(src, x, y, w, h) {
      x = Math.max(0, Math.min(src.w - 1, Math.round(x)));
      y = Math.max(0, Math.min(src.h - 1, Math.round(y)));
      w = Math.max(2, Math.min(src.w - x, Math.round(w)));
      h = Math.max(2, Math.min(src.h - y, Math.round(h)));
      const g = new Float32Array(w * h);
      for (let j = 0; j < h; j++) {
        const srcRow = (y + j) * src.w + x;
        const dstRow = j * w;
        for (let i = 0; i < w; i++) g[dstRow + i] = src.g[srcRow + i];
      }
      return { w, h, g };
    }

    /**
     * تغییر اندازه؛ موقع کوچک‌کردن «میانگینِ ناحیه» (area) و موقع بزرگ‌کردن
     * «دولایه‌ای» (bilinear). کوچک‌کردن با bilinear باعث aliasing می‌شه و
     * تطبیق رو خراب می‌کنه.
     */
    function resizeGray(src, dw, dh) {
      dw = Math.max(1, Math.round(dw));
      dh = Math.max(1, Math.round(dh));
      if (dw === src.w && dh === src.h) return { w: dw, h: dh, g: src.g.slice() };
      if (dw <= src.w && dh <= src.h) return resizeArea(src, dw, dh);
      return resizeBilinear(src, dw, dh);
    }

    /** میانگین‌گیری ناحیه‌ای — برای کوچک‌کردن (بدون aliasing) */
    function resizeArea(src, dw, dh) {
      const out = new Float32Array(dw * dh);
      const xr = src.w / dw;
      const yr = src.h / dh;
      for (let y = 0; y < dh; y++) {
        const y0 = Math.floor(y * yr);
        const y1 = Math.min(src.h, Math.max(y0 + 1, Math.ceil((y + 1) * yr)));
        for (let x = 0; x < dw; x++) {
          const x0 = Math.floor(x * xr);
          const x1 = Math.min(src.w, Math.max(x0 + 1, Math.ceil((x + 1) * xr)));
          let sum = 0;
          let n = 0;
          for (let j = y0; j < y1; j++) {
            const row = j * src.w;
            for (let i = x0; i < x1; i++) {
              sum += src.g[row + i];
              n++;
            }
          }
          out[y * dw + x] = n ? sum / n : 0;
        }
      }
      return { w: dw, h: dh, g: out };
    }

    /** درون‌یابی دولایه‌ای — برای بزرگ‌کردن */
    function resizeBilinear(src, dw, dh) {
      const out = new Float32Array(dw * dh);
      const sx = src.w / dw;
      const sy = src.h / dh;
      for (let y = 0; y < dh; y++) {
        const fy = (y + 0.5) * sy - 0.5;
        const y0 = Math.max(0, Math.min(src.h - 1, Math.floor(fy)));
        const y1 = Math.min(src.h - 1, y0 + 1);
        const wy = Math.max(0, Math.min(1, fy - y0));
        for (let x = 0; x < dw; x++) {
          const fx = (x + 0.5) * sx - 0.5;
          const x0 = Math.max(0, Math.min(src.w - 1, Math.floor(fx)));
          const x1 = Math.min(src.w - 1, x0 + 1);
          const wx = Math.max(0, Math.min(1, fx - x0));
          const a = src.g[y0 * src.w + x0];
          const b = src.g[y0 * src.w + x1];
          const c = src.g[y1 * src.w + x0];
          const d = src.g[y1 * src.w + x1];
          out[y * dw + x] = (a * (1 - wx) + b * wx) * (1 - wy) + (c * (1 - wx) + d * wx) * wy;
        }
      }
      return { w: dw, h: dh, g: out };
    }

    /** میانگین‌گیری جعبه‌ای (کوچک‌کردن سریع برای مرحله‌ی اولِ جست‌وجو) */
    function downsampleGray(src, k) {
      k = Math.max(1, Math.round(k));
      if (k === 1) return { w: src.w, h: src.h, g: src.g.slice() };
      const dw = Math.max(1, Math.floor(src.w / k));
      const dh = Math.max(1, Math.floor(src.h / k));
      const out = new Float32Array(dw * dh);
      for (let y = 0; y < dh; y++) {
        for (let x = 0; x < dw; x++) {
          let sum = 0;
          let n = 0;
          for (let j = 0; j < k; j++) {
            const row = (y * k + j) * src.w + x * k;
            if (row >= src.g.length) break;
            for (let i = 0; i < k; i++) {
              const idx = row + i;
              if (idx >= (y * k + j + 1) * src.w) break;
              sum += src.g[idx];
              n++;
            }
          }
          out[y * dw + x] = n ? sum / n : 0;
        }
      }
      return { w: dw, h: dh, g: out };
    }

    /** تصاویر تجمعی (integral) برای میانگین/واریانس O(1) در هر پنجره */
    function integralImages(img) {
      const { w, h, g } = img;
      const W = w + 1;
      const S = new Float64Array(W * (h + 1));
      const S2 = new Float64Array(W * (h + 1));
      for (let y = 1; y <= h; y++) {
        let rowSum = 0;
        let rowSum2 = 0;
        for (let x = 1; x <= w; x++) {
          const v = g[(y - 1) * w + (x - 1)];
          rowSum += v;
          rowSum2 += v * v;
          S[y * W + x] = S[(y - 1) * W + x] + rowSum;
          S2[y * W + x] = S2[(y - 1) * W + x] + rowSum2;
        }
      }
      return { W, S, S2 };
    }

    function boxSum(II, x, y, w, h) {
      const { W, S, S2 } = II;
      const x1 = x;
      const y1 = y;
      const x2 = x + w;
      const y2 = y + h;
      const s =
        S[y2 * W + x2] - S[y1 * W + x2] - S[y2 * W + x1] + S[y1 * W + x1];
      const s2 =
        S2[y2 * W + x2] - S2[y1 * W + x2] - S2[y2 * W + x1] + S2[y1 * W + x1];
      return { s, s2 };
    }

    /**
     * وزن‌دهی پیکسل‌های قالب بر اساس «لبه‌بودن».
     *
     * ⚠️ چرا لازمه؟ چون کاربر با ماوس دور درخت مستطیل می‌کشه و کادرِ قالب
     * حتماً یه تیکه پس‌زمینه هم داره. اگه پس‌زمینه در دو جای صفحه فرق کنه
     * (آسمون vs چمن)، تطبیقِ خامِ NCC خراب می‌شه (تجربه‌ش کردیم: نمره از
     * ۱ می‌افتاد به ۰.۲۸). با وزن‌دادن به لبه‌ها — که همون ساختار خودِ درخته —
     * و کم‌کردنِ وزنِ نواحیِ تختِ پس‌زمینه، تشخیص پایدار می‌شه.
     */
        /** آماره‌ی قالب: میانگین + قالبِ مرکز-شده (t - mean) */
    function templateStats(tpl) {
      const n = tpl.w * tpl.h;
      let sum = 0;
      for (let i = 0; i < n; i++) sum += tpl.g[i];
      const mean = sum / n;
      const centered = new Float32Array(n);
      let sq = 0;
      for (let i = 0; i < n; i++) {
        const d = tpl.g[i] - mean;
        centered[i] = d;
        sq += d * d;
      }
      let mass = 0;
      for (let i = 0; i < n; i++) mass += Math.abs(centered[i]);
      return { n, mean, centered, g: tpl.g, norm: Math.sqrt(sq), mass };
    }

    /** NCC بین قالب و یک پنجره‌ی مستطیلی از تصویر */
    function nccAt(img, stats, x, y, tw, th) {
      const ct = stats.centered;
      let dot = 0;
      let sum = 0;
      let sum2 = 0;
      for (let j = 0; j < th; j++) {
        let idx = (y + j) * img.w + x;
        let t = j * tw;
        for (let i = 0; i < tw; i++, idx++, t++) {
          const v = img.g[idx];
          dot += ct[t] * v;
          sum += v;
          sum2 += v * v;
        }
      }
      const n = tw * th;
      const mean = sum / n;
      const varI = sum2 - n * mean * mean;
      if (varI <= 1e-6 || stats.norm <= 1e-6) return 0;
      return dot / (stats.norm * Math.sqrt(varI));
    }

/**
     * NCC «مقاوم» — وقتی بخشی از کادرِ قالب یه چیزِ دیگه باشه.
     *
     * مثال واقعی که خودمون دیدیم: کاربر دور یه درخت مستطیل کشیده، ولی یه
     * سنگ/بوته هم داخل کادر افتاده. سنگ فقط ۵٪ پیکسل‌هاست ولی NCC خام رو
     * از ۱ می‌ندازه به ۰.۶۶ → درخت پیدا نمی‌شه.
     *
     * راه‌حل: یه خطِ برازش به داده می‌زنیم، باقی‌مانده‌ها رو حساب می‌کنیم،
     * بدترین‌ها (پرت‌ها) رو کنار می‌ذاریم و NCC رو روی بقیه حساب می‌کنیم.
     */
    function robustNcc(img, stats, x, y, tw, th, opts = {}) {
      const trim = opts.trim != null ? opts.trim : 0.2; // تا ۲۰٪ بدترین پیکسل‌ها نادیده
      const n = tw * th;
      const tg = stats.g;        // مقادیر خودِ قالب
      const tmean = stats.mean;  // میانگینِ قالب
      const g = img.g;

      // گذر ۱: میانگین‌ها و واریانس‌ها
      let sumS = 0;
      let sumS2 = 0;
      let idx = y * img.w + x;
      let k = 0;
      for (let j = 0; j < th; j++) {
        for (let i = 0; i < tw; i++, idx++, k++) {
          const v = g[idx];
          sumS += v;
          sumS2 += v * v;
        }
        idx += img.w - tw;
      }
      const meanS = sumS / n;
      const varS = sumS2 - n * meanS * meanS;
      if (varS <= 1e-6 || stats.norm <= 1e-6) return 0;

      // باقی‌مانده‌ها با فرضِ «کنتراستِ یکسان» (شیب = ۱).
      // ⚠️ با برازش کمترین‌مربعات امتحان کردیم و خراب می‌شد: خودِ پیکسل‌های
      // پرت (سنگِ داخل کادر) شیب رو می‌کشیدن و بعد همه‌ی پیکسل‌ها «پرت»
      // حساب می‌شدن. کنتراستِ قالب و درخت یکی‌ست، پس شیب = ۱ امن‌تره.
      const slope = 1;
      const res = new Float32Array(n);
      idx = y * img.w + x;
      k = 0;
      const sample = [];
      for (let j = 0; j < th; j++) {
        for (let i = 0; i < tw; i++, idx++, k++) {
          const r = g[idx] - (meanS + slope * (tg[k] - tmean));
          res[k] = r < 0 ? -r : r;
        }
        idx += img.w - tw;
      }
      // میانه (روی نمونه‌ی یک‌سوم، برای سرعت) → مقیاسِ مقاوم
      const step = Math.max(1, Math.floor(n / 1200));
      for (let i = 0; i < n; i += step) sample.push(res[i]);
      sample.sort((a, b) => a - b);
      const med = sample.length ? sample[sample.length >> 1] : 0;
      const cut = Math.max(med * 2.2, 6);
      const keepCount = Math.max(4, Math.round(n * (1 - trim)));

      // اگر خیلی از پیکسل‌ها پرت باشن، این کار فایده نداره
      let survived = 0;
      for (let i = 0; i < n; i++) if (res[i] <= cut) survived++;
      if (survived < keepCount * 0.875) return 0;

      // گذر ۳: NCC روی پیکسل‌های مونده
      let nk = 0;
      let st = 0;
      let ss = 0;
      let absT = 0;
      idx = y * img.w + x;
      k = 0;
      for (let j = 0; j < th; j++) {
        for (let i = 0; i < tw; i++, idx++, k++) {
          if (res[k] <= cut && tg) {
            st += tg[k];
            ss += g[idx];
            const ct = tg[k] - tmean;
            absT += ct < 0 ? -ct : ct;
            nk++;
          }
        }
        idx += img.w - tw;
      }
      if (nk < 4) return 0;
      const mt = st / nk;
      const ms = ss / nk;
      let num = 0;
      let dt = 0;
      let ds = 0;
      idx = y * img.w + x;
      k = 0;
      for (let j = 0; j < th; j++) {
        for (let i = 0; i < tw; i++, idx++, k++) {
          if (res[k] <= cut && tg) {
            const a = tg[k] - mt;
            const b = g[idx] - ms;
            num += a * b;
            dt += a * a;
            ds += b * b;
          }
        }
        idx += img.w - tw;
      }
      if (dt <= 1e-6 || ds <= 1e-6) return 0;

      // ⚠️ گاردِ «ساختار»: پیکسل‌های مونده باید پیکسل‌های *خودِ درخت* باشن،
      // نه پس‌زمینه‌ی تخت. بدون این گارد، یه تیکه چمنِ خالی با یه تیکه چمنِ
      // خالیِ دیگه «تطبیق» می‌داد و نمره‌ی الکی ۰.۹۷ می‌گرفت.
      if (absT < 0.5 * stats.mass) return 0;

      return num / Math.sqrt(dt * ds);
    }

    /** NMS: فروپاشیِ کاندیدهای روی‌هم‌افتاده */
    function nms(list, overlap, maxResults) {
      const kept = [];
      const sorted = list.slice().sort((a, b) => b.score - a.score);
      for (const m of sorted) {
        let ok = true;
        for (const k of kept) {
          const dx = Math.abs(m.x + m.w / 2 - (k.x + k.w / 2));
          const dy = Math.abs(m.y + m.h / 2 - (k.y + k.h / 2));
          if (dx < Math.max(4, Math.min(m.w, k.w) * 0.6) && dy < Math.max(4, Math.min(m.h, k.h) * 0.6)) {
            ok = false;
            break;
          }
        }
        if (ok) kept.push(m);
        if (kept.length >= maxResults) break;
      }
      return kept;
    }

    /** لیست مقیاس‌ها از min/max/step */
    function buildScales(min, max, step) {
      min = Number(min) || 1;
      max = Number(max) || 1;
      step = Number(step) || 0.05;
      if (max < min) [min, max] = [max, min];
      if (step <= 0) step = 0.05;
      const out = [];
      for (let s = min; s <= max + 1e-9; s += step) out.push(Math.round(s * 1000) / 1000);
      if (!out.length) out.push(1);
      return out;
    }

    /**
     * جست‌وجوی درخت‌ها — دو مرحله‌ای:
     *   ۱) روی تصویرِ خیلی کوچک‌شده (ارزان) کاندیدها پیدا می‌شن
     *   ۲) هر کاندید در تصویر کامل و با دقت پیکسلی تصحیح می‌شه
     *      (اول با مقیاسِ خودش، اگه نمره کافی نبود با مقیاس‌های همسایه)
     *
     * @param {{w:number,h:number}} screen  تصویر صفحه (خاکستری کامل)
     * @param {{w:number,h:number}} tpl     قالب درخت (خاکستری، کامل)
     * @param {object} opts  {threshold, scales, maxResults, coarseFactor, minVar, refineRadius}
     * @returns {Array<{x,y,w,h,score,scale,center:{x,y}}>}
     */
    function findTrees(screen, tpl, opts = {}) {
      const threshold = opts.threshold != null ? opts.threshold : 0.8;
      const scales = opts.scales && opts.scales.length ? opts.scales : [1];
      const maxResults = opts.maxResults || 20;
      const minVar = opts.minVar != null ? opts.minVar : 25; // واریانس حداقلیِ پنجره

      if (!screen || !tpl || tpl.w < 4 || tpl.h < 4) return [];

      // ── آماده‌سازی: تصویر درشت + اطلاعات هر مقیاس ──
      let k1 = Math.round(opts.coarseFactor || tpl.w / 10);
      k1 = Math.max(3, Math.min(8, k1));
      const coarse = downsampleGray(screen, k1);
      const II = integralImages(coarse);

      const levels = [];
      for (let si = 0; si < scales.length; si++) {
        const scale = scales[si];
        const tw = Math.max(4, Math.round(tpl.w * scale));
        const th = Math.max(4, Math.round(tpl.h * scale));
        const cw = Math.max(3, Math.round(tw / k1));
        const ch = Math.max(3, Math.round(th / k1));
        if (tw > screen.w || th > screen.h || cw > coarse.w || ch > coarse.h) {
          levels.push(null);
          continue;
        }
        const stats = templateStats(resizeGray(tpl, cw, ch));
        levels.push({ scale, tw, th, cw, ch, stats });
      }

      // ── اسکنِ درشت: کاندیدها روی تصویرِ چندپیکسلی ──
      // معیار = «NCC مقاوم» که هم پس‌زمینه‌ی متفاوت و هم یه شیءِ اضافه
      // داخل کادرِ قالب (سنگ/بوته) رو تحمل می‌کنه؛ ولی گاردِ ساختار
      // نمی‌ذاره چمنِ خالی با چمنِ خالی «تطبیق» بشه.
      function scanCoarse(useRobust, softFactor) {
        const cands = [];
        for (let si = 0; si < levels.length; si++) {
          const lv = levels[si];
          if (!lv || lv.stats.norm <= 1e-6) continue;
          const { cw, ch, stats } = lv;
          const maxX = coarse.w - cw;
          const maxY = coarse.h - ch;
          for (let y = 0; y <= maxY; y++) {
            for (let x = 0; x <= maxX; x++) {
              // فیلترِ ارزان با تصویر تجمعی: پنجره‌های بی‌بافت رد می‌شن
              const { s, s2 } = boxSum(II, x, y, cw, ch);
              const n = cw * ch;
              const meanI = s / n;
              if (s2 - n * meanI * meanI <= minVar) continue;
              const score = useRobust
                ? robustNcc(coarse, stats, x, y, cw, ch, { trim: opts.trim })
                : nccAt(coarse, stats, x, y, cw, ch);
              if (score >= threshold * softFactor) cands.push({ x, y, score, si, cw, ch });
            }
          }
        }
        return cands;
      }

      // حذف کاندیدهای تکراری: چنیدن کاندیدِ نزدیک روی یه درختِ واحد
      // باید یکي بشن (وگرنه کاندیدهای درخت‌های دیگه جاشون رو می‌گیرن)
      function prune(cands) {
        cands.sort((a, b) => b.score - a.score);
        const top = cands.slice(0, Math.max(60, maxResults * 8));
        const out = [];
        for (const c of top) {
          const lv = levels[c.si];
          const twc = lv ? lv.tw / k1 : c.cw;
          const thc = lv ? lv.th / k1 : c.ch;
          const ccx = c.x + c.cw / 2;
          const ccy = c.y + c.ch / 2;
          const near = out.some((q) => {
            const qlv = levels[q.si];
            const qtw = qlv ? qlv.tw / k1 : q.cw;
            const qth = qlv ? qlv.th / k1 : q.ch;
            return (
              Math.abs(ccx - (q.x + q.cw / 2)) < 0.5 * Math.min(twc, qtw) &&
              Math.abs(ccy - (q.y + q.ch / 2)) < 0.5 * Math.min(thc, qth)
            );
          });
          if (!near) out.push(c);
          if (out.length >= Math.max(16, maxResults)) break;
        }
        return out;
      }

      // ── تصحیح روی تصویرِ نیم‌اندازه ──
      // نیم‌اندازه: هم ۴ برابر سریع‌تره، هم اختلاف‌های یک‌پیکسلیِ مقیاس‌دهیِ
      // بازی رو نادیده می‌گیره (تحملِ زیرپیکسلی)
      const k2 = Math.max(1, Math.min(3, Math.round(opts.midFactor || 2)));
      const mid = k2 === 1 ? screen : downsampleGray(screen, k2);
      const radius = opts.refineRadius != null ? opts.refineRadius : Math.ceil(k1 / (2 * k2)) + 2;

      function refine(pruned, robustLocate) {
        const refined = [];
        for (const c of pruned) {
          const baseX = ((c.x + c.cw / 2) * k1) / k2;
          const baseY = ((c.y + c.ch / 2) * k1) / k2;

          // اول مقیاسِ خودش؛ اگه کافی نبود مقیاس‌های همسایه هم امتحان می‌شن
          const tryScales = [c.si];
          for (const d of [-1, 1]) {
            const idx = c.si + d;
            if (idx >= 0 && idx < levels.length && levels[idx]) tryScales.push(idx);
          }

          let best = null;
          for (let ti = 0; ti < tryScales.length; ti++) {
            const lv = levels[tryScales[ti]];
            const twm = Math.max(4, Math.round(lv.tw / k2));
            const thm = Math.max(4, Math.round(lv.th / k2));
            if (twm > mid.w || thm > mid.h) continue;
            const stats = templateStats(resizeGray(tpl, twm, thm));
            const cx0 = Math.round(baseX - twm / 2);
            const cy0 = Math.round(baseY - thm / 2);
            const spots = [];

            for (let dy = -radius; dy <= radius; dy++) {
              for (let dx = -radius; dx <= radius; dx++) {
                const px = cx0 + dx;
                const py = cy0 + dy;
                if (px < 0 || py < 0 || px + twm > mid.w || py + thm > mid.h) continue;
                // در پاسِ نجات، همون اول با معیار مقاوم نمره می‌دیم (چون
                // NCC خام وقتی داخل قالب یه شیء اضافه باشه گمراه‌کننده‌ست)
                const score = robustLocate
                  ? robustNcc(mid, stats, px, py, twm, thm, { trim: opts.trim })
                  : nccAt(mid, stats, px, py, twm, thm);
                spots.push({ px, py, score });
                if (!best || score > best.score) {
                  best = {
                    centerX: (px + twm / 2) * k2,
                    centerY: (py + thm / 2) * k2,
                    score,
                    scale: lv.scale,
                    w: lv.tw,
                    h: lv.th,
                  };
                }
              }
            }

            // NCC خام فقط برای «جایابی» استفاده شد؛ تصمیمِ نهایی با NCC مقاومه.
            // ۳ کاندیدِ برتر چک می‌شن (ارزان‌تر از حساب‌کردنِ مقاوم در همه‌ی
            // نقطه‌های پنجره).
            if (best && !robustLocate) {
              spots.sort((a, b) => b.score - a.score);
              for (let q = 0; q < Math.min(3, spots.length); q++) {
                const sp = spots[q];
                const rScore = robustNcc(mid, stats, sp.px, sp.py, twm, thm, { trim: opts.trim });
                if (rScore > best.score) {
                  best = {
                    centerX: (sp.px + twm / 2) * k2,
                    centerY: (sp.py + thm / 2) * k2,
                    score: rScore,
                    scale: lv.scale,
                    w: lv.tw,
                    h: lv.th,
                  };
                }
                if (best.score >= threshold + 0.04) break;
              }
            }
            if (ti === 0 && best && best.score >= threshold + 0.04) break; // مقیاس خودش کافیه
          }

          if (!best || best.score < threshold - 0.25) continue;

          // ── تأییدِ نهایی در رزولوشنِ کامل ──
          // مرحله‌ی نیم‌اندازه فقط برای «جایابی» بود؛ تصمیمِ نهایی این‌جا
          // گرفته می‌شه. (تصویر نیم‌اندازه نرم‌شده‌ست و به‌تنهایی می‌تونه
          // تطبیقِ الکی بده — تجربه‌ش کردیم.)
          const twF = best.w;
          const thF = best.h;
          const fst = templateStats(resizeGray(tpl, twF, thF));
          const fx0 = Math.round(best.centerX - twF / 2);
          const fy0 = Math.round(best.centerY - thF / 2);
          const fine = [];
          for (let dy = -2; dy <= 2; dy++) {
            for (let dx = -2; dx <= 2; dx++) {
              const px = fx0 + dx;
              const py = fy0 + dy;
              if (px < 0 || py < 0 || px + twF > screen.w || py + thF > screen.h) continue;
              fine.push({ px, py, score: nccAt(screen, fst, px, py, twF, thF) });
            }
          }
          fine.sort((a, b) => b.score - a.score);
          let final = null;
          for (let q = 0; q < Math.min(3, fine.length); q++) {
            const sp = fine[q];
            const raw = sp.score;
            const rob = robustNcc(screen, fst, sp.px, sp.py, twF, thF, { trim: opts.trim });
            const score = Math.max(raw, rob);
            if (!final || score > final.score) {
              final = {
                x: sp.px,
                y: sp.py,
                w: twF,
                h: thF,
                score,
                scale: best.scale,
              };
            }
          }
          if (final && final.score >= threshold) refined.push(final);
        }
        return refined;
      }

      // ── پاسِ اول: اسکنِ خام (سریع) ──
      const cands = scanCoarse(false, 0.85);
      let refined = cands.length ? refine(prune(cands), false) : [];

      // ── پاسِ نجات ──
      // اگه پاسِ سریع کم پیدا کرد، با معیارِ «مقاوم» دوباره می‌گردیم:
      // این حالت وقتیه که داخل کادرِ قالب یه سنگ/بوته افتاده باشه یا
      // پس‌زمینه‌ی جای درخت‌ها با جای قالب فرق کنه. کندتره، پس فقط
      // وقتی لازمه اجرا می‌شه.
      if (refined.length < Math.min(2, maxResults) && opts.rescue !== false) {
        const rescue = scanCoarse(true, 0.75);
        // صافیِ میانی: روی تصویرِ نیم‌اندازه (که خیلی دقیق‌تره) فقط یه نقطه
        // از هر کاندید چک می‌شه تا کاندیدهای الکی حذف شن.
        const survivors = [];
        for (const c of rescue) {
          const lv = levels[c.si];
          if (!lv) continue;
          const twm = Math.max(4, Math.round(lv.tw / k2));
          const thm = Math.max(4, Math.round(lv.th / k2));
          if (twm > mid.w || thm > mid.h) continue;
          const px = Math.round(((c.x + c.cw / 2) * k1) / k2 - twm / 2);
          const py = Math.round(((c.y + c.ch / 2) * k1) / k2 - thm / 2);
          if (px < 0 || py < 0 || px + twm > mid.w || py + thm > mid.h) continue;
          const stats = templateStats(resizeGray(tpl, twm, thm));
          const sc = robustNcc(mid, stats, px, py, twm, thm, { trim: opts.trim });
          // نمره‌ی کاندید با نمره‌ی دقیق‌ترِ این مرحله به‌روز می‌شه تا
          // رتبه‌بندی (و حذفِ کاندیدهای اضافی) درست انجام شه
          if (sc >= threshold - 0.15) survivors.push(Object.assign({}, c, { score: sc }));
        }
        if (survivors.length) {
          const extra = refine(prune(survivors), true);
          for (const m of extra) {
            const dup = refined.some(
              (r) =>
                Math.abs(r.x + r.w / 2 - (m.x + m.w / 2)) < Math.max(6, m.w * 0.5) &&
                Math.abs(r.y + r.h / 2 - (m.y + m.h / 2)) < Math.max(6, m.h * 0.5)
            );
            if (!dup) refined.push(m);
          }
        }
      }

      const final = nms(refined, 0.35, maxResults);
      return final.map((m) => ({
        x: m.x,
        y: m.y,
        w: m.w,
        h: m.h,
        score: m.score,
        scale: m.scale,
        center: { x: Math.round(m.x + m.w / 2), y: Math.round(m.y + m.h / 2) },
      }));
    }

    return {
      toGray,
      cropGray,
      resizeGray,
      resizeArea,
      resizeBilinear,
      downsampleGray,
      integralImages,
      boxSum,
      templateStats,
      nccAt,
      robustNcc,
      nms,
      buildScales,
      findTrees,
    };
  })();

  if (typeof module !== 'undefined' && module.exports) module.exports = TreeBotLib;
  if (typeof window !== 'undefined') window.__TreeBotLib = TreeBotLib;

  /* =====================================================================
     ======================== TREEBOT-LIB END =============================
     ===================================================================== */

  if (typeof document === 'undefined') return; // تست در Node → فقط کتابخانه

  // ─────────────────────────── تنظیمات ───────────────────────────

  const STORE_KEY = 'treebot.settings.v1';
  const TPL_KEY = 'treebot.template.v1';

  const DEFAULTS = {
    intervalMs: 5000,        // ⏱ هر ۵ ثانیه (خواسته‌ی اصلی)
    threshold: 0.8,
    scaleMin: 0.9,
    scaleMax: 1.1,
    scaleStep: 0.05,
    jitter: 3,
    clicksPerTree: 1,
    clickMode: 'mouse',      // mouse | touch | both
    clickTarget: 'element',  // element | canvas | both
    randomOrder: true,
    clickDelayMs: 130,
    regionMode: 'canvas',    // canvas | custom
    customRegion: null,      // {rx, ry, rw, rh} نسبت به کانواس (0..1)
    showOverlay: true,
    pauseWhenHidden: true,
    maxTrees: 20,
  };

  const state = {
    running: false,
    busy: false,
    paused: false,
    settings: Object.assign({}, DEFAULTS, loadJSON(STORE_KEY, {})),
    template: null,          // {w,h,g} خاکستریِ قالب
    templatePng: null,       // dataURL برای نمایش
    templateAt: 0,
    lastMatches: [],
    lastRun: 0,
    clicks: 0,
    cycles: 0,
    log: [],
    picking: false,
    pickMode: null,          // 'tree' | 'region'
  };

  // ─────────────────────────── ابزارها ───────────────────────────

  function loadJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function saveJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      return false;
    }
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function logLine(msg, kind) {
    const line = `${new Date().toLocaleTimeString('fa-IR')} — ${msg}`;
    state.log.unshift({ t: line, kind: kind || 'info' });
    state.log = state.log.slice(0, 40);
    renderLog();
  }

  function visible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 20 && r.height > 20 && el.offsetParent !== null;
  }

  function findGameCanvas() {
    const list = Array.from(document.querySelectorAll('canvas')).filter(visible);
    if (!list.length) return null;
    list.sort((a, b) => {
      const ra = a.getBoundingClientRect();
      const rb = b.getBoundingClientRect();
      return rb.width * rb.height - ra.width * ra.height;
    });
    return list[0];
  }

  /** گرفتن فریم از کانواس (باید داخل rAF صدا زده شه تا فریم WebGL خالی نباشه) */
  function grabFrame() {
    const cv = findGameCanvas();
    if (!cv) return { error: 'کانواس بازی پیدا نشد' };
    const w = cv.width;
    const h = cv.height;
    if (!w || !h) return { error: 'کانواس اندازه‌ی معتبر نداره' };
    const off = grabFrame._off || (grabFrame._off = document.createElement('canvas'));
    off.width = w;
    off.height = h;
    const ctx = off.getContext('2d', { willReadFrequently: true });
    try {
      ctx.drawImage(cv, 0, 0, w, h);
      const data = ctx.getImageData(0, 0, w, h);
      return { canvas: cv, w, h, data, gray: TreeBotLib.toGray(w, h, data.data) };
    } catch (e) {
      return { error: 'خوندن پیکسل‌های کانواس ممکن نشد (cross-origin?): ' + e.message };
    }
  }

  function grabFrameAsync() {
    return new Promise((resolve) => {
      requestAnimationFrame(() => {
        try {
          resolve(grabFrame());
        } catch (e) {
          resolve({ error: String(e && e.message ? e.message : e) });
        }
      });
    });
  }

  /** تبدیل مختصاتِ فریم (backing store) ↔ مختصات صفحه */
  function frameToClient(frame, fx, fy) {
    const r = frame.canvas.getBoundingClientRect();
    const sx = r.width / frame.w;
    const sy = r.height / frame.h;
    return { x: r.left + fx * sx, y: r.top + fy * sy, rect: r, sx, sy };
  }

  function clientToFrame(frame, cx, cy) {
    const r = frame.canvas.getBoundingClientRect();
    const sx = frame.w / r.width;
    const sy = frame.h / r.height;
    return { x: (cx - r.left) * sx, y: (cy - r.top) * sy, rect: r, sx, sy };
  }

  // ─────────────────────────── کلیک ───────────────────────────

  function dispatchMouse(el, cx, cy) {
    const common = {
      bubbles: true,
      cancelable: true,
      composed: true,
      view: window,
      clientX: cx,
      clientY: cy,
      screenX: cx,
      screenY: cy,
      button: 0,
      buttons: 1,
    };
    try {
      el.dispatchEvent(new PointerEvent('pointerdown', Object.assign({}, common, { pointerId: 1, pointerType: 'mouse', isPrimary: true })));
    } catch (e) { /* PointerEvent ممکنه نباشه */ }
    el.dispatchEvent(new MouseEvent('mousedown', common));
    try {
      el.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, common, { buttons: 0 })));
    } catch (e) { /* ... */ }
    el.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, common, { buttons: 0 })));
    el.dispatchEvent(new MouseEvent('click', Object.assign({}, common, { buttons: 0 })));
  }

  function dispatchTouch(el, cx, cy) {
    try {
      const touch = new Touch({
        identifier: Date.now() % 100000,
        target: el,
        clientX: cx,
        clientY: cy,
        pageX: cx + window.scrollX,
        pageY: cy + window.scrollY,
      });
      el.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, cancelable: true, touches: [touch], targetTouches: [touch], changedTouches: [touch] }));
      el.dispatchEvent(new TouchEvent('touchend', { bubbles: true, cancelable: true, touches: [], targetTouches: [], changedTouches: [touch] }));
    } catch (e) {
      // بعضی مرورگرها TouchEvent نمی‌سازن
    }
  }

  function clickAt(frame, fx, fy) {
    const cfg = state.settings;
    const j = Math.max(0, Number(cfg.jitter) || 0);
    const x = fx + (j ? Math.round((Math.random() * 2 - 1) * j) : 0);
    const y = fy + (j ? Math.round((Math.random() * 2 - 1) * j) : 0);
    const pos = frameToClient(frame, x, y);

    const targets = [];
    const atPoint = document.elementFromPoint(pos.x, pos.y);
    if (cfg.clickTarget === 'element' || cfg.clickTarget === 'both') {
      if (atPoint) targets.push(atPoint);
      // اگه بالاترین عنصر خود کانواس نبود، کانواس هم امتحان می‌شه (بازی‌ها فرق دارن)
      if (atPoint && atPoint !== frame.canvas && cfg.clickTarget !== 'canvas') targets.push(frame.canvas);
    }
    if (cfg.clickTarget === 'canvas' || cfg.clickTarget === 'both') targets.push(frame.canvas);

    const unique = [];
    for (const t of targets) if (t && unique.indexOf(t) === -1) unique.push(t);
    if (!unique.length) unique.push(frame.canvas);

    for (const el of unique) {
      if (cfg.clickMode === 'touch' || cfg.clickMode === 'both') dispatchTouch(el, pos.x, pos.y);
      if (cfg.clickMode === 'mouse' || cfg.clickMode === 'both') dispatchMouse(el, pos.x, pos.y);
    }
    return { x: Math.round(x), y: Math.round(y) };
  }

  // ─────────────────────────── رابط کاربری ───────────────────────────

  let shadow = null;
  let panel = null;
  let overlay = null;
  let pickLayer = null;
  let els = {};

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: Tahoma, "Segoe UI", IRANSans, system-ui, sans-serif; }
    .panel {
      position: fixed; top: 12px; left: 12px; width: 296px; z-index: 2147483000;
      background: rgba(16,18,22,.96); color: #e9edf2; border: 1px solid #2c3440;
      border-radius: 14px; box-shadow: 0 12px 40px rgba(0,0,0,.55); direction: rtl;
      font-size: 12px; overflow: hidden; backdrop-filter: blur(6px);
    }
    .head { display:flex; align-items:center; gap:8px; padding:9px 11px; background: linear-gradient(90deg,#16281c,#12202a); cursor: move; }
    .head .title { font-weight: 700; font-size: 13px; flex: 1; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background:#e5484d; box-shadow: 0 0 8px currentColor; }
    .dot.on { background:#30a46c; }
    .dot.paused { background:#f5a524; }
    .iconbtn { background:#1d2530; border:1px solid #2c3440; color:#cfd6df; border-radius:8px; width:24px; height:22px; cursor:pointer; line-height:1; }
    .iconbtn:hover { background:#26313f; }
    .body { padding: 10px 11px 12px; display: flex; flex-direction: column; gap: 9px; max-height: 78vh; overflow:auto; }
    .row { display:flex; align-items:center; gap:8px; }
    .row label { flex: 1; color:#a9b4c0; }
    input[type=number], input[type=text], select {
      background:#0f141b; border:1px solid #2c3440; color:#e9edf2; border-radius:8px;
      padding:4px 7px; width:86px; font-size:12px; direction:ltr; text-align:center;
    }
    select { width: 118px; text-align: right; direction: rtl; }
    input:focus, select:focus { outline:none; border-color:#30a46c; }
    .btns { display:grid; grid-template-columns: 1fr 1fr; gap:7px; }
    button.act {
      border:1px solid #2c3440; background:#1a2230; color:#e9edf2; border-radius:10px;
      padding:7px 8px; cursor:pointer; font-size:12px; font-weight:600;
    }
    button.act:hover { background:#22303f; }
    button.act.primary { background:#1d6f47; border-color:#2a8f5c; }
    button.act.primary:hover { background:#23855a; }
    button.act.danger { background:#5c2027; border-color:#8a2f38; }
    button.act.wide { grid-column: 1 / -1; }
    button.act:disabled { opacity:.45; cursor:not-allowed; }
    .thumbs { display:flex; align-items:center; gap:8px; background:#0f141b; border:1px dashed #2c3440; border-radius:10px; padding:7px; }
    .thumbs img { width:44px; height:44px; object-fit:contain; background:#05070a; border-radius:6px; image-rendering: pixelated; }
    .stats { display:grid; grid-template-columns: repeat(3,1fr); gap:6px; text-align:center; }
    .stat { background:#0f141b; border:1px solid #222b36; border-radius:9px; padding:5px 4px; }
    .stat b { display:block; font-size:14px; color:#7ee2a8; }
    .stat span { color:#8d99a6; font-size:10px; }
    .log { background:#0b0f14; border:1px solid #222b36; border-radius:9px; padding:6px 8px; max-height: 104px; overflow:auto; direction:rtl; }
    .log div { padding:2px 0; border-bottom:1px dashed #1b2430; color:#b9c3ce; font-size:11px; }
    .log div:last-child { border-bottom:0; }
    .log div.ok { color:#7ee2a8; }
    .log div.err { color:#ff9aa2; }
    .hint { color:#8d99a6; font-size:10.5px; line-height:1.6; }
    .sep { height:1px; background:#232c38; margin:1px 0; }
    .overlay { position: fixed; inset: 0; pointer-events: none; z-index: 2147482998; }
    .picklayer { position: fixed; inset: 0; cursor: crosshair; z-index: 2147482999; background: rgba(6,10,14,.28); }
    .picklayer .sel { position: absolute; border: 2px dashed #4ade80; background: rgba(74,222,128,.14); }
    .picklayer .tip { position: fixed; top: 14px; left: 50%; transform: translateX(-50%); background:#12181f; color:#dbe4ee; border:1px solid #2c3440; border-radius:999px; padding:7px 14px; font-size:12px; }
    .hidden { display:none !important; }
  `;

  function buildUI() {
    const host = document.createElement('div');
    host.id = 'treebot-host';
    document.documentElement.appendChild(host);
    shadow = host.attachShadow({ mode: 'open' });

    const style = document.createElement('style');
    style.textContent = CSS;
    shadow.appendChild(style);

    // لایه‌ی نمایش کادرها
    overlay = document.createElement('canvas');
    overlay.className = 'overlay';
    overlay.width = window.innerWidth;
    overlay.height = window.innerHeight;
    shadow.appendChild(overlay);

    // پنل
    panel = document.createElement('div');
    panel.className = 'panel';
    panel.innerHTML = `
      <div class="head" id="tb-head">
        <span class="dot" id="tb-dot"></span>
        <span class="title">🌳 بات قطع درخت</span>
        <button class="iconbtn" id="tb-min" title="کوچک/بزرگ">▾</button>
      </div>
      <div class="body" id="tb-body">
        <div class="thumbs">
          <img id="tb-tplimg" alt="قالب" />
          <div style="flex:1">
            <div id="tb-tplinfo" class="hint">قالبِ درخت: انتخاب نشده</div>
            <div class="hint" id="tb-canvasinfo">کانواس: —</div>
          </div>
        </div>

        <div class="btns">
          <button class="act primary" id="tb-start">▶ شروع</button>
          <button class="act" id="tb-test">🧪 تست</button>
          <button class="act" id="tb-pick">🎯 انتخاب درخت</button>
          <button class="act" id="tb-region">🔲 محدوده</button>
          <button class="act wide" id="tb-clear">🗑 پاک‌کردن صفحه‌ی تشخیص</button>
        </div>

        <div class="sep"></div>

        <div class="row"><label>فاصله (ثانیه)</label><input type="number" step="0.5" min="0.5" id="tb-interval"></div>
        <div class="row"><label>آستانه شباهت</label><input type="number" step="0.01" min="0.3" max="0.99" id="tb-threshold"></div>
        <div class="row"><label>مقیاس‌ها (از/تا)</label>
          <input type="number" step="0.01" id="tb-smin" style="width:44px">
          <input type="number" step="0.01" id="tb-smax" style="width:44px">
        </div>
        <div class="row"><label>لرزش ماوس (±px)</label><input type="number" min="0" max="20" id="tb-jitter"></div>
        <div class="row"><label>کلیک روی هر درخت</label><input type="number" min="1" max="10" id="tb-cpt"></div>
        <div class="row"><label>حالت کلیک</label>
          <select id="tb-clickmode">
            <option value="mouse">ماوس</option>
            <option value="touch">لمس (موبایلی)</option>
            <option value="both">هر دو</option>
          </select>
        </div>
        <div class="row"><label>هدف کلیک</label>
          <select id="tb-clicktarget">
            <option value="element">عنصر زیر ماوس</option>
            <option value="canvas">کانواس بازی</option>
            <option value="both">هر دو</option>
          </select>
        </div>
        <div class="row"><label>کادرها رو نشون بده</label><input type="checkbox" id="tb-overlay" style="width:auto"></div>
        <div class="row"><label>ترتیب تصادفی</label><input type="checkbox" id="tb-random" style="width:auto"></div>
        <div class="row"><label>توقف وقتی تب مخفیه</label><input type="checkbox" id="tb-hidden" style="width:auto"></div>

        <div class="sep"></div>

        <div class="stats">
          <div class="stat"><b id="tb-s1">0</b><span>دور</span></div>
          <div class="stat"><b id="tb-s2">0</b><span>کلیک</span></div>
          <div class="stat"><b id="tb-s3">0</b><span>درخت</span></div>
        </div>

        <div class="log" id="tb-log"></div>

        <div class="hint">
          راهنما: «انتخاب درخت» → با ماوس دور یه درختِ کامل مستطیل بکش.
          اگه درختی پیدا نشد، آستانه رو کمتر (مثلاً 0.7) یا مقیاس‌ها رو بازتر کن.
          میان‌برها: F8 توقف/ادامه • F9 خروج
        </div>
      </div>
    `;
    shadow.appendChild(panel);

    // مراجع
    const ids = [
      'head', 'dot', 'min', 'body', 'tplimg', 'tplinfo', 'canvasinfo', 'start', 'test',
      'pick', 'region', 'clear', 'interval', 'threshold', 'smin', 'smax', 'jitter', 'cpt',
      'clickmode', 'clicktarget', 'overlay', 'random', 'hidden', 's1', 's2', 's3', 'log',
    ];
    for (const id of ids) els[id] = shadow.getElementById('tb-' + id);

    // مقدارها
    const s = state.settings;
    els.interval.value = s.intervalMs / 1000;
    els.threshold.value = s.threshold;
    els.smin.value = s.scaleMin;
    els.smax.value = s.scaleMax;
    els.jitter.value = s.jitter;
    els.cpt.value = s.clicksPerTree;
    els.clickmode.value = s.clickMode;
    els.clicktarget.value = s.clickTarget;
    els.overlay.checked = s.showOverlay;
    els.random.checked = s.randomOrder;
    els.hidden.checked = s.pauseWhenHidden;

    // رویدادها
    els.start.addEventListener('click', toggleRun);
    els.test.addEventListener('click', () => runCycle(true));
    els.pick.addEventListener('click', () => startPick('tree'));
    els.region.addEventListener('click', () => startPick('region'));
    els.clear.addEventListener('click', () => {
      state.lastMatches = [];
      clearOverlay();
      logLine('صفحه‌ی تشخیص پاک شد');
    });
    els.min.addEventListener('click', () => {
      els.body.classList.toggle('hidden');
      els.min.textContent = els.body.classList.contains('hidden') ? '▸' : '▾';
    });

    const bind = (el, key, transform) => {
      el.addEventListener('change', () => {
        const v = transform ? transform(el) : el.value;
        state.settings[key] = v;
        saveJSON(STORE_KEY, state.settings);
        logLine(`تنظیم «${key}» = ${v}`);
      });
    };
    bind(els.interval, 'intervalMs', (e) => Math.max(500, Math.round(Number(e.value) * 1000)));
    bind(els.threshold, 'threshold', (e) => Math.min(0.99, Math.max(0.3, Number(e.value))));
    bind(els.smin, 'scaleMin', (e) => Math.max(0.3, Number(e.value)));
    bind(els.smax, 'scaleMax', (e) => Math.min(3, Number(e.value)));
    bind(els.jitter, 'jitter', (e) => Math.max(0, Number(e.value)));
    bind(els.cpt, 'clicksPerTree', (e) => Math.max(1, Number(e.value)));
    bind(els.clickmode, 'clickMode');
    bind(els.clicktarget, 'clickTarget');
    bind(els.overlay, 'showOverlay', (e) => e.checked);
    bind(els.random, 'randomOrder', (e) => e.checked);
    bind(els.hidden, 'pauseWhenHidden', (e) => e.checked);

    makeDraggable(panel, els.head);
    restoreTemplate();
    renderInfo();
    renderLog();
    updateStats();
    resizeOverlay();
    window.addEventListener('resize', resizeOverlay);
    document.addEventListener('visibilitychange', () => {
      if (state.settings.pauseWhenHidden && document.hidden && state.running) {
        logLine('تب مخفی شد → مکث موقت', 'info');
      }
    });
    logLine('آماده — قالب درخت رو انتخاب کن');
  }

  function makeDraggable(el, handle) {
    let sx = 0;
    let sy = 0;
    let ox = 0;
    let oy = 0;
    let dragging = false;
    handle.addEventListener('pointerdown', (e) => {
      if (e.target && e.target.tagName === 'BUTTON') return;
      dragging = true;
      sx = e.clientX;
      sy = e.clientY;
      const r = el.getBoundingClientRect();
      ox = r.left;
      oy = r.top;
      handle.setPointerCapture(e.pointerId);
    });
    handle.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const nx = Math.max(0, Math.min(window.innerWidth - 60, ox + e.clientX - sx));
      const ny = Math.max(0, Math.min(window.innerHeight - 40, oy + e.clientY - sy));
      el.style.left = nx + 'px';
      el.style.top = ny + 'px';
      el.style.right = 'auto';
    });
    handle.addEventListener('pointerup', () => {
      dragging = false;
    });
  }

  // ─────────────────────────── انتخاب درخت / محدوده ───────────────────────────

  function startPick(mode) {
    stopRun();
    state.pickMode = mode;
    state.picking = true;
    pickLayer = document.createElement('div');
    pickLayer.className = 'picklayer';
    const tip = document.createElement('div');
    tip.className = 'tip';
    tip.textContent = mode === 'tree'
      ? '🎯 با ماوس دور یه درختِ کامل مستطیل بکش — Esc = انصراف'
      : '🔲 ناحیه‌ای که ربات جست‌وجو کنه رو بکش — Esc = انصراف';
    const sel = document.createElement('div');
    sel.className = 'sel hidden';
    pickLayer.appendChild(tip);
    pickLayer.appendChild(sel);
    shadow.appendChild(pickLayer);

    let x0 = 0;
    let y0 = 0;
    let drawing = false;
    const onDown = (e) => {
      drawing = true;
      x0 = e.clientX;
      y0 = e.clientY;
      sel.classList.remove('hidden');
      sel.style.left = x0 + 'px';
      sel.style.top = y0 + 'px';
      sel.style.width = '0px';
      sel.style.height = '0px';
    };
    const onMove = (e) => {
      if (!drawing) return;
      const x = Math.min(e.clientX, x0);
      const y = Math.min(e.clientY, y0);
      sel.style.left = x + 'px';
      sel.style.top = y + 'px';
      sel.style.width = Math.abs(e.clientX - x0) + 'px';
      sel.style.height = Math.abs(e.clientY - y0) + 'px';
    };
    const cleanup = () => {
      pickLayer.removeEventListener('mousedown', onDown);
      pickLayer.removeEventListener('mousemove', onMove);
      pickLayer.removeEventListener('mouseup', onUp);
      document.removeEventListener('keydown', onKey);
      if (pickLayer && pickLayer.parentNode) pickLayer.parentNode.removeChild(pickLayer);
      pickLayer = null;
      state.picking = false;
      state.pickMode = null;
    };
    const onKey = (e) => {
      if (e.key === 'Escape') {
        cleanup();
        logLine('انتخاب لغو شد');
      }
    };
    const onUp = async (e) => {
      if (!drawing) return;
      drawing = false;
      const x1 = Math.min(e.clientX, x0);
      const y1 = Math.min(e.clientY, y0);
      const w = Math.abs(e.clientX - x0);
      const h = Math.abs(e.clientY - y0);
      cleanup();
      if (w < 6 || h < 6) {
        logLine('مستطیل خیلی کوچیک بود — دوباره امتحان کن', 'err');
        return;
      }
      const frame = await grabFrameAsync();
      if (frame.error) {
        logLine(frame.error, 'err');
        return;
      }
      const p0 = clientToFrame(frame, x1, y1);
      const p1 = clientToFrame(frame, x1 + w, y1 + h);
      if (mode === 'tree') {
        const tpl = TreeBotLib.cropGray(frame.gray, p0.x, p0.y, p1.x - p0.x, p1.y - p0.y);
        state.template = tpl;
        state.templateAt = Date.now();
        state.templatePng = cropToDataURL(frame, p0.x, p0.y, p1.x - p0.x, p1.y - p0.y);
        saveJSON(TPL_KEY, {
          w: tpl.w,
          h: tpl.h,
          g: Array.from(tpl.g, (v) => Math.round(v)),
          png: state.templatePng,
        });
        logLine(`قالب درخت ثبت شد: ${tpl.w}×${tpl.h} پیکسل`, 'ok');
        renderInfo();
      } else {
        state.settings.regionMode = 'custom';
        state.settings.customRegion = {
          rx: (p0.x) / frame.w,
          ry: (p0.y) / frame.h,
          rw: (p1.x - p0.x) / frame.w,
          rh: (p1.y - p0.y) / frame.h,
        };
        saveJSON(STORE_KEY, state.settings);
        logLine(`محدوده ثبت شد: ${Math.round(state.settings.customRegion.rw * 100)}٪ × ${Math.round(state.settings.customRegion.rh * 100)}٪ از کانواس`, 'ok');
      }
    };
    pickLayer.addEventListener('mousedown', onDown);
    pickLayer.addEventListener('mousemove', onMove);
    pickLayer.addEventListener('mouseup', onUp);
    document.addEventListener('keydown', onKey);
  }

  function cropToDataURL(frame, fx, fy, fw, fh) {
    try {
      const off = document.createElement('canvas');
      off.width = Math.max(1, Math.round(fw));
      off.height = Math.max(1, Math.round(fh));
      const ctx = off.getContext('2d');
      ctx.drawImage(frame.canvas, fx, fy, fw, fh, 0, 0, off.width, off.height);
      return off.toDataURL('image/png');
    } catch (e) {
      return null;
    }
  }

  function restoreTemplate() {
    const saved = loadJSON(TPL_KEY, null);
    if (saved && saved.w && saved.h && saved.g) {
      state.template = { w: saved.w, h: saved.h, g: Float32Array.from(saved.g) };
      state.templatePng = saved.png || null;
      logLine(`قالب ذخیره‌شده بارگذاری شد (${saved.w}×${saved.h})`);
    }
    renderInfo();
  }

  // ─────────────────────────── نمایش ───────────────────────────

  function resizeOverlay() {
    if (!overlay) return;
    overlay.width = window.innerWidth;
    overlay.height = window.innerHeight;
  }

  function clearOverlay() {
    if (!overlay) return;
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
  }

  function drawMatches(frame, matches) {
    if (!overlay || !state.settings.showOverlay) return;
    resizeOverlay();
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    const r = frame.canvas.getBoundingClientRect();
    const sx = r.width / frame.w;
    const sy = r.height / frame.h;
    ctx.lineWidth = 2;
    ctx.font = 'bold 12px Tahoma, sans-serif';
    matches.forEach((m, i) => {
      const x = r.left + m.x * sx;
      const y = r.top + m.y * sy;
      const w = m.w * sx;
      const h = m.h * sy;
      ctx.strokeStyle = '#4ade80';
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = '#4ade80';
      ctx.beginPath();
      ctx.arc(x + w / 2, y + h / 2, 4, 0, Math.PI * 2);
      ctx.fill();
      const label = `${i + 1}: ${(m.score * 100).toFixed(0)}%`;
      ctx.fillStyle = 'rgba(8,12,16,.8)';
      const tw = ctx.measureText(label).width + 8;
      ctx.fillRect(x, y - 17, tw, 16);
      ctx.fillStyle = '#eaffef';
      ctx.fillText(label, x + 4, y - 5);
    });
  }

  function renderInfo() {
    if (!els.tplinfo) return;
    const t = state.template;
    els.tplinfo.textContent = t ? `قالبِ درخت: ${t.w}×${t.h} پیکسل ✅` : 'قالبِ درخت: انتخاب نشده ❌';
    els.tplimg.src = state.templatePng || 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
    const cv = findGameCanvas();
    els.canvasinfo.textContent = cv
      ? `کانواس: ${cv.width}×${cv.height} (CSS ${Math.round(cv.clientWidth)}×${Math.round(cv.clientHeight)})`
      : 'کانواس: پیدا نشد ❌';
  }

  function renderLog() {
    if (!els.log) return;
    els.log.innerHTML = '';
    for (const item of state.log) {
      const d = document.createElement('div');
      d.textContent = item.t;
      if (item.kind === 'ok') d.className = 'ok';
      if (item.kind === 'err') d.className = 'err';
      els.log.appendChild(d);
    }
  }

  function updateStats(trees) {
    els.s1.textContent = String(state.cycles);
    els.s2.textContent = String(state.clicks);
    els.s3.textContent = String(trees != null ? trees : state.lastMatches.length);
    const dot = els.dot;
    dot.className = 'dot' + (state.paused ? ' paused' : state.running ? ' on' : '');
    const b = els.start;
    if (state.running) {
      b.textContent = '⏹ توقف';
      b.classList.add('danger');
      b.classList.remove('primary');
    } else {
      b.textContent = '▶ شروع';
      b.classList.add('primary');
      b.classList.remove('danger');
    }
  }

  // ─────────────────────────── حلقه‌ی اصلی ───────────────────────────

  function searchRegion(frame) {
    const cfg = state.settings;
    if (cfg.regionMode === 'custom' && cfg.customRegion) {
      const c = cfg.customRegion;
      const x = Math.max(0, Math.round(c.rx * frame.w));
      const y = Math.max(0, Math.round(c.ry * frame.h));
      const w = Math.min(frame.w - x, Math.round(c.rw * frame.w));
      const h = Math.min(frame.h - y, Math.round(c.rh * frame.h));
      if (w > 8 && h > 8) return { x, y, w, h };
    }
    return { x: 0, y: 0, w: frame.w, h: frame.h };
  }

  async function runCycle(dryRun) {
    if (state.busy) return;
    if (state.settings.pauseWhenHidden && document.hidden) {
      logLine('تب مخفیه — این دور رد شد');
      return;
    }
    state.busy = true;
    try {
      const frame = await grabFrameAsync();
      if (frame.error) {
        logLine(frame.error, 'err');
        return;
      }
      if (!state.template) {
        logLine('اول با «انتخاب درخت» یه درخت رو مشخص کن', 'err');
        return;
      }
      const cfg = state.settings;
      const region = searchRegion(frame);
      const sub = TreeBotLib.cropGray(frame.gray, region.x, region.y, region.w, region.h);
      const t0 = performance.now();
      const found = TreeBotLib.findTrees(sub, state.template, {
        threshold: cfg.threshold,
        scales: TreeBotLib.buildScales(cfg.scaleMin, cfg.scaleMax, cfg.scaleStep),
        maxResults: cfg.maxTrees,
      });
      const ms = Math.round(performance.now() - t0);
      const matches = found.map((m) => Object.assign({}, m, {
        x: m.x + region.x,
        y: m.y + region.y,
        center: { x: m.center.x + region.x, y: m.center.y + region.y },
      }));

      state.cycles++;
      state.lastMatches = matches;
      drawMatches(frame, matches);

      if (!matches.length) {
        logLine(`دور ${state.cycles}: درختی پیدا نشد (${ms}ms)`);
        updateStats(0);
        return;
      }

      logLine(`دور ${state.cycles}: 🌳 ${matches.length} درخت پیدا شد (${ms}ms)`, 'ok');
      updateStats(matches.length);

      if (dryRun) {
        logLine('🧪 تست — هیچ کلیکی انجام نشد');
        return;
      }

      let order = matches.slice();
      if (cfg.randomOrder) order = order.sort(() => Math.random() - 0.5);
      for (const m of order) {
        if (!state.running || state.paused) break;
        for (let i = 0; i < cfg.clicksPerTree; i++) {
          const p = clickAt(frame, m.center.x, m.center.y);
          state.clicks++;
          if (i < cfg.clicksPerTree - 1) await sleep(60);
          void p;
        }
        updateStats(matches.length);
        await sleep(Math.max(20, cfg.clickDelayMs));
      }
      updateStats(matches.length);
    } catch (e) {
      logLine('خطا: ' + (e && e.message ? e.message : e), 'err');
    } finally {
      state.busy = false;
    }
  }

  let loopToken = 0;

  async function loop() {
    const token = ++loopToken;
    while (state.running && token === loopToken) {
      const t0 = performance.now();
      await runCycle(false);
      const wait = Math.max(200, state.settings.intervalMs - (performance.now() - t0));
      const until = performance.now() + wait;
      while (state.running && token === loopToken && performance.now() < until) {
        await sleep(Math.min(120, until - performance.now()));
      }
    }
  }

  function startRun() {
    if (!state.template) {
      logLine('اول قالبه! «انتخاب درخت» رو بزن', 'err');
      return;
    }
    state.running = true;
    state.paused = false;
    loopToken++;
    logLine(`▶ شروع — هر ${(state.settings.intervalMs / 1000).toFixed(1)} ثانیه یه دور`, 'ok');
    updateStats();
    loop();
  }

  function stopRun() {
    if (state.running) logLine('⏹ متوقف شد');
    state.running = false;
    state.busy = false;
    loopToken++;
    updateStats();
  }

  function toggleRun() {
    if (state.running) stopRun();
    else startRun();
  }

  // ─────────────────────────── میان‌برها + شروع ───────────────────────────

  document.addEventListener('keydown', (e) => {
    if (e.key === 'F8') {
      e.preventDefault();
      if (!state.running) startRun();
      else {
        state.paused = !state.paused;
        logLine(state.paused ? '⏸ مکث' : '▶️ ادامه');
      }
      updateStats();
    } else if (e.key === 'F9') {
      e.preventDefault();
      stopRun();
    }
  });

  window.TreeBot = {
    state,
    lib: TreeBotLib,
    start: startRun,
    stop: stopRun,
    test: () => runCycle(true),
    pick: () => startPick('tree'),
    grab: grabFrameAsync,
    findTrees: (opts) => TreeBotLib.findTrees(grabFrame().gray, state.template, opts),
  };

  function boot() {
    if (document.getElementById('treebot-host')) return;
    buildUI();
    setInterval(renderInfo, 3000);
    console.log('%c🌳 TreeBot ready — window.TreeBot', 'color:#4ade80;font-weight:bold');
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(boot, 800);
  } else {
    window.addEventListener('DOMContentLoaded', () => setTimeout(boot, 800));
  }
})();
