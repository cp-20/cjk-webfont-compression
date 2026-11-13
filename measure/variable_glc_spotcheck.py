#!/usr/bin/env python3
"""Round 3 spot-check: does a finer grid fix the variable-font IUP blow-up?

variable_glc.py found that direct VF quantisation at grid 8 keeps the
*mean* outline error at the static level (~2.6 units) at every weight,
but the *max* point error grows from 4 units at the default weight
(wght=100) to 138 units at wght=900 -- gvar stores deltas for only a
subset of points and interpolates the rest (IUP) from the default
outline, so perturbing the default outline perturbs the interpolation.

If the amplification were multiplicative in the perturbation, grid 2
(perturbation <= 1 unit) would give a worst case near 138/4 ~ 35 units
at wght=900. Measured result (2026-11-12): the worst case is 88 units
-- the amplification is NOT proportional to the perturbation (IUP
interpolation weights depend on the default outline's relative
geometry, so smaller perturbations do not buy proportionally smaller
worst cases) -- and the grid-2 file is 4,346,256 B, within 0.1% of the
stock variable font: at fine grids the direct route buys nothing at
all. Mean error stays at the static level (0.73 units) at both weights.

Writes measure/out/variable_glc_spotcheck.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "vf"
sys.path.insert(0, str(ROOT / "measure"))
from variable_glc import VF, instance, outline_errors, vf_safe_quantize, woff2_bytes  # noqa: E402


def main() -> int:
    grid = 2
    cand = WORK / f"vf_safe_q{grid}.ttf"
    info = vf_safe_quantize(VF, cand, grid)
    result = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "grid": grid, "quantize_info": info, "woff2": woff2_bytes(cand),
              "outline_error_vs_stock_instance": {}}
    print(f"grid {grid}: vf-safe WOFF2 = {result['woff2']:,}", flush=True)
    for w in (100, 900):
        stock_i = WORK / f"stock_{w}.ttf"
        if not stock_i.exists():
            instance(VF, w, stock_i)
        cand_i = instance(cand, w, WORK / f"spot_q{grid}_{w}.ttf")
        err = outline_errors(stock_i, cand_i)
        result["outline_error_vs_stock_instance"][str(w)] = err
        print(f"wght={w}: {err}", flush=True)
    (OUT / "variable_glc_spotcheck.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "variable_glc_spotcheck.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
