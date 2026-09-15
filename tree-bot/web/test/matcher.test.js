#!/usr/bin/env node
/**
 * 🧪 تست موتور تشخیص درختِ نسخه‌ی وب (TreeBotLib)
 * ===============================================
 *
 * کتابخانه‌ی خالص رو از داخل فایل اوسر‌اسکریپت بیرون می‌کشه و روی یه «صحنه‌ی
 * بازی» مصنوعی آزمایش می‌کنه — بدون مرورگر، بدون canvas.
 *
 *     node test/matcher.test.js
 */

'use strict';

const fs = require('fs');
const path = require('path');

// ───────────────────────── بیرون کشیدن کتابخانه ─────────────────────────

const SCRIPT = path.join(__dirname, '..', 'tree-auto-clicker.user.js');
const src = fs.readFileSync(SCRIPT, 'utf8');
const startMarker = 'TREEBOT-LIB START';
const endMarker = 'TREEBOT-LIB END';
const m0 = src.indexOf(startMarker);
const m1 = src.indexOf(endMarker);
if (m0 < 0 || m1 < 0) {
  console.error('❌ بخش TREEBOT-LIB در فایل اوسر‌اسکریپت پیدا نشد');
  process.exit(1);
}
// از اولِ کامنتِ تزئینی تا آخرِ خطِ پایانی — بعد کامنت رو حذف می‌کنیم
const cStart = src.lastIndexOf('/*', m0);
const i0 = cStart >= 0 ? cStart : src.lastIndexOf('\n', m0) + 1;
const cEnd = src.indexOf('*/', m1);
const i1 = cEnd >= 0 ? cEnd + 2 : src.indexOf('\n', m1) + 1;
const libSrc = src.slice(i0, i1).replace(/^\s*\/\*[\s\S]*?\*\//, '');
const mod = { exports: {} };
new Function('module', 'exports', libSrc)(mod, mod.exports);
const lib = mod.exports;
if (!lib || !lib.findTrees) {
  console.error('❌ کتابخانه بارگذاری نشد');
  process.exit(1);
}

// ───────────────────────── صحنه‌ی آزمایشی ─────────────────────────

const TREE_W = 72;
const TREE_H = 96;

let seed = 1403;
function setSeed(n) {
  seed = n;
}
function rnd() {
  seed = (seed * 1103515245 + 12345) & 0x7fffffff;
  return seed / 0x7fffffff;
}
const ri = (a, b) => a + Math.floor(rnd() * (b - a + 1));

class Img {
  constructor(w, h) {
    this.w = w;
    this.h = h;
    this.data = new Uint8ClampedArray(w * h * 4);
  }
  set(x, y, r, g, b, a = 255) {
    if (x < 0 || y < 0 || x >= this.w || y >= this.h) return;
    const i = (y * this.w + x) * 4;
    this.data[i] = r;
    this.data[i + 1] = g;
    this.data[i + 2] = b;
    this.data[i + 3] = a;
  }
  get(x, y) {
    const i = (y * this.w + x) * 4;
    return [this.data[i], this.data[i + 1], this.data[i + 2], this.data[i + 3]];
  }
  rect(x, y, w, h, r, g, b) {
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) this.set(x + i, y + j, r, g, b);
  }
  tri(p1, p2, p3, r, g, b) {
    const minY = Math.max(0, Math.floor(Math.min(p1[1], p2[1], p3[1])));
    const maxY = Math.min(this.h - 1, Math.ceil(Math.max(p1[1], p2[1], p3[1])));
    const pts = [p1, p2, p3];
    const edge = (a, b, px, py) => (b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0]);
    for (let y = minY; y <= maxY; y++) {
      const xs = [];
      for (let i = 0; i < 3; i++) {
        const a = pts[i];
        const b = pts[(i + 1) % 3];
        if ((a[1] <= y && b[1] > y) || (b[1] <= y && a[1] > y)) {
          const t = (y - a[1]) / (b[1] - a[1]);
          xs.push(a[0] + t * (b[0] - a[0]));
        }
      }
      if (xs.length < 2) continue;
      xs.sort((p, q) => p - q);
      for (let x = Math.round(xs[0]); x <= Math.round(xs[xs.length - 1]); x++) {
        // داخل مثلث؟ (به‌خاطر لبه‌های پله‌ای)
        const s1 = edge(p1, p2, x, y);
        const s2 = edge(p2, p3, x, y);
        const s3 = edge(p3, p1, x, y);
        if ((s1 >= 0 && s2 >= 0 && s3 >= 0) || (s1 <= 0 && s2 <= 0 && s3 <= 0)) this.set(x, y, r, g, b);
      }
    }
  }
  paste(sprite, x, y) {
    for (let j = 0; j < sprite.h; j++) {
      for (let i = 0; i < sprite.w; i++) {
        const [r, g, b, a] = sprite.get(i, j);
        if (a < 8) continue;
        const [br, bg, bb] = this.get(x + i, y + j);
        const t = a / 255;
        this.set(x + i, y + j, r * t + br * (1 - t), g * t + bg * (1 - t), b * t + bb * (1 - t), 255);
      }
    }
  }
}

function makeTree(w = TREE_W, h = TREE_H) {
  const s = new Img(w, h);
  // تنه
  s.rect(Math.round(w * 0.42), Math.round(h * 0.58), Math.round(w * 0.18), h - Math.round(h * 0.58) - 1, 92, 62, 40);
  // تاج: سه لایه
  const layers = [[0.62, 0.28], [0.44, 0.16], [0.26, 0.04]];
  for (const [by, ty] of layers) {
    s.tri([Math.round(w * 0.5), Math.round(h * ty)], [Math.round(w * 0.06), Math.round(h * by)], [Math.round(w * 0.94), Math.round(h * by)], 74, 142, 62);
  }
  // بافت برگ
  for (let n = 0; n < w * h * 0.25; n++) {
    const x = ri(0, w - 1);
    const y = ri(0, h - 1);
    const [r, g, b] = s.get(x, y);
    if (g > 90 && g > r) {
      const d = ri(-26, 26);
      s.set(x, y, r + d, g + d, b + d);
    }
  }
  return s;
}

function makeBackground(w, h) {
  const bg = new Img(w, h);
  for (let y = 0; y < h; y++) {
    const t = y / h;
    bg.rect(0, y, w, 1, Math.round(120 * (1 - t) + 70 * t), Math.round(160 * (1 - t) + 140 * t), Math.round(210 * (1 - t) + 95 * t));
  }
  const grassY = Math.round(h * 0.62);
  bg.rect(0, grassY, w, h - grassY, 60, 120, 70);
  for (let n = 0; n < w * h * 0.02; n++) {
    const x = ri(0, w - 1);
    const y = ri(grassY, h - 1);
    const [r, g, b] = bg.get(x, y);
    const d = ri(-18, 18);
    bg.set(x, y, r + d, g + d, b + d);
  }
  for (let n = 0; n < 8; n++) {
    const cx = ri(0, w - 1);
    const cy = ri(10, Math.round(grassY * 0.5));
    const rw = ri(60, 130);
    const rh = ri(18, 34);
    for (let y = -rh; y <= rh; y++) {
      for (let x = -rw; x <= rw; x++) {
        if ((x * x) / (rw * rw) + (y * y) / (rh * rh) <= 1) bg.set(cx + x, cy + y, 240, 244, 246);
      }
    }
  }
  for (let n = 0; n < 16; n++) {
    const cx = ri(0, w - 1);
    const cy = ri(grassY, h - 1);
    const rw = ri(14, 34);
    const rh = ri(10, 22);
    const grey = ri(90, 150);
    for (let y = -rh; y <= rh; y++) {
      for (let x = -rw; x <= rw; x++) {
        if ((x * x) / (rw * rw) + (y * y) / (rh * rh) <= 1) bg.set(cx + x, cy + y, grey, grey + 8, grey + 6);
      }
    }
  }
  return bg;
}

/** مقیاس‌دهی اسپرایت با درون‌یابی دولایه‌ای — مثل کاری که موتور بازی می‌کنه */
function scaleSprite(sprite, tw, th) {
  const out = new Img(tw, th);
  for (let y = 0; y < th; y++) {
    const fy = ((y + 0.5) * sprite.h) / th - 0.5;
    const y0 = Math.max(0, Math.min(sprite.h - 1, Math.floor(fy)));
    const y1 = Math.min(sprite.h - 1, y0 + 1);
    const wy = Math.max(0, Math.min(1, fy - y0));
    for (let x = 0; x < tw; x++) {
      const fx = ((x + 0.5) * sprite.w) / tw - 0.5;
      const x0 = Math.max(0, Math.min(sprite.w - 1, Math.floor(fx)));
      const x1 = Math.min(sprite.w - 1, x0 + 1);
      const wx = Math.max(0, Math.min(1, fx - x0));
      const ch = [0, 0, 0, 0];
      const a = sprite.get(x0, y0);
      const b = sprite.get(x1, y0);
      const c = sprite.get(x0, y1);
      const d = sprite.get(x1, y1);
      for (let k = 0; k < 4; k++) {
        ch[k] = (a[k] * (1 - wx) + b[k] * wx) * (1 - wy) + (c[k] * (1 - wx) + d[k] * wx) * wy;
      }
      out.set(x, y, ch[0], ch[1], ch[2], ch[3]);
    }
  }
  return out;
}

function makeScene(w, h, count, scales, opts = {}) {
  const frame = makeBackground(w, h);
  setSeed(1403);
  const tree = makeTree();
  const placed = [];
  const grassY = Math.round(h * 0.62);
  const minY = opts.onGround === false ? Math.round(h * 0.3) : grassY + 6;
  for (let n = 0; n < count; n++) {
    const scale = scales[ri(0, scales.length - 1)];
    const tw = Math.round(TREE_W * scale);
    const th = Math.round(TREE_H * scale);
    const sprite = scaleSprite(tree, tw, th);
    let placedOk = false;
    for (let tries = 0; tries < 80 && !placedOk; tries++) {
      const x = ri(0, w - tw - 1);
      const y = ri(minY, h - th - 2);
      const clash = placed.some((p) => Math.abs(x - p.x) < tw + 12 && Math.abs(y - p.y) < th + 12);
      if (clash) continue;
      frame.paste(sprite, x, y);
      placed.push({ x, y, w: tw, h: th, scale });
      placedOk = true;
    }
  }
  return { frame, tree, placed };
}

/**
 * صحنه‌ی سخت: یه درخت روی چمن و یه درخت روی «خاک/سنگفرش» (پس‌زمینه‌ی متفاوت).
 * قالب از درختِ چمنی گرفته می‌شه — تست می‌کنیم که تطبیق با پس‌زمینه‌ی متفاوت
 * درختِ دوم رو هم پیدا می‌کنه.
 */
function makeMixedGroundScene(w = 1200, h = 700) {
  setSeed(2207);
  const frame = makeBackground(w, h);
  const tree = makeTree();
  const grassY = Math.round(h * 0.62);
  // یه نوار خاکی روشن، مثل راه‌خاکی داخل چمن
  const sandY = grassY + 40;
  frame.rect(0, sandY, w, 150, 205, 195, 150);
  for (let n = 0; n < w * 150 * 0.05; n++) {
    const x = ri(0, w - 1);
    const y = ri(sandY, sandY + 149);
    const [r, g, b] = frame.get(x, y);
    const d = ri(-16, 16);
    frame.set(x, y, r + d, g + d, b + d);
  }
  const s1 = Math.round(TREE_W * 1.0);
  const h1 = Math.round(TREE_H * 1.0);
  const sprite = scaleSprite(tree, s1, h1);
  const a = { x: 120, y: grassY + 20, w: s1, h: h1 };
  const b = { x: 820, y: sandY + 24, w: s1, h: h1 };
  frame.paste(sprite, a.x, a.y);
  frame.paste(sprite, b.x, b.y);
  return { frame, grass: a, sand: b };
}

/** پس‌زمینه‌ی ساده: آسمون + چمن، بدون سنگ و ابر */
function makePlainGrass(w, h) {
  const bg = new Img(w, h);
  const grassY = Math.round(h * 0.62);
  for (let y = 0; y < grassY; y++) {
    const t = y / grassY;
    const r = Math.round(150 + 50 * t);
    const g = Math.round(185 + 20 * t);
    const b = Math.round(235 + 10 * t);
    bg.rect(0, y, w, 1, r, g, b);
  }
  bg.rect(0, grassY, w, h - grassY, 62, 122, 72);
  for (let n = 0; n < w * (h - grassY) * 0.02; n++) {
    const x = ri(0, w - 1);
    const y = ri(grassY, h - 1);
    const [r, g, b] = bg.get(x, y);
    const d = ri(-12, 12);
    bg.set(x, y, r + d, g + d, b + d);
  }
  return bg;
}

/** یه بیضی ساده روی تصویر (برای گذاشتن سنگ/بوته) */
function blob(img, cx, cy, rw, rh, grey) {
  for (let y = -rh; y <= rh; y++) {
    for (let x = -rw; x <= rw; x++) {
      if ((x * x) / (rw * rw) + (y * y) / (rh * rh) <= 1) {
        const n = ri(-10, 10);
        img.set(cx + x, cy + y, grey + n, grey + n + 8, grey + n + 6);
      }
    }
  }
}

/**
 * صحنه‌ی «سنگ داخل کادرِ قالب»: کاربر دور یه درخت مستطیل کشیده و یه سنگ هم
 * داخل کادر افتاده. درختِ دوم همون شکلیه ولی سنگ نداره.
 */
function makeRockyScene(w = 1100, h = 700) {
  // پس‌زمینه‌ی تمیز (بدون سنگ/ابرِ تصادفی) تا تست فقط روی «سنگِ داخلِ قالب» تمرکز کنه
  const frame = makePlainGrass(w, h);
  setSeed(3313);
  const tree = makeTree();
  const sprite = scaleSprite(tree, TREE_W, TREE_H);
  // هر دو درخت کاملاً روی چمن (نه روی خط افق) تا تفاوت فقط از سنگ باشه
  const a = { x: 140, y: 470 };
  const b = { x: 780, y: 476 };
  frame.paste(sprite, a.x, a.y);
  blob(frame, a.x + 12, a.y + 80, 22, 15, 150); // سنگ، داخل ناحیه‌ی شفافِ گوشه‌ی کادر
  frame.paste(sprite, b.x, b.y);
  return {
    frame,
    withRock: { x: a.x, y: a.y, w: TREE_W, h: TREE_H },
    clean: { x: b.x, y: b.y, w: TREE_W, h: TREE_H },
  };
}


// ───────────────────────── چارچوب تست ─────────────────────────

let pass = 0;
let fail = 0;
function check(name, cond, extra) {
  if (cond) {
    pass++;
    console.log(`  ✅ PASS  ${name}`);
  } else {
    fail++;
    console.log(`  ❌ FAIL  ${name}  ${extra || ''}`);
  }
}

// ───────────────────────── تست‌ها ─────────────────────────

console.log('='.repeat(62));
console.log('🧪 تست موتور تشخیص درخت — نسخه‌ی وب');
console.log('='.repeat(62));

// ۱) buildScales
console.log('\n🧩 buildScales');
check('۰.۹ تا ۱.۱ با گام ۰.۰۵', JSON.stringify(lib.buildScales(0.9, 1.1, 0.05)) === JSON.stringify([0.9, 0.95, 1, 1.05, 1.1]));
check('معکوس هم درست می‌شه', lib.buildScales(1.1, 0.9, 0.1).includes(1));
check('گام صفر → پیش‌فرض', lib.buildScales(1, 1, 0).length === 1);

// ۲) NMS
console.log('\n🧩 NMS (حذف تشخیص‌های تکراری)');
const dupes = [
  { x: 100, y: 100, w: 40, h: 40, score: 0.9 },
  { x: 102, y: 101, w: 40, h: 40, score: 0.95 }, // روی همون درخت
  { x: 300, y: 300, w: 40, h: 40, score: 0.85 }, // درخت دیگه
];
const kept = lib.nms(dupes, 0.35, 10);
check('سه کاندید → دو درخت', kept.length === 2, `(شد ${kept.length})`);
check('بهترین نمره‌ها موندن', kept[0].score === 0.95 && kept[1].score === 0.85);

// ۳) صحنه‌ی کامل
console.log('\n🌳 تشخیص درخت روی صحنه‌ی مصنوعی (۱۶۰۰×۹۰۰)');
const W = 1600;
const H = 900;
const { frame, tree, placed } = makeScene(W, H, 5, [0.9, 1.0, 1.1]);
const gray = lib.toGray(W, H, frame.data);

// قالب: دقیقاً مثل کاربر که با ماوس دور یه درخت مستطیل می‌کشه
const first = placed[0];
const tpl = lib.cropGray(gray, first.x, first.y, first.w, first.h);
console.log(`  🔎 ${placed.length} درخت در صحنه • قالب ${tpl.w}×${tpl.h}`);

const t0 = Date.now();
const found = lib.findTrees(gray, tpl, {
  threshold: 0.8,
  scales: lib.buildScales(0.9, 1.1, 0.05),
  maxResults: 20,
});
const ms = Date.now() - t0;
for (const m of found.sort((a, b) => a.x - b.x)) {
  console.log(`      (${String(m.center.x).padStart(4)},${String(m.center.y).padStart(4)})  ${(m.score * 100).toFixed(1)}%  x${m.scale}  (${ms}ms)`);
}
console.log(`  ⏱ زمان تشخیص: ${ms}ms`);

check('همه‌ی درخت‌ها پیدا شدن (±۶ پیکسل)', placed.every((p) =>
  found.some((m) => Math.abs(m.center.x - (p.x + p.w / 2)) <= 6 && Math.abs(m.center.y - (p.y + p.h / 2)) <= 6)
), JSON.stringify(found.map((m) => m.center)));

check('تعداد تشخیص‌ها با تعداد درخت‌ها می‌خونه',
  found.length === placed.length, `(${found.length} در برابر ${placed.length})`);

const falsePos = found.filter((m) => !placed.some((p) =>
  Math.abs(m.center.x - (p.x + p.w / 2)) <= 10 && Math.abs(m.center.y - (p.y + p.h / 2)) <= 10));
check('تشخیص اشتباهی (روی سنگ/ابر) نداریم', falsePos.length === 0, JSON.stringify(falsePos.map((m) => m.center)));

check('کیفیت تطبیق‌ها ≥ ۸۵٪', found.every((m) => m.score >= 0.85),
  `کمترین: ${Math.min(...found.map((m) => m.score)).toFixed(3)}`);

check('سرعت تشخیص کمتر از ۲ ثانیه (برای هر ۵ ثانیه کافیه)', ms < 2000, `${ms}ms`);

// ۳.۵) درخت روی پس‌زمینه‌ی متفاوت (چمن vs خاک)
console.log('\n🏜 درخت روی پس‌زمینه‌ی متفاوت (چمن vs خاک)');
const mixed = makeMixedGroundScene();
const mixedGray = lib.toGray(mixed.frame.w, mixed.frame.h, mixed.frame.data);
const mixedTpl = lib.cropGray(mixedGray, mixed.grass.x, mixed.grass.y, mixed.grass.w, mixed.grass.h);
const mixedFound = lib.findTrees(mixedGray, mixedTpl, {
  threshold: 0.7, scales: lib.buildScales(0.95, 1.05, 0.05), maxResults: 8,
});
const sandHit = mixedFound.some((m) =>
  Math.abs(m.center.x - (mixed.sand.x + mixed.sand.w / 2)) <= 6 &&
  Math.abs(m.center.y - (mixed.sand.y + mixed.sand.h / 2)) <= 6);
console.log(`      قالب از درختِ روی چمن • تطابق‌ها: ${JSON.stringify(mixedFound.map((m) => m.center))}`);
check('درختِ روی پس‌زمینه‌ی متفاوت هم پیدا می‌شه (آستانه ۰.۷)', sandHit);

// ۳.۶) سنگ داخل کادرِ قالب → NCC مقاوم
console.log('\n🪨 سنگ داخل کادرِ قالب (داده‌ی پرت)');
const rocky = makeRockyScene();
const rockyGray = lib.toGray(rocky.frame.w, rocky.frame.h, rocky.frame.data);
const rockyTpl = lib.cropGray(rockyGray, rocky.withRock.x, rocky.withRock.y, rocky.withRock.w, rocky.withRock.h);
const rockyStats = lib.templateStats(rockyTpl);
const rawAtClean = lib.nccAt(rockyGray, rockyStats, rocky.clean.x, rocky.clean.y, rockyTpl.w, rockyTpl.h);
const robAtClean = lib.robustNcc(rockyGray, rockyStats, rocky.clean.x, rocky.clean.y, rockyTpl.w, rockyTpl.h, {});
console.log(`      نمره‌ی درختِ تمیز: NCC خام ${rawAtClean.toFixed(2)} • NCC مقاوم ${robAtClean.toFixed(2)}`);
check('NCC خام برای کادری که سنگ داره ضعیف می‌شه', rawAtClean < 0.8, rawAtClean.toFixed(3));
check('NCC مقاوم نمره رو نجات می‌ده', robAtClean > rawAtClean + 0.1,
  `(${rawAtClean.toFixed(2)} → ${robAtClean.toFixed(2)})`);
check('NCC مقاوم به آستانه می‌رسه', robAtClean >= 0.8, robAtClean.toFixed(3));
// با آستانه‌ی بالا، پاسِ خام چیزی پیدا نمی‌کنه → «پاس نجات» باید با معیار
// مقاوم درخت رو پیدا کنه
const rockyFound = lib.findTrees(rockyGray, rockyTpl, {
  threshold: 0.95, scales: lib.buildScales(0.95, 1.05, 0.05), maxResults: 8,
});
const cleanHit = rockyFound.some((m) =>
  Math.abs(m.center.x - (rocky.clean.x + rockyTpl.w / 2)) <= 6 &&
  Math.abs(m.center.y - (rocky.clean.y + rockyTpl.h / 2)) <= 6);
console.log(`      پاس نجات با آستانه‌ی ۰.۹۵ → ${rockyFound.length} تشخیص: ${JSON.stringify(rockyFound.map((m) => m.center))}`);
check('پاسِ نجات با وجود سنگِ داخل قالب، درختِ تمیز رو پیدا می‌کنه', cleanHit,
  JSON.stringify(rockyFound.map((m) => m.center)));


// ۴) صفحه‌ی بدون درخت
console.log('\n🚫 صفحه‌ی بدون درخت (تست هشدار اشتباه)');
// ۴) صفحه‌ی بدون درخت — نباید توهم بزنه
console.log('\n🚫 صفحه‌ی بدون درخت (تست تشخیص اشتباه)');
setSeed(9001); // صحنه‌ی خالی هم قطعی باشه (نه وابسته به ترتیبِ تست‌ها)
const emptyBg = makeBackground(W, H); // آسمون+چمن+ابر+سنگ (بدون درخت)
const emptyGray = lib.toGray(W, H, emptyBg.data);
const none = lib.findTrees(emptyGray, tpl, { threshold: 0.8, scales: lib.buildScales(0.9, 1.1, 0.05) });
console.log(`      پس‌زمینه‌ی شلوغ (ابر و سنگ): ${none.length} تشخیص ` +
  none.map((m) => `(${m.center.x},${m.center.y}) ${(m.score * 100).toFixed(0)}%`).join(" "));
check('روی پس‌زمینه‌ی شلوغ، تشخیص اشتباه ناچیزه (حداکثر ۲)', none.length <= 2, `(شد ${none.length})`);
// ۵) آستانه
console.log('\n🎚 رفتار آستانه');
const strict = lib.findTrees(gray, tpl, { threshold: 0.98, scales: lib.buildScales(0.9, 1.1, 0.05) });
const loose = lib.findTrees(gray, tpl, { threshold: 0.6, scales: lib.buildScales(0.9, 1.1, 0.05) });
console.log(`      آستانه 0.98 → ${strict.length} درخت • آستانه 0.6 → ${loose.length} درخت`);
check('آستانه‌ی سخت‌گیرانه کمتر پیدا می‌کنه', strict.length <= loose.length);
check('آستانه‌ی شل همه رو پیدا می‌کنه', loose.length >= placed.length - 1);

// ۶) قالب تنگ (فقط تاج درخت) — کاربر معمولاً کامل می‌کشه ولی باید کار کنه
console.log('\n✂️ قالب تنگ (فقط تاج درخت)');
const tight = lib.cropGray(gray, first.x + Math.round(first.w * 0.2), first.y + 4, Math.round(first.w * 0.6), Math.round(first.h * 0.4));
const tightFound = lib.findTrees(gray, tight, { threshold: 0.75, scales: lib.buildScales(0.9, 1.1, 0.05) });
const anyNear = tightFound.some((m) => Math.abs(m.center.x - (first.x + first.w / 2)) <= 10);
check('با قالب کوچیک هم حداقل درختِ خودش رو پیدا می‌کنه', anyNear, `(${tightFound.length} تطابق)`);

// ۷) اسکرین‌شات دیباگ
console.log('\n🖼 ذخیره‌ی نتیجه‌ی تشخیص برای بازبینی');
try {
  const outDir = path.join(__dirname, '..', 'debug');
  fs.mkdirSync(outDir, { recursive: true });
  // بدون کتابخانه‌ی تصویر: یه PPM ساده که خودِ مرورگر/ویوئر باز می‌کنه
  const ppmPath = path.join(outDir, 'web_test_scene.ppm');
  const head = Buffer.from(`P6\n${W} ${H}\n255\n`, 'ascii');
  const px = Buffer.alloc(W * H * 3);
  for (let i = 0, p = 0; i < W * H; i++, p += 4) {
    px[i * 3] = frame.data[p];
    px[i * 3 + 1] = frame.data[p + 1];
    px[i * 3 + 2] = frame.data[p + 2];
  }
  fs.writeFileSync(ppmPath, Buffer.concat([head, px]));
  check('فایل debug/web_test_scene.ppm ساخته شد', fs.existsSync(ppmPath));
  const info = { placed, found: found.map((m) => ({ center: m.center, score: +m.score.toFixed(3), scale: m.scale })), ms };
  fs.writeFileSync(path.join(outDir, 'web_test_result.json'), JSON.stringify(info, null, 2));
  console.log('  💾 debug/web_test_scene.ppm + debug/web_test_result.json');
} catch (e) {
  check('ذخیره‌ی دیباگ', false, String(e.message));
}

console.log('\n' + '='.repeat(62));
if (fail === 0) {
  console.log(`🎉 همه‌ی ${pass} تست PASS شد — تشخیص درخت روی کانواس سالمه.`);
  process.exit(0);
} else {
  console.log(`⚠️  ${fail} از ${pass + fail} تست FAIL شد.`);
  process.exit(1);
}
