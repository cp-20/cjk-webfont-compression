#!/usr/bin/env python3
"""Probe: how much of a CJK font can be encoded as a *delta* against a similar glyph?

For every simple glyph we look for a "structural twin": another glyph with the same
contour topology (same number of contours and same number of points per contour).
A twin can be encoded as (twin index + per-point coordinate residual), which is
what the proposed DG3 (Delta-Glyph) container does.

Outputs the achievable size estimate vs. the plain glyf table.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent


def contour_ends(glyph):
    ep = getattr(glyph, "endPts", None)
    if ep is None:
        ep = getattr(glyph, "endPtsOfContours", [])
        if callable(ep):
            ep = ep()
    return list(ep)


def varint(n: int) -> int:
    n = max(0, n)
    bits = 1
    while n >= 128:
        n >>= 7
        bits += 1
    return bits


def analyse(path: str, limit_groups: int | None = None):
    font = TTFont(path)
    glyf = font["glyf"]
    cmap = font.getBestCmap()
    groups = defaultdict(list)
    for cp, gn in sorted(cmap.items()):
        if gn not in glyf.glyphs:
            continue
        g = glyf[gn]
        if g.numberOfContours <= 0 or g.isComposite():
            continue
        ends = contour_ends(g)
        sig = (g.numberOfContours, tuple(
            (e - s) for s, e in zip([0] + list(ends[:-1]), ends)))
        groups[sig].append((cp, gn))
    multi = {k: v for k, v in groups.items() if len(v) > 1}
    glyphs_in_multi = sum(len(v) for v in multi.values())
    total = sum(len(v) for v in groups.values())

    # estimate residual cost for a sample of groups
    random.seed(11)
    sample_groups = list(multi.values())
    if limit_groups:
        sample_groups = random.sample(sample_groups, min(limit_groups, len(sample_groups)))
    residual_bits = 0
    base_bits = 0
    checked = 0
    for members in sample_groups:
        members = members[:12]
        for i, (cp, gn) in enumerate(members):
            g = glyf[gn]
            coords = [tuple(c) for c in g.coordinates]
            # self cost: absolute coordinates as varints (what a naive encoding costs)
            self_bits = sum(varint(abs(x)) + varint(abs(y)) for x, y in coords)
            best = None
            for j, (cp2, gn2) in enumerate(members):
                if i == j:
                    continue
                g2 = glyf[gn2]
                c2 = [tuple(c) for c in g2.coordinates]
                if len(c2) != len(coords):
                    continue
                d = 0
                for (x, y), (x2, y2) in zip(coords, c2):
                    d += varint(abs(x - x2)) + varint(abs(y - y2))
                if best is None or d < best:
                    best = d
            if best is None:
                residual_bits += self_bits
                base_bits += self_bits
            else:
                residual_bits += best + 32  # twin index + overhead
                base_bits += self_bits
            checked += 1
    out = {
        "font": Path(path).name,
        "simple_glyphs": total,
        "glyphs_with_structural_twin": glyphs_in_multi,
        "twin_ratio": glyphs_in_multi / total if total else 0,
        "sampled_glyphs": checked,
        "naive_coord_bits": base_bits,
        "delta_coord_bits": residual_bits,
        "est_ratio_delta_vs_naive": residual_bits / base_bits if base_bits else None,
    }
    print(f"{Path(path).name:28s} glyphs={total:6d} with_twin={glyphs_in_multi:6d} "
          f"({100*out['twin_ratio']:.1f}%)  naive={base_bits/8/1024:8.1f} KiB -> "
          f"delta={residual_bits/8/1024:8.1f} KiB ({100*out['est_ratio_delta_vs_naive']:.1f}%)",
          flush=True)
    return out


if __name__ == "__main__":
    targets = [
        "measure/out/NotoSansJP-Regular.ttf",
        "fonts/MPLUS1p-Regular.ttf",
        "fonts/NanumGothic-Regular.ttf",
        "fonts/ZenKakuGothicNew-Regular.ttf",
    ]
    rows = []
    for t in targets:
        p = ROOT / t
        if p.exists():
            rows.append(analyse(str(p), limit_groups=120))
    (ROOT / "measure" / "out" / "delta_probe.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
