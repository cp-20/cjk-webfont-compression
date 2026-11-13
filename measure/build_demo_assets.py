#!/usr/bin/env python3
"""Round 3: build the live-font assets for the interactive demo.

Round 2's demo swapped pre-rendered PNGs when the epsilon slider moved
(and, until this round's fix, those PNGs were upside down). The round-3
demo renders text *live in the browser* with the actual quantised fonts:

  report/assets/demo_font_g{0,2,4,8,16,32}.woff2
      Noto Sans JP (static 400) subset to the demo charset, GLC-quantised
      at each grid. Loaded on demand by the page via the FontFace API.

Demo charset (3,500+ characters): every character used by the 31
Japanese pages of the project corpus (measure/web/corpus_stats.json),
plus full ASCII, kana and common punctuation blocks, plus the demo's
sample texts. Broad enough for typical typed Japanese; the page greys
out characters outside the subset instead of showing silent tofu.

Also measured here, on the shipped assets themselves (with the fixed
renderer from measure/glc_render.py): per-grid rendering fidelity of the
sample text at 24 px -- changed-pixel fraction, max channel difference,
and PSNR against the grid-0 asset.

Writes the assets plus measure/out/demo_assets.json (sizes, charset,
fidelity) which report/build_demo.py embeds into the page.
"""
from __future__ import annotations

import io
import json
import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
ASSETS = ROOT / "report" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
FONT = OUT / "NotoSansJP-Regular.ttf"
GRIDS = [0, 2, 4, 8, 16, 32]
SAMPLE = ("日本語の文字形は、筆画の組合せで成立する。永遠の描写質量、"
          "鬱蒼とした森と鸚鵡。フォント圧縮の効果を大きなサイズで確かめてください。")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "measure"))
from glyphcodec import process_font  # noqa: E402
import glc_render  # noqa: E402  (renderer fixed in round 3)


def demo_charset() -> list[int]:
    stats = json.loads((ROOT / "measure/web/corpus_stats.json").read_text(encoding="utf-8"))
    cps = set()
    for r in stats:
        if r.get("lang") == "ja" and "unique_chars" in r:
            cps.update(ord(c) for c in r["unique_chars"])
    for lo, hi in [(0x20, 0x7E), (0x3000, 0x30FF), (0xFF01, 0xFF65)]:
        cps.update(range(lo, hi + 1))
    cps.update(ord(c) for c in SAMPLE)
    from fontTools.ttLib import TTFont
    f = TTFont(str(FONT), lazy=True)
    cmap = set(f.getBestCmap())
    f.close()
    return sorted(cps & cmap)


def subset_ttf(cps, dst: Path) -> Path:
    from fontTools import subset
    o = subset.Options()
    o.hinting = False
    o.layout_features = ["*"]
    o.name_IDs = [1, 2, 3, 4, 5, 6]
    o.name_languages = ["*"]
    o.notdef_outline = True
    o.recalc_bounds = True
    o.drop_tables += ["DSIG", "VDMX", "vhea", "vmtx"]
    font = subset.load_font(str(FONT), o)
    ss = subset.Subsetter(options=o)
    ss.populate(unicodes=set(cps))
    ss.subset(font)
    font.save(str(dst))
    font.close()
    return dst


def to_woff2(ttf_path: Path, dst: Path) -> int:
    from fontTools.ttLib import TTFont
    f = TTFont(str(ttf_path))
    f.flavor = "woff2"
    buf = io.BytesIO()
    f.save(buf)
    f.close()
    dst.write_bytes(buf.getvalue())
    return len(buf.getvalue())


def fidelity(ref_ttf: Path, var_ttf: Path, px: int = 24) -> dict:
    ca, w, h = glc_render.render(str(ref_ttf), SAMPLE, px)
    cb, _, _ = glc_render.render(str(var_ttf), SAMPLE, px)
    se = 0.0
    changed = 0
    total = 0
    worst = 0
    for ra, rb in zip(ca, cb):
        for va, vb in zip(ra, rb):
            total += 1
            d = abs(va - vb)
            if d:
                changed += 1
                se += d * d
                if d > worst:
                    worst = d
    mse = se / total if total else 0.0
    psnr = round(10 * math.log10(255 * 255 / mse), 2) if mse > 0 else None
    return {"px": px, "changed_pct": round(100 * changed / total, 3),
            "max_diff": worst, "psnr_db": psnr}


def main() -> int:
    if not FONT.exists():
        raise SystemExit(f"missing {FONT} -- run measure/reproduce_headline.py first")
    cps = demo_charset()
    print(f"charset: {len(cps)} chars", flush=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="demo-assets-") as td:
        tmp = Path(td)
        base_ttf = subset_ttf(cps, tmp / "demo_subset.ttf")
        ref_ttf = base_ttf
        for grid in GRIDS:
            if grid == 0:
                ttf = base_ttf
            else:
                ttf = tmp / f"demo_subset_q{grid}.ttf"
                process_font(str(base_ttf), str(ttf), canonical=False, grid=grid)
            asset = ASSETS / f"demo_font_g{grid}.woff2"
            size = to_woff2(ttf, asset)
            fid = ({"px": 24, "changed_pct": 0.0, "max_diff": 0, "psnr_db": None}
                   if grid == 0 else fidelity(ref_ttf, ttf))
            rows.append({"grid": grid, "file": asset.name, "bytes": size,
                         "fidelity": fid})
            print(f"grid {grid:2d}: {size:,} B  fidelity={fid}", flush=True)
    result = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "font": "Noto Sans JP (static 400), demo charset subset",
              "charset_size": len(cps),
              "charset": "".join(chr(c) for c in cps),
              "sample": SAMPLE,
              "grids": rows}
    (OUT / "demo_assets.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "demo_assets.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
