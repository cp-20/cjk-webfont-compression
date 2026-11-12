# 調査メモ：CJK ウェブフォントの圧縮・最適化（2026-11-11 時点）

本ファイルはレポート `report/index.html` の根拠をまとめた調査ノート。引用はすべて一次資料（仕様・公式ブログ・論文・OSS リポジトリ）に基づく。数値は引用元の表記をそのまま記録し、本リポジトリでの実測値とは区別する。

---

## 1. 仕様・規格

### W3C WOFF File Format 2.0
- URL: https://www.w3.org/TR/WOFF2/ ・ 2024-08-08 改訂 W3C Recommendation（初版 2018-01-31）
- 内容: Brotli 圧縮 + `glyf` / `loca` / `hmtx` の内容依存変換（transform）。CFF はデサブルーチン化を推奨。
- 引用: 「The experiments conducted as part of WOFF2 development and evaluation have shown that Brotli compression technology works more efficiently and produces better compression gains for WOFF2 fonts if the CFF outline data is de-subroutinized prior to WOFF2 encoding - this will on average reduce the compressed data size by 5-10%.」
- 参考: https://lists.w3.org/Archives/Public/public-webfonts-wg/2024Apr/0006.html — glyf transform の post-Brotli 効果 median 約 14% 減（2016 年の Google Fonts 全体分析）。

### W3C Incremental Font Transfer (IFT)
- URL: https://www.w3.org/TR/IFT/ ・ 2026-10-13 Candidate Recommendation Draft
- 経緯: 2021-09 Working Draft → 2024-05 → 2025-07 Snapshot → 2025-11 CR → 2026-10 CR
- 方式: (1) フォントパッチ方式（サーバが patch を生成）、(2) レンジリクエスト方式（`RangeRequest` 草案は 2024-12-10 廃止、IFT へ統合）。
- 引用: 「This specification defines a method to incrementally transfer a font from server to client. The client loads only the portion(s) of the font that they actually need, significantly reducing data transfer.」
- 引用: 「Incremental font transfer does not suffer from this issue as it can encompass the original font and all of it's layout rules.」（unicode-range と違い組版ルールを保てる）
- 実装状況: Chromium `Intent to Prototype`（2026-04-28, blink-dev）。https://groups.google.com/a/chromium.org/g/blink-dev/c/3emvPjUOtaM
  - 引用: 「Web fonts for languages with large character sets—such as Chinese, Japanese, and Korean (CJK)—often exceed several megabytes in size.」
  - 引用: 「From our demo, incremental font transfer sees typical savings of 50% or more compared to the subsetting approach.」
- 参考: fontations 実装 https://chromium.googlesource.com/external/github.com/googlefonts/fontations/

### W3C Progressive Font Enrichment 評価報告書
- URL: https://www.w3.org/TR/PFE-evaluation/ ・ 2020-10-15 WG Note
- 測定対象: CJK 約 6,000 シーケンス（日本語 60%、中韓 35%）、フォントは Noto / Source Han 系（すべてデサブルーチン化）。
- CJK のファイルサイズ: 中央値 1,834,496 B（WOFF2 で 768,492 B）、p75 2.6 MB（WOFF2 1.2 MB）、p95 5.52 MB（WOFF2 2.75 MB）。
- 転送バイト数（中央値改善率）: Patch Subset 90%（2G のみ 65%）、Range Request 約 80%、Unicode Range 50%。
- 引用: 「It became clear from both trials that network bandwidth, although important, was not the limiting factor for performance. Rather, the network latency (overall round-trip time for a single request) was the important variable.」
- 引用: 「A 2019 study by the HTTP Archive found that the median number of bytes used for Web Fonts on websites in China was zero.」（CJJ での webfont 採用は事実上ゼロ）
- 手法比較（初期試行）: Patch Subset は理論最適比 +19%、Adobe 方式は +45%。

### W3C Range Request IFT（廃止草案）
- URL: https://www.w3.org/TR/RangeRequest/ ・ 2024-12-10 Discontinued Draft
- 引用: 「This works particularly well for Chinese, Japanese, and Korean fonts, where 90% or more of the font data is outline data.」
- 方式: 輪郭をファイル末尾に並べ、テーブルディレクトリまで取得後に個別グリフを Range 要求。glyph 順序の最適化に simulated annealing を使用。

### RFC 7932 Brotli
- URL: https://www.rfc-editor.org/rfc/rfc7932.txt ・ Informational, 2016-07
- Brotli は静的前辞書（付録 A, 122,784 B）を持つ。文字列参照は静的辞書エントリも指せる。
- WOFF2 の CompressedFontData ストリームも Brotli 必須（WOFF2 仕様 5 章）。

### RFC 8081 font メディアタイプ / RFC 9842 Compression Dictionary Transport
- font/woff2 などのメディアタイプ登録: https://www.rfc-editor.org/rfc/rfc8081
- 圧縮辞書転送: https://www.rfc-editor.org/info/rfc9842/ 。Content-Encoding `dcb`（Brotli ベース）/ `dcz`（Zstd ベース）。Chrome 130 以降が対応、MDN に互換表あり。

---

## 2. 公式ブログ・実装事例

### Google Fonts「Google Fonts launches Japanese support」2018-09-28
- URL: https://developers.googleblog.com/google-fonts-launches-japanese-support/
- 手法: 数百万の日本語ページから文字頻度を取得して分割を設計。
- 戦略: 上位 3,000 文字を 20 スライス、残りを Unicode コードポイント順に 100 スライス → フルフォント比で 80% 削減。
- 韓国版: 上位 2,000 文字を 20 スライス、残りを 100 スライス → 前方式比 38% 削減。
- 引用: 「For Japanese, we found that segmenting the first 3,000 characters into 20 slices was best, resulting in clients downloading 80% fewer bytes than they would if we just sent the whole font.」
- 引用: 「The core features we rely on to efficiently deliver sliced fonts are unicode-range and woff2 / Browsers that support unicode-range and woff2 also support HTTP/2 / HTTP/2 enables the concurrent delivery of many small files.」

### Google Developers Blog「Smaller Fonts with WOFF 2.0 and unicode-range」2015-02-18
- URL: https://developers.googleblog.com/smaller-fonts-with-woff-20-and-unicode-range/
- 引用: 「Combined, they are reducing the size of the downloaded fonts by more than 40 percent on average.」
- 引用: 「WOFF 2.0 responses use ~25 percent less bytes than WOFF with Zopfli.」
- unicode-range 平均 20% 削減、大規模-ES タイプでは 50% 削減。

### Adobe Fonts「Dynamic subsetting & web font serving」
- URL: https://helpx.adobe.com/fonts/web/web-design-and-development/dynamic-subsetting.html
- DOM 変更を監視して不足する文字を動的に要求。404 → 生成 → 200 でキャッシュ。

### cn-font-split（中文網字計画）
- URL: https://github.com/KonghaYao/cn-font-split ・ Apache-2.0 ・ 1.3k stars
- Rust/wasm 実装の CJK フォント分包ツール。パッケージサイズ制御、`vite-plugin-font` も提供。
- 引用（README 英訳）: 「A revolutionary font subetter that supports CJK and any characters! It enables multi-threaded subset of otf, ttf, and woff2 fonts, allowing for precise control over package size.」

### 既存ツール
- fontTools / pyftsubset: https://github.com/fonttools/fonttools （`--flavor=woff2`, `--no-hinting`, `--text-file`）
- glyphhanger: https://github.com/zachleat/glyphhanger （HTML から使用文字を抽出）
- subfont: https://github.com/Munter/subfont （ビルド時サブセット）
- google/woff2: https://github.com/google/woff2 （参照実装）
- font-spider, fontmin, opentype.js など。

---

## 3. 研究論文

### MLFont: Machine Learning-Driven Font Subsetting and Range-Compact Unicode-Range Slicing for Low-Latency Web Typography
- arXiv:2610.24937v1 (2026-10-18), Quan Wang, Yiran Mao ・ https://arxiv.org/abs/2610.24937 ・ コード: https://github.com/wq2012/mlfont
- 3 段構成: (1) Zipf 高頻度層、(2) LDA / 深層 topic による共起モデル、(3) メモ化遺伝的アルゴリズムによるレンジ圧縮。
- 報告値: Noto 5 種（LGC/KR/JP/TC/SC）で 3G レイテンシ 56.7〜75.3% 減（単一ファイル比）、equal_bin 比 46.1〜66.3% 減、CSS 区間数 17.9〜41.7% 減、1.56×〜6.09× のコールドキャッシュ高速化、CJK の帯域節約 65.4〜84.9%。
- 引用: 「If a slice groups together characters that rarely co-occur on the same web page, downloading it for a single needed character forces the client to download hundreds of unused glyphs, resulting in poor glyph utilization.」
- 本リポジトリでの位置づけ: 本稿の層 2（共起最適化スライス）は同系統の単純化であり、本稿は層 1（ページ適応型厳密サブセット）と層 3（IFT 差分）を足す。

### 既存研究（参考）
- Hobby & Gu, "Using String Matching to Compress Chinese Characters", Stanford CS-TR-82-914 (1982) — 輪郭の文字列マッチング圧縮、圧縮比 最大 150。
- Gao & Hua, "Chinese Font Structural Compression Method and Implementation", 清华大学 (2003) — 筆画抽出による構造圧縮。
- "A new automatic compression method for Chinese vector fonts", 図学学报 2021 — 部品再利用で元フォントの約 20% 体积に。
- "Stroke Extraction as the Preprocessing Step for CJK Outline Font Compression" (2015) — https://citeseerx.ist.psu.edu/viewdoc/summary?doi=10.1.1.558.3293
- "Efficient and Scalable Chinese Vector Font Generation via Component Composition", arXiv:2404.06779 — 11K の部品データセット。
- W3C PFE-evaluation §4.6 Codepoint Prediction — 予測Codepoint 追加のトレードオフ（3G では N=1500, F=0.005 など）。

---

## 4. 実測データ（HTTP Archive / Web Almanac）
- Web Almanac 2025 Page Weight: https://almanac.httparchive.org/en/2025/page-weight
  - 引用: 「Fonts accounted for 139 KB on home pages and 138 KB on inner pages.」（2025 年中央値、desktop）
- HTTP Archive Font Bytes（2025-12, desktop）: p10 43.7 / p25 86.0 / p50 170.0 / p75 318.8 / p90 567.9 KB
  - https://httparchive.org/reports/page-weight
- Font Requests（2025-12, desktop）: p50 4 / p90 11 リクエスト

---

## 5. 本リポジトリでの実測（再現手順はレポート付録 B）

| 対象 | 実測値 |
|---|---|
| Noto Sans JP 可変 | 9.59 MB / 17,936 グリフ → WOFF2 4.35 MB（45.4%） |
| Noto Serif JP 可変 | 13.57 MB → WOFF2 5.97 MB |
| Noto Sans SC 可変 | 17.77 MB → WOFF2 7.78 MB |
| Noto Sans KR 可変 | 10.41 MB → WOFF2 3.91 MB |
| Google Fonts Noto Sans JP | 124 スライス / 合計 2.94 MB / 中央値 12.7 KiB / 最大 47.9 KiB |
| Google Fonts Noto Sans JP CSS | 116,174 B（unicode-range が 81,122 B = 69.8%、Brotli 後 17,984 B） |
| 日本語 31 ページ | 中央値 40 スライス / 約 400 KiB、最大 2.3 MB（Wikipedia「日本語」） |

### 方式比較の主要結果（Noto Sans JP を静的 400 重みにインスタンス化、31 ページ）

| 方式 | 1 ページ中央値 | 未学習 10 ページ中央値 | 要求数 | グリフ利用率 |
|---|---:|---:|---:|---:|
| 実 Google Fonts（CDN 実測） | 509 KiB | — | 43 | — |
| C. Google 方式の再現（190 スライス） | 439 KiB | 486 KiB | 17 | 18.9% |
| **提案 A. 共有ベース 500 文字 ＋ 尾部 100 分割** | **111 KiB** | **161 KiB** | **1** | 48.8% |
| 提案 A'. ベース 1,000 文字 | 183 KiB | 234 KiB | 1 | 32.2% |
| C'. 共起最適化スライス 32（学習ページで分割を学習） | 250 KiB | 590 KiB | 19 | 44.6% |
| D. ビルド時厳密サブセット（ページ固有） | 102 KiB | 92 KiB | 1 | 100% |
| IFT 試算（ベース 500 ＋ 差分） | 136 KiB | 133 KiB | 1+ | — |

- 共起学習スライスは学習ページで Google 方式を上回るが未学習ページで下回る＝小さなコーパスでは過適合。
- ページ固有の厳密サブセット（方式 D）は最小だが、セッション合計では方式 C の 3.7 倍。

### その他の実測

- 可変 vs 静的: Noto Sans JP 可変の WOFF2 は 4.35 MB、同じフォントの静的 400 重みは 2.29 MB（約 2 倍）。
- hinting 除去: サイズ変化 +0.0%（効果なし）。GSUB/GPOS も除去: −0.8% のみ。
- CFF vs glyf: Source Han Sans JP（CFF）は WOFF2 化しても元ファイルの 69.8% に留まる（glyf を持つ TrueType 系は 17〜45%）。
- 共有圧縮辞書: 5 種の CJK 輪郭から 1 MiB の Zstandard 辞書を学習しても、held-out フォントの圧縮率は 0〜0.4% の変化のみ。**CJK には共有辞書は効かない**。

（値の詳細は `measure/out/*.json`）
