#!/usr/bin/env python3
"""Sweep the GLC-4 quantisation parameter (grid width = "q") over real fonts.

For every (font, grid) pair we measure
  * WOFF2 size of a 3,000 character subset and of the whole font
  * time to build the intermediate TTF and to encode the WOFF2
  * geometric error (Hausdorff distance between contour point sets)
  * visual noise: changed pixels, mean/RMS/max pixel difference, PSNR

Outputs: measure/out/glc_sweep.json
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "sweep"
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402
from cff2glyf import cff_to_glyf  # noqa: E402
import freetype  # noqa: E402

N_CHARS = 3000
GRIDS = [0, 2, 4, 8, 16, 32]
SIZES = (16, 24, 32, 48)

FONTS = [
    ("Noto Sans JP", "measure/out/NotoSansJP-Regular.ttf", "ja", False),
    ("M PLUS 1p", "fonts/MPLUS1p-Regular.ttf", "ja", False),
    ("Nanum Gothic", "fonts/NanumGothic-Regular.ttf", "ko", False),
    ("Source Han Sans JP", "fonts/SourceHanSansJP-Regular.otf", "ja", True),
]


def top_chars(lang: str, n: int):
    corpus = json.loads((ROOT / "measure" / "web" / "corpus.json").read_text(encoding="utf-8"))
    tf = Counter()
    for r in corpus:
        if r.get("lang") != lang or "text" not in r:
            continue
        for c in r["text"]:
            if not c.isspace():
                tf[ord(c)] += 1
    return [cp for cp, _ in tf.most_common(n)]


def subset_woff2(src: Path, dst: Path, chars, brotli_q=None):
    cmd = [sys.executable, "-m", "fontTools.subset", str(src),
           "--unicodes=" + ",".join(f"U+{c:04X}" for c in chars),
           "--flavor=woff2", "--no-hinting", "--layout-features=*",
           "--name-IDs=1,2,3,4,5,6", "--name-languages=*",
           "--notdef-outline", "--recalc-bounds", "--drop-tables+=vhea,vmtx",
           f"--output-file={dst}"]
    if brotli_q:
        cmd.append(f"--compress-level={brotli_q}")
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return dst.stat().st_size, round(time.time() - t0, 2)


def render(face, text: str, px: int):
    face.set_char_size(px * 64)
    rows = []
    pen = 0
    for ch in text:
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bm = face.glyph.bitmap
        rows.append((pen, face.glyph.bitmap_left >> 6, face.glyph.bitmap_top >> 6, bm.width, bm.rows, bm.buffer))
        pen += face.glyph.advance.x >> 6
    width = pen + 4
    height = px * 2
    canvas = bytearray(width * height)
    for (pen_x, left, top, w, h, buf) in rows:
        for row in range(h):
            y = px + top - row
            if not (0 <= y < height):
                continue
            for col in range(w):
                x = pen_x + left + col
                if 0 <= x < width:
                    i = y * width + x
                    if buf[row * w + col] > canvas[i]:
                        canvas[i] = buf[row * w + col]
    return canvas, width, height


def noise(a, b, w, h):
    diff = 0
    total = 0
    worst = 0
    se = 0
    n = min(len(a), len(b))
    for i in range(n):
        d = abs(a[i] - b[i])
        total += 1
        se += d * d
        if d:
            diff += 1
            if d > worst:
                worst = d
    total = n
    rms = math.sqrt(se / total) if total else 0.0
    psnr = 20 * math.log10(255.0 / rms) if rms > 0 else float("inf")
    return {"changed_pct": round(100 * diff / total, 4), "mean_abs_diff": round(total and sum(
        abs(a[i] - b[i]) for i in range(len(a))) / total, 4),
        "rms": round(rms, 4), "max_diff": worst,
        "psnr_db": round(psnr, 2)}


def contour_sets(path: Path):
    from fontTools.ttLib import TTFont
    font = TTFont(str(path), lazy=False)
    glyf = font["glyf"]
    out = {}
    for gn in font.getGlyphOrder():
        if gn not in glyf.glyphs:
            continue
        g = glyf[gn]
        if g.numberOfContours <= 0:
            continue
        co = [tuple(c) for c in g.coordinates]
        ends = list(getattr(g, "endPtsOfContours", None) or getattr(g, "endPts", []))
        if callable(ends):
            ends = ends()
        cs, s = [], 0
        for e in ends:
            cs.append(sorted(co[s:e + 1]))
            s = e + 1
        out[gn] = sorted(cs)
    font.close()
    return out


def shape_error(a: Path, b: Path):
    A, B = contour_sets(a), contour_sets(b)

    def one_way(p, q):
        return max(min(max(abs(x1 - x2), abs(y1 - y2)) for (x2, y2) in q) for (x1, y1) in p)

    worst = 0
    total = 0.0
    n = 0
    for gn, ca in A.items():
        cb = B.get(gn)
        if not cb:
            continue
        for pa in ca:
            d = min(one_way(pa, pb) for pb in cb)
            total += d
            n += 1
            worst = max(worst, d)
        for pb in cb:
            d = min(one_way(pb, pa) for pa in ca)
            total += d
            n += 1
            worst = max(worst, d)
    return worst, round(total / n, 4) if n else 0.0


def main():
    corpus = json.loads((ROOT / "measure" / "web" / "corpus.json").read_text(encoding="utf-8"))
    tf = Counter()
    for r in corpus:
        if r.get("lang") != "ja" or "text" not in r:
            continue
        for c in r["text"]:
            if not c.isspace():
                tf[ord(c)] += 1
    text = "".join(chr(c) for c, _ in tf.most_common(120))

    rows = []
    for family, rel, lang, is_cff in FONTS:
        src = ROOT / rel
        if not src.exists():
            continue
        chars = top_chars(lang, N_CHARS)
        tag = family.replace(" ", "_")
        cur = src
        if is_cff:
            ttf = WORK / f"{tag}_glyf.ttf"
            if not ttf.exists():
                cff_to_glyf(str(src), str(ttf), max_err_ratio=0.001)
            cur = ttf
        base_face = freetype.Face(str(cur))
        for grid in GRIDS:
            ttf = WORK / f"{tag}_q{grid}.ttf"
            t0 = time.time()
            if not ttf.exists():
                process_font(str(cur), str(ttf), canonical=False, grid=grid)
            prep_s = round(time.time() - t0, 2)
            w = WORK / f"{tag}_q{grid}.woff2"
            size, enc_s = subset_woff2(ttf, w, chars)
            worst, mean_err = shape_error(cur, ttf)
            face = freetype.Face(str(ttf))
            noise_rows = []
            for px in SIZES:
                ca, w1, h1 = render(base_face, text, px)
                cb, w2, h2 = render(face, text, px)
                noise_rows.append({"px": px, **noise(ca, cb, w1, h1)})
            rows.append({
                "font": family, "grid": grid,
                "subset_woff2_bytes": size, "subset_encode_s": enc_s, "prep_s": prep_s,
                "max_err_units": worst, "mean_err_units": mean_err,
                "noise": noise_rows,
            })
            print(f"{family:20s} grid={grid:2d} woff2={size/1024:8.1f} KiB enc={enc_s:5.1f}s "
                  f"prep={prep_s:5.1f}s err<={worst:3d}u "
                  f"px24: chg={noise_rows[1]['changed_pct']:6.3f}% psnr={noise_rows[1]['psnr_db']:5.1f}dB",
                  flush=True)
            (OUT / "glc_sweep.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "glc_sweep.json")


if __name__ == "__main__":
    main()
