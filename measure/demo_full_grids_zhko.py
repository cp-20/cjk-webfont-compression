#!/usr/bin/env python3
"""Round 5: full-font WOFF2 bytes per GLC grid for Noto Sans SC / KR.

The demo's section 2 shows, per language, the full-font WOFF2 size at
each grid as a reference next to the demo subset's size. For Japanese
those numbers come from measure/out/glc_fullsweep.json; the sweep never
covered SC/KR, so this script measures them with the identical method
(glyphcodec.process_font, canonical=False, then the fontTools WOFF2
encoder) on the same static instances the combined study used
(measure/out/NotoSans{SC,KR}-Regular.ttf).

Always regenerates its intermediates (the round-2/3 stale-cache lesson).
Output: measure/out/demo_full_zhko.json.
Usage:  .venv/bin/python measure/demo_full_grids_zhko.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402

GRIDS = [0, 2, 4, 8, 16, 32]
FONTS = [
    ("zh", "Noto Sans SC", "measure/out/NotoSansSC-Regular.ttf"),
    ("ko", "Noto Sans KR", "measure/out/NotoSansKR-Regular.ttf"),
]


def woff2(src: Path, dst: Path):
    cmd = [sys.executable, "-m", "fontTools.ttLib.woff2", "compress",
           str(src), "-o", str(dst)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-400:])
    return dst.stat().st_size, round(time.time() - t0, 2)


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory(prefix="demo-full-") as td:
        tmp = Path(td)
        for lang, family, rel in FONTS:
            src = ROOT / rel
            for grid in GRIDS:
                ttf = tmp / f"full_{lang}_q{grid}.ttf"
                t0 = time.time()
                process_font(str(src), str(ttf), canonical=False, grid=grid)
                prep_s = round(time.time() - t0, 2)
                w = tmp / f"full_{lang}_q{grid}.woff2"
                size, enc_s = woff2(ttf, w)
                rows.append({"lang": lang, "font": family, "grid": grid,
                             "bytes": size, "prep_s": prep_s,
                             "encode_s": enc_s})
                print(f"{family:14s} grid={grid:2d} {size:,} B "
                      f"prep={prep_s:.1f}s enc={enc_s:.1f}s", flush=True)
                (OUT / "demo_full_zhko.json").write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print("wrote", OUT / "demo_full_zhko.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
