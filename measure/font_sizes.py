#!/usr/bin/env python3
"""Measure raw / gzip / brotli / WOFF2 sizes and table composition of CJK fonts."""
from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from fontTools.ttLib import TTFont
import brotli

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
OUT = ROOT / "measure" / "out"
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = [
    ("NotoSansJP[wght].ttf", "Noto Sans JP", "variable"),
    ("NotoSerifJP[wght].ttf", "Noto Serif JP", "variable"),
    ("NotoSansSC[wght].ttf", "Noto Sans SC", "variable"),
    ("NotoSansKR[wght].ttf", "Noto Sans KR", "variable"),
    ("MPLUS1p-Regular.ttf", "M PLUS 1p", "static"),
    ("ZenKakuGothicNew-Regular.ttf", "Zen Kaku Gothic New", "static"),
    ("KosugiMaru-Regular.ttf", "Kosugi Maru", "static"),
    ("ShipporiMincho-Regular.ttf", "Shippori Mincho", "static"),
    ("SawarabiMincho-Regular.ttf", "Sawarabi Mincho", "static"),
    ("LXGWWenKai-Regular.ttf", "LXGW WenKai", "static"),
    ("NanumGothic-Regular.ttf", "Nanum Gothic", "static"),
    ("SourceHanSansJP-Full-Regular.otf", "Source Han Sans JP", "cff"),
]


def table_sizes(font: TTFont) -> dict[str, int]:
    out = {}
    for tag in font.reader.tables:
        try:
            out[tag] = font.reader.tables[tag].length
        except Exception:
            pass
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def woff2_compress(src: Path, dst: Path) -> float:
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "-m", "fontTools.ttLib.woff2", "compress", str(src), "-o", str(dst)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1000:])
    return time.time() - t0


def main() -> int:
    out_json = OUT / "font_sizes.json"
    rows = []
    if out_json.exists():
        try:
            rows = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    done = {r["file"] for r in rows}
    for fname, family, kind in TARGETS:
        src = FONTS / fname
        if not src.exists():
            print(f"skip missing {fname}", flush=True)
            continue
        if fname in done:
            print(f"skip done {fname}", flush=True)
            continue
        t0 = time.time()
        font = TTFont(str(src), lazy=True)
        n_glyphs = len(font.getGlyphOrder())
        upm = font["head"].unitsPerEm
        tables = table_sizes(font)
        has = {
            "glyf": "glyf" in font,
            "CFF": "CFF " in font,
            "CFF2": "CFF2" in font,
            "gvar": "gvar" in font,
            "fvar": "fvar" in font,
        }
        axes = []
        if "fvar" in font:
            axes = [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes]
        font.close()

        raw = src.read_bytes()
        gz = gzip.compress(raw, 9)
        br = brotli.compress(raw, quality=11, lgwin=24)
        w2 = OUT / (src.stem + ".woff2")
        secs = woff2_compress(src, w2)
        w2_size = w2.stat().st_size

        row = {
            "family": family,
            "file": fname,
            "kind": kind,
            "raw_bytes": len(raw),
            "gzip9_bytes": len(gz),
            "brotli11_bytes": len(br),
            "woff2_bytes": w2_size,
            "woff2_encode_s": round(secs, 2),
            "num_glyphs": n_glyphs,
            "units_per_em": upm,
            "tables": has,
            "axes": axes,
            "top_tables": dict(list(tables.items())[:10]),
            "load_s": round(time.time() - t0, 2),
        }
        rows.append(row)
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
        print(
            f"{family:22s} glyphs={n_glyphs:6d} raw={len(raw)/1e6:7.2f}MB "
            f"w2={w2_size/1e6:7.2f}MB ({w2_size/len(raw)*100:5.1f}%) "
            f"br11={len(br)/len(raw)*100:5.1f}% enc={secs:.1f}s",
            flush=True,
        )

    (OUT / "font_sizes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    with open(OUT / "font_sizes.csv", "w", encoding="utf-8") as f:
        keys = ["family", "file", "kind", "raw_bytes", "gzip9_bytes", "brotli11_bytes", "woff2_bytes", "woff2_encode_s", "num_glyphs", "units_per_em"]
        f.write(",".join(keys) + "\n")
        for r in rows:
            f.write(",".join(str(r[k]) for k in keys) + "\n")
    print("wrote", OUT / "font_sizes.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
