#!/usr/bin/env python3
"""Build the Japanese HTML report from measured JSON data."""
from __future__ import annotations

import html
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WEB = ROOT / "measure" / "web"
REPORT = ROOT / "report"

CSS = """
:root{
  --bg:#ffffff; --fg:#1b1b1f; --muted:#5b5b66; --line:#e3e3e8; --soft:#f6f6f9;
  --accent:#2f5fd0; --accent-soft:#e8eefb; --warn:#b3541e; --ok:#1d7a4c;
  --shadow:0 1px 2px rgba(16,16,24,.06),0 8px 24px rgba(16,16,24,.05);
}
@media (prefers-color-scheme: dark){
  :root{--bg:#111318;--fg:#e8e8ee;--muted:#a0a0ae;--line:#282a33;--soft:#181a21;
        --accent:#8fb0ff;--accent-soft:#1b2233;--warn:#e39a63;--ok:#63c396;
        --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.3);}
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);
  font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic UI",Meiryo,sans-serif;
  line-height:1.85;font-size:16px;}
.wrap{max-width:1080px;margin:0 auto;padding:48px 24px 120px}
header.top{border-bottom:1px solid var(--line);padding-bottom:28px;margin-bottom:36px}
h1{font-size:1.95rem;line-height:1.4;margin:0 0 12px;letter-spacing:.01em}
.sub{color:var(--muted);font-size:.95rem;margin:0}
.meta{color:var(--muted);font-size:.82rem;margin-top:14px}
h2{font-size:1.42rem;margin:64px 0 6px;padding-top:18px;border-top:1px solid var(--line);letter-spacing:.01em}
h3{font-size:1.12rem;margin:34px 0 4px}
h4{font-size:1rem;margin:22px 0 2px;color:var(--fg)}
p{margin:.55em 0 .9em}
a{color:var(--accent);text-underline-offset:2px}
ul,ol{margin:.4em 0 1em;padding-left:1.35em}
li{margin:.28em 0}
small,.small{font-size:.84rem;color:var(--muted)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.87em;
  background:var(--soft);padding:.1em .35em;border-radius:4px}
pre{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:14px 16px;
  overflow:auto;font-size:.84rem;line-height:1.6}
pre code{background:none;padding:0}
.lead{font-size:1.03rem;color:var(--fg)}
.card{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:18px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:22px 0}
.kpi{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}
.kpi .v{font-size:1.5rem;font-weight:650;letter-spacing:-.01em;line-height:1.25}
.kpi .l{font-size:.8rem;color:var(--muted);margin-top:4px;line-height:1.5}
table{width:100%;border-collapse:collapse;margin:14px 0 8px;font-size:.9rem}
th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-weight:650;background:var(--soft);white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tbody tr:hover{background:var(--accent-soft)}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
figure{margin:22px 0}
figure img,figure svg{width:100%;height:auto;display:block}
figcaption{font-size:.84rem;color:var(--muted);margin-top:8px;line-height:1.6}
.toc{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:24px 0}
.toc ol{margin:.2em 0;padding-left:1.2em;columns:2;column-gap:32px}
.toc a{text-decoration:none;color:var(--fg)}
.toc a:hover{color:var(--accent);text-decoration:underline}
.tag{display:inline-block;font-size:.72rem;padding:1px 7px;border-radius:99px;border:1px solid var(--line);
  color:var(--muted);vertical-align:middle;white-space:nowrap}
.tag.meas{color:var(--ok);border-color:currentColor}
.tag.est{color:var(--warn);border-color:currentColor}
.tag.prop{color:var(--accent);border-color:currentColor}
blockquote{margin:14px 0;padding:10px 16px;border-left:3px solid var(--accent);background:var(--soft);
  color:var(--fg);border-radius:0 8px 8px 0}
blockquote .src{display:block;font-size:.8rem;color:var(--muted);margin-top:8px}
.quote-ja{font-size:.95rem}
.quote-en{font-size:.82rem;color:var(--muted);margin-top:6px;padding-top:6px;border-top:1px dashed var(--line)}
.kv{display:grid;grid-template-columns:auto 1fr;gap:2px 14px;font-size:.9rem}
.kv dt{color:var(--muted)}
.kv dd{margin:0}
.steps{counter-reset:s;list-style:none;padding:0}
.steps>li{counter-increment:s;position:relative;padding-left:38px;margin:14px 0}
.steps>li::before{content:counter(s);position:absolute;left:0;top:2px;width:24px;height:24px;border-radius:50%;
  background:var(--accent);color:#fff;display:grid;place-items:center;font-size:.78rem;font-weight:600}
.note{font-size:.85rem;color:var(--muted);margin-top:6px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:26px}
@media (max-width:760px){.grid2{grid-template-columns:1fr}.toc ol{columns:1}}
footer{margin-top:80px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:.84rem}
"""


def esc(s) -> str:
    return html.escape(str(s))


def load(name, default=None):
    p = OUT / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def kb(n):
    return f"{n/1024:,.0f} KiB"


def mb(n):
    return f"{n/1e6:,.2f} MB"


def fmt_int(n):
    return f"{n:,}"


# --------------------------------------------------------------- charts
def svg_bars(rows, labels, title, unit="KiB", colors=None, height=250, value_fmt=None):
    """rows: list of lists of numbers (series per group). labels: group labels."""
    n_g = len(labels)
    n_s = len(rows)
    pad_l, pad_r, pad_t, pad_b = 58, 12, 16, 44
    w = 760
    h = height
    vmax = max(max(r) for r in rows) if rows else 1
    vmax = vmax * 1.12
    plot_h = h - pad_t - pad_b
    plot_w = w - pad_l - pad_r
    gw = plot_w / n_g
    bw = min(46, (gw - 12) / n_s)
    colors = colors or ["#2f5fd0", "#9bb4e8", "#b3541e"]
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    s.append(f'<text x="{pad_l}" y="12" font-size="12" fill="currentColor" font-weight="600">{esc(title)}</text>')
    for i in range(5):
        y = pad_t + plot_h * i / 4
        v = vmax * (4 - i) / 4
        s.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="currentColor" stroke-opacity=".12"/>')
        txt = value_fmt(v) if value_fmt else f"{v:,.0f}"
        s.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" font-size="10.5" text-anchor="end" fill="currentColor" fill-opacity=".65">{esc(txt)}</text>')
    for g in range(n_g):
        x0 = pad_l + g * gw + (gw - bw * n_s) / 2
        for si, row in enumerate(rows):
            v = row[g]
            bh = plot_h * (v / vmax) if vmax else 0
            x = x0 + si * bw
            s.append(f'<rect x="{x:.1f}" y="{pad_t+plot_h-bh:.1f}" width="{bw-3:.1f}" height="{max(bh,1):.1f}" fill="{colors[si%len(colors)]}" rx="2"><title>{esc(labels[g])}: {esc(value_fmt(v) if value_fmt else f"{v:,.0f}")}</title></rect>')
            if n_s <= 3:
                txt = value_fmt(v) if value_fmt else f"{v:,.0f}"
                s.append(f'<text x="{x+bw/2-1.5:.1f}" y="{pad_t+plot_h-bh-4:.1f}" font-size="9.5" text-anchor="middle" fill="currentColor" fill-opacity=".8">{esc(txt)}</text>')
        lab = labels[g]
        if len(lab) > 14:
            lab = lab[:13] + "…"
        s.append(f'<text x="{pad_l+g*gw+gw/2:.1f}" y="{h-pad_b+16}" font-size="10" text-anchor="middle" fill="currentColor" fill-opacity=".8">{esc(lab)}</text>')
    s.append("</svg>")
    return "".join(s)


def svg_grouped_bars(groups, series, title, unit="", height=280):
    """groups: [(label, [v1,v2,...])] series: [(name,color)]"""
    pad_l, pad_r, pad_t, pad_b = 62, 12, 22, 48
    w, h = 760, height
    vmax = max(max(vals) for _, vals in groups) * 1.14
    plot_h = h - pad_t - pad_b
    plot_w = w - pad_l - pad_r
    gw = plot_w / len(groups)
    n_s = len(series)
    bw = min(52, (gw - 16) / n_s)
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    s.append(f'<text x="{pad_l}" y="13" font-size="12.5" fill="currentColor" font-weight="600">{esc(title)}</text>')
    # legend
    lx = w - pad_r
    for name, color in reversed(series):
        tw = len(name) * 6.2 + 16
        lx -= tw
        s.append(f'<rect x="{lx:.0f}" y="4" width="10" height="10" rx="2" fill="{color}"/>')
        s.append(f'<text x="{lx+14:.0f}" y="13" font-size="10.5" fill="currentColor" fill-opacity=".8">{esc(name)}</text>')
    for i in range(5):
        y = pad_t + plot_h * i / 4
        v = vmax * (4 - i) / 4
        s.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="currentColor" stroke-opacity=".12"/>')
        s.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" font-size="10.5" text-anchor="end" fill="currentColor" fill-opacity=".65">{v:,.0f}</text>')
    for g, (label, vals) in enumerate(groups):
        x0 = pad_l + g * gw + (gw - bw * n_s) / 2
        for si, v in enumerate(vals):
            bh = plot_h * (v / vmax)
            x = x0 + si * bw
            s.append(f'<rect x="{x:.1f}" y="{pad_t+plot_h-bh:.1f}" width="{bw-4:.1f}" height="{max(bh,1):.1f}" fill="{series[si][1]}" rx="2"><title>{esc(label)} / {esc(series[si][0])}: {v:,.0f}</title></rect>')
        s.append(f'<text x="{pad_l+g*gw+gw/2:.1f}" y="{h-pad_b+18}" font-size="10" text-anchor="middle" fill="currentColor" fill-opacity=".8">{esc(label)}</text>')
    s.append(f'<text x="{pad_l}" y="{h-6}" font-size="9.5" fill="currentColor" fill-opacity=".55">{esc(unit)}</text>')
    s.append("</svg>")
    return "".join(s)


def svg_hbar(items, title, unit="", height=None, color="#2f5fd0", fmt=None):
    """items: [(label, value)] sorted ascending"""
    fmt = fmt or (lambda v: f"{v:,.0f}")
    pad_l, pad_r, pad_t, pad_b = 200, 70, 24, 10
    row_h = 22
    w = 760
    h = height or (pad_t + pad_b + row_h * len(items))
    vmax = max(v for _, v in items) * 1.02
    plot_w = w - pad_l - pad_r
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    s.append(f'<text x="0" y="13" font-size="12.5" fill="currentColor" font-weight="600">{esc(title)}</text>')
    for i, (lab, v) in enumerate(items):
        y = pad_t + i * row_h
        bw = plot_w * (v / vmax) if vmax else 0
        s.append(f'<text x="{pad_l-10}" y="{y+14}" font-size="10.5" text-anchor="end" fill="currentColor" fill-opacity=".85">{esc(lab)}</text>')
        s.append(f'<rect x="{pad_l}" y="{y+3}" width="{max(bw,1):.1f}" height="13" fill="{color}" rx="2"><title>{esc(lab)}: {esc(fmt(v))}</title></rect>')
        s.append(f'<text x="{pad_l+bw+7:.1f}" y="{y+14}" font-size="10" fill="currentColor" fill-opacity=".7">{esc(fmt(v))}</text>')
    s.append(f'<text x="0" y="{h-2}" font-size="9.5" fill="currentColor" fill-opacity=".55">{esc(unit)}</text>')
    s.append("</svg>")
    return "".join(s)


def svg_stacked_single(parts, title, colors, height=52):
    """parts: [(label, bytes)] single stacked bar"""
    total = sum(v for _, v in parts) or 1
    w, h = 760, height
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    s.append(f'<text x="0" y="12" font-size="12.5" fill="currentColor" font-weight="600">{esc(title)}</text>')
    x = 0.0
    for (lab, v), c in zip(parts, colors):
        bw = w * v / total
        s.append(f'<rect x="{x:.1f}" y="20" width="{bw:.1f}" height="18" fill="{c}"><title>{esc(lab)}: {esc(f"{v:,} B ({100*v/total:.1f}%)")}</title></rect>')
        if bw > 90:
            s.append(f'<text x="{x+bw/2:.1f}" y="33" font-size="10" text-anchor="middle" fill="#fff">{esc(lab)}</text>')
        x += bw
    x = 0.0
    for (lab, v), c in zip(parts, colors):
        bw = w * v / total
        s.append(f'<text x="{x:.1f}" y="49" font-size="9.5" fill="currentColor" fill-opacity=".7">{esc(lab)} {v:,} B ({100*v/total:.1f}%)</text>')
        x += bw
    s.append("</svg>")
    return "".join(s)


def svg_lines(series, xlabels, title, ylabel="", height=260, ymax=None, xlabel=""):
    """series: [(name, color, [values])] - values aligned with xlabels."""
    pad_l, pad_r, pad_t, pad_b = 66, 14, 22, 42
    w, h = 760, height
    allv = [v for _, _, vals in series for v in vals if v is not None]
    vmax = ymax or (max(allv) * 1.12 if allv else 1)
    vmin = 0
    plot_h = h - pad_t - pad_b
    plot_w = w - pad_l - pad_r
    n = len(xlabels)
    def X(i):
        return pad_l + (plot_w * i / max(1, n - 1))
    def Y(v):
        return pad_t + plot_h - plot_h * (v - vmin) / (vmax - vmin)
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    s.append(f'<text x="{pad_l}" y="13" font-size="12.5" fill="currentColor" font-weight="600">{esc(title)}</text>')
    lx = w - pad_r
    for name, color, _ in reversed(series):
        tw = len(name) * 6.4 + 18
        lx -= tw
        s.append(f'<rect x="{lx:.0f}" y="4" width="10" height="10" rx="2" fill="{color}"/>')
        s.append(f'<text x="{lx+14:.0f}" y="13" font-size="10.5" fill="currentColor" fill-opacity=".8">{esc(name)}</text>')
    for i in range(5):
        y = pad_t + plot_h * i / 4
        v = vmax * (4 - i) / 4
        s.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="currentColor" stroke-opacity=".12"/>')
        s.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" font-size="10.5" text-anchor="end" fill="currentColor" fill-opacity=".65">{v:,.0f}</text>')
    for name, color, vals in series:
        pts = [(X(i), Y(v)) for i, v in enumerate(vals) if v is not None]
        if len(pts) > 1:
            s.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>' % (
                color, " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)))
        for (x, y), v in zip(pts, [v for v in vals if v is not None]):
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{color}"><title>{esc(name)}: {v:,.1f}</title></circle>')
    for i, lab in enumerate(xlabels):
        s.append(f'<text x="{X(i):.1f}" y="{h-pad_b+18}" font-size="10" text-anchor="middle" fill="currentColor" fill-opacity=".8">{esc(lab)}</text>')
    s.append(f'<text x="{pad_l}" y="{h-4}" font-size="9.5" fill="currentColor" fill-opacity=".55">{esc(xlabel)}</text>')
    s.append(f'<text x="2" y="{pad_t-6}" font-size="9.5" fill="currentColor" fill-opacity=".55">{esc(ylabel)}</text>')
    s.append("</svg>")
    return "".join(s)


def svg_arch():
    """Architecture diagram of the proposed method."""
    w, h = 760, 300
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="提案手法の構成">']
    s.append('<defs><marker id="ar" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto">'
             '<path d="M0,0 L9,3.5 L0,7 z" fill="currentColor" fill-opacity=".55"/></marker></defs>')
    boxes = [
        (20, 40, 190, 92, "ブラウザ", "HTML / DOM を解析\n必要グリフ集合を算出"),
        (250, 30, 210, 112, "層1: 共有ベース", "頻度上位 500 文字を 1 枚に\n全ページ・全サイトで URL 共有"),
        (250, 160, 210, 112, "層2: ページ固有", "本文と完全一致の厳密サブセット\n(≈ 数十〜100 KiB) / ページ固有"),
        (500, 30, 230, 112, "層3: IFT 差分", "未取得グリフを差分パッチで追記\n(Chrome 実験実装 / 標準化候補)"),
        (500, 160, 230, 112, "フォールバック: 尾部スライス", "ベース以外の文字を 100 分割で担保\n(完全カバレッジ・共有可)"),
    ]
    for x, y, bw, bh, title, body in boxes:
        s.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="10" fill="none" stroke="currentColor" stroke-opacity=".35"/>')
        s.append(f'<text x="{x+12}" y="{y+22}" font-size="12" font-weight="600" fill="currentColor">{esc(title)}</text>')
        for i, line in enumerate(body.split("\n")):
            s.append(f'<text x="{x+12}" y="{y+44+i*18}" font-size="10.5" fill="currentColor" fill-opacity=".72">{esc(line)}</text>')
    arrows = [(210, 86, 250, 86), (460, 86, 500, 86), (210, 86, 250, 216),
              (460, 216, 500, 216), (460, 86, 460, 216)]
    for x1, y1, x2, y2 in arrows:
        s.append(f'<path d="M{x1},{y1} C{x1+24},{y1} {x2-24},{y2} {x2},{y2}" fill="none" stroke="currentColor" stroke-opacity=".45" stroke-width="1.4" marker-end="url(#ar)"/>')
    s.append('<text x="250" y="292" font-size="10.5" fill="currentColor" fill-opacity=".7">層1 を先に要求し、必要な文字がベースに入っていなければ層2 / 層3 を追加取得する</text>')
    s.append("</svg>")
    return "".join(s)


def svg_flow(size_fn):
    return ""
