#!/usr/bin/env python3
"""CJK web font delivery experiment v3 - real WOFF2 measurements (cached).

Content-addressed subset cache: every subset is keyed by a SHA-1 of its
codepoint list, so re-runs only measure what is missing.

Schemes:
  exact_page / first1000   build-time exact subsets (per page)
  google_like              reproduction of the Google Fonts slicing strategy
  lsa_K16 / lsa_K32        co-occurrence (LSA + k-means) topic slices + tail bins
  base_only(N)             one base slice (top-N token frequency) + tail bins
  ift_base+patch           simulated incremental font transfer
"""
from __future__ import annotations

import hashlib
import io
import json
import statistics
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
CACHE = OUT / "subset_cache.json"
CORPUS = ROOT / "measure" / "web" / "corpus.json"
WORKERS = 6
FONT_JA = "measure/out/NotoSansJP-Regular.ttf"

_W = {}


# --------------------------------------------------------------- subsetting
def _init_worker(font_path: str) -> None:
    from fontTools import subset

    o = subset.Options()
    o.flavor = "woff2"
    o.hinting = False
    o.layout_features = ["*"]
    o.name_IDs = [1, 2, 3, 4, 5, 6]
    o.name_languages = ["*"]
    o.notdef_outline = True
    o.recalc_bounds = True
    o.drop_tables += ["DSIG", "VDMX"]
    _W["opts"] = o
    _W["path"] = font_path


def _subset_bytes(arg):
    from fontTools import subset

    key, cps = arg
    o = _W["opts"]
    t0 = time.time()
    font = subset.load_font(_W["path"], o)
    ss = subset.Subsetter(options=o)
    ss.populate(unicodes=set(cps))
    ss.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, o)
    return key, len(buf.getvalue()), round(time.time() - t0, 2)


def hkey(cps):
    return hashlib.sha1(",".join(str(c) for c in sorted(cps)).encode()).hexdigest()[:16]


# --------------------------------------------------------------- corpus
def load_corpus():
    recs = json.loads(CORPUS.read_text(encoding="utf-8"))
    by_lang = defaultdict(list)
    for r in recs:
        if r.get("error") or "text" not in r:
            continue
        by_lang[r["lang"]].append(r)
    return by_lang


def token_freq(recs):
    tf = Counter()
    for r in recs:
        for c in r["text"]:
            if not c.isspace():
                tf[ord(c)] += 1
    return tf


def font_cmap(path: str):
    f = TTFont(path, lazy=True)
    cm = f.getBestCmap()
    f.close()
    return cm


def ordered_first(rec, n):
    seen, out = set(), []
    for c in rec["text"]:
        if c.isspace():
            continue
        cp = ord(c)
        if cp in seen:
            continue
        seen.add(cp)
        out.append(cp)
        if len(out) >= n:
            break
    return out


# --------------------------------------------------------------- clustering
def lsa_clusters(train_pages, universe, K, seed=7):
    chars = sorted(universe)
    idx = {c: i for i, c in enumerate(chars)}
    X = np.zeros((len(train_pages), len(chars)), dtype=np.float32)
    for r, ps in enumerate(train_pages):
        for cp in ps:
            X[r, idx[cp]] = 1.0
    dfreq = X.sum(axis=0)
    idf = np.log((1 + len(train_pages)) / (1 + dfreq)) + 1.0
    Xw = X * idf
    Xc = Xw - Xw.mean(axis=0, keepdims=True)
    kk = min(K, len(chars) - 1)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    V = Vt[:kk].T
    norms = np.linalg.norm(V, axis=1, keepdims=True)
    norms[norms == 0] = 1
    Vn = V / norms
    rng = np.random.default_rng(seed)
    centers = [Vn[rng.integers(len(Vn))]]
    for _ in range(kk - 1):
        d = np.min([((Vn - c) ** 2).sum(axis=1) for c in centers], axis=0)
        p = d / d.sum() if d.sum() > 0 else np.full(len(Vn), 1 / len(Vn))
        centers.append(Vn[rng.choice(len(Vn), p=p)])
    C = np.array(centers)
    assign = np.zeros(len(Vn), dtype=int)
    for _ in range(60):
        dist = ((Vn[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
        new = dist.argmin(axis=1)
        if (new == assign).all():
            break
        assign = new
        for j in range(kk):
            m = assign == j
            if m.any():
                C[j] = Vn[m].mean(axis=0)
    clusters = [[] for _ in range(kk)]
    for c, a in zip(chars, assign):
        clusters[a].append(c)
    return [c for c in clusters if c]


def codepoint_bins(cps, k):
    cps = sorted(cps)
    if not cps:
        return []
    per = (len(cps) + k - 1) // k
    return [cps[i * per:(i + 1) * per] for i in range(k) if cps[i * per:(i + 1) * per]]


# --------------------------------------------------------------- evaluation
def eval_slices(pages, sets, sizes):
    per_page, cache, total = [], set(), 0
    union = set()
    for s in sets:
        union |= s
    for ps in pages:
        used = [i for i, s in enumerate(sets) if s and (s & ps)]
        b = sum(sizes[i] for i in used)
        glyphs = sum(len(sets[i]) for i in used)
        covered = len(ps & union)
        per_page.append({
            "bytes": b, "requests": len(used), "glyphs_fetched": glyphs,
            "chars_used": covered,
            "utilisation": round(covered / glyphs, 4) if glyphs else None,
            "warm_cache_bytes": sum(sizes[i] for i in used if i not in cache),
        })
        total += b
        cache.update(used)
    return per_page, total, sum(sizes[i] for i in cache), len(cache)


def stats(vals):
    v = sorted(vals)
    if not v:
        return {}
    return {"median": v[len(v) // 2], "mean": sum(v) / len(v),
            "p10": v[int(0.1 * (len(v) - 1))], "p90": v[int(0.9 * (len(v) - 1))],
            "min": v[0], "max": v[-1], "total": sum(v)}


def intervals(blocks):
    tot = 0
    for b in blocks:
        b = sorted(b)
        tot += 1 + sum(1 for i in range(len(b) - 1) if b[i + 1] != b[i] + 1)
    return tot


def main():
    t_start = time.time()
    corpus = load_corpus()
    recs = corpus["ja"]
    cmap = font_cmap(FONT_JA)
    supported = set(cmap)
    ps_all = [{cp for cp in ({ord(c) for c in r["text"] if not c.isspace()}) if cp in supported}
              for r in recs]
    tf_all = {cp: n for cp, n in token_freq(recs).items() if cp in supported}
    test_idx = [i for i in range(len(recs)) if i % 3 == 2]
    train_idx = [i for i in range(len(recs)) if i % 3 != 2]
    train_pages = [ps_all[i] for i in train_idx]

    df = Counter()
    for ps in train_pages:
        for cp in ps:
            df[cp] += 1
    universe = set().union(*train_pages)
    token_order = [cp for cp, _ in sorted(tf_all.items(), key=lambda kv: (-kv[1], kv[0]))]
    tail = sorted(set(supported) - universe)
    print(f"pages={len(recs)} train={len(train_pages)} test={len(test_idx)} "
          f"universe={len(universe)} font_cps={len(supported)} tail={len(tail)}", flush=True)

    tail_bins = codepoint_bins(tail, 100)

    # ---------------- schemes
    schemes = {}
    df_order = sorted(universe, key=lambda cp: (-df.get(cp, 0), cp))
    top = df_order[:3000]
    rest = sorted(df_order[3000:])
    gl = [top[i * 150:(i + 1) * 150] for i in range(20)]
    gl += codepoint_bins(rest, 100) + tail_bins
    schemes["google_like"] = gl
    for K in (16, 32):
        schemes[f"lsa_K{K}"] = list(lsa_clusters(train_pages, universe, K)) + tail_bins
    for n in (500, 1000, 2000, 3000):
        schemes[f"base{n}_only"] = [token_order[:n]] + tail_bins
    schemes["base1000_lsa32"] = [token_order[:1000]] + list(lsa_clusters(train_pages, universe, 32)) + tail_bins

    # ---------------- items (content addressed)
    items, keymap = [], {}

    def add(key, cps):
        if not cps:
            return
        h = hkey(cps)
        keymap[key] = h
        if h not in {i[0] for i in items}:
            items.append((h, sorted(cps)))

    for key, blocks in schemes.items():
        for i, b in enumerate(blocks):
            add(f"{key}#{i}", b)
    for i, ps in enumerate(ps_all):
        add(f"exact#{i}", sorted(ps))
        add(f"first1000#{i}", ordered_first(recs[i], 1000))
    for n in (500, 1000, 2000, 3000):
        add(f"base{n}", token_order[:n])
        b = set(token_order[:n])
        for i, ps in enumerate(ps_all):
            add(f"union{n}#{i}", sorted(b | ps))

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [(h, cps) for h, cps in items if h not in cache]
    print(f"subsets: {len(items)} unique, {len(todo)} not cached", flush=True)
    if todo:
        with Pool(WORKERS, initializer=_init_worker, initargs=(FONT_JA,)) as pool:
            done = 0
            for h, size, secs in pool.imap_unordered(_subset_bytes, todo, chunksize=1):
                cache[h] = size
                done += 1
                if done % 20 == 0:
                    print(f"  measured {done}/{len(todo)}", flush=True)
                    CACHE.write_text(json.dumps(cache))
        CACHE.write_text(json.dumps(cache))
    print(f"  measurement done ({time.time()-t_start:.0f}s)", flush=True)

    def size_of(key):
        return cache[keymap[key]]

    # ---------------- evaluation
    out = {
        "meta": {
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "font": FONT_JA, "pages": len(recs),
            "train_pages": len(train_pages), "test_pages": len(test_idx),
            "train_universe": len(universe), "font_codepoints": len(supported),
            "cache_entries": len(cache),
        },
        "schemes": {},
    }
    for key, blocks in schemes.items():
        sets = [set(b) for b in blocks]
        sl = [size_of(f"{key}#{i}") for i in range(len(blocks))]
        per_page, total, uniq_b, n_fetched = eval_slices(ps_all, sets, sl)
        out["schemes"][key] = {
            "n_slices": len(blocks),
            "total_bytes_all_slices": sum(sl),
            "css_intervals": intervals(blocks),
            "css_bytes_estimate": intervals(blocks) * 12,
            "per_page": per_page,
            "stats_all": stats([p["bytes"] for p in per_page]),
            "stats_train": stats([per_page[i]["bytes"] for i in train_idx]),
            "stats_test": stats([per_page[i]["bytes"] for i in test_idx]),
            "stats_requests": stats([p["requests"] for p in per_page]),
            "stats_utilisation": stats([p["utilisation"] for p in per_page if p["utilisation"]]),
            "session_total_bytes": total,
            "session_unique_bytes": uniq_b,
            "session_slices_fetched": n_fetched,
        }
        s = out["schemes"][key]
        print(f"  {key:16s} slices={len(blocks):4d} med={s['stats_all']['median']/1024:8.1f}KiB "
              f"test={s['stats_test']['median']/1024:8.1f}KiB req={s['stats_requests']['median']:5.1f} "
              f"util={s['stats_utilisation']['median']:.3f} css={s['css_intervals']}", flush=True)

    ex = [{"bytes": size_of(f"exact#{i}"), "chars": len(ps_all[i])} for i in range(len(recs))]
    f1 = [{"bytes": size_of(f"first1000#{i}"), "chars": len(ordered_first(recs[i], 1000))}
          for i in range(len(recs))]
    out["exact_subsets"] = {"per_page": ex,
                            "stats_all": stats([e["bytes"] for e in ex]),
                            "stats_train": stats([ex[i]["bytes"] for i in train_idx]),
                            "stats_test": stats([ex[i]["bytes"] for i in test_idx])}
    out["first1000_subsets"] = {"per_page": f1,
                                "stats_all": stats([e["bytes"] for e in f1]),
                                "stats_test": stats([f1[i]["bytes"] for i in test_idx])}
    print(f"  exact_page      median={out['exact_subsets']['stats_all']['median']/1024:8.1f} KiB "
          f"test={out['exact_subsets']['stats_test']['median']/1024:8.1f} KiB", flush=True)

    ift = {}
    for n in (500, 1000, 2000, 3000):
        base_bytes = size_of(f"base{n}")
        rows = []
        for i, ps in enumerate(ps_all):
            ub = size_of(f"union{n}#{i}")
            rows.append({"base": base_bytes, "patch": max(0, ub - base_bytes),
                         "total": base_bytes + max(0, ub - base_bytes)})
        ift[str(n)] = {"base_bytes": base_bytes, "per_page": rows,
                       "session_total_bytes": sum(r["total"] for r in rows),
                       "stats_all": stats([r["total"] for r in rows]),
                       "stats_test": stats([rows[i]["total"] for i in test_idx])}
        print(f"  ift base{n:<5d} base={base_bytes/1024:7.1f}KiB median_total="
              f"{ift[str(n)]['stats_all']['median']/1024:8.1f}KiB", flush=True)
    out["ift_sim"] = ift

    gf_rows = []
    for r in corpus["ja"]:
        if "gf_estimate" in r:
            e = r["gf_estimate"]
            gf_rows.append({"url": r["url"], "bytes": e["bytes_used"], "slices": e["slices_used"],
                            "unique_chars": r.get("unique_char_count"), "coverage_pct": e["coverage_pct"]})
    out["google_fonts_measured"] = gf_rows
    out["google_fonts_measured_summary"] = {
        "stats_all": stats([r["bytes"] for r in gf_rows]),
        "stats_train": stats([gf_rows[i]["bytes"] for i in train_idx]),
        "stats_test": stats([gf_rows[i]["bytes"] for i in test_idx]),
        "slices": stats([r["slices"] for r in gf_rows]),
    }
    print(f"  google fonts    median={out['google_fonts_measured_summary']['stats_all']['median']/1024:8.1f} KiB "
          f"slices_med={out['google_fonts_measured_summary']['slices']['median']:.0f}", flush=True)

    json.dump(out, open(OUT / "slicing_results.json", "w"), ensure_ascii=False, indent=2)
    print(f"done in {time.time()-t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
