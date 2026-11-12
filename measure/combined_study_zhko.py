#!/usr/bin/env python3
"""Round 3: the combined delivery x GLC study, extended to Chinese and Korean.

Round 2 ran the combined study for Japanese only (measure/combined_study.py).
This script reruns the identical harness for the zh and ko pages of the same
committed corpus summary (measure/web/corpus_stats.json), with the matching
Noto fonts (static wght=400 instances of Noto Sans SC / Noto Sans KR):

  full            the whole font as one stock WOFF2
  google_fonts    per-page bytes from the published corpus audit
  exact           per-page exact subset, stock WOFF2
  exact+glc       the same subset, then GLC-2 (grids 4 and 8)
  base500         shared 500-character base slice (document frequency over
                  the language's pages) + per-page residual; cold and warm
  base500+glc     the same with GLC applied to both parts

Corpus caveats (disclosed, not hidden): zh has 7 usable pages; ko has only
4 -- news.naver.com and www.daum.net have no character set and no Google
Fonts estimate in the committed corpus summary, so they are excluded here
exactly as a page would be excluded from the ja arm for missing data.
With 4 pages the ko document-frequency base is coarse; the medians are
over 4 pages and are reported as such.

Usage:  .venv/bin/python measure/combined_study_zhko.py
Writes: measure/out/combined_study_zh.json, measure/out/combined_study_ko.json
"""
from __future__ import annotations

import io
import json
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
STATS = ROOT / "measure" / "web" / "corpus_stats.json"
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402

GRIDS_COMBINED = (4, 8)
ANCHOR_SIZES = [100, 200, 300, 500, 750, 1000, 1500, 2000, 3000]
BASE_N = 500

LANGS = {
    "zh": {"font": OUT / "NotoSansSC-Regular.ttf",
           "font_name": "Noto Sans SC (static 400, instanced from variable)"},
    "ko": {"font": OUT / "NotoSansKR-Regular.ttf",
           "font_name": "Noto Sans KR (static 400, instanced from variable)"},
}


def subset_ttf_bytes(font_path: Path, cps, drop_vertical: bool) -> bytes:
    from fontTools import subset
    o = subset.Options()
    o.hinting = False
    o.layout_features = ["*"]
    o.name_IDs = [1, 2, 3, 4, 5, 6]
    o.name_languages = ["*"]
    o.notdef_outline = True
    o.recalc_bounds = True
    o.drop_tables += ["DSIG", "VDMX"]
    if drop_vertical:
        o.drop_tables += ["vhea", "vmtx"]
    font = subset.load_font(str(font_path), o)
    ss = subset.Subsetter(options=o)
    ss.populate(unicodes=set(cps))
    ss.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    font.close()
    return buf.getvalue()


def woff2_size(ttf_bytes: bytes) -> int:
    from fontTools.ttLib import TTFont
    f = TTFont(io.BytesIO(ttf_bytes))
    f.flavor = "woff2"
    buf = io.BytesIO()
    f.save(buf)
    f.close()
    return len(buf.getvalue())


def glc_woff2_size(ttf_bytes: bytes, grid: int, tmpdir: Path, tag: str) -> int:
    src = tmpdir / f"{tag}.ttf"
    dst = tmpdir / f"{tag}_q.ttf"
    src.write_bytes(ttf_bytes)
    process_font(str(src), str(dst), canonical=False, grid=grid)
    return woff2_size(dst.read_bytes())


def measure(font_path: Path, cps, tmpdir: Path, tag: str, grids=GRIDS_COMBINED) -> dict:
    plain_ttf = subset_ttf_bytes(font_path, cps, drop_vertical=False)
    glc_ttf = subset_ttf_bytes(font_path, cps, drop_vertical=True)
    row = {"chars": len(cps), "exact": woff2_size(plain_ttf)}
    for g in grids:
        row[f"exact_glc{g}"] = glc_woff2_size(glc_ttf, g, tmpdir, f"{tag}_g{g}")
    return row


def agg(vals):
    v = sorted(vals)
    return {"median": v[len(v) // 2], "mean": round(statistics.mean(v), 1),
            "min": v[0], "max": v[-1]}


def run_lang(lang: str, cfg: dict) -> dict:
    from fontTools.ttLib import TTFont
    font_path = cfg["font"]
    if not font_path.exists():
        raise SystemExit(f"missing {font_path} -- instance the variable font first")
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    pages = []
    skipped = []
    for r in stats:
        if r.get("lang") != lang:
            continue
        if "unique_chars" not in r or not r.get("gf_estimate"):
            skipped.append(r["url"])
            continue
        pages.append({"url": r["url"], "genre": r.get("genre"),
                      "cps": {ord(c) for c in r["unique_chars"]},
                      "google_fonts_bytes": r["gf_estimate"]["bytes_used"]})
    f = TTFont(str(font_path), lazy=True)
    cmap = set(f.getBestCmap())
    f.close()
    for p in pages:
        p["cps"] &= cmap
    df = Counter()
    for p in pages:
        for cp in p["cps"]:
            df[cp] += 1
    df_order = [cp for cp, _ in sorted(df.items(), key=lambda kv: (-kv[1], kv[0]))]
    base = set(df_order[:BASE_N])
    full_bytes = woff2_size(font_path.read_bytes())
    print(f"[{lang}] pages={len(pages)} skipped={len(skipped)} base={len(base)} "
          f"full={full_bytes:,}", flush=True)

    with tempfile.TemporaryDirectory(prefix=f"combined-{lang}-") as td:
        tmp = Path(td)
        base_row = measure(font_path, sorted(base), tmp, "base")
        print(f"[{lang}] base500: exact={base_row['exact']:,} glc8={base_row['exact_glc8']:,}",
              flush=True)
        rows = []
        for i, p in enumerate(pages):
            row = measure(font_path, sorted(p["cps"]), tmp, f"page{i}")
            resid = sorted(p["cps"] - base)
            rrow = measure(font_path, resid, tmp, f"page{i}r") if resid else {
                "chars": 0, "exact": 0, **{f"exact_glc{g}": 0 for g in GRIDS_COMBINED}}
            out = {"url": p["url"], "genre": p["genre"], "chars": row["chars"],
                   "google_fonts": p["google_fonts_bytes"],
                   "exact": row["exact"], "resid_chars": rrow["chars"]}
            for g in GRIDS_COMBINED:
                out[f"exact_glc{g}"] = row[f"exact_glc{g}"]
                out[f"base_resid_cold_glc{g}"] = base_row[f"exact_glc{g}"] + rrow[f"exact_glc{g}"]
                out[f"base_resid_warm_glc{g}"] = rrow[f"exact_glc{g}"]
            out["base_resid_cold"] = base_row["exact"] + rrow["exact"]
            out["base_resid_warm"] = rrow["exact"]
            rows.append(out)
            print(f"[{lang} {i+1}/{len(pages)}] chars={row['chars']:5d} "
                  f"exact={row['exact']/1024:7.1f}KiB glc8={row['exact_glc8']/1024:7.1f}KiB",
                  flush=True)

        anchors = []
        for n in ANCHOR_SIZES:
            if n > len(df_order):
                print(f"[{lang}] anchor {n} skipped (only {len(df_order)} distinct chars)",
                      flush=True)
                continue
            a = measure(font_path, df_order[:n], tmp, f"anchor{n}", grids=(4, 8, 16))
            a0 = woff2_size(subset_ttf_bytes(font_path, df_order[:n], drop_vertical=False))
            anchors.append({"chars": n, "exact": a0,
                            **{f"exact_glc{g}": a[f"exact_glc{g}"] for g in (4, 8, 16)}})
            print(f"[{lang}] anchor {n:5d}: exact={a0/1024:7.1f}KiB "
                  f"glc8={a['exact_glc8']/1024:7.1f}KiB", flush=True)

    keys = ["google_fonts", "exact", "exact_glc4", "exact_glc8",
            "base_resid_cold", "base_resid_warm",
            "base_resid_cold_glc8", "base_resid_warm_glc8"]
    summary = {k: agg([r[k] for r in rows]) for k in keys}
    gains = {
        "glc_gain_on_exact_subsets_pct": {
            f"grid{g}": round(100 * (1 - statistics.median(
                [r[f"exact_glc{g}"] / r["exact"] for r in rows])), 2)
            for g in GRIDS_COMBINED},
        "glc_gain_on_base500_pct": round(
            100 * (1 - base_row["exact_glc8"] / base_row["exact"]), 2),
        "glc_gain_on_anchors_pct": {
            str(a["chars"]): round(100 * (1 - a["exact_glc8"] / a["exact"]), 2)
            for a in anchors},
    }
    return {
        "meta": {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "lang": lang, "font": cfg["font_name"],
                 "pages": len(pages), "pages_skipped_no_data": skipped,
                 "base_size": BASE_N,
                 "base_order": "document frequency over the language's pages",
                 "full_font_woff2_bytes": full_bytes,
                 "base500_chars": "".join(chr(c) for c in df_order[:BASE_N]),
                 "base500": base_row},
        "summary": summary, "gains": gains,
        "anchors": anchors, "per_page": rows,
    }


def main() -> int:
    for lang, cfg in LANGS.items():
        result = run_lang(lang, cfg)
        out_path = OUT / f"combined_study_{lang}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"wrote {out_path}", flush=True)
        print(f"[{lang}] summary:", json.dumps(result["summary"]), flush=True)
        print(f"[{lang}] gains:", json.dumps(result["gains"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
