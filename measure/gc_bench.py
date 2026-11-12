#!/usr/bin/env python3
"""Benchmark of the GLC method (canonicalise + quantise) against plain WOFF2.

Variants (all with hinting removed so that the comparison is purely geometric):
  ref        untouched outlines            (the WOFF2 baseline)
  canon      canonical contour order       (lossless)
  canon_gN   canonical + N-unit lattice    (lossy, error measured)

Outputs: measure/out/gc_bench.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "gc"
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402

FONTS = [
    ("Noto Sans JP", "measure/out/NotoSansJP-Regular.ttf", "ja"),
    ("M PLUS 1p", "fonts/MPLUS1p-Regular.ttf", "ja"),
    ("Zen Kaku Gothic New", "fonts/ZenKakuGothicNew-Regular.ttf", "ja"),
    ("Nanum Gothic", "fonts/NanumGothic-Regular.ttf", "ko"),
]
VARIANTS = [("ref", False, 0), ("canon", True, 0), ("canon_g1", True, 1),
            ("canon_g2", True, 2), ("canon_g4", True, 4), ("canon_g8", True, 8),
            ("canon_g16", True, 16)]
N_CHARS = 3000
SIZES_PX = [16, 24, 32, 48]


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


def subset_woff2(src: Path, dst: Path, chars):
    cmd = [sys.executable, "-m", "fontTools.subset", str(src),
           "--unicodes=" + ",".join(f"U+{c:04X}" for c in chars),
           "--flavor=woff2", "--no-hinting", "--layout-features=*",
           "--name-IDs=1,2,3,4,5,6", "--name-languages=*",
           "--notdef-outline", "--recalc-bounds",
           "--output-file=" + str(dst)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    return dst.stat().st_size, round(time.time() - t0, 2)


def subset_points(woff2: Path) -> int:
    f = TTFont(str(woff2), lazy=False)
    glyf = f["glyf"]
    n = 0
    for gn in f.getGlyphOrder():
        if gn not in glyf.glyphs:
            continue
        g = glyf[gn]
        if g.numberOfContours > 0:
            n += len(g.coordinates)
    f.close()
    return n


def render_diff(font_a: Path, font_b: Path, text: str, px: int):
    from PIL import Image, ImageChops, ImageDraw, ImageFont
    try:
        fa = ImageFont.truetype(str(font_a), px)
        fb = ImageFont.truetype(str(font_b), px)
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}
    w, h = 64 * px, 2 * px
    imgs = []
    for f in (fa, fb):
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).text((2, 2), text, font=f, fill=255)
        imgs.append(im)
    hist = ImageChops.difference(imgs[0], imgs[1]).histogram()
    nonzero = sum(hist[1:])
    maxdiff = max((i for i, c in enumerate(hist) if c), default=0)
    total = sum(hist)
    mean = sum(i * c for i, c in enumerate(hist)) / total if total else 0
    return {"px": px, "nonzero_pixels": nonzero, "max_channel_diff": maxdiff,
            "mean_abs_diff": round(mean, 4)}


def main():
    rows = []
    for family, rel, lang in FONTS:
        src = ROOT / rel
        if not src.exists():
            continue
        chars = top_chars(lang, N_CHARS)
        text = "".join(chr(c) for c in chars[:300])
        ref_ttf = None
        for name, canonical, grid in VARIANTS:
            ttf = WORK / f"{family.replace(' ', '_')}_{name}.ttf"
            if not ttf.exists():
                t0 = time.time()
                stats = process_font(str(src), str(ttf), canonical=canonical, grid=grid)
                stats["prep_s"] = round(time.time() - t0, 1)
            else:
                stats = {}
            if ref_ttf is None:
                ref_ttf = ttf
            woff2 = WORK / f"{family.replace(' ', '_')}_{name}.woff2"
            size, enc_s = subset_woff2(ttf, woff2, chars)
            pts = subset_points(woff2)
            row = {
                "font": family, "variant": name, "grid": grid, "canonical": canonical,
                "woff2_bytes": size, "encode_s": enc_s,
                "subset_points": pts,
                "bits_per_point": round(size * 8 / pts, 2) if pts else None,
                "max_point_error_units": stats.get("max_point_error_units"),
                "mean_point_error_units": stats.get("mean_point_error_units"),
                "prep_s": stats.get("prep_s"),
            }
            if name != "ref":
                row["render"] = [render_diff(ref_ttf, ttf, text, px) for px in SIZES_PX]
            rows.append(row)
            print(f"{family:20s} {name:10s} woff2={size/1024:8.1f} KiB  bpp={row['bits_per_point']:5.2f}  "
                  f"maxerr={row['max_point_error_units']}u", flush=True)
    (OUT / "gc_bench.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "gc_bench.json")


if __name__ == "__main__":
    main()
