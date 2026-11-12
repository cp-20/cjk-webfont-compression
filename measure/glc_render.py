#!/usr/bin/env python3
"""Rendering quality measurement with FreeType, hinting disabled.

This is the closest approximation to what a browser does with an unhinted web
font: geometry is rasterised without grid fitting, so the measured difference
reflects the outline geometry and not the autohinter.

Output: measure/out/glc_render.json
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import freetype

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
SIZES = (16, 24, 32, 48)


def render(path: str, text: str, px: int):
    face = freetype.Face(path)
    face.set_char_size(px * 64)
    out = []
    pen_x = 0
    for ch in text:
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bmp = face.glyph.bitmap
        w, h = bmp.width, bmp.rows
        buf = bmp.buffer
        out.append((pen_x, face.glyph.bitmap_left >> 6, face.glyph.bitmap_top >> 6, w, h, buf))
        pen_x += face.glyph.advance.x >> 6
    width = pen_x + 8
    height = px * 2
    canvas = [[0] * width for _ in range(height)]
    for (pen_x, left, top, w, h, buf) in out:
        for row in range(h):
            src = buf[row * w:(row + 1) * w]
            y = px + top - row
            if not (0 <= y < height):
                continue
            for col in range(w):
                x = pen_x + left + col
                if 0 <= x < width:
                    canvas[y][x] = max(canvas[y][x], src[col])
    return canvas, width, height


def compare(ca, cb):
    diff = 0
    total = 0
    worst = 0
    for ra, rb in zip(ca, cb):
        for va, vb in zip(ra, rb):
            total += 1
            d = abs(va - vb)
            if d:
                diff += 1
                if d > worst:
                    worst = d
    return {"changed_px": diff, "total_px": total, "max_diff": worst,
            "changed_pct": round(100 * diff / total, 3) if total else 0}


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
    for fam in ["Noto Sans JP", "M PLUS 1p", "Zen Kaku Gothic New", "Nanum Gothic"]:
        key = fam.replace(" ", "_")
        ref = ROOT / f"measure/out/gc/{key}_ref.ttf"
        if not ref.exists():
            continue
        for grid in (0, 4, 8, 16):
            var = ROOT / f"measure/out/glc/{key}_q{grid}.ttf"
            if not var.exists():
                continue
            entry = {"font": fam, "grid": grid, "render": []}
            for px in SIZES:
                ca, _, _ = render(str(ref), text, px)
                cb, _, _ = render(str(var), text, px)
                entry["render"].append({"px": px, **compare(ca, cb)})
            rows.append(entry)
            print(f"{fam:20s} grid={grid:2d} " + " | ".join(
                f"{x['px']}px changed={x['changed_pct']:6.3f}% max={x['max_diff']:3d}"
                for x in entry["render"]), flush=True)
    (OUT / "glc_render.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "glc_render.json")


if __name__ == "__main__":
    main()
