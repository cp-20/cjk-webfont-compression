#!/usr/bin/env python3
"""Seed the content-addressed subset cache from the first (v2) measurement run."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slicing_experiment as S  # noqa: E402

ROOT = S.ROOT
OUT = S.OUT

corpus = S.load_corpus()
recs = corpus["ja"]
cmap = S.font_cmap(S.FONT_JA)
supported = set(cmap)
ps_all = [{cp for cp in ({ord(c) for c in r["text"] if not c.isspace()}) if cp in supported}
          for r in recs]
tf_all = {cp: n for cp, n in S.token_freq(recs).items() if cp in supported}
train_idx = [i for i in range(len(recs)) if i % 3 != 2]
train_pages = [ps_all[i] for i in train_idx]
df = Counter()
for ps in train_pages:
    for cp in ps:
        df[cp] += 1
universe = set().union(*train_pages)
token_order = [cp for cp, _ in sorted(tf_all.items(), key=lambda kv: (-kv[1], kv[0]))]
tail = sorted(set(supported) - universe)
tail_bins = S.codepoint_bins(tail, 100)

schemes = {}
df_order = sorted(universe, key=lambda cp: (-df.get(cp, 0), cp))
top = df_order[:3000]
rest = sorted(df_order[3000:])
schemes["google_like"] = [top[i * 150:(i + 1) * 150] for i in range(20)] + S.codepoint_bins(rest, 100) + tail_bins
for K in (16, 32):
    schemes[f"lsa_K{K}"] = list(S.lsa_clusters(train_pages, universe, K)) + tail_bins
for n in (500, 1000, 2000, 3000):
    schemes[f"base{n}_only"] = [token_order[:n]] + tail_bins
schemes["base1000_lsa32"] = [token_order[:1000]] + list(S.lsa_clusters(train_pages, universe, 32)) + tail_bins

keymap = {}


def add(key, cps):
    if not cps:
        return
    keymap[key] = S.hkey(cps)


for key, blocks in schemes.items():
    for i, b in enumerate(blocks):
        add(f"{key}#{i}", b)
for i, ps in enumerate(ps_all):
    add(f"exact#{i}", sorted(ps))
    add(f"first1000#{i}", S.ordered_first(recs[i], 1000))
for n in (500, 1000, 2000, 3000):
    add(f"base{n}", token_order[:n])
    b = set(token_order[:n])
    for i, ps in enumerate(ps_all):
        add(f"union{n}#{i}", sorted(b | ps))

PREFIX_RENAME = [
    ("base_plus_lsa32#", "base1000_lsa32#"),
    ("base_only#", "base1000_only#"),
]

old = json.loads((OUT / "subset_sizes.json").read_text())
cache = {}
if S.CACHE.exists():
    cache = json.loads(S.CACHE.read_text())
hit = miss = 0
for name, size in old.items():
    newname = name
    for a, b in PREFIX_RENAME:
        if name.startswith(a):
            newname = b + name[len(a):]
            break
    if newname in keymap:
        cache.setdefault(keymap[newname], size)
        hit += 1
    else:
        miss += 1
S.CACHE.write_text(json.dumps(cache))
print(f"migrated {hit} entries ({miss} unmatched), cache now {len(cache)} entries")
