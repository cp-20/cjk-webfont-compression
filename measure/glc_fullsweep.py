#!/usr/bin/env python3
"""Full-font (no subset) size and encoding time for every quantisation grid."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "sweep"
WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402

GRIDS = [0, 2, 4, 8, 16, 32]
FONTS = [
    ("Noto Sans JP (static 400)", "measure/out/NotoSansJP-Regular.ttf"),
    ("M PLUS 1p", "fonts/MPLUS1p-Regular.ttf"),
]


def woff2(src: Path, dst: Path):
    cmd = [sys.executable, "-m", "fontTools.ttLib.woff2", "compress", str(src), "-o", str(dst)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-400:])
    return dst.stat().st_size, round(time.time() - t0, 2)


def main():
    rows = []
    for family, rel in FONTS:
        src = ROOT / rel
        if not src.exists():
            continue
        tag = family.split(" ")[0].replace(" ", "_")
        for grid in GRIDS:
            ttf = WORK / f"full_{tag}_q{grid}.ttf"
            t0 = time.time()
            if not ttf.exists():
                process_font(str(src), str(ttf), canonical=False, grid=grid)
            prep_s = round(time.time() - t0, 2)
            w = WORK / f"full_{tag}_q{grid}.woff2"
            size, enc_s = woff2(ttf, w)
            rows.append({"font": family, "grid": grid, "bytes": size,
                         "prep_s": prep_s, "encode_s": enc_s,
                         "total_s": round(prep_s + enc_s, 2)})
            print(f"{family:26s} grid={grid:2d} {size/1e6:6.3f} MB  prep={prep_s:5.1f}s enc={enc_s:5.1f}s", flush=True)
            (OUT / "glc_fullsweep.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "glc_fullsweep.json")


if __name__ == "__main__":
    main()
