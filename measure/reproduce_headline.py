#!/usr/bin/env python3
"""Reproduce the published GLC headline numbers from scratch (round 2).

The published full-font numbers (measure/out/glc_fullsweep.json) depend on
measure/out/NotoSansJP-Regular.ttf -- a static wght=400 instance of the
variable font that no script in this repository creates. This script closes
that gap: it instances the variable font, runs the GLC-4 quantisation at
every published grid through tools/glyphcodec.process_font, encodes WOFF2,
and compares each result byte-for-byte with the published value.

Usage:
    .venv/bin/python measure/reproduce_headline.py
Writes: measure/out/repro_headline.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "repro"
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402

GRIDS = [0, 2, 4, 8, 16, 32]


def woff2(src: Path, dst: Path) -> int:
    cmd = [sys.executable, "-m", "fontTools.ttLib.woff2", "compress", str(src), "-o", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-500:])
    return dst.stat().st_size


def main() -> int:
    var = ROOT / "fonts" / "NotoSansJP[wght].ttf"
    inst = OUT / "NotoSansJP-Regular.ttf"
    if not inst.exists():
        cmd = [sys.executable, "-m", "fontTools.varLib.instancer", str(var),
               "wght=400", "-o", str(inst)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-500:])
        print(f"instanced wght=400 -> {inst} ({inst.stat().st_size:,} B)")

    published = {}
    for row in json.loads((OUT / "glc_fullsweep.json").read_text(encoding="utf-8")):
        if row["font"].startswith("Noto Sans JP"):
            published[row["grid"]] = row["bytes"]

    rows = []
    ok = True
    for grid in GRIDS:
        ttf = WORK / f"noto_q{grid}.ttf"
        if not ttf.exists():
            process_font(str(inst), str(ttf), canonical=False, grid=grid)
        size = woff2(ttf, WORK / f"noto_q{grid}.woff2")
        pub = published.get(grid)
        match = (size == pub)
        ok = ok and match
        rows.append({"font": "Noto Sans JP (static 400, full)", "grid": grid,
                     "published_bytes": pub, "reproduced_bytes": size,
                     "diff_bytes": None if pub is None else size - pub,
                     "exact_match": match})
        print(f"grid={grid:2d}  published={pub:,}  reproduced={size:,}  "
              f"{'EXACT MATCH' if match else 'DIFF ' + str(size - pub)}", flush=True)
    (OUT / "repro_headline.json").write_text(
        json.dumps({"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "instance_bytes": inst.stat().st_size,
                    "all_exact": ok, "rows": rows}, indent=2), encoding="utf-8")
    print("wrote", OUT / "repro_headline.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
