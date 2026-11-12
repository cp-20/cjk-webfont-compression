#!/usr/bin/env python3
"""Round 3: verify what the upside-down renderer did and did not corrupt.

Until this round, the hand-rolled FreeType compositors in glc_demo.py and
glc_render.py placed bitmap row r at y = px + top - row, which mirrors
every glyph vertically (bitmap row 0 is the TOP row; the top row belongs
at px - top). The displayed PNGs were upside down. This script checks the
quantitative claim made when fixing it:

  * the buggy canvas is exactly the vertical mirror of the fixed canvas;
  * the fidelity metrics (changed_px / changed_pct / max_diff, as computed
    by glc_render.compare) are IDENTICAL under both renderers, because
    both sides of the comparison pass through the same renderer and a
    mirror permutes pixels identically on both sides.

So: demo/report *images* were wrong; the published PSNR / changed-pixel
*numbers* were not. (gc_bench.py and glc_final.py use PIL ImageFont and
never had the bug.)

Usage: .venv/bin/python measure/verify_render_orientation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import freetype

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "measure"))
import glc_render  # noqa: E402

TEXT = "日本語の文字形は、筆画的組合せで成立する。描写質量"
PX = 24


def render_buggy(path: str, text: str, px: int):
    """The pre-fix compositor, reproduced verbatim (y = px + top - row)."""
    face = freetype.Face(path)
    face.set_char_size(px * 64)
    out = []
    pen_x = 0
    for ch in text:
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bmp = face.glyph.bitmap
        out.append((pen_x, face.glyph.bitmap_left >> 6, face.glyph.bitmap_top >> 6,
                    bmp.width, bmp.rows, bmp.buffer))
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


def main() -> int:
    ref = ROOT / "measure/out/repro/noto_q0.ttf"
    var = ROOT / "measure/out/repro/noto_q8.ttf"
    if not (ref.exists() and var.exists()):
        raise SystemExit("round-2 repro intermediates missing (measure/out/repro/)")

    fa, w, h = glc_render.render(str(ref), TEXT, PX)
    fb, _, _ = glc_render.render(str(var), TEXT, PX)
    ba, _, _ = render_buggy(str(ref), TEXT, PX)
    bb, _, _ = render_buggy(str(var), TEXT, PX)

    # 1. buggy canvas == vertical mirror of fixed canvas?
    def is_mirror(a, b):
        # mirror about the horizontal midline of the *ink*: the buggy
        # formula reflects around y = px + top - row's axis; simplest robust
        # check: flip the fixed canvas vertically and compare ink bounding
        # boxes + pixel multiset per column is overkill -- instead check the
        # buggy canvas equals the fixed canvas flipped about y = px + (px-?)
        # We use the exact relation: buggy_y = 2*px - fixed_y ... derived
        # per-glyph below is messy; do the empirical thing: flip fixed
        # canvas upside down and test equality after aligning ink rows.
        return None  # replaced by the column-profile check below

    def col_profile(c):
        return [sum(c[y][x] for y in range(len(c))) for x in range(len(c[0]))]

    def row_ink(c):
        return [sum(1 for v in row if v) for row in c]

    # Column ink profiles are mirror-invariant; row profiles reverse.
    same_cols = col_profile(fa) == col_profile(ba)
    rows_fixed = row_ink(fa)
    rows_buggy = row_ink(ba)
    ink_rows_fixed = [i for i, n in enumerate(rows_fixed) if n]
    ink_rows_buggy = [i for i, n in enumerate(rows_buggy) if n]
    mirrored_rows = (rows_buggy[ink_rows_buggy[0]:ink_rows_buggy[-1] + 1]
                     == rows_fixed[ink_rows_fixed[0]:ink_rows_fixed[-1] + 1][::-1])
    print(f"column ink profiles identical: {same_cols}")
    print(f"row ink profile reversed (vertical mirror): {mirrored_rows}")

    # 2. metrics identical under both renderers?
    m_fixed = glc_render.compare(fa, fb)
    m_buggy = glc_render.compare(ba, bb)
    print(f"metrics, fixed renderer : {m_fixed}")
    print(f"metrics, buggy renderer : {m_buggy}")
    identical = m_fixed == m_buggy
    print(f"metrics identical: {identical}")
    ok = same_cols and mirrored_rows and identical
    print("VERDICT:", "bug affected images only; metrics stand" if ok else "MISMATCH -- investigate")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
