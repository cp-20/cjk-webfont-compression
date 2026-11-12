# CJK Web Font Compression — measurements, a method that beats WOFF2, and the negative results

> **English abstract.** This repository measures how CJK web fonts are actually compressed and delivered, and
> proposes **GLC (Glyph-Level Compression)** — a build-time pre-processing pipeline whose *output is still a
> plain WOFF2 file* — that makes Japanese/Chinese/Korean web fonts **9–34 % smaller than WOFF2** at a bounded
> perceptual error (0.1–0.8 % em), with no browser changes. Everything in the two reports was produced by
> generating real WOFF2 files and measuring them; three ideas that *did not* work are published as well.
> [日本語版 below](#日本語).

**Live reports (GitHub Pages):** <https://cp-20.github.io/cjk-webfont-compression/>

| Report | Topic | Headline result |
|---|---|---|
| [`report/index.html`](report/index.html) | **Which glyphs to send** (delivery layer) | A shared base slice of the 500 most frequent characters cuts the per-page font payload from **509 KiB → 111 KiB** vs. Google Fonts' slicing, with 1 request instead of 43 |
| [`report/glc.html`](report/glc.html) | **How to encode the glyphs** (compression layer) | GLC: Noto Sans JP (static 400, 17 936 glyphs) **2.303 MB → 1.756 MB** WOFF2 at 0.4 % em error; CFF Source Han Sans JP **553 KiB → 380 KiB** (−31.4 %) |

---

## GLC in one paragraph

WOFF2 already compresses TrueType outlines close to the entropy limit (≈ 12 bits per outline point for a
3 000-glyph Japanese subset), so there is little room left *inside* the format. The remaining head-room is in
what WOFF2 does **not** do: it never transforms CFF outlines (Chinese fonts keep 70 % of their size), it never
reduces coordinate precision, and it keeps tables a horizontal-only site does not need. GLC adds four
build-time steps that keep the output format unchanged:

| Stage | What it does | Lossless? | Measured |
|---|---|---|---|
| GLC-0 | CFF (cubic) → glyf (quadratic) so WOFF2's content transform applies at all | no (cu2qu, 0.1 % em budget) | −16.8 % |
| GLC-1 | CFF de-subroutinisation (WOFF2 spec §5.4) | yes | −6.4 % |
| GLC-2 | drop vertical metrics (vhea / vmtx) | yes | −0.7 % |
| GLC-4 | error-bounded coordinate quantisation (grid = 2ε·upm, **bbox preserved**) | no (≤ grid/2 units) | −8 … −34 % |

Plus a mandatory **safety valve**: encode before and after, keep the smaller — because quantisation *hurts*
some fonts (Korean Nanum Gothic grows by 10.5 % at grid 4).

## Negative results (published, not hidden)

1. **Δ-Glyph** (delta against a structurally identical glyph): only 14–37 % of glyphs have a "twin", and the
   residual is no smaller than absolute coordinates — WOFF2's transform already does intra-glyph delta coding.
2. **Shared compression dictionary** across CJK fonts: a 1 MiB Zstandard dictionary trained on five fonts
   changes compressed size by **0–0.4 %**. Han outlines are not byte-shared across designs.
3. **Lossless outline canonicalisation**: geometric error exactly 0, but size is a wash (−7 % … +1.6 %) and it
   perturbs rasteriser coverage accumulation. Dropped.

## Reproduce

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python fonttools brotli requests beautifulsoup4 numpy pillow freetype-py

python scripts/fetch_assets.py --all      # fonts + PLaMo 3 Translate GGUF + llama.cpp build

.venv/bin/python measure/font_sizes.py      # per-format sizes and table composition
.venv/bin/python measure/web/fetch_google_css.py   # Google Fonts slices (live CSS + HEAD)
.venv/bin/python measure/web/fetch_corpus.py       # 44 real pages (robots.txt respected)
.venv/bin/python measure/slicing_experiment.py     # delivery-layer comparison
.venv/bin/python measure/glc_final.py              # GLC pipeline comparison
.venv/bin/python measure/glc_sweep.py               # q sweep: size / time / noise
.venv/bin/python measure/glc_render.py             # PSNR (FreeType, hinting off)
.venv/bin/python measure/glc_demo.py               # visual demo PNGs
.venv/bin/python report/content.py                  # build report/index.html
.venv/bin/python report/glc_content.py             # build report/glc.html
```

Translation (EN ↔ JA) is done locally with **PLaMo 3 Translate 0.8B** (Q4_K_M) through a llama.cpp server:

```bash
tools/llama.cpp/build/bin/llama-server -m models/plamo-0.8b-Q4_K_M.gguf \
    -c 8192 --port 8080 --alias plamo-3-translate --jinja --no-prefill-assistant &
.venv/bin/python tools/translate.py --input report/translation_input.jsonl \
    --output report/translation_output.jsonl
```

## Layout

| Path | Contents |
|---|---|
| `report/index.html` | Delivery-layer report (Japanese, self-contained, dark-mode) |
| `report/glc.html` | Compression-layer report: GLC method, q sweep, visual demo (Japanese) |
| `report/content.py`, `report/glc_content.py` | report generators (read the measurement JSON) |
| `report/build_report.py` | shared CSS + inline SVG charts |
| `measure/` | every measurement script and its JSON results (`measure/out/`) |
| `measure/out/` | measured results (JSON) — the evidence behind the reports |
| `tools/glyphcodec.py` | outline quantisation / canonicalisation (GLC-4 / GLC-3) |
| `tools/cff2glyf.py` | CFF → glyf conversion (GLC-0) |
| `tools/translate.py` | batch translation client for the local LLM |
| `fonts/manifest.json` | the 15 CJK fonts: source URL, licence, SHA-256 |
| `research/sources.md` | research notes: primary sources, quotes, prior art |
| `research/standards.md` | standards dossier: W3C / IETF / OpenType status, browser support |
| `scripts/fetch_assets.py` | downloads the fonts / model with hash verification |

Large third-party binaries (fonts, the GGUF model, the llama.cpp build) are **not** in the repository;
`scripts/fetch_assets.py` re-downloads them and verifies SHA-256.

## Licensing

- Code in this repository: MIT (see [`LICENSE`](LICENSE)).
- The CJK fonts are redistributed from their upstream projects under the OFL / Apache-2.0 licences recorded in
  `fonts/manifest.json` and `fonts/licenses/`; they are **not** part of this repository's source.
- PLaMo 3 Translate weights are under the **PLaMo Community License** (free for personal and non-commercial
  use; commercial use has conditions — see the model card).

---

## 日本語

日本語（および中国語・韓国語）の Web フォントは、文字数と 1 文字あたりの輪郭の複雑さの積でファイルサイズが決まるため、
WOFF2 化しても 1 種で 0.7〜7.8 MB になる。本リポジトリは実フォントと実ページを使って圧縮・配信手法を定量比較し、
**WOFF2 を出力形式のまま 8〜42% 小さくするビルド時前処理パイプライン「GLC」**と、3 層配信を提案する。

- レポート 1: [`report/index.html`](report/index.html) — 「どのグリフを配るか」（配信層）
- レポート 2: [`report/glc.html`](report/glc.html) — 「グリフをどう符号化するか」（圧縮層・GLC の提案と実測）
- 公開ページ: <https://cp-20.github.io/cjk-webfont-compression/>

主な実測（2026-11-11〜12）:

- Noto Sans JP 静的 400 重み全体（17,936 グリフ）: WOFF2 2.303 MB → GLC 1.756 MB（誤差 0.4% em、−23.8%）
- CFF の Source Han Sans JP（3,000 文字サブセット）: 553 KiB → 380 KiB（−31.4%）
- Google Fonts の日本語配信: 124 スライス・合計 2.94 MB、1 ページ中央値 509 KiB・43 リクエスト
- 共有ベース 500 文字方式: 1 ページ 111 KiB・1 リクエスト（全ページでキャッシュ共有可）
- 共有圧縮辞書は CJK で効かない（実測 0〜0.4%）、可変フォントは静的インスタンスの約 2 倍大きい

引用の英日翻訳はすべて Plamo 3 Translate 0.8B をローカル実行して生成した。
