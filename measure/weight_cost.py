#!/usr/bin/env python3
"""Round 4, item 2b: what each variable-font weight costs (Arm A prices).

Round 3's per-weight table lived in measure/out/variable_glc.json, which
did not survive (the vf/ working files did). This script recomputes every
number from the surviving artifacts, so the round-4 analysis stands on
files that exist:

  * full instances: measure/out/vf/stock_{100..900}.ttf -> WOFF2 bytes,
    and their GLC grid-8 counterparts inst_{w}_q8.ttf -> WOFF2 bytes
    (inst_900_q8.ttf was missing; it is regenerated from stock_900.ttf
    with tools/glc.py and written back into vf/).
  * single-file arms: the stock VF and vf_safe_q8.ttf -> WOFF2 bytes
    (cross-check of round 3's "-8.6%" claim for Arm B2).
  * per-page subset costs: for each Japanese corpus page, the page's
    character set subsetted from the 400 / 500 / 700 stock instances,
    with and without GLC grid 8 -- the per-weight price in the
    subset-delivery model of the combined study.

Output: measure/out/weight_cost.json
Usage:  .venv/bin/python measure/weight_cost.py
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
import glc as glc_mod  # noqa: E402

VF_DIR = HERE / "out" / "vf"
STATS = HERE / "web" / "corpus_stats.json"
OUT = HERE / "out" / "weight_cost.json"
WEIGHTS = list(range(100, 1000, 100))
LAYOUT = "abvm,blwm,ccmp,dtls,flac,halt, isol, jalt, kern, ljmo, locl, " \
         "mkmk, palt, pkna, pwid, ruby, tjmo, tnum, vhal, vjmo, vkna, " \
         "vkrn, vpal, vrt2".replace(" ", "")


def woff2_bytes(path: Path) -> int:
    f = TTFont(str(path))
    f.flavor = "woff2"
    buf = io.BytesIO()
    f.save(buf)
    return buf.tell()


def subset_woff2(ttf: Path, unicodes: str, tmp: Path) -> int:
    sub = tmp / "sub.ttf"
    subprocess.run(
        [sys.executable, "-m", "fontTools.subset", str(ttf),
         f"--unicodes={unicodes}", f"--output-file={sub}",
         f"--layout-features={LAYOUT}", "--no-hinting", "--desubroutinize"],
        check=True, capture_output=True)
    return woff2_bytes(sub)


def subset_glc_woff2(ttf: Path, unicodes: str, tmp: Path) -> int:
    sub = tmp / "sub.ttf"
    out = tmp / "sub_q.ttf"
    subprocess.run(
        [sys.executable, "-m", "fontTools.subset", str(ttf),
         f"--unicodes={unicodes}", f"--output-file={sub}",
         f"--layout-features={LAYOUT}", "--no-hinting", "--desubroutinize"],
        check=True, capture_output=True)
    glc_mod.process_font(str(sub), str(out), grid=8)
    return woff2_bytes(out)


def median(v: list[float]) -> float:
    s = sorted(v)
    return s[len(s) // 2]


def main() -> int:
    # --- regenerate the one missing GLC instance (weight 900)
    inst900 = VF_DIR / "inst_900_q8.ttf"
    if not inst900.exists():
        glc_mod.process_font(str(VF_DIR / "stock_900.ttf"), str(inst900),
                             grid=8)
        print("regenerated inst_900_q8.ttf")

    full = {}
    for w in WEIGHTS:
        stock = woff2_bytes(VF_DIR / f"stock_{w}.ttf")
        quant = woff2_bytes(VF_DIR / f"inst_{w}_q8.ttf")
        full[str(w)] = {"stock_woff2": stock, "glc8_woff2": quant,
                        "glc_gain_pct": round(100 * (1 - quant / stock), 1)}
        print(f"w{w}: stock {stock:,} glc8 {quant:,} "
              f"({full[str(w)]['glc_gain_pct']}%)")

    vf_stock = woff2_bytes(ROOT / "fonts" / "NotoSansJP[wght].ttf")
    vf_b2 = woff2_bytes(VF_DIR / "vf_safe_q8.ttf")
    single = {"vf_stock_woff2": vf_stock, "vf_safe_q8_woff2": vf_b2,
              "b2_gain_pct": round(100 * (1 - vf_b2 / vf_stock), 1)}
    print(f"VF stock {vf_stock:,}  B2 safe {vf_b2:,}  "
          f"gain {single['b2_gain_pct']}%  (round 3 claimed -8.6%)")

    arm_a = {}
    for label, ws in [("{400}", [400]), ("{400,700}", [400, 700]),
                      ("{400,500,700}", [400, 500, 700]),
                      ("{100..900}", WEIGHTS)]:
        arm_a[label] = sum(full[str(w)]["glc8_woff2"] for w in ws)
    print("Arm A totals:", arm_a)

    # --- per-page subset costs at 400 / 500 / 700 (Japanese pages)
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    ja = [r for r in stats if r.get("lang") == "ja" and r.get("unique_chars")]
    per_page: dict[str, list] = {str(w): [] for w in (400, 500, 700)}
    per_page_raw: dict[str, list] = {str(w): [] for w in (400, 500, 700)}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for rec in ja:
            cmap = TTFont(str(VF_DIR / "stock_400.ttf"),
                          lazy=True).getBestCmap()
            chars = "".join(c for c in rec["unique_chars"] if ord(c) in cmap)
            unicodes = ",".join(f"U+{ord(c):04X}" for c in chars)
            row = {}
            for w in (400, 500, 700):
                src = VF_DIR / f"stock_{w}.ttf"
                raw = subset_woff2(src, unicodes, tmp)
                q = subset_glc_woff2(src, unicodes, tmp)
                per_page[str(w)].append(q)
                per_page_raw[str(w)].append(raw)
                row[w] = q
            print(f"page chars={len(chars):4d} glc subsets: {row}")
    subset_med = {w: {"glc8_median": median(per_page[w]),
                      "raw_median": median(per_page_raw[w])}
                  for w in per_page}
    print("subset medians:", subset_med)

    out = {"provenance": {
               "note": "recomputed from measure/out/vf/*.ttf (round 3 "
                       "working files); inst_900_q8.ttf regenerated",
               "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
           "full_instances": full, "single_file": single, "arm_a_totals": arm_a,
           "page_subsets_ja": {"n_pages": len(ja), "medians": subset_med,
                               "per_page_glc8": per_page}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
