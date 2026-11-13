#!/usr/bin/env python3
"""Round 3: can GLC quantise a *variable* font?

tools/glc.py refuses an uninstanced variable font today. Two candidate
product shapes:

  Arm A (instance, then GLC): instance the VF at each weight a site uses,
  GLC each instance, ship one static file per weight. Total cost grows
  with the number of weights.

  Arm B (GLC the VF directly): quantise the default outlines once, keep
  gvar, ship ONE file covering all weights. Geometrically this is sound
  iff the rendered outline at weight w is Q(default) + delta(w): the
  quantisation error is then the default instance's error field,
  weight-invariant. It breaks if the codec's static-font assumptions
  (composite expansion during hinting strip, point renumbering) desync
  glyf from gvar's point indices.

This script measures both arms on Noto Sans JP variable at grid 8
(eps 0.4 % of em, the project's default):

  * B1: naive glyphcodec.process_font on the VF -- does the result still
    instance, and how wrong are the outlines at non-default weights?
  * B2: a VF-safe prototype quantiser (simple glyphs only; composites
    and gvar untouched; hinting stripped without expanding composites).
    Per-weight outline error vs the stock VF's instances.
  * A:  size sums for weight sets {400}, {400,700}, {400,500,700},
    {100,200,...,900} -- stock instances vs GLC'd instances vs Arm B's
    single file.

Writes measure/out/variable_glc.json. Sequential; ~10 min on this VM.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "vf"
WORK.mkdir(parents=True, exist_ok=True)
VF = ROOT / "fonts" / "NotoSansJP[wght].ttf"
GRID = 8
WEIGHTS_CHECK = [100, 300, 400, 500, 700, 900]
WEIGHT_SETS = [[400], [400, 700], [400, 500, 700], list(range(100, 1000, 100))]

sys.path.insert(0, str(ROOT / "tools"))
import glyphcodec  # noqa: E402
from glyphcodec import process_font, quantize_glyph  # noqa: E402


def woff2_bytes(path: Path) -> int:
    from fontTools.ttLib import TTFont
    f = TTFont(str(path))
    f.flavor = "woff2"
    buf = io.BytesIO()
    f.save(buf)
    f.close()
    return len(buf.getvalue())


def instance(src: Path, wght: int, dst: Path) -> Path:
    from fontTools.varLib.instancer import instantiateVariableFont
    from fontTools.ttLib import TTFont
    f = TTFont(str(src))
    instantiateVariableFont(f, {"wght": wght}, inplace=True)
    f.save(str(dst))
    f.close()
    return dst


def outline_errors(font_a: Path, font_b: Path) -> dict:
    """Per-point outline deltas between two static fonts (same glyph order).

    Returns max/mean abs coordinate delta over glyphs whose point counts
    match, plus counts of structural mismatches -- the signature of a
    glyf/gvar desync."""
    from fontTools.ttLib import TTFont
    fa = TTFont(str(font_a))
    fb = TTFont(str(font_b))
    ga, gb = fa["glyf"], fb["glyf"]
    maxd = 0
    sumd = 0
    npts = 0
    mismatch = 0
    compared = 0
    for name in fa.getGlyphOrder():
        if name not in ga.glyphs or name not in gb.glyphs:
            mismatch += 1
            continue
        a = ga[name]  # indexing decompiles the lazy glyph
        b = gb[name]
        if a.numberOfContours <= 0 or b.numberOfContours <= 0:
            continue
        ca, _, _ = a.getCoordinates(ga)
        cb, _, _ = b.getCoordinates(gb)
        if len(ca) != len(cb):
            mismatch += 1
            continue
        compared += 1
        for (xa, ya), (xb, yb) in zip(ca, cb):
            d = max(abs(xa - xb), abs(ya - yb))
            if d > maxd:
                maxd = d
            sumd += d
            npts += 1
    fa.close()
    fb.close()
    return {"glyphs_compared": compared, "point_count_mismatches": mismatch,
            "max_abs_delta_units": maxd,
            "mean_abs_delta_units": round(sumd / npts, 3) if npts else 0.0}


def vf_safe_quantize(src: Path, dst: Path, grid: int) -> dict:
    """Prototype: quantise simple glyphs' default outlines in place.

    Differences from glyphcodec.process_font, all forced by gvar:
      * composite glyphs are NOT quantised and NOT expanded -- their
        point layout (components + phantom points) is what gvar indexes;
      * hinting is stripped by deleting fpgm/prep/cvt /cvar and emptying
        glyph programs WITHOUT expand() (expand decomposes composites);
      * gvar, fvar, HVAR, STAT are left untouched.
    """
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables.ttProgram import Program
    font = TTFont(str(src))
    glyf = font["glyf"]
    n_simple = n_comp = 0
    for name in font.getGlyphOrder():
        if name not in glyf.glyphs:
            continue
        g = glyf[name]  # indexing decompiles the lazy glyph
        if g.numberOfContours > 0:
            quantize_glyph(g, grid)
            g.recalcBounds(glyf)
            n_simple += 1
        elif g.numberOfContours == -1:
            n_comp += 1
    for tag in ("fpgm", "prep", "cvt ", "cvar"):
        if tag in font:
            del font[tag]
    for name in font.getGlyphOrder():
        if name not in glyf.glyphs:
            continue
        g = glyf[name]
        if hasattr(g, "program"):
            try:
                g.program = Program()
            except Exception:
                pass
    font.save(str(dst))
    font.close()
    return {"simple_glyphs_quantized": n_simple, "composite_glyphs_kept": n_comp}


def main() -> int:
    result = {"meta": {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "font": "Noto Sans JP variable (fonts/NotoSansJP[wght].ttf)",
                       "grid": GRID},
              "sizes": {}, "arm_b1_naive": {}, "arm_b2_vfsafe": {}}

    vf_woff2 = woff2_bytes(VF)
    result["sizes"]["variable_font_stock_woff2"] = vf_woff2
    print(f"VF stock WOFF2: {vf_woff2:,}", flush=True)

    # ---- Arm B1: naive process_font on the VF
    b1_ttf = WORK / "vf_naive_q8.ttf"
    try:
        stats = process_font(str(VF), str(b1_ttf), canonical=False, grid=GRID)
        result["arm_b1_naive"]["process_stats"] = stats
        result["arm_b1_naive"]["woff2"] = woff2_bytes(b1_ttf)
        print(f"B1 naive GLC VF WOFF2: {result['arm_b1_naive']['woff2']:,}", flush=True)
    except Exception as e:  # noqa: BLE001
        result["arm_b1_naive"]["error"] = repr(e)
        print("B1 process_font failed:", repr(e), flush=True)
        b1_ttf = None

    # ---- Arm B2: VF-safe prototype
    b2_ttf = WORK / "vf_safe_q8.ttf"
    info = vf_safe_quantize(VF, b2_ttf, GRID)
    result["arm_b2_vfsafe"]["quantize_info"] = info
    result["arm_b2_vfsafe"]["woff2"] = woff2_bytes(b2_ttf)
    print(f"B2 vf-safe GLC VF WOFF2: {result['arm_b2_vfsafe']['woff2']:,} {info}", flush=True)

    # ---- Per-weight validation for B1/B2 against stock instances
    for tag, cand in (("arm_b1_naive", b1_ttf), ("arm_b2_vfsafe", b2_ttf)):
        if cand is None:
            continue
        errs = {}
        for w in WEIGHTS_CHECK:
            stock_i = instance(VF, w, WORK / f"stock_{w}.ttf")
            try:
                cand_i = instance(cand, w, WORK / f"{tag}_{w}.ttf")
                errs[str(w)] = outline_errors(stock_i, cand_i)
            except Exception as e:  # noqa: BLE001
                errs[str(w)] = {"error": repr(e)}
            print(f"{tag} wght={w}: {errs[str(w)]}", flush=True)
        result[tag]["outline_error_vs_stock_instance"] = errs

    # ---- Arm A: instance -> GLC size sums per weight set
    per_weight = {}
    for w in sorted({w for s in WEIGHT_SETS for w in s}):
        inst = WORK / f"stock_{w}.ttf"
        if not inst.exists():
            instance(VF, w, inst)
        glc = WORK / f"inst_{w}_q8.ttf"
        process_font(str(inst), str(glc), canonical=False, grid=GRID)
        per_weight[str(w)] = {"stock_woff2": woff2_bytes(inst),
                              "glc8_woff2": woff2_bytes(glc)}
        print(f"wght={w}: stock={per_weight[str(w)]['stock_woff2']:,} "
              f"glc8={per_weight[str(w)]['glc8_woff2']:,}", flush=True)
    result["arm_a_per_weight"] = per_weight
    sets = {}
    for s in WEIGHT_SETS:
        key = "+".join(str(w) for w in s)
        sets[key] = {
            "stock_sum": sum(per_weight[str(w)]["stock_woff2"] for w in s),
            "glc8_sum": sum(per_weight[str(w)]["glc8_woff2"] for w in s),
        }
    result["sizes"]["arm_a_weight_sets"] = sets
    result["sizes"]["arm_b2_single_file_all_weights"] = result["arm_b2_vfsafe"].get("woff2")
    result["sizes"]["arm_b1_single_file_all_weights"] = result["arm_b1_naive"].get("woff2")

    (OUT / "variable_glc.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "variable_glc.json")
    print(json.dumps(result["sizes"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
