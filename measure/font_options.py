#!/usr/bin/env python3
"""Measure the effect of WOFF2-relevant font options on a CJK font (incremental writes).

Variants (real WOFF2 files, Brotli q11):
  full                    default (hinting kept, all layout features)
  no_hinting              hinting dropped
  no_hinting_no_layout    + GSUB/GPOS dropped
"""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
JSON = OUT / "font_options.json"

TARGETS = [
    ("Noto Sans JP (TrueType, static 400)", "measure/out/NotoSansJP-Regular.ttf"),
]


def build(path, hinting=True, layout=True):
    o = subset.Options()
    o.flavor = "woff2"
    o.hinting = hinting
    o.layout_features = ["*"] if layout else []
    o.name_IDs = [1, 2, 3, 4, 5, 6]
    o.name_languages = ["*"]
    o.notdef_outline = True
    o.recalc_bounds = True
    o.drop_tables += ["DSIG", "VDMX"]
    t0 = time.time()
    font = subset.load_font(path, o)
    ss = subset.Subsetter(options=o)
    ss.populate(glyphs=list(font.getGlyphOrder()))
    ss.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, o)
    return len(buf.getvalue()), round(time.time() - t0, 1)


def main():
    rows = []
    for label, rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            continue
        f = TTFont(p, lazy=True)
        n_glyphs = len(f.getGlyphOrder())
        f.close()
        for name, kw in [("full", dict(hinting=True, layout=True)),
                         ("no_hinting", dict(hinting=False, layout=True)),
                         ("no_hinting_no_layout", dict(hinting=False, layout=False))]:
            size, secs = build(str(p), **kw)
            rows.append({"font": label, "variant": name, "bytes": size,
                         "glyphs": n_glyphs, "encode_s": secs})
            JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{label[:26]:26s} {name:22s} {size/1e6:6.2f} MB  ({secs:5.1f}s)", flush=True)
    print("wrote", JSON)


if __name__ == "__main__":
    main()
