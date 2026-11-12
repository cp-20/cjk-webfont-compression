#!/usr/bin/env python3
"""Build report/demo.html from existing measurements; never measure fonts.

Usage: python3 report/build_demo.py
Requires measure/out/{combined_study,glc_fullsweep,glc_sweep}.json.
CSS, JavaScript and data are inline; PNGs use the existing assets/ paths.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from build_report import CSS, esc

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
REPORT = ROOT / "report"
GRIDS = (0, 2, 4, 8, 16, 32)
ARMS = (
    ("google_fonts", "Google Fonts 方式"),
    ("exact", "完全一致サブセット / stock WOFF2"),
    ("exact_glc4", "完全一致サブセット + GLC g=4"),
    ("exact_glc8", "完全一致サブセット + GLC g=8"),
    ("base_resid_cold", "base500 + 差分 / cold"),
    ("base_resid_warm", "base500 + 差分 / warm"),
    ("base_resid_cold_glc8", "base500 + 差分 + GLC g=8 / cold"),
    ("base_resid_warm_glc8", "base500 + 差分 + GLC g=8 / warm"),
)
ESTIMATES = (
    ("exact", "完全一致サブセット / stock WOFF2"),
    ("exact_glc8", "完全一致サブセット + GLC g=8"),
    ("cold", "base500 + 差分 / cold"),
    ("warm", "base500 + 差分 / warm"),
    ("cold_glc8", "base500 + 差分 + GLC g=8 / cold"),
    ("warm_glc8", "base500 + 差分 + GLC g=8 / warm"),
)
SAMPLE = "日本語のウェブフォントを、必要な文字だけ軽く届ける。圧縮率と文字の見た目を比べてみましょう。"


def obj(value):
    return value if isinstance(value, dict) else {}


def number(value):
    """Finite, nonnegative measurement, or None (never coerce missing to zero)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(value) and value >= 0:
            return value
    return None


def read_json(name, expected_type):
    path = OUT / name
    if not path.is_file():
        raise SystemExit(
            f"Missing required measurement data: {path}\n"
            "Place the existing measurement JSON here and rerun this builder. "
            "No font measurements are run by this script."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read measurement JSON {path}: {exc}") from exc
    if not isinstance(data, expected_type):
        raise SystemExit(f"Invalid measurement JSON {path}: expected {expected_type.__name__}")
    return data


def grid_data(fullsweep, sweep):
    """Join the actual full-font label (static 400) and the subset label."""
    def noto_rows(rows):
        return {
            row.get("grid"): row
            for row in rows
            if isinstance(row, dict)
            and row.get("font") in ("Noto Sans JP", "Noto Sans JP (static 400)")
            and number(row.get("grid")) in GRIDS
        }

    full, subsets = noto_rows(fullsweep), noto_rows(sweep)
    result = {}
    for grid in GRIDS:
        row = subsets.get(grid, {})
        noise = row.get("noise")
        noise24 = next(
            (n for n in noise if isinstance(n, dict) and n.get("px") == 24), {}
        ) if isinstance(noise, list) else {}
        psnr = noise24.get("psnr_db")
        # The grid-0 source JSON contains Infinity, which strict JSON rejects.
        if isinstance(psnr, (int, float)) and psnr == math.inf:
            psnr = "Infinity"
        else:
            psnr = number(psnr)
        result[str(grid)] = {
            "full_bytes": number(full.get(grid, {}).get("bytes")),
            "subset_bytes": number(row.get("subset_woff2_bytes")),
            "psnr_db": psnr,
            "changed_pct": number(noise24.get("changed_pct")),
        }
    return result


def inline_json(data):
    # A base character may itself be '<'; never allow a closing script tag.
    return (json.dumps(data, ensure_ascii=False, allow_nan=False)
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def byte_label(value):
    value = number(value)
    return f"{value / 1024:,.1f} KiB（{value:,.0f} B）" if value is not None else "データなし"


def interpretation(gains):
    """Use optional gains, preserving the distinction between two medians."""
    gains = obj(gains)

    def change(value):
        return f"{abs(value):.1f}% {'削減' if value >= 0 else '増加'}"

    def gain(value):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

    sentences = []
    exact = obj(gains.get("glc_gain_on_exact_subsets_pct"))
    parts = [f"g={grid} で {change(value)}" for grid in (4, 8)
             if (value := gain(exact.get(f"grid{grid}"))) is not None]
    if parts:
        sentences.append(
            "同じページの完全一致サブセットに GLC を加えたときの削減率の中央値は、"
            + "、".join(parts) + "です（表の中央値同士の比とは異なります）。"
        )
    base = gain(gains.get("glc_gain_on_base500_pct"))
    if base is not None:
        sentences.append(
            f"共有ベース500文字への GLC g=8 の適用は {change(base)}で、"
            "warm ではベースを取得済みと仮定するため、その転送量を数えません。"
        )
    anchors = obj(gains.get("glc_gain_on_anchors_pct"))
    values = [v for value in anchors.values() if (v := gain(value)) is not None]
    if values:
        sentences.append(
            f"アンカーサブセットの GLC g=8 による削減率は {min(values):.1f}〜{max(values):.1f}%"
            "（正が削減）で、文字数・文字構成に依存するため、任意の文章で同じ効果を保証しません。"
        )
    return "".join(f"<p>{esc(sentence)}</p>" for sentence in sentences)


def summary_table(summary, full_bytes):
    summary = obj(summary)
    reference = number(obj(summary.get("google_fonts")).get("median"))
    rows = []
    for key, label in (*ARMS, ("full", "全体フォント WOFF2（固定参考値）")):
        value = number(full_bytes if key == "full" else obj(summary.get(key)).get("median"))
        size = f"{value / 1024:,.1f}" if value is not None else "データなし"
        saving = f"{100 * (1 - value / reference):.1f}%" if value is not None and reference else "—"
        rows.append(f'<tr><th scope="row">{esc(label)}</th><td class="num">{size}</td>'
                    f'<td class="num">{saving}</td></tr>')
    return ('<div class="tablewrap"><table><caption>配信方式と GLC の組合せ / Combined results</caption>'
            '<thead><tr><th scope="col">方式</th><th scope="col" class="num">中央値 / 参考値 (KiB)</th>'
            '<th scope="col" class="num">Google Fonts 比削減率</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table></div>')


EXTRA_CSS = """
h2 .en{display:block;font-size:.8rem;font-weight:400;color:var(--muted);letter-spacing:0}
label{display:block;font-weight:600;margin:12px 0 6px}
textarea{display:block;width:100%;min-height:140px;resize:vertical;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--fg);padding:12px 14px;font:inherit;line-height:1.8}
textarea:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
input[type=range]{width:100%;margin:16px 0 4px;accent-color:var(--accent)}
.grid-labels{display:flex;justify-content:space-between;font-size:.8rem;color:var(--muted)}
.control-value{font-size:1.05rem;font-weight:650;font-variant-numeric:tabular-nums}
.demo-frame{border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}
.demo-frame img{width:100%;height:auto;display:block}
caption{text-align:left;font-size:.84rem;color:var(--muted);padding-bottom:8px}
tbody th{white-space:normal;background:transparent;font-weight:400}
output{font-variant-numeric:tabular-nums}
.toc ol{columns:1}
"""


JS = r"""
(() => {
  'use strict';
  const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const valid = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
  const element = id => document.getElementById(id);
  const put = (id, value) => { const node = element(id); if (node) node.textContent = value; };
  let data = {};
  try { data = object(JSON.parse(element('demo-data')?.textContent || '{}')); }
  catch (_) { put('data-status', '埋め込みデータを読み込めませんでした。'); }
  const meta = object(data.meta);
  const base = object(meta.base500);
  const hasBase = typeof meta.base500_chars === 'string';
  const baseChars = new Set(hasBase ? Array.from(meta.base500_chars) : []);
  const format = (value, digits = 0) => value.toLocaleString('ja-JP', {
    minimumFractionDigits: digits, maximumFractionDigits: digits
  });
  const bytes = value => valid(value) ? `${format(value / 1024, 1)} KiB（${format(value)} B）` : 'データなし';

  function series(key, residual) {
    const points = new Map();
    for (const item of Array.isArray(data.anchors) ? data.anchors : []) {
      const row = object(item);
      if (valid(row.chars) && row.chars > 0 && valid(row[key]) && row[key] > 0) {
        points.set(row.chars, row[key]);
      }
    }
    if (residual) points.set(0, 0);
    return Array.from(points, ([chars, size]) => ({chars, bytes: size}))
      .sort((a, b) => a.chars - b.chars);
  }

  function interpolate(count, points) {
    if (!valid(count)) return null;
    if (count === 0) return 0; // No subset needs transferring.
    if (!points.length || !points.some(point => point.chars > 0)) return null;
    const first = points[0];
    const last = points[points.length - 1];
    if (!first || !last) return null;
    if (count <= first.chars) return first.bytes;
    if (count >= last.chars) return last.bytes;
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i];
      if (!a || !b || count > b.chars) continue;
      const t = (count - a.chars) / (b.chars - a.chars);
      // Log-linear: log(bytes) is linear in character count. A zero endpoint
      // cannot be logged, so bridge (0, 0) to the first measured point linearly.
      if (a.bytes === 0 || b.bytes === 0) return a.bytes + t * (b.bytes - a.bytes);
      return Math.exp(Math.log(a.bytes) + t * (Math.log(b.bytes) - Math.log(a.bytes)));
    }
    return null;
  }

  const exact = series('exact', false), glc8 = series('exact_glc8', false);
  const residualExact = series('exact', true), residualGlc8 = series('exact_glc8', true);
  const add = (a, b) => valid(a) && valid(b) ? a + b : null;

  function updateText() {
    const text = element('your-text-input');
    if (!text) return;
    // Array.from iterates Unicode code points, including supplementary kanji.
    const unique = new Set(Array.from(text.value || '').filter(ch => !/\s/u.test(ch)));
    let covered = 0;
    for (const ch of unique) if (baseChars.has(ch)) covered++;
    const remaining = hasBase ? unique.size - covered : null;
    put('unique-count', format(unique.size));
    put('base-count', hasBase ? format(covered) : 'データなし');
    put('residual-count', valid(remaining) ? format(remaining) : 'データなし');
    const plain = interpolate(remaining, residualExact);
    const quantized = interpolate(remaining, residualGlc8);
    const estimates = {
      exact: interpolate(unique.size, exact),
      exact_glc8: interpolate(unique.size, glc8),
      cold: add(base.exact, plain), warm: plain,
      cold_glc8: add(base.exact_glc8, quantized), warm_glc8: quantized
    };
    for (const [key, value] of Object.entries(estimates)) put(`estimate-${key}`, `推定 ${bytes(value)}`);
  }

  const grids = [0, 2, 4, 8, 16, 32];
  const perGrid = object(data.grids);
  function updateGrid() {
    const slider = element('epsilon-grid');
    if (!slider) return;
    const index = Number(slider.value);
    const grid = Number.isInteger(index) ? grids[index] : undefined;
    if (grid === undefined) return;
    const row = object(perGrid[String(grid)]);
    const baseline = object(perGrid['0']).full_bytes;
    const epsilon = grid / (2 * 1000) * 100;
    put('grid-value', `g = ${grid}`);
    slider.setAttribute('aria-valuetext', `格子幅 ${grid}、最大誤差 ${format(epsilon, 1)}% em`);
    put('epsilon-value', `${format(epsilon, 1)}% em`);
    put('full-bytes', bytes(row.full_bytes));
    put('full-ratio', valid(row.full_bytes) && valid(baseline) && baseline > 0
      ? `${format(row.full_bytes / baseline * 100, 1)}%（g=0 を 100%）` : 'データなし');
    put('subset-bytes', bytes(row.subset_bytes));
    put('psnr-value', row.psnr_db === 'Infinity' ? '∞ dB（差分なし）'
      : valid(row.psnr_db) ? `${format(row.psnr_db, 2)} dB` : 'データなし');
    put('changed-value', valid(row.changed_pct) ? `${format(row.changed_pct, 2)}%` : 'データなし');
    const image = element('grid-image');
    if (image) {
      image.src = `assets/demo_g${grid}.png`;
      image.alt = `Noto Sans JP、格子幅 ${grid} の描画。下段は左から基準、GLC、差分を6倍に強調。`;
    }
  }

  element('your-text-input')?.addEventListener('input', updateText);
  element('epsilon-grid')?.addEventListener('input', updateGrid);
  updateText();
  updateGrid();
})();
"""


def build(combined, fullsweep, sweep):
    meta = obj(combined.get("meta"))
    summary = obj(combined.get("summary"))
    base = obj(meta.get("base500"))
    # Embed only the fields the demo needs, not per-page URLs or the whole study.
    anchors = combined.get("anchors")
    payload = {
        "meta": {"base500_chars": meta.get("base500_chars") if isinstance(meta.get("base500_chars"), str) else None,
                 "base500": {key: number(base.get(key)) for key in ("exact", "exact_glc8")}},
        "anchors": [{key: number(obj(row).get(key)) for key in ("chars", "exact", "exact_glc8")}
                    for row in anchors] if isinstance(anchors, list) else [],
        "grids": grid_data(fullsweep, sweep),
    }
    estimate_rows = "".join(
        f'<tr><th scope="row">{esc(label)} <span class="tag est">推定</span></th>'
        f'<td class="num" id="estimate-{key}">推定 —</td></tr>' for key, label in ESTIMATES
    )
    full_label = esc(byte_label(meta.get("full_font_woff2_bytes")))
    google_label = esc(byte_label(obj(summary.get("google_fonts")).get("median")))
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="CJK Web フォントの配信方式と GLC 圧縮を、既存の実測データで比較するデモ。">
<title>CJK Web フォント圧縮 — インタラクティブデモ</title>
<style>{CSS}\n{EXTRA_CSS}</style>
</head>
<body><main class="wrap">
<header class="top">
<h1>CJK Web フォント圧縮を試す</h1>
<p class="sub">必要な文字を選ぶ配信方式と、輪郭の精度を調整する GLC を組み合わせる</p>
<p class="small" lang="en">Interactive demo · Text payload estimates, visual error, and combined measurements</p>
<p class="meta">対象: Noto Sans JP ／ 既存の測定 JSON に基づく比較</p>
</header>
<p class="lead">文章を入力して転送量の目安を確認し、格子幅を動かして容量と描画の変化を比べられます。
ここで新たなフォント圧縮・描画測定は行いません。入力した文章の処理はブラウザ内で完結します。</p>
<nav class="toc" aria-label="目次"><ol>
<li><a href="#your-text">あなたの文章と推定転送量</a></li>
<li><a href="#epsilon">許容誤差と見た目</a></li>
<li><a href="#combined">配信方式 × GLC の実測結果</a></li>
</ol></nav>
<noscript><p class="card">対話操作には JavaScript が必要です。末尾の実測表はそのまま読めます。</p></noscript>
<p class="note" id="data-status" role="status"></p>

<section aria-labelledby="your-text">
<h2 id="your-text">1. あなたの文章と推定転送量<span class="en" lang="en">Your text · Estimated payload</span></h2>
<label for="your-text-input">比べたい文章</label>
<textarea id="your-text-input" aria-describedby="estimate-model cache-note" spellcheck="false">{esc(SAMPLE)}</textarea>
<div class="kpis" role="status" aria-live="polite" aria-atomic="true">
<div class="kpi"><div class="v"><output id="unique-count">—</output></div><div class="l">異なり文字数（空白を除く）</div></div>
<div class="kpi"><div class="v"><output id="base-count">—</output></div><div class="l">共有ベース500文字に含まれる文字</div></div>
<div class="kpi"><div class="v"><output id="residual-count">—</output></div><div class="l">ベース外の文字（差分）</div></div>
</div>
<div class="tablewrap"><table><caption>入力文の推定と、入力文によらない固定参考値</caption>
<thead><tr><th scope="col">方式</th><th scope="col" class="num">転送量（推定 / 固定参考値）</th></tr></thead>
<tbody>{estimate_rows}
<tr><th scope="row">全体フォント WOFF2 <span class="tag meas">実測・固定参考</span></th><td class="num">{full_label}</td></tr>
<tr><th scope="row">Google Fonts 方式の中央値 <span class="tag meas">実測・固定参考</span></th><td class="num">{google_label}</td></tr>
</tbody></table></div>
<p class="note" id="estimate-model">推定モデル: 実測アンカーの正の点の間で、文字数に対して log(バイト数) を線形補間し、
測定範囲外は端点に固定します（空の入力は0バイト、差分には仮想点「0文字・0バイト」を加えて最初の実測点まで線形補間）。</p>
<p class="note">文字の形・組合せ、フォントの収録範囲、極小サブセットの固定費用は再現していないため、入力文そのものの圧縮結果ではありません。
文字数は Unicode コードポイント単位で数えます。</p>
<p class="note" id="cache-note">cold は共有ベース全体と差分の合計、warm はベースがキャッシュ済みの場合の差分のみ。
差分0文字は0バイトで、cold にはベースの取得費用が残ります。</p>
</section>

<section aria-labelledby="epsilon">
<h2 id="epsilon">2. 許容誤差と見た目<span class="en" lang="en">Epsilon slider · Size and rendering error</span></h2>
<p>GLC は輪郭座標を格子に丸めます。格子幅 g を大きくすると、容量と描画差分がどう変わるかを確認できます。</p>
<div class="card">
<label for="epsilon-grid">格子幅 <output id="grid-value" for="epsilon-grid" class="control-value">g = 8</output></label>
<input id="epsilon-grid" type="range" min="0" max="5" step="1" value="3" aria-describedby="epsilon-model">
<div class="grid-labels" aria-hidden="true"><span>0</span><span>2</span><span>4</span><span>8</span><span>16</span><span>32</span></div>
<p class="note" id="epsilon-model">最大座標誤差 ε = g / (2 × UPM) × 100%。UPM = 1000、g=0 は基準です。</p>
<dl class="kv" aria-live="polite" aria-atomic="true">
<dt>ε（em 比）</dt><dd id="epsilon-value">—</dd>
<dt>全体 WOFF2</dt><dd id="full-bytes">—</dd>
<dt>全体サイズの基準比</dt><dd id="full-ratio">—</dd>
<dt>3,000文字サブセット</dt><dd id="subset-bytes">—</dd>
<dt>PSNR / 24px</dt><dd id="psnr-value">—</dd>
<dt>変化した画素 / 24px</dt><dd id="changed-value">—</dd>
</dl></div>
<figure><div class="demo-frame"><img id="grid-image" src="assets/demo_g8.png"
alt="Noto Sans JP、格子幅8の描画。下段は左から基準、GLC、差分を6倍に強調。"></div>
<figcaption>既存の24px描画例。下段は左から基準、GLC適用後、輝度差を6倍に強調した画像（各6倍拡大）。
PSNR と変化画素率は別途測定した24pxの描画差分で、見やすさの主観評価ではありません。</figcaption></figure>
<p class="note">数値は Noto Sans JP の各スイープの実測値です。GLC の前処理にはテーブル整理なども含まれ、
容量変化のすべてが座標の丸めだけに由来するわけではありません。</p>
</section>

<section aria-labelledby="combined">
<h2 id="combined">3. 配信方式 × GLC の実測結果<span class="en" lang="en">Combined results · Measured medians</span></h2>
<p>同じ日本語ページ集合で、必要な文字の選び方と GLC を組み合わせた結果です。
全体フォントの行は固定の参考サイズで、それ以外はページ別転送量の中央値です。</p>
{summary_table(summary, meta.get('full_font_woff2_bytes'))}
<p class="note">削減率 = (1 − 各中央値または参考値 / Google Fonts 方式の中央値) × 100%。負の値は増加を表します。
中央値はページ別の比率の中央値とは一致しません。cold / warm のキャッシュ条件は上記と同じです。</p>
{interpretation(combined.get('gains'))}
</section>
<footer>
<p><a href="index.html">配信方式のレポート</a> ／ <a href="glc.html">GLC のレポート</a></p>
<p>出典の数値は実フォントでの測定値です（data: <code>measure/out/*.json</code>）。
入力文の転送量は実測アンカーに基づく推定です。画像は <code>assets/demo_g*.png</code> を使用しています。</p>
<p>生成: <code>report/build_demo.py</code> ／ CSS・JavaScript・数値データはこの HTML 内に収録。</p>
</footer>
</main>
<script id="demo-data" type="application/json">{inline_json(payload)}</script>
<script>{JS}</script>
</body></html>
"""


def main():
    combined = read_json("combined_study.json", dict)
    fullsweep = read_json("glc_fullsweep.json", list)
    sweep = read_json("glc_sweep.json", list)
    output = REPORT / "demo.html"
    output.write_text(build(combined, fullsweep, sweep), encoding="utf-8")
    print(f"Wrote {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
