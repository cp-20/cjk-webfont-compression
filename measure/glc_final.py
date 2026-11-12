#!/usr/bin/env python3
"""Final benchmark of the GLC (Glyph-Level Compression) pipeline.

GLC-0  CFF -> glyf conversion (cubic->quadratic, error budget)
GLC-1  CFF de-subroutinisation (per WOFF2 spec 5.4)
GLC-2  drop vertical metrics (vhea/vmtx) for horizontal-only sites
GLC-3  lossless canonicalisation of contour order
GLC-4  error-bounded lattice quantisation of the outline coordinates

Everything ends in a *plain WOFF2 file*: no browser change is required.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "glc"
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402
from cff2glyf import cff_to_glyf  # noqa: E402

N_CHARS = 3000

FONTS = [
    ("Noto Sans JP", "measure/out/NotoSansJP-Regular.ttf", "ja"),
    ("M PLUS 1p", "fonts/MPLUS1p-Regular.ttf", "ja"),
    ("Zen Kaku Gothic New", "fonts/ZenKakuGothicNew-Regular.ttf", "ja"),
    ("Nanum Gothic", "fonts/NanumGothic-Regular.ttf", "ko"),
    ("Source Han Sans JP", "fonts/SourceHanSansJP-Regular.otf", "ja"),
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


def subset_woff2(src: Path, dst: Path, chars, extra=()):
    cmd = [sys.executable, "-m", "fontTools.subset", str(src),
           "--unicodes=" + ",".join(f"U+{c:04X}" for c in chars),
           "--flavor=woff2", "--no-hinting", "--layout-features=*",
           "--name-IDs=1,2,3,4,5,6", "--name-languages=*",
           "--notdef-outline", "--recalc-bounds", "--drop-tables+=vhea,vmtx",
           f"--output-file={dst}", *extra]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return dst.stat().st_size, round(time.time() - t0, 2)


def render_diff(fa: Path, fb: Path, text: str, px: int):
    from PIL import Image, ImageChops, ImageDraw, ImageFont
    try:
        a = ImageFont.truetype(str(fa), px, layout_engine=ImageFont.Layout.BASIC)
        b = ImageFont.truetype(str(fb), px, layout_engine=ImageFont.Layout.BASIC)
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}
    w, h = 64 * px, 2 * px
    ims = []
    for f in (a, b):
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).text((2, 2), text, font=f, fill=255)
        ims.append(im)
    hist = ImageChops.difference(ims[0], ims[1]).histogram()
    total = sum(hist)
    return {"px": px,
            "nonzero_pixels": sum(hist[1:]),
            "max_channel_diff": max((i for i, c in enumerate(hist) if c), default=0),
            "mean_abs_diff": round(sum(i * c for i, c in enumerate(hist)) / total, 4) if total else 0}


def contour_point_sets(path: Path):
    """{contour key -> sorted point list} per glyph, for shape comparison."""
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
        coords = [tuple(c) for c in g.coordinates]
        ends = list(getattr(g, "endPtsOfContours", None) or getattr(g, "endPts", []))
        if callable(ends):
            ends = ends()
        cs, start = [], 0
        for e in ends:
            cs.append(sorted(coords[start:e + 1]))
            start = e + 1
        out[gn] = sorted(cs)
    font.close()
    return out


def shape_error(a: Path, b: Path):
    """max / mean geometric deviation between two fonts (contour aware).

    For every glyph we compare the *sets* of contours with a symmetric
    Hausdorff distance (each contour is matched to its nearest counterpart),
    so that reordering of contours or points does not distort the metric.
    """
    A, B = contour_point_sets(a), contour_point_sets(b)

    def one_way(p, q):
        w = 0
        for (x1, y1) in p:
            d = min(max(abs(x1 - x2), abs(y1 - y2)) for (x2, y2) in q)
            if d > w:
                w = d
        return w

    worst = 0
    total = 0.0
    n = 0
    for gn, ca in A.items():
        cb = B.get(gn)
        if not cb:
            continue
        for pts_a in ca:
            d = min(one_way(pts_a, pts_b) for pts_b in cb) if cb else 0
            total += d
            n += 1
            if d > worst:
                worst = d
        for pts_b in cb:
            d = min(one_way(pts_b, pts_a) for pts_a in ca) if ca else 0
            total += d
            n += 1
            if d > worst:
                worst = d
    return worst, (total / n if n else 0.0)


def main():
    rows = []
    for family, rel, lang in FONTS:
        src = ROOT / rel
        if not src.exists():
            continue
        chars = top_chars(lang, N_CHARS)
        text = "".join(chr(c) for c in chars[:300])
        tag = family.replace(" ", "_")
        is_cff = src.suffix.lower() == ".otf"
        # ---- reference: untouched font, plain WOFF2 (the thing we must beat)
        ref_w = WORK / f"{tag}_ref.woff2"
        ref_size, ref_s = subset_woff2(src, ref_w, chars)
        rows.append({"font": family, "stage": "WOFF2 (baseline)", "bytes": ref_size,
                     "encode_s": ref_s, "delta": 0.0, "max_err_units": 0,
                     "mean_err_units": 0.0, "cff": is_cff})
        print(f"{family:22s} {'WOFF2 baseline':34s} {ref_size/1024:8.1f} KiB", flush=True)

        # ---- GLC-1: CFF de-subroutinisation
        cur = src
        if is_cff:
            w = WORK / f"{tag}_desubr.woff2"
            size, s = subset_woff2(src, w, chars, extra=("--desubroutinize",))
            rows.append({"font": family, "stage": "GLC-1 CFF de-subroutinise", "bytes": size,
                         "encode_s": s, "delta": 1 - size / ref_size, "max_err_units": 0,
                         "mean_err_units": 0.0, "cff": True})
            print(f"{family:22s} {'GLC-1 CFF de-subroutinise':34s} {size/1024:8.1f} KiB "
                  f"({100*(1-size/ref_size):5.1f}% 減)", flush=True)

        # ---- GLC-0: CFF -> glyf
        if is_cff:
            ttf = WORK / f"{tag}_glyf.ttf"
            if not ttf.exists():
                cff_to_glyf(str(src), str(ttf), max_err_ratio=0.001)
            w = WORK / f"{tag}_glyf.woff2"
            size, s = subset_woff2(ttf, w, chars)
            rows.append({"font": family, "stage": "GLC-0 CFF->glyf", "bytes": size,
                         "encode_s": s, "delta": 1 - size / ref_size, "max_err_units": 1,
                         "mean_err_units": 0.0, "cff": True})
            print(f"{family:22s} {'GLC-0 CFF->glyf':34s} {size/1024:8.1f} KiB "
                  f"({100*(1-size/ref_size):5.1f}% 減)", flush=True)
            cur = ttf

        # ---- GLC-3 + GLC-4 on the (possibly converted) font
        for grid in (0, 4, 8, 16):
            name = "GLC-3 canonical (control)" if grid == 0 else f"GLC-4 quant{grid}"
            ttf = WORK / f"{tag}_q{grid}.ttf"
            if not ttf.exists():
                stats = process_font(str(cur), str(ttf), canonical=(grid == 0), grid=grid)
            else:
                stats = {}
            w = WORK / f"{tag}_q{grid}.woff2"
            size, s = subset_woff2(ttf, w, chars)
            if is_cff:
                worst, mean_err = 1, 0.0   # cu2qu error budget (1 unit = 0.1% em)
            else:
                worst, mean_err = shape_error(src, ttf)
            row = {"font": family, "stage": name, "bytes": size, "encode_s": s,
                   "delta": 1 - size / ref_size,
                   "max_err_units": worst, "mean_err_units": round(mean_err, 4), "cff": is_cff}
            if grid > 0:
                row["render"] = [render_diff(src, ttf, text, px) for px in (16, 24, 32, 48)]
            rows.append(row)
            print(f"{family:22s} {name:34s} {size/1024:8.1f} KiB "
                  f"({100*row['delta']:5.1f}% 減)  max_err={row['max_err_units']}u", flush=True)
        (OUT / "glc_bench.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "glc_bench.json")


if __name__ == "__main__":
    main()
