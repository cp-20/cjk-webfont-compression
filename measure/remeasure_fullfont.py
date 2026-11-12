#!/usr/bin/env python3
"""Round 3: clean-room re-measurement of the two conflicting full-font tables.

Background. Two published JSONs claim to be "the" full-font GLC table and
disagree by ~5 % on the quantised rows:

  * measure/out/glc_fullsweep.json -- Noto grid 8: 1,755,656 B (reproduces)
  * measure/out/glc_fullfont.json  -- Noto grid 8: 1,667,400 B (does not)

and inside glc_fullsweep.json the M PLUS 1p quantised rows have prep_s = 0.0,
i.e. that script reused intermediate TTFs instead of measuring them.

Both generator scripts call the same tools/glyphcodec.process_font with the
same arguments; they differ only in their cache directory -- and both skip
regenerating an intermediate that already exists. So a table can silently
inherit sizes produced by an *older state of the code*. The report text
itself (report/glc_content.py) records that an early quantiser variant did
NOT preserve glyph bounding boxes and measured 1.667 MB at grid 8, ~5 %
smaller than the bbox-preserving pipeline -- exactly the size of the
discrepancy.

This script settles it from scratch, in a fresh work directory, with no
cache reuse anywhere:

  1. Noto Sans JP (static 400) and M PLUS 1p, grids 0/2/4/8/16/32, through
     the committed process_font (canonical=False, bbox preserved), each
     compared against both published tables.
  2. A forensic arm: Noto at grids 4/8/16 with quantize_glyph monkeypatched
     to keep_bbox=False (the pre-fix variant). If those rows land on the
     glc_fullfont.json values, the stale rows are identified, not guessed.

Usage: .venv/bin/python measure/remeasure_fullfont.py
Writes: measure/out/glc_remeasure.json
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "remeasure"
if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)
sys.path.insert(0, str(ROOT / "tools"))
import glyphcodec  # noqa: E402
from glyphcodec import process_font  # noqa: E402

GRIDS = [0, 2, 4, 8, 16, 32]
FONTS = [
    ("Noto Sans JP (static 400)", OUT / "NotoSansJP-Regular.ttf"),
    ("M PLUS 1p", ROOT / "fonts" / "MPLUS1p-Regular.ttf"),
]


def woff2(src: Path, dst: Path) -> int:
    r = subprocess.run([sys.executable, "-m", "fontTools.ttLib.woff2", "compress",
                        str(src), "-o", str(dst)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-500:])
    return dst.stat().st_size


def published() -> dict:
    sweep = {}
    for row in json.loads((OUT / "glc_fullsweep.json").read_text(encoding="utf-8")):
        sweep[(row["font"], row["grid"])] = row["bytes"]
    full = {}
    variant_grid = {"woff2_baseline": 0, "glc_g4": 4, "glc_g8": 8, "glc_g16": 16}
    for row in json.loads((OUT / "glc_fullfont.json").read_text(encoding="utf-8")):
        full[("Noto Sans JP (static 400)", variant_grid[row["variant"]])] = row["bytes"]
    return {"sweep": sweep, "fullfont": full}


def main() -> int:
    pub = published()
    rows = []
    for family, src in FONTS:
        tag = "noto" if family.startswith("Noto") else "mplus"
        for grid in GRIDS:
            ttf = WORK / f"{tag}_q{grid}.ttf"
            t0 = time.time()
            process_font(str(src), str(ttf), canonical=False, grid=grid)
            prep = round(time.time() - t0, 2)
            size = woff2(ttf, WORK / f"{tag}_q{grid}.woff2")
            row = {"font": family, "grid": grid, "bytes": size, "prep_s": prep,
                   "published_fullsweep": pub["sweep"].get((family, grid)),
                   "published_fullfont": pub["fullfont"].get((family, grid))}
            rows.append(row)
            print(f"{family:26s} grid={grid:2d}  fresh={size:,}  "
                  f"sweep={row['published_fullsweep']}  fullfont={row['published_fullfont']}",
                  flush=True)

    # forensic arm: pre-fix quantiser (no bbox preservation), Noto only
    orig = glyphcodec.quantize_glyph

    def no_bbox(glyph, grid, keep_bbox=True):
        return orig(glyph, grid, keep_bbox=False)

    glyphcodec.quantize_glyph = no_bbox
    try:
        for grid in (4, 8, 16):
            ttf = WORK / f"noto_nobbox_q{grid}.ttf"
            process_font(str(FONTS[0][1]), str(ttf), canonical=False, grid=grid)
            size = woff2(ttf, WORK / f"noto_nobbox_q{grid}.woff2")
            row = {"font": "Noto Sans JP (static 400) [keep_bbox=False]",
                   "grid": grid, "bytes": size, "prep_s": None,
                   "published_fullsweep": pub["sweep"].get(("Noto Sans JP (static 400)", grid)),
                   "published_fullfont": pub["fullfont"].get(("Noto Sans JP (static 400)", grid))}
            rows.append(row)
            print(f"NO-BBOX                    grid={grid:2d}  fresh={size:,}  "
                  f"fullfont={row['published_fullfont']}", flush=True)
    finally:
        glyphcodec.quantize_glyph = orig

    (OUT / "glc_remeasure.json").write_text(
        json.dumps({"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "method": "fresh work dir, no cache reuse; committed process_font; "
                              "plus a keep_bbox=False forensic arm",
                    "rows": rows}, indent=2), encoding="utf-8")
    print("wrote", OUT / "glc_remeasure.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
