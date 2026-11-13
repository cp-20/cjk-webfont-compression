#!/usr/bin/env python3
"""Build the live-font assets for the interactive demo.

Round 2's demo swapped pre-rendered PNGs when the epsilon slider moved
(and, until round 3's fix, those PNGs were upside down). The round-3
demo renders text *live in the browser* with the actual quantised
fonts; round 5 extends the same treatment to Chinese and Korean:

  report/assets/demo_font_g{0,2,4,8,16,32}.woff2        (Japanese)
  report/assets/demo_font_zh_g{0,2,4,8,16,32}.woff2     (Chinese)
  report/assets/demo_font_ko_g{0,2,4,8,16,32}.woff2     (Korean)
      Noto Sans {JP,SC,KR} (static 400) subset to the per-language
      demo charset, GLC-quantised at each grid. Loaded on demand by
      the page via the FontFace API.

Demo charset (per language): every character used by that language's
pages in the project corpus (measure/web/corpus_stats.json), plus
ASCII, CJK punctuation and fullwidth blocks, script blocks (kana for
ja, Hangul jamo for ko), plus the language's sample text. Broad enough
for typical typed text; the page marks characters outside the subset
instead of showing silent tofu.

Also measured here, on the shipped assets themselves (with the fixed
renderer from measure/glc_render.py): per-grid rendering fidelity of
the sample text at 24 px -- changed-pixel fraction, max channel
difference, and PSNR against the grid-0 asset.

Writes the assets plus measure/out/demo_assets.json (per-language
sizes, charsets, fidelity) which report/build_demo.py embeds into the
page. The top-level fields remain the Japanese entry, as in round 3;
round 5 adds a "languages" map with all three.
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
GRIDS = [0, 2, 4, 8, 16, 32]

SAMPLE_JA = ("日本語の文字形は、筆画の組合せで成立する。永遠の描写質量、"
             "鬱蒼とした森と鸚鵡。フォント圧縮の効果を大きなサイズで確かめてください。")
SAMPLE_ZH = ("中文的文字形，由笔画的组合构成。永恒的描写与质量，"
             "郁郁葱葱的森林和鹦鹉。请在大字号下确认字体压缩的效果。")
SAMPLE_KO = ("한국어의 글자 모양은 획의 조합으로 이루어진다. 영원한 묘사의 질, "
             "울창한 숲과 앵무새. 큰 크기에서 글꼴 압축 효과를 확인해 보세요.")

# (lang, static font, asset prefix, sample, extra unicode blocks)
LANGS = [
    ("ja", OUT / "NotoSansJP-Regular.ttf", "demo_font", SAMPLE_JA,
     [(0x3000, 0x30FF)]),                                   # kana
    ("zh", OUT / "NotoSansSC-Regular.ttf", "demo_font_zh", SAMPLE_ZH,
     []),
    ("ko", OUT / "NotoSansKR-Regular.ttf", "demo_font_ko", SAMPLE_KO,
     [(0x1100, 0x11FF), (0x3130, 0x318F)]),                 # Hangul jamo
]
COMMON_BLOCKS = [(0x20, 0x7E), (0x3000, 0x303F), (0xFF01, 0xFF65)]

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "measure"))
from glyphcodec import process_font  # noqa: E402
import glc_render  # noqa: E402  (renderer fixed in round 3)


def demo_charset(lang: str, font_path: Path, sample: str,
                 extra_blocks: list) -> list[int]:
    stats = json.loads((ROOT / "measure/web/corpus_stats.json")
                       .read_text(encoding="utf-8"))
    cps = set()
    for r in stats:
        if r.get("lang") == lang and "unique_chars" in r:
            cps.update(ord(c) for c in r["unique_chars"])
    for lo, hi in COMMON_BLOCKS + list(extra_blocks):
        cps.update(range(lo, hi + 1))
    cps.update(ord(c) for c in sample)
    from fontTools.ttLib import TTFont
    f = TTFont(str(font_path), lazy=True)
    cmap = set(f.getBestCmap())
    f.close()
    return sorted(cps & cmap)


def subset_ttf(font_path: Path, cps, dst: Path) -> Path:
    from fontTools import subset
    o = subset.Options()
    o.hinting = False
    o.layout_features = ["*"]
    o.name_IDs = [1, 2, 3, 4, 5, 6]
    o.name_languages = ["*"]
    o.notdef_outline = True
    o.recalc_bounds = True
    o.drop_tables += ["DSIG", "VDMX", "vhea", "vmtx"]
    font = subset.load_font(str(font_path), o)
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


def fidelity(ref_ttf: Path, var_ttf: Path, sample: str, px: int = 24) -> dict:
    ca, w, h = glc_render.render(str(ref_ttf), sample, px)
    cb, _, _ = glc_render.render(str(var_ttf), sample, px)
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


def build_lang(lang: str, font_path: Path, prefix: str, sample: str,
               extra_blocks: list, tmp: Path) -> dict:
    from fontTools.ttLib import TTFont
    f = TTFont(str(font_path), lazy=True)
    upm = f["head"].unitsPerEm
    f.close()
    cps = demo_charset(lang, font_path, sample, extra_blocks)
    print(f"[{lang}] charset: {len(cps)} chars", flush=True)
    base_ttf = subset_ttf(font_path, cps, tmp / f"demo_subset_{lang}.ttf")
    rows = []
    for grid in GRIDS:
        if grid == 0:
            ttf = base_ttf
        else:
            ttf = tmp / f"demo_subset_{lang}_q{grid}.ttf"
            process_font(str(base_ttf), str(ttf), canonical=False, grid=grid)
        asset = ASSETS / f"{prefix}_g{grid}.woff2"
        size = to_woff2(ttf, asset)
        fid = ({"px": 24, "changed_pct": 0.0, "max_diff": 0, "psnr_db": None}
               if grid == 0 else fidelity(base_ttf, ttf, sample))
        rows.append({"grid": grid, "file": asset.name, "bytes": size,
                     "fidelity": fid})
        print(f"[{lang}] grid {grid:2d}: {size:,} B  fidelity={fid}",
              flush=True)
    return {"font": f"{font_path.stem} (static 400), demo charset subset",
            "upm": upm, "charset_size": len(cps),
            "charset": "".join(chr(c) for c in cps),
            "sample": sample, "grids": rows}


def main() -> int:
    languages = {}
    with tempfile.TemporaryDirectory(prefix="demo-assets-") as td:
        tmp = Path(td)
        for lang, font_path, prefix, sample, blocks in LANGS:
            if not font_path.exists():
                raise SystemExit(f"missing {font_path} -- run the corpus / "
                                 "reproduce scripts first")
            languages[lang] = build_lang(lang, font_path, prefix, sample,
                                         blocks, tmp)
    ja = languages["ja"]
    result = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "font": "Noto Sans JP (static 400), demo charset subset",
              "charset_size": ja["charset_size"], "charset": ja["charset"],
              "sample": ja["sample"], "grids": ja["grids"],
              "languages": languages}
    (OUT / "demo_assets.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "demo_assets.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
