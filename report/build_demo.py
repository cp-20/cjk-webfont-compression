#!/usr/bin/env python3
"""Build report/demo.html from existing measurements; never measure fonts.

Usage: python3 report/build_demo.py
Requires measure/out/{combined_study,combined_study_zh,combined_study_ko,
glc_fullsweep,demo_assets,demo_full_zhko}.json and the live demo fonts
report/assets/demo_font{,_zh,_ko}_g{0,2,4,8,16,32}.woff2 (built by
measure/build_demo_assets.py; the SC/KR full-font grid references come
from measure/demo_full_grids_zhko.py).

Round 3: section 2 renders text *live in the browser* with the actual
quantised subset fonts (FontFace API) instead of swapping pre-rendered
PNGs; section 3 shows the delivery x GLC layers as animated bars with a
ja/zh/ko switcher. Round 5: the section-2 live preview gets the same
ja/zh/ko switcher, with per-language subset assets, charsets, samples
and full-font grid references. CSS, JavaScript and numeric data are
inline; the demo fonts are the only external files, loaded on demand.
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
LANGS = (
    ("ja", "日本語", "Noto Sans JP"),
    ("zh", "中文（簡体）", "Noto Sans SC"),
    ("ko", "한국어", "Noto Sans KR"),
)


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


def full_grid_bytes(fullsweep):
    """Full-font WOFF2 bytes per grid for the Noto rows of the sweep."""
    result = {}
    for row in fullsweep:
        if isinstance(row, dict) and row.get("font") in ("Noto Sans JP", "Noto Sans JP (static 400)"):
            grid = number(row.get("grid"))
            if grid in GRIDS:
                result[str(int(grid))] = number(row.get("bytes"))
    return result


def full_grid_bytes_by_lang(fullsweep, demo_full_zhko):
    """Per-language full-font WOFF2 bytes per grid (ja from the published
    sweep, zh/ko from measure/demo_full_grids_zhko.py)."""
    result = {"ja": full_grid_bytes(fullsweep), "zh": {}, "ko": {}}
    for row in demo_full_zhko:
        if isinstance(row, dict) and row.get("lang") in ("zh", "ko"):
            grid = number(row.get("grid"))
            if grid in GRIDS:
                result[row["lang"]][str(int(grid))] = number(row.get("bytes"))
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


def study_payload(study):
    meta = obj(study.get("meta"))
    summary = obj(study.get("summary"))
    pages = number(meta.get("pages"))
    if pages is None and isinstance(study.get("per_page"), list):
        pages = len(study["per_page"])
    skipped = meta.get("pages_skipped_no_data")
    return {
        "pages": pages,
        "skipped": skipped if isinstance(skipped, list) else [],
        "full_bytes": number(meta.get("full_font_woff2_bytes")),
        "arms": {key: number(obj(summary.get(key)).get("median")) for key, _ in ARMS},
    }


def study_block(lang, label, font_label, study, active):
    """One language's bar chart + table for section 3 (JS switches blocks)."""
    payload = study_payload(study)
    arms = payload["arms"]
    reference = arms.get("google_fonts")
    scale = max([v for v in arms.values() if v is not None], default=None)
    bars = []
    for key, arm_label in ARMS:
        value = arms.get(key)
        width = (100 * value / scale) if value is not None and scale else 0
        size = f"{value / 1024:,.1f} KiB" if value is not None else "データなし"
        saving = (f"GF 比 −{100 * (1 - value / reference):.1f}%"
                  if value is not None and reference else "—")
        bars.append(
            f'<div class="bar-row"><span class="bar-label">{esc(arm_label)}</span>'
            f'<span class="bar-track"><span class="bar" data-w="{width:.2f}"></span></span>'
            f'<span class="bar-value">{esc(size)}<small>{esc(saving)}</small></span></div>')
    rows = []
    for key, arm_label in (*ARMS, ("full", "全体フォント WOFF2（固定参考値）")):
        value = payload["full_bytes"] if key == "full" else arms.get(key)
        size = f"{value / 1024:,.1f}" if value is not None else "データなし"
        saving = (f"{100 * (1 - value / reference):.1f}%"
                  if value is not None and reference else "—")
        rows.append(f'<tr><th scope="row">{esc(arm_label)}</th><td class="num">{size}</td>'
                    f'<td class="num">{saving}</td></tr>')
    skipped_note = ""
    if payload["skipped"]:
        skipped_note = (f'<p class="note">文字集合の記録がない {len(payload["skipped"])} ページ'
                        f'（{esc("、".join(str(s) for s in payload["skipped"]))}）は対象外です。</p>')
    pages = payload["pages"]
    pages_label = f'{pages:,.0f} ページ' if pages is not None else 'ページ数不明'
    hidden = "" if active else " hidden"
    return f"""<div class="study" data-study="{lang}"{hidden}>
<p class="note">対象: {esc(font_label)} ／ コーパス {pages_label}（Google Fonts 列は公開監査値、それ以外は実測）。</p>
<div class="bars" role="img" aria-label="{esc(label)}の方式別中央値バー">{''.join(bars)}</div>
<div class="tablewrap"><table><caption>配信方式と GLC の組合せ / Combined results（{esc(label)}）</caption>
<thead><tr><th scope="col">方式</th><th scope="col" class="num">中央値 / 参考値 (KiB)</th>
<th scope="col" class="num">Google Fonts 比削減率</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
{skipped_note}
{interpretation(study.get('gains'))}
</div>"""


EXTRA_CSS = """
h2 .en{display:block;font-size:.8rem;font-weight:400;color:var(--muted);letter-spacing:0}
label{display:block;font-weight:600;margin:12px 0 6px}
textarea{display:block;width:100%;min-height:110px;resize:vertical;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--fg);padding:12px 14px;font:inherit;line-height:1.8}
textarea:focus-visible,input:focus-visible,button:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
input[type=range]{width:100%;margin:16px 0 4px;accent-color:var(--accent)}
.grid-labels{display:flex;justify-content:space-between;font-size:.8rem;color:var(--muted)}
.control-value{font-size:1.05rem;font-weight:650;font-variant-numeric:tabular-nums}
caption{text-align:left;font-size:.84rem;color:var(--muted);padding-bottom:8px}
tbody th{white-space:normal;background:transparent;font-weight:400}
output{font-variant-numeric:tabular-nums}
.toc ol{columns:1}
.preview{border:1px solid var(--line);border-radius:8px;background:#fff;color:#111;padding:14px 16px;margin-top:10px}
.preview .big{font-size:52px;line-height:1.5;word-break:break-all;white-space:pre-wrap}
.preview .body{font-size:20px;line-height:1.9;word-break:break-all;white-space:pre-wrap;border-top:1px dashed #ccc;margin-top:10px;padding-top:10px}
.preview .oob{background:#ffe1e1;color:#a00;border-bottom:2px dotted #a00}
.bars{margin:14px 0}
.bar-row{display:flex;align-items:center;gap:10px;margin:5px 0}
.bar-label{flex:0 0 15.5em;font-size:.86rem}
.bar-track{flex:1;background:var(--line);border-radius:4px;height:18px;overflow:hidden}
.bar{display:block;height:100%;width:0;background:var(--accent);border-radius:4px;transition:width .7s ease}
.bar-value{flex:0 0 11em;font-size:.86rem;font-variant-numeric:tabular-nums}
.bar-value small{display:block;color:var(--muted)}
.lang-switch{display:flex;gap:8px;margin:10px 0}
.lang-switch button{border:1px solid var(--line);background:var(--bg);color:var(--fg);
  border-radius:999px;padding:6px 16px;font:inherit;cursor:pointer}
.lang-switch button[aria-pressed="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
@media (max-width:640px){.bar-label{flex-basis:9em}.bar-value{flex-basis:8em}.preview .big{font-size:36px}}
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

  /* ---------- section 1: payload estimator (Japanese anchors) ---------- */
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
    if (count === 0) return 0;
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

  /* ---------- section 2: live rendering with the real quantised fonts ---------- */
  const grids = [0, 2, 4, 8, 16, 32];
  const langNames = {ja: 'Noto Sans JP', zh: 'Noto Sans SC', ko: 'Noto Sans KR'};
  const allAssets = object(data.demo_assets);
  const fullGrids = object(data.full_grids);
  let epsLang = 'ja';
  const loadedFaces = new Map();
  const charsetCache = new Map();
  let loadToken = 0;

  const langAssets = () => object(allAssets[epsLang]);
  function langCharset() {
    if (!charsetCache.has(epsLang)) {
      const cs = langAssets().charset;
      charsetCache.set(epsLang, new Set(typeof cs === 'string' ? Array.from(cs) : []));
    }
    return charsetCache.get(epsLang);
  }
  const langUpm = () => {
    const upm = langAssets().upm;
    return valid(upm) && upm > 0 ? upm : 1000;
  };

  function renderPreview() {
    const input = element('sample-input');
    if (!input) return;
    const charset = langCharset();
    const text = input.value || '';
    let oob = 0;
    const build = target => {
      if (!target) return;
      target.textContent = '';
      let run = '';
      const flush = () => {
        if (run) { target.appendChild(document.createTextNode(run)); run = ''; }
      };
      for (const ch of Array.from(text)) {
        if (charset.has(ch) || /\s/u.test(ch)) { run += ch; continue; }
        flush();
        const span = document.createElement('span');
        span.className = 'oob';
        span.textContent = ch;
        span.title = 'デモ用サブセットに含まれない文字（代替フォントで表示）';
        target.appendChild(span);
        oob++;
      }
      flush();
    };
    build(element('preview-big'));
    const before = oob;
    build(element('preview-body'));
    put('oob-note', oob > 0
      ? `サブセット外の文字が ${format(before)} 文字あります（赤く表示・代替フォント）。`
      : '入力文字はすべてデモ用サブセットに含まれています。');
  }

  async function applyGrid(grid) {
    const assetGrids = object(langAssets().grids);
    const row = object(assetGrids[String(grid)]);
    const token = ++loadToken;
    const status = element('font-status');
    if (!row.file) { put('font-status', 'この格子幅のフォントデータがありません。'); return; }
    if (status) status.textContent = `g=${grid} の実フォントを読み込み中…`;
    try {
      const family = `GLCDemoLive-${epsLang}-g${grid}`;
      const key = `${epsLang}:${grid}`;
      if (!loadedFaces.has(key)) {
        const face = new FontFace(family, `url("assets/${row.file}")`, {style: 'normal', weight: '400'});
        await face.load();
        document.fonts.add(face);
        loadedFaces.set(key, face);
      }
      if (token !== loadToken) return; // a newer slider position won
      for (const id of ['preview-big', 'preview-body']) {
        const node = element(id);
        if (node) node.style.fontFamily = `'${family}', sans-serif`;
      }
      if (status) status.textContent = `いま表示しているのは g=${grid} の実フォント（${bytes(row.bytes)}）で描画した文字です。`;
    } catch (err) {
      if (token === loadToken && status) {
        status.textContent = 'フォントを読み込めませんでした。通信環境を確認してください。';
      }
    }
    const base0 = object(assetGrids['0']);
    const epsilon = grid / (2 * langUpm()) * 100;
    put('grid-value', `g = ${grid}`);
    const slider = element('epsilon-grid');
    if (slider) slider.setAttribute('aria-valuetext', `格子幅 ${grid}、最大誤差 ${format(epsilon, 1)}% em`);
    put('epsilon-value', `${format(epsilon, 1)}% em`);
    put('asset-bytes', bytes(row.bytes));
    put('asset-delta', valid(row.bytes) && valid(base0.bytes) && base0.bytes > 0
      ? `g=0 比 ${format(100 * (row.bytes / base0.bytes - 1), 1)}%（${format(Math.abs(row.bytes - base0.bytes))} B ${row.bytes <= base0.bytes ? '減' : '増'}）`
      : 'データなし');
    const full = object(fullGrids[epsLang])[String(grid)];
    const full0 = object(fullGrids[epsLang])['0'];
    put('full-bytes', bytes(full));
    put('full-ratio', valid(full) && valid(full0) && full0 > 0
      ? `${format(full / full0 * 100, 1)}%（g=0 を 100%）` : 'データなし');
    const fid = object(row.fidelity);
    put('psnr-value', fid.psnr_db === null || fid.psnr_db === undefined
      ? '∞ dB（差分なし）' : valid(fid.psnr_db) ? `${format(fid.psnr_db, 2)} dB` : 'データなし');
    put('changed-value', valid(fid.changed_pct) ? `${format(fid.changed_pct, 2)}%` : 'データなし');
    put('maxdiff-value', valid(fid.max_diff) ? `${format(fid.max_diff)} / 255` : 'データなし');
  }

  function updateGrid() {
    const slider = element('epsilon-grid');
    if (!slider) return;
    const grid = grids[Number(slider.value)];
    if (grid !== undefined) applyGrid(grid);
  }

  function showEpsLang(lang) {
    if (!allAssets[lang]) return;
    const prevSample = langAssets().sample;
    epsLang = lang;
    for (const btn of document.querySelectorAll('[data-eps-btn]')) {
      btn.setAttribute('aria-pressed', String(btn.getAttribute('data-eps-btn') === lang));
    }
    put('eps-font-name', langNames[lang] || lang);
    const cs = langAssets().charset_size;
    put('eps-charset-size', valid(cs) ? format(cs) : '数千');
    put('eps-upm', format(langUpm()));
    const input = element('sample-input');
    const sample = langAssets().sample;
    if (input && typeof sample === 'string' && sample &&
        (input.value === prevSample || input.value === '')) {
      input.value = sample; // untouched sample follows the language switch
    }
    renderPreview();
    updateGrid();
  }

  /* ---------- section 3: language switcher + bar animation ---------- */
  function showStudy(lang) {
    for (const block of document.querySelectorAll('[data-study]')) {
      const active = block.getAttribute('data-study') === lang;
      block.hidden = !active;
      if (active) {
        requestAnimationFrame(() => requestAnimationFrame(() => {
          for (const bar of block.querySelectorAll('.bar')) {
            bar.style.width = `${bar.getAttribute('data-w')}%`;
          }
        }));
      }
    }
    for (const btn of document.querySelectorAll('[data-lang-btn]')) {
      btn.setAttribute('aria-pressed', String(btn.getAttribute('data-lang-btn') === lang));
    }
  }

  element('your-text-input')?.addEventListener('input', updateText);
  element('sample-input')?.addEventListener('input', renderPreview);
  element('epsilon-grid')?.addEventListener('input', updateGrid);
  for (const btn of document.querySelectorAll('[data-lang-btn]')) {
    btn.addEventListener('click', () => showStudy(btn.getAttribute('data-lang-btn')));
  }
  for (const btn of document.querySelectorAll('[data-eps-btn]')) {
    btn.addEventListener('click', () => showEpsLang(btn.getAttribute('data-eps-btn')));
  }
  updateText();
  showEpsLang('ja');
  showStudy('ja');
})();
"""


def lang_asset_payload(entry):
    """One language's demo-asset block for the embedded payload."""
    rows = {}
    for row in entry.get("grids", []):
        if isinstance(row, dict) and number(row.get("grid")) in GRIDS:
            fid = obj(row.get("fidelity"))
            rows[str(int(row["grid"]))] = {
                "file": row.get("file"),
                "bytes": number(row.get("bytes")),
                "fidelity": {
                    "changed_pct": number(fid.get("changed_pct")),
                    "max_diff": number(fid.get("max_diff")),
                    "psnr_db": number(fid.get("psnr_db")),
                },
            }
    return {
        "charset": entry.get("charset") if isinstance(entry.get("charset"), str) else "",
        "charset_size": number(entry.get("charset_size")),
        "upm": number(entry.get("upm")),
        "sample": entry.get("sample") if isinstance(entry.get("sample"), str) else "",
        "grids": rows,
    }


def build(combined, studies, fullsweep, demo_assets, demo_full_zhko):
    meta = obj(combined.get("meta"))
    summary = obj(combined.get("summary"))
    base = obj(meta.get("base500"))
    languages = obj(demo_assets.get("languages"))
    if not languages:
        # Round-3 shape: top-level fields are the Japanese entry.
        languages = {"ja": demo_assets}
    assets_payload = {lang: lang_asset_payload(obj(languages.get(lang)))
                      for lang, _, _ in LANGS}
    payload = {
        "meta": {"base500_chars": meta.get("base500_chars") if isinstance(meta.get("base500_chars"), str) else None,
                 "base500": {key: number(base.get(key)) for key in ("exact", "exact_glc8")}},
        "anchors": [{key: number(obj(row).get(key)) for key in ("chars", "exact", "exact_glc8")}
                    for row in combined.get("anchors", [])] if isinstance(combined.get("anchors"), list) else [],
        "full_grids": full_grid_bytes_by_lang(fullsweep, demo_full_zhko),
        "demo_assets": assets_payload,
    }
    estimate_rows = "".join(
        f'<tr><th scope="row">{esc(label)} <span class="tag est">推定</span></th>'
        f'<td class="num" id="estimate-{key}">推定 —</td></tr>' for key, label in ESTIMATES
    )
    full_label = esc(byte_label(meta.get("full_font_woff2_bytes")))
    google_label = esc(byte_label(obj(summary.get("google_fonts")).get("median")))
    ja_assets = obj(languages.get("ja"))
    sample_text = ja_assets.get("sample") if isinstance(ja_assets.get("sample"), str) else SAMPLE
    charset_size = assets_payload["ja"]["charset_size"]
    charset_label = f"{charset_size:,.0f}" if charset_size is not None else "数千"
    lang_buttons = "".join(
        f'<button type="button" data-lang-btn="{lang}" aria-pressed="{"true" if lang == "ja" else "false"}">{esc(label)}</button>'
        for lang, label, _ in LANGS)
    eps_buttons = "".join(
        f'<button type="button" data-eps-btn="{lang}" aria-pressed="{"true" if lang == "ja" else "false"}">{esc(label)}</button>'
        for lang, label, _ in LANGS)
    blocks = "".join(
        study_block(lang, label, font_label, studies[lang], lang == "ja")
        for lang, label, font_label in LANGS)
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="CJK Web フォントの配信方式と GLC 圧縮を、実フォントのライブ描画と実測データで比べるデモ。">
<title>CJK Web フォント圧縮 — インタラクティブデモ</title>
<style>{CSS}\n{EXTRA_CSS}</style>
</head>
<body><main class="wrap">
<header class="top">
<h1>CJK Web フォント圧縮を試す</h1>
<p class="sub">必要な文字を選ぶ配信方式と、輪郭の精度を調整する GLC を組み合わせる</p>
<p class="small" lang="en">Interactive demo · Live font rendering, text payload estimates, and combined measurements</p>
<p class="meta">対象: Noto Sans JP / SC / KR ／ 実測 JSON と実フォントに基づく比較</p>
</header>
<p class="lead">文章を入力して転送量の目安を確認し、格子幅スライダーでは<b>実際の量子化フォントを
ブラウザに読み込んで、その場で文字を描き直します</b>（画像の差し替えではありません）。
入力した文章の処理はブラウザ内で完結します。</p>
<nav class="toc" aria-label="目次"><ol>
<li><a href="#your-text">あなたの文章と推定転送量</a></li>
<li><a href="#epsilon">許容誤差と見た目（ライブ描画）</a></li>
<li><a href="#combined">配信方式 × GLC の実測結果（日・中・韓）</a></li>
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
<h2 id="epsilon">2. 許容誤差と見た目（ライブ描画）<span class="en" lang="en">Epsilon slider · Live rendering with the real fonts</span></h2>
<p>GLC は輪郭座標を格子に丸めます。スライダーを動かすと、その格子幅で実際に量子化した
サブセットフォント（<span id="eps-font-name">Noto Sans JP</span>、<span id="eps-charset-size">{charset_label}</span> 文字収録）をブラウザが読み込み、下の文章を描き直します。
言語を切り替えると中国語・韓国語の実フォントでも同じ体験ができます。
文章は編集できます。サブセットに無い文字は赤く表示され、代替フォントで描かれます。</p>
<div class="lang-switch" role="group" aria-label="プレビューの言語切替">{eps_buttons}</div>
<div class="card">
<label for="epsilon-grid">格子幅 <output id="grid-value" for="epsilon-grid" class="control-value">g = 8</output></label>
<input id="epsilon-grid" type="range" min="0" max="5" step="1" value="3" aria-describedby="epsilon-model">
<div class="grid-labels" aria-hidden="true"><span>0</span><span>2</span><span>4</span><span>8</span><span>16</span><span>32</span></div>
<p class="note" id="epsilon-model">最大座標誤差 ε = g / (2 × UPM) × 100%。UPM = <span id="eps-upm">1000</span>、g=0 は基準です。</p>
<label for="sample-input">プレビューの文章（編集可）</label>
<textarea id="sample-input" spellcheck="false">{esc(sample_text)}</textarea>
<p class="note" id="font-status" role="status">フォントを読み込んでいません。</p>
<p class="note" id="oob-note" role="status"></p>
<div class="preview" aria-label="ライブ描画プレビュー">
<div class="big" id="preview-big"></div>
<div class="body" id="preview-body"></div>
</div>
<dl class="kv" aria-live="polite" aria-atomic="true">
<dt>ε（em 比）</dt><dd id="epsilon-value">—</dd>
<dt>デモ用サブセット WOFF2</dt><dd id="asset-bytes">—</dd>
<dt>g=0 からの変化</dt><dd id="asset-delta">—</dd>
<dt>全体フォント WOFF2（参考）</dt><dd id="full-bytes">—</dd>
<dt>全体サイズの基準比</dt><dd id="full-ratio">—</dd>
<dt>PSNR / 24px（実測）</dt><dd id="psnr-value">—</dd>
<dt>変化した画素 / 24px（実測）</dt><dd id="changed-value">—</dd>
<dt>最大輝度差 / 24px（実測）</dt><dd id="maxdiff-value">—</dd>
</dl></div>
<p class="note">PSNR 等の描画指標は、配布しているデモ用サブセットそのものについて 24px で測定した実測値です
（見やすさの主観評価ではありません）。全体フォントの容量はフルスイープ実測値で、GLC の前処理
（テーブル整理など）も含むため、容量変化のすべてが座標の丸めだけに由来するわけではありません。</p>
</section>

<section aria-labelledby="combined">
<h2 id="combined">3. 配信方式 × GLC の実測結果<span class="en" lang="en">Combined results · Measured medians (ja / zh / ko)</span></h2>
<p>言語ごとに、必要な文字の選び方と GLC を組み合わせた実測の中央値です。
全体フォントの行は固定の参考サイズで、それ以外はページ別転送量の中央値です。</p>
<div class="lang-switch" role="group" aria-label="言語切替">{lang_buttons}</div>
{blocks}
<p class="note">削減率 = (1 − 各中央値または参考値 / Google Fonts 方式の中央値) × 100%。負の値は増加を表します。
中央値はページ別の比率の中央値とは一致しません。cold / warm のキャッシュ条件はセクション1と同じです。
中国語・韓国語は文字集合の記録があるページのみが対象です（記録のないページは各ブロックに明記）。</p>
</section>
<footer>
<p><a href="index.html">配信方式のレポート</a> ／ <a href="glc.html">GLC のレポート</a></p>
<p>出典の数値は実フォントでの測定値です（data: <code>measure/out/*.json</code>）。
入力文の転送量は実測アンカーに基づく推定です。ライブ描画には <code>assets/demo_font{{,_zh,_ko}}_g*.woff2</code>
（<code>measure/build_demo_assets.py</code> で生成）を使います。</p>
<p>生成: <code>report/build_demo.py</code> ／ CSS・JavaScript・数値データはこの HTML 内に収録。</p>
</footer>
</main>
<script id="demo-data" type="application/json">{inline_json(payload)}</script>
<script>{JS}</script>
</body></html>
"""


def main():
    combined = read_json("combined_study.json", dict)
    studies = {
        "ja": combined,
        "zh": read_json("combined_study_zh.json", dict),
        "ko": read_json("combined_study_ko.json", dict),
    }
    fullsweep = read_json("glc_fullsweep.json", list)
    demo_assets = read_json("demo_assets.json", dict)
    demo_full_zhko = read_json("demo_full_zhko.json", list)
    prefixes = {"ja": "demo_font", "zh": "demo_font_zh", "ko": "demo_font_ko"}
    for lang, prefix in prefixes.items():
        for grid in GRIDS:
            asset = REPORT / "assets" / f"{prefix}_g{grid}.woff2"
            if not asset.is_file():
                raise SystemExit(f"Missing demo font {asset} -- run measure/build_demo_assets.py first")
    output = REPORT / "demo.html"
    output.write_text(build(combined, studies, fullsweep, demo_assets,
                            demo_full_zhko), encoding="utf-8")
    print(f"Wrote {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
