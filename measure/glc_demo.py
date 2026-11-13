#!/usr/bin/env python3
"""Render a visual demo of the GLC-4 quantisation noise.

Produces PNGs (in report/assets/) that show, for each grid width, the same
Japanese text rendered with the baseline font and with the quantised font,
plus a 6x zoom of a region with complex kanji and an amplified difference
image that makes the noise visible.

Use --legacy-orientation to reproduce the mirrored figures published before
the round-3 orientation fix (including gh-pages b40afeb).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import freetype
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "sweep"
ASSETS = ROOT / "report" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402

TEXT = "日本語の文字形は、筆画的組合せで成立する。表示质量的誤差は 0.4% em 以内に収まる。"
ZOOM_TEXT = "描写質量"
GRIDS = [0, 2, 4, 8, 16, 32]
PX = 24
ZOOM = 6


def render(face, text, px, legacy_orientation=False):
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
            # FreeType bitmap row 0 is the glyph's TOP row and bitmap_top is
            # the baseline->top distance, so the top row lands at px - top.
            # (Was px + top - row until round 3: every glyph came out
            # vertically mirrored -- the "upside-down demo" bug.)
            y = px + top - row if legacy_orientation else px - top + row
            if not (0 <= y < height):
                continue
            for col in range(w):
                x = pen_x + left + col
                if 0 <= x < width:
                    i = y * width + x
                    if buf[row * w + col] > canvas[i]:
                        canvas[i] = buf[row * w + col]
    return canvas, width, height


def to_image(canvas, w, h):
    return Image.frombytes("L", (w, h), bytes(canvas))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--legacy-orientation", action="store_true")
    args = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    src = ROOT / "measure/out/NotoSansJP-Regular.ttf"
    if not src.exists():
        # Use the same static 400 instance as reproduce_headline.py.
        subprocess.run([
            sys.executable, "-m", "fontTools.varLib.instancer",
            str(ROOT / "fonts" / "NotoSansJP[wght].ttf"),
            "wght=400", "-o", str(src),
        ], check=True)
    base_ttf = WORK / "Noto_Sans_JP_q0.ttf"
    if not base_ttf.exists():
        process_font(str(src), str(base_ttf), canonical=False, grid=0)
    base_face = freetype.Face(str(base_ttf))
    base_line, bw, bh = render(base_face, TEXT, PX, args.legacy_orientation)
    base_zoom, zw, zh = render(base_face, ZOOM_TEXT, PX, args.legacy_orientation)
    base_line_im = to_image(base_line, bw, bh)
    base_zoom_im = to_image(base_zoom, zw, zh)

    out = []
    for grid in GRIDS:
        ttf = WORK / f"Noto_Sans_JP_q{grid}.ttf"
        if not ttf.exists():
            process_font(str(src), str(ttf), canonical=False, grid=grid)
        face = freetype.Face(str(ttf))
        line, w, h = render(face, TEXT, PX, args.legacy_orientation)
        zoom, zw2, zh2 = render(face, ZOOM_TEXT, PX, args.legacy_orientation)
        line_im = to_image(line, w, h)
        zoom_im = to_image(zoom, zw2, zh2)
        # difference (amplified) of the zoom area
        diff = Image.new("L", (zw, zh))
        px_base = base_zoom_im.load()
        px_var = zoom_im.load()
        px_diff = diff.load()
        for y in range(zh):
            for x in range(zw):
                px_diff[x, y] = min(255, abs(px_base[x, y] - px_var[x, y]) * 6)
        # compose: text line on top, zoom row (base | variant | amplified diff) below
        z = base_zoom_im.crop((0, 0, zw, zh)).resize((zw * ZOOM, zh * ZOOM), Image.NEAREST)
        zv = zoom_im.crop((0, 0, zw, zh)).resize((zw * ZOOM, zh * ZOOM), Image.NEAREST)
        zd = diff.crop((0, 0, zw, zh)).resize((zw * ZOOM, zh * ZOOM), Image.NEAREST)
        pad = 8
        comp = Image.new("L", (max(line_im.width, z.width * 3 + pad * 2), line_im.height + z.height + pad), 255)
        comp.paste(line_im, (0, 0))
        comp.paste(z, (0, line_im.height + pad))
        comp.paste(zv, (z.width + pad, line_im.height + pad))
        comp.paste(zd, ((z.width + pad) * 2, line_im.height + pad))
        name = f"demo_g{grid}.png"
        comp.save(ASSETS / name)
        out.append({"grid": grid, "file": name, "bytes": (ASSETS / name).stat().st_size})
        print(f"wrote {name} ({comp.width}x{comp.height})", flush=True)
    (OUT / "glc_demo.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "glc_demo.json")


if __name__ == "__main__":
    main()
