#!/usr/bin/env python3
"""Full-font WOFF2 sizes with and without the GLC pipeline (headline numbers)."""
from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "glc"; WORK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font

def woff2(src: Path, dst: Path):
    cmd = [sys.executable, "-m", "fontTools.ttLib.woff2", "compress", str(src), "-o", str(dst)]
    t0 = time.time(); r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-500:])
    return dst.stat().st_size, round(time.time()-t0, 1)

rows = []
src = ROOT / "measure/out/NotoSansJP-Regular.ttf"
for name, grid in [("woff2_baseline", 0), ("glc_g4", 4), ("glc_g8", 8), ("glc_g16", 16)]:
    ttf = WORK / f"full_{name}.ttf"
    if name == "woff2_baseline":
        if not ttf.exists():
            process_font(str(src), str(ttf), canonical=False, grid=0)
    else:
        if not ttf.exists():
            process_font(str(src), str(ttf), canonical=False, grid=grid)
    w = WORK / f"full_{name}.woff2"
    size, secs = woff2(ttf, w)
    rows.append({"font": "Noto Sans JP (static 400, full)", "variant": name, "bytes": size, "encode_s": secs})
    print(f"{name:18s} {size/1e6:6.3f} MB  ({secs}s)", flush=True)
(OUT / "glc_fullfont.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
print("wrote", OUT / "glc_fullfont.json")
