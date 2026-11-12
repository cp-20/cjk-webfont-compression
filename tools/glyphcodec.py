#!/usr/bin/env python3
"""Glyph-level preprocessing for TrueType (glyf) fonts.

Implements the two building blocks of the proposed "GLC" (Glyph-Level Compression)
method:

  canonicalize(glyph)  lossless normalisation of the outline byte order
                       - rotate every contour so that it starts at its
                         lexicographically smallest on-curve point
                       - sort contours by (yMin, xMin, #points) so that
                         glyphs with similar shapes produce similar bytes
  quantize(glyph, g)    lossy coordinate rounding onto a g-unit grid
                       (font units; 1000 upm => g=4 is 0.4% of em)

Both operations are pure point-set operations: the filled area of a glyph is
unchanged by contour rotation/sorting (TrueType uses the non-zero winding
rule), so `canonicalize` is byte-exact in shape.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram


def contour_ends(glyph):
    ep = getattr(glyph, "endPts", None)
    if ep is None:
        ep = getattr(glyph, "endPtsOfContours", [])
        if callable(ep):
            ep = ep()
    return list(ep)


def _contour_ranges(glyph):
    start = 0
    for e in contour_ends(glyph):
        yield start, e
        start = e + 1


def canonicalize_glyph(glyph) -> bool:
    """Rotate contour start points and sort contours. Returns True if changed."""
    if glyph.numberOfContours <= 0 or glyph.isComposite():
        return False
    coords = [tuple(c) for c in glyph.coordinates]
    flags = list(glyph.flags)
    contours = []
    for s, e in _contour_ranges(glyph):
        pts = coords[s:e + 1]
        fl = flags[s:e + 1]
        # Rotate the contour so that it starts at its smallest on-curve point.
        # Only safe when the contour already starts on-curve: otherwise the
        # implied start point (midpoint of last and first point) would be
        # replaced by a real point and the outline would change shape.
        if fl and (fl[0] & 1):
            oncurve = [i for i, f in enumerate(fl) if f & 1]
            if oncurve:
                best = min(oncurve, key=lambda i: (pts[i][0], pts[i][1], i))
                if best:
                    pts = pts[best:] + pts[:best]
                    fl = fl[best:] + fl[:best]
        contours.append((pts, fl))
    # sort contours by geometry (stable, deterministic)
    def key(cf):
        pts, fl = cf
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(ys), min(xs), len(pts), sum(xs), sum(ys))
    contours.sort(key=key)
    new_coords = [p for pts, _ in contours for p in pts]
    new_flags = [f for _, fl in contours for f in fl]
    new_ends = []
    acc = -1
    for pts, _ in contours:
        acc += len(pts)
        new_ends.append(acc)
    changed = (new_coords != coords) or (new_flags != flags) or (new_ends != contour_ends(glyph))
    if changed:
        glyph.coordinates[:] = new_coords   # keep the ttCoordinates type
        glyph.flags[:] = new_flags
        if hasattr(glyph, "endPtsOfContours"):
            glyph.endPtsOfContours = new_ends
        else:
            glyph.endPts = new_ends
        glyph.program = ttProgram.Program()  # hinting refers to the old point order
    return changed


def quantize_glyph(glyph, grid: int, keep_bbox: bool = True) -> bool:
    """Round every point onto a `grid`-unit lattice.

    With keep_bbox the original bounding box is preserved: the TrueType
    advance width is derived from the outline bbox (via the phantom points),
    so a bbox that moves by one unit changes the advance width and can
    change line breaking. Rounded coordinates are therefore clamped to the
    original box.
    """
    if glyph.numberOfContours <= 0 or glyph.isComposite():
        return False
    new_coords = [(int(round(x / grid)) * grid, int(round(y / grid)) * grid)
                   for x, y in glyph.coordinates]
    if keep_bbox:
        xs = [c[0] for c in glyph.coordinates]
        ys = [c[1] for c in glyph.coordinates]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        new_coords = [(min(max(x, x0), x1), min(max(y, y0), y1)) for x, y in new_coords]
        # pin the extremal points to their original values so that the bounding
        # box (and therefore the advance width) is preserved exactly
        for i, (ox, oy) in enumerate(glyph.coordinates):
            nx, ny = new_coords[i]
            if ox == x0:
                nx = x0
            elif ox == x1:
                nx = x1
            if oy == y0:
                ny = y0
            elif oy == y1:
                ny = y1
            new_coords[i] = (nx, ny)
    changed = new_coords != [tuple(c) for c in glyph.coordinates]
    if changed:
        glyph.coordinates[:] = new_coords   # keep the ttCoordinates type
        glyph.program = ttProgram.Program()
    return changed


def process_font(path: str, out: str, canonical: bool = True, grid: int = 0,
                 drop_hinting: bool = True) -> dict:
    font = TTFont(path, recalcBBoxes=False, recalcTimestamp=False)
    glyf = font["glyf"]
    stats = {"canonicalized": 0, "quantized": 0, "glyphs": 0,
             "max_point_error_units": 0, "mean_point_error_units": 0.0,
             "points": 0}
    err_sum = 0.0
    err_n = 0
    for gn in font.getGlyphOrder():
        if gn not in glyf.glyphs:
            continue
        g = glyf[gn]  # expands the lazy glyph
        if g.numberOfContours <= 0:
            continue
        stats["glyphs"] += 1
        orig = [tuple(c) for c in g.coordinates]
        if canonical and canonicalize_glyph(g):
            stats["canonicalized"] += 1
        if grid and quantize_glyph(g, grid):
            stats["quantized"] += 1
        new = [tuple(c) for c in g.coordinates]
        if len(orig) == len(new):
            for (x, y), (x2, y2) in zip(orig, new):
                d = max(abs(x - x2), abs(y - y2))
                if d:
                    err_sum += d
                    err_n += 1
                    if d > stats["max_point_error_units"]:
                        stats["max_point_error_units"] = d
        try:
            g.recalcBounds(glyf)
        except Exception:
            pass
    if drop_hinting:
        for tag in ("fpgm", "prep", "cvt ", "cvar"):
            if tag in font:
                del font[tag]
        for gn in font.getGlyphOrder():
            g = glyf.glyphs.get(gn)
            if g is not None:
                g.expand(glyf)
                try:
                    g.trim(remove_hinting=True, extended=glyf.extended)
                except Exception:
                    g.program = ttProgram.Program()
    stats["points"] = err_n + (stats["glyphs"] * 0)
    stats["mean_point_error_units"] = round(err_sum / err_n, 4) if err_n else 0.0
    font.save(out)
    return stats


def process_variable_font(path: str, out: str, grid: int = 0,
                          drop_vertical: bool = False) -> dict:
    """Quantise a variable font's *default* outlines in place (GLC for VF).

    gvar addresses glyph points by index, so this path is deliberately
    more conservative than process_font:

      * simple glyphs are quantised with the same bbox-preserving
        quantiser; point counts and order never change;
      * composite glyphs are left entirely alone -- their point layout
        (component transforms + phantom points) is what gvar indexes;
      * hinting is stripped (fpgm/prep/cvt /cvar deleted, glyph programs
        emptied) WITHOUT expand(), which would decompile/restructure
        glyphs;
      * gvar, fvar, HVAR and STAT are untouched.

    Measured caveat (round 3, measure/variable_glc.py): the MEAN outline
    error stays at the static-font level at every weight (~2.6 units at
    grid 8), but the MAX point error grows with distance from the
    default weight -- 4 units at wght=100 (Noto Sans JP's default) vs
    138 units at wght=900 -- because gvar stores deltas for only a
    subset of points and interpolates the rest (IUP) from the default
    outline; perturbing the default perturbs the interpolation. The
    static guarantee (error <= grid/2 everywhere) does NOT hold here.
    """
    from fontTools.ttLib.tables.ttProgram import Program
    font = TTFont(path, recalcBBoxes=False, recalcTimestamp=False)
    if "fvar" not in font:
        raise ValueError("process_variable_font: input is not a variable font")
    glyf = font["glyf"]
    stats = {"quantized": 0, "glyphs": 0, "composites_kept": 0}
    for gn in font.getGlyphOrder():
        if gn not in glyf.glyphs:
            continue
        g = glyf[gn]  # indexing decompiles the lazy glyph
        if g.numberOfContours > 0:
            stats["glyphs"] += 1
            if grid and quantize_glyph(g, grid):
                stats["quantized"] += 1
                try:
                    g.recalcBounds(glyf)
                except Exception:
                    pass
        elif g.numberOfContours == -1:
            stats["composites_kept"] += 1
    for tag in ("fpgm", "prep", "cvt ", "cvar"):
        if tag in font:
            del font[tag]
    for gn in font.getGlyphOrder():
        if gn not in glyf.glyphs:
            continue
        g = glyf[gn]
        if hasattr(g, "program"):
            try:
                g.program = Program()
            except Exception:
                pass
    if drop_vertical:
        for tag in ("vhea", "vmtx"):
            if tag in font:
                del font[tag]
    font.save(out)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--canonical", action="store_true")
    ap.add_argument("--grid", type=int, default=0)
    args = ap.parse_args()
    stats = process_font(args.input, args.output, canonical=args.canonical, grid=args.grid)
    print(stats)


if __name__ == "__main__":
    main()
