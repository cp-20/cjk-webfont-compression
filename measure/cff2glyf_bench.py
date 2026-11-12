#!/usr/bin/env python3
"""Measure WOFF2 sizes for CFF fonts vs. the same outlines converted to glyf.

WOFF2's content transform only applies to glyf/loca/hmtx. CFF (PostScript)
outlines therefore keep ~70% of their original size, while the cubic->quadratic
converted font can use the transform.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
sys.path.insert(0, str(ROOT / "tools"))
from cff2glyf import cff_to_glyf  # noqa: E402

WORK = OUT / "cff2glyf"
WORK.mkdir(parents=True, exist_ok=True)

CASES = [
    ("Source Han Sans JP", "fonts/SourceHanSansJP-Full-Regular.otf", "ja"),
    ("Source Han Sans JP (subset OTF)", "fonts/SourceHanSansJP-Regular.otf", "ja"),
]


def top_chars(lang: str, n: int):
    corpus = json.loads((ROOT / "measure" / "web" / "corpus.json").read_text(encoding="utf-8"))
    tf = Counter()
    for r in corpus:
        if r.get("lang") != lang or "text" not in r:
            continue
        for c in r["text"]:
            if not c.isspace():
                tf[ord(c)] += 1
    return [cp for cp, _ in tf.most_common(n)]


def subset_woff2(src: Path, dst: Path, chars):
    cmd = [sys.executable, "-m", "fontTools.subset", str(src),
           "--unicodes=" + ",".join(f"U+{c:04X}" for c in chars),
           "--flavor=woff2", "--no-hinting", "--layout-features=*",
           "--name-IDs=1,2,3,4,5,6", "--name-languages=*",
           "--notdef-outline", "--recalc-bounds", "--output-file=" + str(dst)]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return dst.stat().st_size, round(time.time() - t0, 1)


def main():
    n_chars = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    rows = []
    for family, rel, lang in CASES:
        src = ROOT / rel
        if not src.exists():
            continue
        chars = top_chars(lang, n_chars)
        tag = family.replace(" ", "_").replace("(", "").replace(")", "")
        # CFF baseline
        cff_w = WORK / f"{tag}_cff.woff2"
        size_cff, s1 = subset_woff2(src, cff_w, chars)
        # converted to glyf
        ttf = WORK / f"{tag}.ttf"
        if not ttf.exists():
            t0 = time.time()
            stats = cff_to_glyf(str(src), str(ttf), max_err_ratio=0.001)
            print("convert:", stats, flush=True)
        gly_w = WORK / f"{tag}_glyf.woff2"
        size_gly, s2 = subset_woff2(ttf, gly_w, chars)
        row = {
            "font": family, "chars": len(chars),
            "cff_woff2_bytes": size_cff, "cff_encode_s": s1,
            "glyf_woff2_bytes": size_gly, "glyf_encode_s": s2,
            "saving": 1 - size_gly / size_cff,
            "ttf_bytes": ttf.stat().st_size,
            "source_bytes": src.stat().st_size,
        }
        rows.append(row)
        print(f"{family:32s} CFF {size_cff/1024:9.1f} KiB -> glyf {size_gly/1024:9.1f} KiB "
              f"({100*row['saving']:.1f}% 減)", flush=True)
    (OUT / "cff2glyf_bench.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "cff2glyf_bench.json")


if __name__ == "__main__":
    main()
