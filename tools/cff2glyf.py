#!/usr/bin/env python3
"""Convert a CFF (PostScript-outline) OpenType font into a TrueType (glyf) font.

Why this matters for the web: the WOFF2 content transform (glyf / loca / hmtx)
does not apply to CFF, so a CFF CJK font keeps ~70% of its original size after
WOFF2, while a glyf font of the same design shrinks to 31-45%. Converting the
cubic outlines to quadratic glyf outlines *before* WOFF2 encoding lets the
transform do its work.

The conversion is cubic -> quadratic (cu2qu), so it is lossy in the strict sense;
the error is bounded by `max_err` font units and is far below one pixel at text
sizes.
"""
from __future__ import annotations

import argparse
import copy
import time
from pathlib import Path

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import _g_l_y_f


def cff_to_glyf(src: str, dst: str, max_err: float = 1.0, max_err_ratio: float | None = None,
                drop_names: bool = True) -> dict:
    font = TTFont(src)
    stats = {"glyphs": 0, "points": 0, "max_err": max_err}
    glyph_set = font.getGlyphSet()
    glyf = _g_l_y_f.table__g_l_y_f()
    glyf.glyphOrder = list(font.getGlyphOrder())
    glyf.glyphs = {}
    upm = font["head"].unitsPerEm
    err = max_err if max_err_ratio is None else max_err_ratio * upm
    for name in glyf.glyphOrder:
        pen = TTGlyphPen(None)
        cu2qu = Cu2QuPen(pen, err)
        try:
            glyph_set[name].draw(cu2qu)
            g = pen.glyph()
        except Exception:  # noqa: BLE001
            g = TTGlyphPen(None).glyph()
        try:
            g.recalcBounds(glyf)
        except Exception:  # noqa: BLE001
            pass
        glyf.glyphs[name] = g
        stats["glyphs"] += 1
        if g.numberOfContours > 0:
            stats["points"] += len(g.coordinates)
    font["glyf"] = glyf
    font["loca"] = newTable("loca")
    for tag in ("CFF ", "CFF2", "VORG"):
        if tag in font:
            del font[tag]
    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for attr in ("maxPoints", "maxContours", "maxCompositePoints", "maxCompositeContours",
                 "maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs",
                 "maxInstructionDefs", "maxStackElements", "maxSizeOfInstructions",
                 "maxComponentElements", "maxComponentDepth"):
        setattr(maxp, attr, 0)
    maxp.recalc(font)
    if drop_names and "post" in font:
        post = font["post"]
        post.formatType = 3.0
        post.glyphOrder = None
        post.extraNames = []
        post.mapping = {}
        post.nameData = ""
    font["head"].glyphDataFormat = 0
    # the sfnt version must switch from 'OTTO' to TrueType, otherwise
    # FreeType (and browsers) look for a CFF table that is no longer there
    font.sfntVersion = "\x00\x01\x00\x00"
    t0 = time.time()
    font.save(dst)
    stats["save_s"] = round(time.time() - t0, 1)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--max-err", type=float, default=1.0)
    ap.add_argument("--max-err-ratio", type=float, default=None,
                    help="error budget in units of the em (e.g. 0.001 = 0.1%% of em)")
    args = ap.parse_args()
    stats = cff_to_glyf(args.input, args.output, args.max_err, args.max_err_ratio)
    print(stats)


if __name__ == "__main__":
    main()
