#!/usr/bin/env python3
"""Round 2: measure the delivery layer and the compression layer *combined*.

The published reports measured the two layers separately:

  * delivery (report/index.html): subsetting / slicing decides *which*
    glyphs are sent -- a shared 500-character base slice cuts the median
    per-page payload from 509 KiB (Google Fonts) to 111 KiB;
  * encoding (report/glc.html): GLC decides *how* the glyphs are encoded --
    9-34 % below stock WOFF2 on 3,000-character subsets and full fonts.

Nobody had measured the product of the two: subset first, *then* GLC.
This script does, on the same 31 Japanese pages as the delivery study
(per-page character sets from measure/web/corpus_stats.json, the committed
summary of the corpus; the raw texts are not redistributed).

Arms (all Noto Sans JP, static wght=400 instance):
  full            the whole font as one stock WOFF2 (no subsetting)
  google_fonts    per-page bytes from the published corpus audit
                  (gf_estimate in corpus_stats.json; live-measured 2026-11-11)
  exact           per-page exact subset, stock WOFF2 (delivery layer only;
                  same subset options as measure/slicing_experiment.py)
  exact+glc       the same subset, then GLC-2 + GLC-4 (this study)
  base500         shared base slice (500 most frequent characters) +
                  per-page residual subset; "cold" = base + residual,
                  "warm" = residual only (base already cached / shared)
  base500+glc     the same, with GLC applied to both parts

The base slice here is ordered by *document* frequency across the 31 pages
(the committed corpus summary has per-page character sets, not token
counts), whereas the delivery report used token frequency over the raw
texts. The base is therefore a close relative of the published one, not a
byte-identical copy -- one more reason this study reports its own numbers
for every arm instead of mixing in published subset sizes.

Also measured: frequency-ordered anchor subsets of 100..3,000 characters at
grids 0/4/8/16, which the interactive demo (report/demo.html) uses to
estimate payloads for arbitrary text, and which show how the GLC gain
depends on subset size.

Usage:  .venv/bin/python measure/combined_study.py
Writes: measure/out/combined_study.json
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
FONT = OUT / "NotoSansJP-Regular.ttf"
sys.path.insert(0, str(ROOT / "tools"))
from glyphcodec import process_font  # noqa: E402

GRIDS_COMBINED = (4, 8)      # eps 0.2 % / 0.4 % of em at upm 1000
ANCHOR_SIZES = [100, 200, 300, 500, 750, 1000, 1500, 2000, 3000]
ANCHOR_GRIDS = (0, 4, 8, 16)
BASE_N = 500


def subset_ttf_bytes(cps, drop_vertical: bool) -> bytes:
    """Exact subset as an uncompressed TTF, with the delivery study's options."""
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
    font = subset.load_font(str(FONT), o)
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
    """GLC-4 quantisation (+ hinting strip, as in the published pipeline)."""
    src = tmpdir / f"{tag}.ttf"
    dst = tmpdir / f"{tag}_q.ttf"
    src.write_bytes(ttf_bytes)
    process_font(str(src), str(dst), canonical=False, grid=grid)
    return woff2_size(dst.read_bytes())


def measure(cps, tmpdir: Path, tag: str, grids=GRIDS_COMBINED) -> dict:
    plain_ttf = subset_ttf_bytes(cps, drop_vertical=False)
    glc_ttf = subset_ttf_bytes(cps, drop_vertical=True)
    row = {"chars": len(cps), "exact": woff2_size(plain_ttf)}
    for g in grids:
        row[f"exact_glc{g}"] = glc_woff2_size(glc_ttf, g, tmpdir, f"{tag}_g{g}")
    return row


def agg(vals):
    v = sorted(vals)
    return {"median": v[len(v) // 2], "mean": round(statistics.mean(v), 1),
            "min": v[0], "max": v[-1]}


def main() -> int:
    if not FONT.exists():
        raise SystemExit(f"missing {FONT} -- run measure/reproduce_headline.py first")
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    pages = []
    for r in stats:
        if r.get("lang") != "ja" or "unique_chars" not in r:
            continue
        pages.append({"url": r["url"], "genre": r.get("genre"),
                      "cps": {ord(c) for c in r["unique_chars"]},
                      "google_fonts_bytes": r["gf_estimate"]["bytes_used"]})
    from fontTools.ttLib import TTFont
    f = TTFont(str(FONT), lazy=True)
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
    full_bytes = woff2_size(FONT.read_bytes())
    print(f"pages={len(pages)} base={len(base)} full={full_bytes:,}", flush=True)

    with tempfile.TemporaryDirectory(prefix="combined-") as td:
        tmp = Path(td)
        base_row = measure(sorted(base), tmp, "base")
        print(f"base500: exact={base_row['exact']:,} "
              f"glc8={base_row['exact_glc8']:,}", flush=True)
        rows = []
        for i, p in enumerate(pages):
            row = measure(sorted(p["cps"]), tmp, f"page{i}")
            resid = sorted(p["cps"] - base)
            rrow = measure(resid, tmp, f"page{i}r") if resid else {
                "chars": 0, "exact": 0, **{f"exact_glc{g}": 0 for g in GRIDS_COMBINED}}
            out = {"url": p["url"], "genre": p["genre"], "chars": row["chars"],
                   "google_fonts": p["google_fonts_bytes"],
                   "exact": row["exact"],
                   "resid_chars": rrow["chars"]}
            for g in GRIDS_COMBINED:
                out[f"exact_glc{g}"] = row[f"exact_glc{g}"]
                out[f"base_resid_cold_glc{g}"] = base_row[f"exact_glc{g}"] + rrow[f"exact_glc{g}"]
                out[f"base_resid_warm_glc{g}"] = rrow[f"exact_glc{g}"]
            out["base_resid_cold"] = base_row["exact"] + rrow["exact"]
            out["base_resid_warm"] = rrow["exact"]
            rows.append(out)
            print(f"[{i+1:2d}/{len(pages)}] chars={row['chars']:5d} "
                  f"exact={row['exact']/1024:7.1f}KiB glc8={row['exact_glc8']/1024:7.1f}KiB "
                  f"resid={rrow['chars']:5d}", flush=True)

        anchors = []
        for n in ANCHOR_SIZES:
            a = measure(df_order[:n], tmp, f"anchor{n}", grids=ANCHOR_GRIDS[1:])
            a0 = woff2_size(subset_ttf_bytes(df_order[:n], drop_vertical=False))
            anchors.append({"chars": n, "exact": a0,
                            **{f"exact_glc{g}": a[f"exact_glc{g}"] for g in ANCHOR_GRIDS[1:]}})
            print(f"anchor {n:5d}: exact={a0/1024:7.1f}KiB glc8={a['exact_glc8']/1024:7.1f}KiB",
                  flush=True)

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
    result = {
        "meta": {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "font": "Noto Sans JP (static 400, instanced from variable)",
                 "pages": len(pages), "base_size": BASE_N,
                 "base_order": "document frequency over the 31 pages (see docstring)",
                 "full_font_woff2_bytes": full_bytes,
                 "base500_chars": "".join(chr(c) for c in df_order[:BASE_N]),
                 "base500": base_row},
        "summary": summary, "gains": gains,
        "anchors": anchors, "per_page": rows,
    }
    (OUT / "combined_study.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "combined_study.json")
    print(json.dumps(summary, indent=1))
    print(json.dumps(gains, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
