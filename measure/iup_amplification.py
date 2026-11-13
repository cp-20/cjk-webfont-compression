#!/usr/bin/env python3
"""Round 4, item 4 prototype: is gvar IUP error amplification concentrated?

The gvar-aware quantiser design (docs/gvar-aware-quantiser-design.md)
rests on one empirical claim: when a variable font's default outline is
quantised, the worst-case error at other weights blows up (4 -> 138
units, round 3) only for a *small tail* of glyphs -- the ones whose IUP
interpolation geometry is near-degenerate. If the blow-up were spread
evenly, protecting the tail with explicit deltas would cost as much as
instancing and the design would be pointless.

This script tests the claim on round 3's surviving artifacts: it
instances nothing new -- it compares, glyph by glyph, the outline errors
of the VF-safe quantised font (arm_b2_vfsafe_{w}.ttf) against the stock
instances (stock_{w}.ttf) at three weights. Weight 100 is this font's
fvar default, where quantisation error is bounded by grid/2 = 4 units
by construction; weight 400 is mid-axis; weight 900 is where round 3
measured the 138-unit worst case.

Output: measure/out/iup_amplification.json (percentiles + tail counts).
Usage:  .venv/bin/python measure/iup_amplification.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
VF = HERE / "out" / "vf"
OUT = HERE / "out" / "iup_amplification.json"


def glyph_errors(quant_path: Path, stock_path: Path):
    """Per-glyph max coordinate error (simple glyphs, matching points)."""
    fq = TTFont(str(quant_path))
    fs = TTFont(str(stock_path))
    gq, gs = fq["glyf"], fs["glyf"]
    errs: dict[str, float] = {}
    skipped = 0
    for name in fq.getGlyphOrder():
        try:
            a, b = gq[name], gs[name]
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        if a.isComposite() or b.isComposite() or not hasattr(a, "coordinates"):
            skipped += 1
            continue
        ca, cb = a.coordinates, b.coordinates
        if len(ca) != len(cb):
            skipped += 1
            continue
        errs[name] = max((max(abs(x1 - x2), abs(y1 - y2))
                          for (x1, y1), (x2, y2) in zip(ca, cb)), default=0)
    return errs, skipped


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def describe(errs):
    vals = sorted(errs.values())
    return {
        "glyphs": len(vals),
        "max": vals[-1] if vals else 0,
        "p50": pct(vals, 0.50), "p90": pct(vals, 0.90),
        "p99": pct(vals, 0.99), "p999": pct(vals, 0.999),
        "over_4": sum(1 for v in vals if v > 4),
        "over_8": sum(1 for v in vals if v > 8),
        "over_16": sum(1 for v in vals if v > 16),
        "over_32": sum(1 for v in vals if v > 32),
        "over_64": sum(1 for v in vals if v > 64),
    }


def main() -> int:
    e100, sk100 = glyph_errors(VF / "arm_b2_vfsafe_100.ttf",
                               VF / "stock_100.ttf")
    e400, sk400 = glyph_errors(VF / "arm_b2_vfsafe_400.ttf",
                               VF / "stock_400.ttf")
    e900, sk900 = glyph_errors(VF / "arm_b2_vfsafe_900.ttf",
                               VF / "stock_900.ttf")
    print("wght 100 (fvar default):", describe(e100), "skipped:", sk100)
    print("wght 400 (mid-axis):", describe(e400), "skipped:", sk400)
    print("wght 900:", describe(e900), "skipped:", sk900)

    # Amplification among glyphs that actually moved at the default:
    # ratio err900 / err100 for glyphs with err100 >= 2.
    ratios = sorted(e900[g] / e100[g] for g in e100
                    if e100.get(g, 0) >= 2 and g in e900)
    tail = sorted(((e900[g], g, e100[g]) for g in e900
                   if e900[g] > 16), reverse=True)
    out = {
        "provenance": {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime()),
                       "fvar_default_weight": 100,
                       "inputs": ["vf/arm_b2_vfsafe_100.ttf",
                                  "vf/stock_100.ttf",
                                  "vf/arm_b2_vfsafe_400.ttf",
                                  "vf/stock_400.ttf",
                                  "vf/arm_b2_vfsafe_900.ttf",
                                  "vf/stock_900.ttf"]},
        "wght100_default": describe(e100),
        "wght400_midaxis": describe(e400),
        "wght900": describe(e900),
        "amplification_ratio_err100_ge2": {
            "glyphs": len(ratios),
            "p50": pct(ratios, 0.5), "p90": pct(ratios, 0.9),
            "p99": pct(ratios, 0.99), "max": ratios[-1] if ratios else 0},
        "tail_over_16_at_900": [
            {"glyph": g, "err900": e9, "err100": e1} for e9, g, e1 in tail],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"tail glyphs with err900>16: {len(tail)} of {len(e900)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
