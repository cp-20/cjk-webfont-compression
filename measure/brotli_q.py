#!/usr/bin/env python3
"""Brotli quality sweep for WOFF2 encoding (the conventional "q value").

fontTools' WOFF2 writer always uses Brotli's default quality (11). This script
patches the Brotli call so that the quality can be chosen, then subsets a font
and measures size and encoding time for each quality.
"""
from __future__ import annotations

import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

import fontTools.ttLib.woff2 as w2
from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WORK = OUT / "sweep"
N_CHARS = 3000
QUALITIES = [4, 5, 6, 8, 9, 10, 11]

_orig = w2.brotli.compress


def set_quality(q: int):
    def f(data, **kw):
        kw["quality"] = q
        return _orig(data, **kw)
    w2.brotli.compress = f


def main():
    corpus = json.loads((ROOT / "measure" / "web" / "corpus.json").read_text(encoding="utf-8"))
    tf = Counter()
    for r in corpus:
        if r.get("lang") != "ja" or "text" not in r:
            continue
        for c in r["text"]:
            if not c.isspace():
                tf[ord(c)] += 1
    chars = [cp for cp, _ in tf.most_common(N_CHARS)]
    src = WORK / "Noto_Sans_JP_q8.ttf"
    if not src.exists():
        src = ROOT / "measure/out/NotoSansJP-Regular.ttf"

    rows = []
    for q in QUALITIES:
        set_quality(q)
        o = subset.Options()
        o.flavor = "woff2"
        o.hinting = False
        o.layout_features = ["*"]
        o.name_IDs = [1, 2, 3, 4, 5, 6]
        o.name_languages = ["*"]
        o.notdef_outline = True
        o.recalc_bounds = True
        o.drop_tables += ["DSIG", "VDMX", "vhea", "vmtx"]
        t0 = time.time()
        font = subset.load_font(str(src), o)
        ss = subset.Subsetter(options=o)
        ss.populate(unicodes=set(chars))
        ss.subset(font)
        buf = io.BytesIO()
        subset.save_font(font, buf, o)
        data = buf.getvalue()
        secs = round(time.time() - t0, 2)
        (WORK / f"bq_q{q}.woff2").write_bytes(data)
        rows.append({"brotli_q": q, "bytes": len(data), "encode_s": secs})
        print(f"brotli q={q:2d} {len(data)/1024:8.1f} KiB ({secs:5.1f}s)", flush=True)
    (OUT / "glc_brotli_q.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "glc_brotli_q.json")


if __name__ == "__main__":
    main()
