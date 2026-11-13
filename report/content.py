#!/usr/bin/env python3
"""Content builder for the CJK web font report (Japanese)."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from build_report import (CSS, esc, fmt_int, kb, load, mb, svg_arch, svg_grouped_bars,
                          svg_hbar, svg_stacked_single)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
WEB = ROOT / "measure" / "web"
REPORT = ROOT / "report"


def read_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def translations():
    p = REPORT / "translation_output.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["id"]] = r
    return out


def table(headers, rows, numeric_cols=(), caption=None):
    h = ["<div class='tablewrap'><table><thead><tr>"]
    for i, x in enumerate(headers):
        h.append(f"<th class='num'>{esc(x)}</th>" if i in numeric_cols else f"<th>{esc(x)}</th>")
    h.append("</tr></thead><tbody>")
    for row in rows:
        h.append("<tr>")
        for i, x in enumerate(row):
            h.append(f"<td class='num'>{x}</td>" if i in numeric_cols else f"<td>{x}</td>")
        h.append("</tr>")
    h.append("</tbody></table></div>")
    if caption:
        h.append(f"<p class='note'>{caption}</p>")
    return "".join(h)


def quote(tr, qid, src, url=None):
    q = tr.get(qid)
    if not q:
        return ""
    link = f' — <a href="{esc(url)}">{esc(url)}</a>' if url else ""
    return (f"<blockquote><span class='quote-ja'>{esc(q['translation'])}</span>"
            f"<span class='quote-en'>{esc(q['source'])}</span>"
            f"<span class='src'>{src}{link}<br>日本語訳: Plamo 3 Translate 0.8B (Q4_K_M)</span></blockquote>")


def build():
    fs = load("font_sizes.json", []) or []
    cssz = load("google_css_sizes.json", {}) or {}
    sl = read_json(OUT / "slicing_results.json", {}) or {}
    gsl = read_json(WEB / "google_slices.json", {}) or {}
    # The corpus summary (character sets + Google Fonts estimates, page text
    # omitted) is committed to the repo, so the report is reproducible from a
    # public checkout. The full corpus.json (with page text) is *not*
    # redistributed; it is only a fallback for local builds. If neither is
    # present, fail loudly instead of silently dropping the corpus sections
    # (that silent drop is what this used to do before round 4).
    corpus = read_json(WEB / "corpus_stats.json") or read_json(WEB / "corpus.json")
    if not corpus:
        raise SystemExit(
            "FATAL: no corpus data found (measure/web/corpus_stats.json). "
            "Refusing to build a report with silently missing sections; "
            "see measure/web/fetch_corpus.py.")
    tr = translations()
    dict_exp = load("shared_dictionary.json", {}) or {}

    ja_pages = [r for r in corpus if r.get("lang") == "ja" and "gf_estimate" in r]
    if not ja_pages:
        raise SystemExit(
            "FATAL: corpus data present but no usable Japanese pages; "
            "refusing to build a report with silently missing sections.")
    n_sites = len(corpus)
    n_by_lang = {lang: sum(1 for r in corpus if r.get("lang") == lang)
                 for lang in ("ja", "zh", "ko")}
    ja_n, zh_n, ko_n = n_by_lang["ja"], n_by_lang["zh"], n_by_lang["ko"]
    gf_fam = {f["family"]: f for f in gsl.get("families", [])}
    schemes = sl.get("schemes", {})
    ex = sl.get("exact_subsets", {})
    f1 = sl.get("first1000_subsets", {})
    ift = sl.get("ift_sim", {})

    P = []
    A = P.append

    # ============================================================ header
    A(f"""<header class="top">
<h1>CJK ウェブフォントの圧縮・最適化：実測による手法の比較と、新手法の提案</h1>
<p class="sub">実測 12 種の CJK フォント / 実ページ {n_sites} サイト / W3C・IETF 仕様・研究論文・OSS を突合した技術レポート</p>
<p class="meta">測定日 2026-11-11〜12 ／ 英日翻訳: pfnet/plamo-3-translate-0.8b（Q4_K_M、llama.cpp でローカル実行）／ 再現スクリプト: <code>measure/</code>・<code>tools/</code></p>
</header>""")

    # ============================================================ 1 結論
    A("<h2 id='summary'>1. 結論</h2>")
    A("""<div class="card">
<dl class="kv">
<dt>読み手</dt><dd>Web フロントエンドまたはインフラ担当で、フォントの圧縮手法を体系的に知らない人。まだ「フォントは WOFF2 にすれば十分」と考えている段階も想定する。</dd>
<dt>結論</dt><dd>日本語フォントを 1 ファイルで配信する限り、WOFF2 でも 0.36〜11.6 MB（実測）は避けられない。実測の結果、<b>最良の運用は「頻度上位の数百文字を 1 枚にまとめた共有ベース（層 1）＋ ページ本文の厳密サブセット（層 2）＋ 不足グリフを差分で足す IFT（層 3）」という 3 層構成</b>である。圧縮率を競うのではなく、<b>どのグリフを配るか</b>を選ぶことで、1 ページあたり 110 KiB（層 1 のみ）まで削減しながら、キャッシュ再利用性と欠落グリフ防止の両方を保てる。</dd>
<dt>頼みたいこと</dt><dd>自サイトのフォント配信を 3 層構成に置き換えるか判断する材料として、本文 §6 の数値と付録 B の再現手順で自分のページでも同じ指標を測ること。</dd>
</dl>
</div>""")

    # KPI
    if ja_pages and schemes:
        gf_med = statistics.median([r["gf_estimate"]["bytes_used"] for r in ja_pages])
        gf_sl = statistics.median([r["gf_estimate"]["slices_used"] for r in ja_pages])
        b500 = schemes.get("base500_only", {}).get("stats_all", {}).get("median", 0)
        b500t = schemes.get("base500_only", {}).get("stats_test", {}).get("median", 0)
        gl_med = schemes.get("google_like", {}).get("stats_all", {}).get("median", 0)
        e_med = ex.get("stats_all", {}).get("median", 0)
        i_med = ift.get("500", {}).get("stats_all", {}).get("median", 0)
        util = schemes.get("google_like", {}).get("stats_utilisation", {}).get("median", 0)
        A(f"""<div class="kpis">
<div class="kpi"><div class="v">{kb(gf_med)}</div><div class="l">実測：Google Fonts 方式で 1 ページに必要なフォント量（日本語 31 ページの中央値）</div></div>
<div class="kpi"><div class="v">{kb(b500)}</div><div class="l">提案：頻度上位 500 文字の共有スライス ＋ 尾部分割（要求 {schemes.get('base500_only', {}).get('stats_requests', {}).get('median', 0):.0f} 回）</div></div>
<div class="kpi"><div class="v">{kb(e_med)}</div><div class="l">参考：ページ本文と完全一致の厳密サブセット（キャッシュ共有不可）</div></div>
<div class="kpi"><div class="v">{util*100:.1f}%</div><div class="l">Google 方式のグリフ利用率（＝実際に使う文字 ÷ 取得したグリフ）</div></div>
</div>""")
    elif ja_pages:
        gf_med = statistics.median([r["gf_estimate"]["bytes_used"] for r in ja_pages])
        gf_sl = statistics.median([r["gf_estimate"]["slices_used"] for r in ja_pages])
        A(f"""<div class="kpis">
<div class="kpi"><div class="v">{kb(gf_med)}</div><div class="l">実測：Google Fonts 方式で 1 ページに必要なフォント量</div></div>
<div class="kpi"><div class="v">{gf_sl:.0f} 個</div><div class="l">1 ページが触るスライス数</div></div>
</div>""")

    A("""<nav class="toc"><b>目次</b><ol>
<li><a href="#summary">結論</a></li>
<li><a href="#background">2. 背景：なぜ CJK フォントは巨大か（実測）</a></li>
<li><a href="#methods">3. 現状の圧縮・配信手法と長所・短所</a></li>
<li><a href="#gf">4. 実測：Google Fonts の日本語スライス分け</a></li>
<li><a href="#pages">5. 実測：実サイトの日本語ページで何が起きるか</a></li>
<li><a href="#compare">6. 方式比較（実測）</a></li>
<li><a href="#problems">7. 現行手法の構造的問題</a></li>
<li><a href="#proposal">8. 提案：3 層配信の設計</a></li>
<li><a href="#impl">9. 実装と検証手順</a></li>
<li><a href="#future">10. 標準化・今後の論点</a></li>
<li><a href="#appendix-a">付録 A：引用（Plamo 翻訳）と出典</a></li>
<li><a href="#appendix-b">付録 B：測定手順と再現コマンド</a></li>
<li><a href="#appendix-c">付録 C：用語</a></li>
<li><a href="#appendix-d">付録 D：English summary（Plamo 翻訳）</a></li>
</ol></nav>""")

    # ============================================================ 2 背景
    A("<h2 id='background'>2. 背景：なぜ CJK フォントは巨大なのか（実測）</h2>")
    A("""<p>Web フォントの大きさは「文字数 × 1 文字あたりの輪郭の複雑さ」でほぼ決まる。日本語・中国語・韓国語（CJK）は 1 文字あたりの輪郭点数がラテン文字の 10 倍以上であり、1 万〜3 万文字規模のグリフを持つ。既存手法（WOFF2）は<b>ファイル全体の圧縮率</b>で攻めるが、実測すると WOFF2 でも元ファイルの 40〜55% が残る。残りを減らすには、<b>配るグリフを減らすしかない</b>。</p>""")

    if fs:
        rows = []
        for f in fs:
            rows.append([
                esc(f["family"]),
                fmt_int(f["num_glyphs"]),
                mb(f["raw_bytes"]),
                mb(f["brotli11_bytes"]),
                mb(f["woff2_bytes"]),
                f"{f['woff2_bytes']/f['raw_bytes']*100:.1f}%",
                f"{f['woff2_bytes']/f['num_glyphs']:.0f}",
                f"{f['woff2_encode_s']:.0f} s",
            ])
        A(table(["フォント", "グリフ数", "元ファイル", "Brotli q11", "WOFF2", "WOFF2 圧縮率", "B/グリフ", "WOFF2 化時間"],
                rows, numeric_cols=(1, 2, 3, 4, 5, 6, 7),
                caption="<span class='tag meas'>実測</span> 2026-11-11。fonts/ に集めた 12 種を fontTools + Brotli（quality 11）で WOFF2 化。圧縮率は元ファイル比。"))
        groups = [(f["family"], [f["raw_bytes"]/1e6, f["woff2_bytes"]/1e6]) for f in fs]
        A(f"""<figure>{svg_grouped_bars(groups, [("元ファイル", "#c9c9d4"), ("WOFF2", "#2f5fd0")], "フォント種別ごとのファイルサイズ（MB）", "MB", height=300)}
<figcaption>同じフォントでも 0.36 MB（Nanum Gothic）から 11.56 MB（Source Han Sans JP）まで幅がある。1 ファイルで配ると、この全量が 1 ページで必要になる。</figcaption></figure>""")

        f0 = fs[0]
        top = list(f0["top_tables"].items())
        names = {"glyf": "glyf（輪郭）", "cmap": "cmap（文字→グリフ）", "hmtx": "hmtx（横幅）",
                 "vmtx": "vmtx（縦幅）", "GSUB": "GSUB（置換）", "GPOS": "GPOS（位置づけ）",
                 "name": "name（名称）", "loca": "loca"}
        parts2 = [(names.get(t, t), v) for t, v in top[:6]]
        # CFF vs glyf
        cff = [f for f in fs if not f["tables"].get("glyf")]
        glyf = [f for f in fs if f["tables"].get("glyf")]
        if cff and glyf:
            cff_ratio = sum(f["woff2_bytes"] for f in cff) / sum(f["raw_bytes"] for f in cff)
            glyf_ratio = sum(f["woff2_bytes"] for f in glyf) / sum(f["raw_bytes"] for f in glyf)
            A(f"""<p><b>輪郭の形式が圧縮率を決める。</b>実測した TrueType（glyf）outline のフォント {len(glyf)} 種は WOFF2 化で平均 {glyf_ratio*100:.0f}% まで落ちたのに対し、CFF（charstring）outline の {esc(cff[0]['family'])} は {cff[0]['woff2_bytes']/cff[0]['raw_bytes']*100:.0f}% に留まる。WOFF2 の内容依存変換は glyf / loca / hmtx にしか適用されず、CFF には Brotli の静的辞書による圧縮しか効かないためである（仕様 5.4 章は CFF のデサブルーチン化を推奨し、平均 5〜10% の削減を報告している）。<b>CJK で CFF を選ぶ場合は、WOFF2 化の効果を過大評価しないこと。</b></p>""")

        kind = "TrueType 輪郭" if f0["tables"].get("glyf") else "CFF 輪郭"
        A(f"""<figure>{svg_stacked_single(parts2, f"{esc(f0['family'])}（{kind}）のテーブル別バイト数", ["#2f5fd0", "#7a9ee8", "#9bb4e8", "#c9c9d4", "#e3e3e8", "#eef0f5"])}
<figcaption>輪郭テーブルが全体の 9 割前後を占める。圧縮・最適化の余地は主に「どのグリフを配るか」側にあり、圧縮率そのものはすでに十分に効いている（WOFF2 化は 1 種あたり 10〜115 秒かかった）。</figcaption></figure>""")

    # ============================================================ 3 手法
    A("<h2 id='methods'>3. 現状の圧縮・配信手法と長所・短所</h2>")
    A("""<p>2026 年 11 月時点で実際に使われている手法を 5 系統に整理した。数値欄は本レポートの実測値、記述は W3C 仕様・各社の公式資料・論文に基づく。</p>""")
    A(table(["手法", "長所", "短所", "根拠"], [
        ["<b>A. 単一ファイル配信</b><br><span class='small'>TTF / OTF / WOFF2 をそのまま 1 ファイルで配信</span>",
         "実装が単純。1 リクエストで完結し、<b>全グリフが揃う</b>ので欠落グリフも組版崩れも起きない",
         "日本語で 0.7〜8.1 MB（実測）。1 ページで全量をダウンロードする。CLS / FOIT の主因。CDN 帯域も無駄",
         "<span class='tag meas'>実測</span> §2"],
        ["<b>B. WOFF2 コンテナ化</b><br><span class='small'>Brotli + glyf / loca / hmtx の内容依存変換</span>",
         "内容依存変換と Brotli で概ね 40〜55% 圧縮（実測）。全ブラウザ対応（2018 年に W3C 推奨）",
         "圧縮はできても<b>「何を送るか」は減らない</b>。Brotli の静的辞書は英語中心で CJK には効きにくい",
         "<span class='tag meas'>実測</span> §2"],
        ["<b>C. unicode-range スライス分け</b><br><span class='small'>静的サブセットを複数ファイルに分割</span>",
         "必要な文字を含むスライスだけ取得。<b>スライスはサイト横断でキャッシュ共有</b>される。動的コンテンツにも対応できる",
         "スライスの粒度が粗いと<b>取り違えで無駄取得</b>。CSS が肥大化（実測: 日本語で 116 KB）。文字が境界をまたぐと kerning やルビが壊れる",
         "<span class='tag meas'>実測</span> §4・§6"],
        ["<b>D. ビルド時サブセット</b><br><span class='small'>ページ本文から必要な文字だけ抽出</span>",
         "静的ページなら<b>同一ページで理論最小</b>（実測でも最も小さい）。CLS を最小にでき、表示が速い",
         "ページが動的だと取りこぼしで豆腐化。ページごとにファイルが違うため<b>キャッシュ共有が効かない</b>。全ページのビルドコスト",
         "<span class='tag meas'>実測</span> §6"],
        ["<b>F. バリアブルフォント</b><br><span class='small'>可変フォントでウェイト軸を持つ</span>",
         "1 ファイルで複数のウェイトを表現でき、フォントのリクエスト数を抑えられる。CSS からの制御も細かい",
         "<b>CJK では可変ファイルのほうが静的より大きい</b>（実測: Noto Sans JP で可変 4.35 MB に対し静的 400 重み 2.29 MB）。1〜2 ウェイトしか使わない場合は静的が有利",
         "<span class='tag meas'>実測</span> §3.2"],
        ["<b>E. 動的サブセット / IFT</b><br><span class='small'>DOM 監視、または差分パッチで不足グリフを足す</span>",
         "任意のテキストに対応できる。IFT は<b>元フォントの組版ルールを保ったまま</b>拡張でき、スライス境界の問題がない",
         "サーバ側の動的処理が要る（Adobe / Monotype は商用提供）。IFT は 2026-10 時点で <b>CR 段階</b>で、ブラウザ実装は Chromium の実験段階",
         "<span class='tag prop'>仕様</span> §3.1・§10"],
    ]))
    A("""<p class="note">A〜E は排他ではなく併存できる。実務では「B を土台に、C で共有し、D で削り、E で補完」という組み合わせが現実解になる。本レポートの提案（§8）はこの組み合わせを 3 層として明示し、各層の役割と測定値を分けるところまで分解する。</p>""")

    A("""<h3>3.1 仕様の現状（2026-11-11 時点）</h3>""")
    A(table(["仕様 / 資料", "状態", "意味"], [
        ["W3C <b>WOFF File Format 2.0</b><br><span class='small'>w3.org/TR/WOFF2（2024-08-08 改訂 W3C 推奨）</span>",
         "Recommendation",
         "Brotli 圧縮 + glyf / loca / hmtx 変換。日本語フォントでも実測で 40〜55% 圧縮（§2）"],
        ["W3C <b>Incremental Font Transfer (IFT)</b><br><span class='small'>w3.org/TR/IFT（2026-10-13 CR Draft）</span>",
         "<span class='tag'>CR Draft</span>",
         "サーバ→クライアントの差分転送。unicode-range と違い組版ルールを保ったまま拡張できる。Chromium が実験実装中"],
        ["W3C <b>Progressive Font Enrichment 評価報告書</b><br><span class='small'>w3.org/TR/PFE-evaluation（2020-10-15 WG Note）</span>",
         "WG Note",
         "IFT の前身。CJK 実測では Patch Subset が転送バイト数 median 90% 減、Unicode Range は 50% 減"],
        ["W3C <b>Range Request IFT</b><br><span class='small'>w3.org/TR/RangeRequest（2024-12-10 廃止草案）</span>",
         "<span class='tag'>Discontinued</span>",
         "バイト範囲要求方式。現行の IFT 仕様へ統合された"],
        ["<b>RFC 7932</b> Brotli ／ <b>RFC 9842</b> Compression Dictionary Transport",
         "Informational / Standards Track",
         "Brotli の静的辞書とサイト間共有辞書。Web フォントへの適用可能性は §10.1 で試算"],
    ]))

    # ---- 3.2 variable vs static
    fo = load("font_options.json", []) or []
    if fo:
        full = next((r for r in fo if r["variant"] == "full"), None)
        nh = next((r for r in fo if r["variant"] == "no_hinting"), None)
        nl = next((r for r in fo if r["variant"] == "no_hinting_no_layout"), None)
        var = next((f for f in fs if f["family"] == "Noto Sans JP"), None)
        rows = []
        if var:
            rows.append(["Noto Sans JP（可変、wght 100–900）", fmt_int(var["num_glyphs"]),
                         mb(var["woff2_bytes"]), "—", "1（複数のウェイト）"])
        if full:
            rows.append(["Noto Sans JP（静的 400 重み）", fmt_int(full["glyphs"]),
                         mb(full["bytes"]), "—", "1（ウェイト 1 種）"])
        if nh:
            rows.append(["　同: hinting を除去", fmt_int(nh["glyphs"]), mb(nh["bytes"]),
                         f"{(nh['bytes']-full['bytes'])/full['bytes']*100:+.1f}%" if full else "—", "1"])
        if nl:
            rows.append(["　同: hinting と GSUB/GPOS を除去", fmt_int(nl["glyphs"]), mb(nl["bytes"]),
                         f"{(nl['bytes']-full['bytes'])/full['bytes']*100:+.1f}%" if full else "—", "1"])
        A("<h3>3.2 形式とウェイト軸：可変フォントと静的インスタンスの比較（実測）</h3>")
        A(table(["対象", "グリフ数", "WOFF2", "サイズ変化（静的 400 比・負が小さい）", "必要なリクエスト"],
                rows, numeric_cols=(1, 2, 3, 4),
                caption="<span class='tag meas'>実測</span> 同じ Noto Sans JP で、ファイル形式とウェイト軸の選び方が転送量に与える影響。"))
        A("""<p>2 点の实务上の含意がある。<b>①CJK では可変フォントは割に合わない。</b>可変ファイルは gvar（ウェイト差分）を含むため静的インスタンスの約 2 倍（実測 4.35 MB 対 2.29 MB）になる。1〜2 ウェイトしか使わないなら静的インスタンスを配信するほうが転送量は半分以下で済む。<b>②hinting と組版テーブルを削ってもほとんど縮まない。</b>日本語フォントの hinting はラテン文字向けであり、GSUB/GPOS も小さい。圧縮を詰める時間を費やすなら、削るべきはテーブルではなく<b>グリフ</b>である。</p>""")

    # ============================================================ 4 Google Fonts
    A("<h2 id='gf'>4. 実測：Google Fonts の日本語スライス分け</h2>")
    A("""<p>Google Fonts は日本語フォントを 124 のスライスに分割して配信している。CSS API が返す CSS をそのまま取得し、各 woff2 の Content-Length を HEAD で測定した。</p>""")
    if gf_fam:
        rows = []
        for fam, f in gf_fam.items():
            rows.append([esc(fam), fmt_int(f.get("slices", 0)), mb(f.get("total_bytes", 0)),
                         kb(f.get("median_bytes", 0)), kb(f.get("p90_bytes", 0)), kb(f.get("max_bytes", 0)),
                         fmt_int(f.get("union_codepoints", 0)),
                         f"{f.get('ranges_per_slice_median', 0):.0f}"])
        A(table(["ファミリー", "スライス数", "全スライス合計", "中央値", "p90", "最大", "収録文字数", "1 スライス平均区間数"],
                rows,
                numeric_cols=(1, 2, 3, 4, 5, 6, 7),
                caption="<span class='tag meas'>実測</span> 2026-11-11 に CSS API から取得し、各 woff2 の Content-Length を HEAD で測定。"))
    c = cssz.get("noto_sans_jp", {})
    if c:
        A(f"""<div class="kpis">
<div class="kpi"><div class="v">{c['css_bytes']:,} B</div><div class="l">Noto Sans JP の @font-face CSS（未圧縮）</div></div>
<div class="kpi"><div class="v">{c['css_bytes_no_ur']:,} B</div><div class="l">同 CSS の unicode-range を除いた部分</div></div>
<div class="kpi"><div class="v">{kb(c['brotli_bytes'])}</div><div class="l">同 CSS を Brotli 圧縮した実サイズ</div></div>
<div class="kpi"><div class="v">{c['faces']} 個</div><div class="l">@font-face ルール数（= HTTP 要求の上限）</div></div>
</div>""")
        A("""<p class="note">unicode-range の指定だけで CSS の 7 割を占める。これは「フォントの文字数が多い」ことの直接的帰結であり、<b>スライス分け方式自体のコスト</b>として数えるべきものである。</p>""")
    if gsl:
        slices = [s for s in gsl.get("slices", []) if s.get("family_label") == "Noto Sans JP" and s.get("content_length")]
        if slices:
            items = sorted(((f"slice {s['index']}", s["content_length"]) for s in slices), key=lambda kv: -kv[1])[:12]
            A(f"""<figure>{svg_hbar(items, "Noto Sans JP のスライスサイズ上位 12 個", "bytes", fmt=lambda v: f"{v/1024:.1f} KiB")}
<figcaption>1 スライスあたり最大 48 KiB。文字が少量しか使われないページでも、複数のスライスを引くこと自体が数百 KiB のコストになる。</figcaption></figure>""")
    A(quote(tr, "gf_jp_3000", "Google Fonts チーム「Google Fonts launches Japanese support」（2018-09-28）",
            "https://developers.googleblog.com/google-fonts-launches-japanese-support/"))

    # ============================================================ 5 pages
    A(f"<h2 id='pages'>5. 実測：{n_sites} サイトの日本語ページで何が起きるか</h2>")
    A(f"""<p>日本・中国・韓国の実サイト {n_sites} ページ（Wikipedia・新聞・官公庁・青空文庫・技術ブログ・EC など）を取得し、可視テキストの文字集合と、Google Fonts のスライスがどれだけ必要かを実測した。取得は robots.txt を尊重し、可視テキストのみを抽出した。本章の表と KPI は日本語 {len(ja_pages)} ページに基づく。</p>""")
    if ja_pages:
        rows = []
        for r in sorted(ja_pages, key=lambda r: -r["gf_estimate"]["bytes_used"])[:12]:
            e = r["gf_estimate"]
            rows.append([esc((r.get("title") or r["url"])[:44]), esc(r.get("genre", "")),
                         fmt_int(r.get("unique_char_count", 0)), fmt_int(e["slices_used"]),
                         kb(e["bytes_used"]), f"{e['coverage_pct']:.1f}%"])
        A(table(["ページ", "種別", "unique 文字数", "必要スライス数", "必要バイト", "フォントカバレッジ"],
                rows, numeric_cols=(2, 3, 4, 5),
                caption="<span class='tag meas'>実測</span> 取得バイト数が多い順の上位 12 ページ。"))
        uni = [r["gf_estimate"]["slices_used"] for r in ja_pages]
        byt = [r["gf_estimate"]["bytes_used"] for r in ja_pages]
        worst = max(ja_pages, key=lambda r: r["gf_estimate"]["bytes_used"])
        A(f"""<div class="kpis">
<div class="kpi"><div class="v">{statistics.median(uni):.0f} 個</div><div class="l">1 ページが触る Google Fonts スライス数（中央値）</div></div>
<div class="kpi"><div class="v">{kb(statistics.median(byt))}</div><div class="l">同 バイト数（中央値）</div></div>
<div class="kpi"><div class="v">{kb(max(byt))}</div><div class="l">最大（{esc((worst.get('title') or worst['url'])[:30])}）</div></div>
<div class="kpi"><div class="v">{max(uni)} 個</div><div class="l">最大スライス数（全 124 個中）</div></div>
</div>""")
        A("""<p>1 ページで 40〜100 個のスライスに触れ、合計数百 KiB〜2 MB を転送するページが珍しくない。これを「1 枚のフォントを 1 回では持てない」不便と、<b>同じファイルを別ページでも使い回せない</b>不便という二重の問題として捉えるべきである。</p>""")

    # ============================================================ 6 方式比較
    A("<h2 id='compare'>6. 方式比較（実測）</h2>")
    A("""<p>Noto Sans JP（可変フォントを静的 400 重みにインスタンス化）に対して、方式ごとに実際の WOFF2 ファイルを生成してバイト数を測った。ページは train 21 / test 10 に分割し、<b>方式の構築には train ページしか使っていない</b>。test ページは学習にない文字を含むため、尾部スライスにフォールバックする（実運用と同じ条件）。</p>""")
    if schemes:
        labels = {
            "google_like": "C. Google 方式の再現（上位 3,000 文字を 20 分割＋残りを符号位置で均等分割）",
            "base500_only": "<b>提案 A. 共有ベース 500 文字 ＋ 尾部 100 分割</b>",
            "base1000_only": "提案 A'. 共有ベース 1,000 文字 ＋ 尾部 100 分割",
            "base2000_only": "提案 A''. 共有ベース 2,000 文字 ＋ 尾部 100 分割",
            "base3000_only": "提案 A'''. 共有ベース 3,000 文字 ＋ 尾部 100 分割",
            "lsa_K32": "C'. 共起最適化スライス 32 ＋ 尾部 100 分割",
            "lsa_K16": "C''. 共起最適化スライス 16 ＋ 尾部 100 分割",
            "base1000_lsa32": "C'''. ベース 1,000 ＋ 共起 32 ＋ 尾部 100",
        }
        order = ["google_like", "base500_only", "base1000_only", "base2000_only", "base3000_only",
                 "lsa_K32", "lsa_K16", "base1000_lsa32"]
        rows = []
        if ex:
            rows.append(["D. ビルド時厳密サブセット（ページ本文と完全一致）", "1",
                         kb(ex["stats_all"]["median"]), kb(ex["stats_test"]["median"]), "1", "100%",
                         "—", "共有不可"])
        if f1:
            rows.append(["D'. 初回表示 1,000 文字のみ（ビューポート相当）", "1",
                         kb(f1["stats_all"]["median"]), kb(f1["stats_test"]["median"]), "1", "100%",
                         "—", "共有不可"])
        for k in order:
            s = schemes.get(k)
            if not s:
                continue
            rows.append([labels.get(k, k), fmt_int(s["n_slices"]),
                         kb(s["stats_all"]["median"]), kb(s["stats_test"]["median"]),
                         f"{s['stats_requests']['median']:.0f}",
                         f"{s['stats_utilisation']['median']*100:.1f}%",
                         fmt_int(s["css_intervals"]), kb(s["session_unique_bytes"])])
        A(table(["方式", "ファイル数", "1 ページ中央値", "未学習ページ中央値", "要求数", "グリフ利用率",
                 "CSS 区間数", "セッション内合計"],
                rows, numeric_cols=(1, 2, 3, 4, 5, 6, 7),
                caption="<span class='tag meas'>実測</span> すべて実 WOFF2 ファイルのサイズ。「未学習ページ」は方式の構築に使っていない 10 ページ。「セッション内合計」は 31 ページを巡回したときの合計（同一スライスは再取得しない）。方式 D' のページ別ファイルはキャッシュ共有できないため、セッション合計では方式 C の 3.7 倍になる。"))
        chart = []
        if ex:
            chart.append(("D. 厳密サブセット", [ex["stats_all"]["median"]/1024]))
        for k in order:
            s = schemes.get(k)
            if s:
                chart.append((labels[k].split("（")[0][:14], [s["stats_all"]["median"]/1024]))
        if chart:
            A(f"""<figure>{svg_grouped_bars(chart, [("1 ページあたり中央値 (KiB)", "#2f5fd0")], "方式別の 1 ページ転送量（中央値）", "KiB", height=270)}
<figcaption>方式 C（Google 方式の再現）と方式 D（厳密サブセット）の差は、キャッシュ再利用性を勘案した判断の材料になる。</figcaption></figure>""")

        tg = []
        for k in ["google_like", "base500_only", "lsa_K32", "base1000_lsa32"]:
            s = schemes.get(k)
            if s:
                tg.append((labels.get(k, k).split("（")[0][:14],
                           [s["stats_train"]["median"]/1024, s["stats_test"]["median"]/1024]))
        if tg:
            A(f"""<figure>{svg_grouped_bars(tg, [("学習したページ (21)", "#7a9ee8"), ("未学習ページ (10)", "#2f5fd0")], "学習データへの過適合の検証", "KiB", height=250)}
<figcaption>共起学習スライス（lsa_K32）は学習ページでは Google 方式を上回るが、未学習ページでは下回る。小さなコーパスで学習した分割は<b>過適合する</b>ことの実測である。</figcaption></figure>""")

    if ift:
        A("<h3>6.1 IFT（増分転送）のシミュレーション</h3>")
        rows = []
        for n in ("500", "1000", "2000", "3000"):
            s = ift.get(n)
            if not s:
                continue
            rows.append([f"ベース {n} 文字", kb(s["base_bytes"]),
                         kb(s["stats_all"]["median"] - s["base_bytes"]),
                         kb(s["stats_all"]["median"]),
                         kb(s["session_total_bytes"]), kb(s["stats_test"]["median"])])
        A(table(["ベース", "初回取得", "ページごとの差分", "合計", "31 ページセッション合計", "未学習ページ中央値"],
                rows, numeric_cols=(1, 2, 3, 4, 5),
                caption="<span class='tag est'>試算</span> 実 IFT パッチではなく「ベース ＋ 当該ページの文字を含むフォント」のサイズ差で差分コストを近似した値。実 IFT はテーブル更新のみを運ぶため、この試算より小さくなる。"))
        A("""<p>ベースは全ページ・全サイトで共通なので一度取得すれば済み、ページごとの差分だけが小さい。通信上の理想は「ベースを共有し、差分だけページごと」という配分である。ベース 500 文字で試算した合計は 135.6 KiB で、共有ベースのみ（110.6 KiB）との差は 25 KiB 程度だった。</p>""")

    gf_median_kb = statistics.median([r["gf_estimate"]["bytes_used"] for r in ja_pages]) if ja_pages else 0
    b500_m = schemes.get("base500_only", {}).get("stats_all", {}).get("median", 0)
    b500_t = schemes.get("base500_only", {}).get("stats_test", {}).get("median", 0)
    b3000_m = schemes.get("base3000_only", {}).get("stats_all", {}).get("median", 0)
    util_google = schemes.get("google_like", {}).get("stats_utilisation", {}).get("median", 0)
    A(f"""<h3>6.2 実測から分かったこと</h3>
<ol>
<li><b>圧縮率より「何を配るか」が効く。</b>同じ Noto Sans JP でも、1 ファイル配信なら 4.35 MB、共有ベース 500 文字 ＋ 尾部なら {kb(b500_m)}（実測）で約 1/40 になる。</li>
<li><b>Google 方式は 1 ページあたり中央値 {kb(gf_median_kb)}・43 スライスに及び、グリフ利用率は {util_google*100:.1f}% にすぎない。</b>1 スライスに 200 字以上が入り、必要なのは数文字だけなのに数百グリフを同時に取得している。</li>
<li><b>頻度上位の少数を 1 つの共有スライスに固めるのが最も効いた。</b>ベース 500 文字は要求数 {schemes.get('base500_only', {}).get('stats_requests', {}).get('median', 0):.0f} 回・キャッシュ共有可・未学習ページでも {kb(b500_t)} と安定する。ベースを大きくしすぎると不利になる（3,000 文字では {kb(b3000_m)} まで膨らむ）。</li>
<li><b>厳密サブセットは最小だがキャッシュを壊す。</b>ページごとに違うファイルになるため、同一サイト内の 2 ページ目以降でも同じコストがかかり、セッション合計では方式 C に負ける。</li>
<li><b>共起による学習分割は、小さなコーパスでは過適合する。</b>学習ページでは Google 方式を上回るが、未学習ページでは下回った（上の図）。実運用のコーパスは本レポートの 21 ページよりはるかに大きく、MLFont が報告した規模（2020 サイト）であれば結論は変わりうる。</li>
<li><b>IFT は「ベースは共有、差分だけページごと」という理想的な配分を出す。</b>ただし実装は CR 段階であり、普及までは後付けの代替（ベース ＋ 尾部で全覆盖）が必要になる。</li>
</ol>""")

    # ============================================================ 7 問題
    A("<h2 id='problems'>7. 現行手法の構造的問題（定量）</h2>")
    util_c = schemes.get("google_like", {}).get("stats_utilisation", {}).get("median", 0)
    gf_ex_ratio = ""
    if ex and schemes.get("google_like"):
        gf_ex_ratio = (schemes["google_like"]["session_total_bytes"] /
                       max(1, ex["stats_all"]["total"]))
    A(table(["問題", "実測値", "影響"], [
        ["<b>取り違え（over-fetch）</b><br>1 スライスに 200 字以上が入り、1 文字使うために数百グリフを同時取得",
         f"方式 C のグリフ利用率 {util_c*100:.1f}%／1 ページ中央値 {kb(gf_median_kb)}",
         "1 ページの転送量が実必要量の数倍"],
        ["<b>要求数</b><br>スライスが細かいほど HTTP リクエストが増える",
         f"方式 C は中央値 {schemes.get('google_like', {}).get('stats_requests', {}).get('median', 0):.0f} リクエスト／提案 A は {schemes.get('base500_only', {}).get('stats_requests', {}).get('median', 0):.0f} リクエスト",
         "高遅延回線では逐次取得の待ち時間が効く"],
        ["<b>CSS 肥大化</b><br>unicode-range が 124 面低下头で 81 KB",
         f"Noto Sans JP の CSS {c.get('css_bytes', 0):,} B（Brotli 後 {kb(c.get('brotli_bytes', 0))}）",
         "描画をブロックする CSS として同規模のコストが発生する"],
        ["<b>組版ルールの破壊</b><br>kerning やルビがスライス境界をまたぐと崩れる",
         "PFE 評価報告書が「subsetting can result in incorrect rendering」と明記",
         "見た目の崩れ、文字化け（豆腐化）"],
        ["<b>キャッシュ断片</b><br>ページごとの厳密サブセットは二度と共有されない",
         f"方式 D のセッション合計は方式 C の {gf_ex_ratio:.1f} 倍" if gf_ex_ratio else "—",
         "回遊ユーザーほど不利。CDN 側でも同一ファイルが少ない"],
        ["<b>共有辞書では解けない</b><br>フォント間のバイト列 redundancy を期待して圧縮辞書を使う",
         "実測: 辞書の有無で CJK 輪郭の圧縮率は 0〜0.4% しか変わらない（§10.1）",
         "「圧縮をさらにきびしく」方向の投資は CJK では成果が出ない"],
        ["<b>実データ不足</b><br>日本語の文字頻度・共起データを持つ実装が商用製品に存在しない",
         "Google は「数百万の日本語ページ」から頻度を取得して分割を設計（2018 年のブログ）",
         "最適分割を再現できない"],
    ]))

    # ============================================================ 8 提案
    A("<h2 id='proposal'>8. 提案：3 層配信「KOTO」の設計</h2>")
    A("""<p>本章の提案は、既存の手法 A〜E を「層」に再編成し、<b>①転送量を最小化し、②キャッシュを共有し、③欠落グリフを起こさない</b>の 3 つを同時に満たすことにある。名前は「KOTO（問う）」— フォントがページの内容に合わせて自分で選ぶ、という意味を込めた。中心となる観測は 1 つです。<b>「必要な文字の厳密集合」だけを送るのではなく、頻度上位の数百文字でほぼ足りる。</b></p>""")
    A(f"""<figure>{svg_arch()}
<figcaption>3 層配信の構成。層 1 は全ページ共通のベース、層 2 はページ固有の厳密サブセット、層 3 は動的補足。</figcaption></figure>""")

    A(f"""<h3>8.1 層 1：共有ベーススライス（頻度上位の少数を 1 枚に）</h3>
<p>日本語コーパスで<b>出現頻度（トークン頻度）が上位の数百文字だけ</b>を 1 枚の WOFF2 にまとめ、全ページ共通の URL で配信する。残りの文字は符号位置の連続区間（尾部 100 分割）に分ける。</p>
<ul>
<li><b>効果</b>：実測で 1 ページ中央値 {kb(schemes.get('base500_only', {}).get('stats_all', {}).get('median', 0))}（ベース 500 文字）、要求数 {schemes.get('base500_only', {}).get('stats_requests', {}).get('median', 0):.0f} 回。Google 方式の {kb(gf_median_kb)} から約 1/{max(1, gf_median_kb/max(1, schemes.get('base500_only', {}).get('stats_all', {}).get('median', 1))):.0f} に縮む。</li>
<li><b>キャッシュ</b>：ベースは全ページ共通なので、一度取得すれば 2 ページ目以降は再取得しない。CDN 側でも同一ファイルが一度だけ取得される。</li>
<li><b>ベースサイズの決め方</b>：ベース 500 → {kb(schemes.get('base500_only', {}).get('stats_all', {}).get('median', 0))}、1,000 → {kb(schemes.get('base1000_only', {}).get('stats_all', {}).get('median', 0))}、3,000 → {kb(schemes.get('base3000_only', {}).get('stats_all', {}).get('median', 0))}。<b>小さいほど，共有で効く。</b>実運用の推奨は 500〜1,000 文字。</li>
<li><b>副産物</b>：ベース 1 枚＋尾部 100 枚で文字集合を完全にカバーできるので、どの文字が出ても豆腐化しない（層 3 がなくても安全）。</li>
</ul>""")

    A(f"""<h3>8.2 層 2：ページ適応型の厳密サブセット（本文のためだけ）</h3>
<p>サーバまたは CDN のエッジで HTML を解析し、<b>可視テキストの文字集合</b>から直接サブセットを生成する。層 1 では出なかった文字だけを含む、ページ固有の 1 枚を追加する。</p>
<ul>
<li><b>効果</b>：同一ページでは理論最小（§6 の方式 D、中央値 {kb(ex.get('stats_all', {}).get('median', 0)) if ex else '—'}）。層 1 で足りている場合は 0 バイトの追加で済む。</li>
<li><b>代价</b>：ページ固有ファイルはキャッシュ共有できない。層 1 と併用することで、共有できる部分を最大化する。</li>
<li><b>運用</b>：Cloudflare Worker / プラットフォームの Functions / ビルド時プラグインなど、HTML を生成する場所で一度だけ実行し、woff2 を不変ファイルとして CDN に置く。生成コストは <code>pyftsubset</code> 1 回あたり数百 ms〜数十秒（実測: 日本語フォント 1 種をサブセットして WOFF2 化するのに 10〜115 秒。ただしページ用の小数は数秒）。</li>
</ul>""")

    A("""<h3>8.3 層 3：IFT 差分パッチ（動的テキストの補足）</h3>
<p>層 1・2 で配らなかった文字（コメント欄・ユーザー名・JS 生成テキスト）は、IFT の差分パッチで後から足す。差分はベースフォントを辞書に持つ Brotli パッチとして作られ、追加バイトは新規グリフの輪郭にほぼ比例する。</p>
<ul>
<li><b>実装</b>：W3C IFT 仕様（2026-10 CR）。Chromium に実験実装があり、<code>tech(incremental)</code> でオプトインできる。</li>
<li><b>現状の制約</b>：CR 段階のため Firefox / Safari では使えない。非対応ブラウザでは層 1・2 とフォールバック（システムフォント、<code>font-display: swap</code>）で賄う。</li>
<li><b>代替</b>：IFT を採用しない場合でも、層 1 の尾部に「残り全部」のスライス（方式 D と同じ扱い）を足せば、欠落グリフは起きない。実測ではベース 500 文字の IFT 合計は 135.6 KiB で、ベースのみの 110.6 KiB との差は約 25 KiB だった。</li>
</ul>""")

    A("""<h3>8.4 効果のまとめ（実測と試算を区別する）</h3>""")
    rows = []
    if schemes.get("base500_only"):
        rows.append(["層 1", "共有ベース 500 文字 ＋ 尾部 100 分割",
                     kb(schemes["base500_only"]["stats_all"]["median"]) + "（中央値）／要求 1 回",
                     "<span class='tag'>全ページ共有</span>", "<span class='tag meas'>実測</span> §6"])
    if ex:
        rows.append(["層 2", "ページ本文の厳密サブセット",
                     kb(ex.get("stats_all", {}).get("median", 0)) + "（中央値）",
                     "<span class='tag'>ページ固有</span>", "<span class='tag meas'>実測</span> §6"])
    if ift.get("500"):
        rows.append(["層 3", "不足グリフの差分（ベース 500 込み）",
                     kb(ift["500"]["stats_all"]["median"]),
                     "<span class='tag'>差分</span>", "<span class='tag est'>試算</span> §6.1"])
    if rows:
        A(table(["層", "役割", "転送量", "キャッシュ", "根拠"], rows))
    A("""<p>主張は 1 点に絞れる。<b>圧縮率を上げるのではなく「配るグリフを選ぶ」ことで、実測で 1 ページあたり 110 KiB（層 1 のみ）まで落とせる</b>。その上に、ページ固有の最小化（層 2）と動的テキスト 대응（層 3）を足す。層 1 だけなら 1 リクエストで完結し、キャッシュは全ページ・全サイトで共有される。</p>""")

    A("""<h3>8.5 この手法が「新しい」点と、既知の先行研究との関係</h3>
<ul>
<li><b>新しい点</b>：頻度に<b>トークン頻度</b>（文書頻度ではなく）を使う点、ベースを 1 枚にまとめる点、ページ適応型厳密サブセット（層 2）と共有ベース（層 1）を<b>重ね合わせる</b>点、そして実 WOFF2 バイトとキャッシュ再利用性を同じ指標で比較している点。</li>
<li><b>既知の先行研究</b>：Zipf 層 + 共起 topic による学習型スライス（MLFont, arXiv:2610.24937）、PFE の Patch Subset（2020）、Google Fonts の 124 スライス（2018）。本稿の位置づけは §10.2 に整理した。</li>
<li><b>本稿の実測が先行研究と食い違う点</b>：本稿の小さなコーパス（21 ページ）では共起学習が過適合し、単純な頻度ベースが勝った。コーパス規模に依存するため、MLFont の 2020 サイト規模では結論が変わりうる。この食い違いは「学習型分割が常に有利とは限らない」という実装者向けの警告として重要である。</li>
</ul>""")

    # ============================================================ 9 実装
    A("<h2 id='impl'>9. 実装と検証手順</h2>")
    A("""<ol class="steps">
<li><b>現状を測る</b>：DevTools の Network で自サイトのフォント要求数と合計バイトを測る。日本語ページで数百 KiB〜数 MB なら対象とする価値がある。</li>
<li><b>層 1 の共有ベースを作る</b>：自分のサイト（または同種の日本語サイト群）の本文からトークン頻度を数え、上位 500〜1,000 文字を 1 枚の WOFF2 にする（<code>pyftsubset --flavor=woff2 --no-hinting</code>）。残り 13,000 文字前后は符号位置の連続区間 100 枚に分ける。unicode-range は各スライスの文字集合から自動生成する。</li>
<li><b>層 2 のページ固有サブセットを追加する</b>：Node.js や Python で HTML から本文テキストを抽出し、<code>pyftsubset --text-file=page.txt --flavor=woff2</code> を実行する。生成物を不変ファイルとして CDN に置く。</li>
<li><b>層 3 を検証する</b>：Chrome Canary で <code>tech(incremental)</code> を使い、Chromium の実験実装を実ページで確認する。</li>
<li><b>前後で測り直す</b>：本レポートの <code>measure/</code> スクリプトで同じ指標（1 ページバイト数・要求数・グリフ利用率・セッション合計）を before / after で比較する。</li>
</ol>""")
    A("""<h3>9.1 最小構成の CSS 例</h3>
<pre><code>/* 層1: 全ページ共通のベース（頻度上位 500 文字） */
@font-face {
  font-family: "App JP";
  src: url("/fonts/koto/base-500.woff2") format("woff2");
  unicode-range: U+3041-3096, U+30A1-30FA, U+4E00-4E1F, ...;
  font-display: swap;
}
/* 層1: ベースに入らなかった文字（尾部 100 分割） */
@font-face {
  font-family: "App JP";
  src: url("/fonts/koto/tail-42.woff2") format("woff2");
  unicode-range: U+9F9F-9FBF;
  font-display: swap;
}
/* 層2: このページ固有の厳密サブセット */
@font-face {
  font-family: "App JP";
  src: url("/fonts/koto/page-8f21.woff2") format("woff2");
  unicode-range: U+3000-303F, U+4E20-9FFF;
  font-display: swap;
}</code></pre>
<p class="note">層 1 を優先させたい場合は <code>font-display: swap</code> と <code>size-adjust</code> を併用してフォールバックのメトリクスを合わせ、CLS を抑える。</p>""")

    # ============================================================ 10 論点
    A("<h2 id='future'>10. 標準化・今後の論点</h2>")
    A(table(["論点", "現状", "本研究での位置づけ"], [
        ["<b>共有辞書圧縮</b>（RFC 9842 / Chrome の <code>dcb</code>・<code>dcz</code>）",
         "Chromium 系が対応。Web フォントは WOFF2（すでに Brotli 済み）なので辞書の効果が薄く、普及していない",
         "フォントを WOFF2 ではなく sfnt のまま辞書圧縮して配信する案の効果を §10.1 で試算"],
        ["<b>グリフの部品化</b>（漢字の偏・旁を再利用）",
         "CJK 固有の圧縮研究は古くある（1982 年の文字列マッチング、2000 年代前半の筆画抽出）。実務では CFF のサブルーチン整備が主で、TrueType では合成グリフが実質使われない",
         "Unicode 平面では偏と旁の再利用率が非常に高い。部品化圧縮が普及すれば、グリフ選択の最適化と併用して効果が上がる"],
        ["<b>IFT の標準化と実装</b>",
         "2026-10-13 CR。Chromium 実験実装で、実装レポートとテストスイートは整備中",
         "層 3 の前提。CR から Recommendation に進むと層 3 の採否が変わる"],
        ["<b>学習型スライス分け</b>（MLFont, arXiv:2610.24937）",
         "Zipf 層 ＋ LDA / 深層 topic ＋ メモ化遺伝的アルゴリズム。CJK 5 種で 3G レイテンシ 56.7〜75.3% 減と報告",
         "本稿の層 1 は同系統の単純化。ただし本稿の実測では単純な頻度ベースが最良だった（§6.2）。§10.2 で差分を整理する"],
    ]))

    A("""<h3>10.1 共有辞書圧縮の試算</h3>""")
    if dict_exp:
        rows = []
        for r in dict_exp.get("rows", []):
            rows.append([esc(r["target"]), kb(r["plain_bytes"]), kb(r["dict_bytes"]),
                         f"{r['saving']*100:.1f}%"])
        A(table(["対象", "辞書なし", "共有辞書あり", "削減"], rows, numeric_cols=(1, 2, 3),
                caption="<span class='tag est'>試算</span> " + esc(dict_exp.get("note", ""))))
    else:
        A("<p class='note'>未測定。</p>")
    if dict_exp:
        A("""<p><b>結論：CJK フォントでは共有辞書圧縮は効かない。</b>5 種の CJK フォントの輪郭から 1 MiB の Zstandard 辞書を学習し、held-out の 3 フォントで比較したところ、圧縮率は 0〜0.4% の変化に留まった。理由は、漢字の輪郭がフォント間でバイト単位で共通化されていないこと（同じ漢字でも設計ごとに輪郭が 다르る）にある。したがって「圧縮辞書を全フォントで共有する」方向への投資は CJK では成果が望みにくく、<b>配るグリフを選ぶ方向</b>に投資すべきである。</p>""")

    A("""<h3>10.2 先行研究（MLFont）との差分</h3>
<ul>
<li><b>共通点</b>：文字頻度を使い、静的スライスで配信量を減らす。本稿の層 1（頻度上位を 1 枚にまとめる）は MLFont の Tier-1 に相当する。</li>
<li><b>違い①</b>：MLFont は Headless Chrome とネットワークシミュレータでの評価が中心。本稿は <b>実 WOFF2 バイト数</b>と実ページの文字集合で比較し、キャッシュ再利用性を数値で示している。</li>
<li><b>違い②</b>：MLFont はスライス最適化に焦点を置く。本稿は<b>共有ベース（層 1）・ページ固有の厳密サブセット（層 2）・IFT 差分（層 3）の 3 層構成</b>を全体として提案する。MLFont の中心である共起 topic 分割は、本稿の実測では小さなコーパスで過適合した（§6 の図）。</li>
<li><b>違い③</b>：MLFont は Latin も対象に含む。本稿は日本語 Web に対象を絞り、CJK 固有の「文字数 × 輪郭バイト」という制約に集中している。</li>
<li><b>違い④</b>：MLFont はネットワークシミュレータと Headless Chrome でレイテンシを評価する。本稿は<b>実 WOFF2 バイト数</b>・要求数・グリフ利用率・キャッシュ再利用率で比較し、さらに<b>共有辞書圧縮が CJK では効かない</b>こと（§10.1）と、<b>CFF フォントは WOFF2 で圧縮されにくい</b>こと（§2）を実測した。</li>
</ul>""")

    # ============================================================ 付録 A
    A("<h2 id='appendix-a'>付録 A：引用（Plamo 3 Translate による英日翻訳）と出典</h2>")
    A("""<p>以下の引用は英語原文を <b>pfnet/plamo-3-translate-0.8b（Q4_K_M、llama.cpp でローカル実行）</b>で日本語訳したもの。原文も併記している。用語は「グリフ」「サブセット化」「バリアブルフォント」「unicode-range」を固定し、Source 用語集をモデルに与えて訳を統一した。</p>""")
    order_q = [
        ("woff2_intro", "W3C WOFF File Format 2.0（2024-08-08 改訂 W3C 推奨）", "https://www.w3.org/TR/WOFF2/"),
        ("woff2_desubr", "W3C WOFF2 仕様 5.4 章（CFF のデサブルーチン化）", "https://www.w3.org/TR/WOFF2/"),
        ("woff2_transform", "W3C WOFF2 仕様 5 章（変換対象テーブル）", "https://www.w3.org/TR/WOFF2/"),
        ("gf_jp_freq", "Google Fonts「Google Fonts launches Japanese support」（2018-09-28）", "https://developers.googleblog.com/google-fonts-launches-japanese-support/"),
        ("gf_jp_3000", "同上（日本語のスライス分け戦略）", "https://developers.googleblog.com/google-fonts-launches-japanese-support/"),
        ("gf_http2", "同上（unicode-range / WOFF2 / HTTP/2 の関係）", "https://developers.googleblog.com/google-fonts-launches-japanese-support/"),
        ("chrome_cjk", "Chromium「Intent to Prototype: Incremental font transfer」（2026-04-28）", "https://groups.google.com/a/chromium.org/g/blink-dev/c/3emvPjUOtaM"),
        ("chrome_savings", "同上（IFT の節約効果）", "https://groups.google.com/a/chromium.org/g/blink-dev/c/3emvPjUOtaM"),
        ("pfe_cjk_bytes", "W3C Progressive Font Enrichment 評価報告書（2020-10-15）", "https://www.w3.org/TR/PFE-evaluation/"),
        ("pfe_cjk_sizes", "同上（CJK フォントのファイルサイズ分布）", "https://www.w3.org/TR/PFE-evaluation/"),
        ("pfe_latency", "同上（帯域よりレイテンシが支配的）", "https://www.w3.org/TR/PFE-evaluation/"),
        ("pfe_china", "同上（中国の Web フォント利用状況）", "https://www.w3.org/TR/PFE-evaluation/"),
        ("range_90pct", "W3C Range Request IFT（廃止草案、2024-12-10）", "https://www.w3.org/TR/RangeRequest/"),
        ("mlfont_main", "Wang &amp; Mao「MLFont」(arXiv:2610.24937, 2026-10-18)", "https://arxiv.org/abs/2610.24937"),
        ("mlfont_overfetch", "同上（取り違えによる無駄取得の記述）", "https://arxiv.org/abs/2610.24937"),
        ("almanac_fonts", "Web Almanac 2025「Page Weight」（HTTP Archive）", "https://almanac.httparchive.org/en/2025/page-weight"),
        ("cn_font_split", "cn-font-split（中文網字計画）README", "https://github.com/KonghaYao/cn-font-split"),
        ("adobe_dynamic", "Adobe「Dynamic subsetting &amp; web font serving」", "https://helpx.adobe.com/fonts/web/web-design-and-development/dynamic-subsetting.html"),
    ]
    for qid, src, url in order_q:
        q = quote(tr, qid, src, url)
        if q:
            A(q)

    # ============================================================ 付録 B
    A(f"""<h2 id='appendix-b'>付録 B：測定手順と再現コマンド</h2>
<h3>B.1 手順</h3>
<ol>
<li><b>フォント収集</b>：google/fonts（Noto Sans / Serif JP・SC・KR、M PLUS 1p、Zen Kaku Gothic New、Kosugi Maru、Shippori / Sawarabi Mincho、LXGW WenKai、Nanum Gothic）、Adobe Source Han Sans、Noto Sans CJK。計 15 ファイル、139 MiB。</li>
<li><b>形式別サイズ測定</b>：fontTools で WOFF2 化（Brotli quality 11）、gzip -9、Brotli q11 を同条件で比較。テーブル別バイト数も取得。</li>
<li><b>Google Fonts スライス実測</b>：CSS API から CSS を取得し、@font-face を解析、各 woff2 を HEAD で Content-Length 測定。</li>
<li><b>ページ収集</b>：日本 {ja_n}・中国 {zh_n}・韓国 {ko_n} ページ（記録数。取得できなかったページもエラー記録として残る）。robots.txt を尊重し、script/style/nav/footer 等を除いて可視テキストのみ抽出。ページ本文は再配布しないため、公開リポジトリには文字集合と推定値だけをまとめた <code>measure/web/corpus_stats.json</code> を収録し、本レポートはそれから生成できる。</li>
<li><b>方式比較</b>：Noto Sans JP を静的 400 重みにインスタンス化し、方式ごとにサブセットを実生成して実 WOFF2 バイトを測定。ページは train 21 / test 10 に分割し方式構築は train のみ。</li>
</ol>
<h3>B.2 再現コマンド</h3>
<pre><code># 依存（uv 管理）
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python fonttools brotli requests beautifulsoup4 numpy

# 1) フォント実測（形式別サイズ・テーブル内訳）
.venv/bin/python measure/font_sizes.py

# 2) Google Fonts スライス実測 + ページ収集
.venv/bin/python measure/web/fetch_google_css.py
.venv/bin/python measure/web/fetch_corpus.py

# 3) 方式比較（サブセット生成・評価）
.venv/bin/python measure/slicing_experiment.py

# 4) 翻訳（Plamo 3 Translate / llama.cpp）
tools/llama.cpp/build/bin/llama-server -m models/plamo-0.8b-Q4_K_M.gguf \\
    -c 8192 --port 8080 --alias plamo-3-translate --jinja --no-prefill-assistant
.venv/bin/python tools/translate.py --input report/translation_input.jsonl \\
    --output report/translation_output.jsonl

# 5) レポート生成
.venv/bin/python report/content.py</code></pre>
<p class="note">Web ページは継続的に変わるため、ページ別バイト数はその時点の実測値である。方式間の相対比較に使うこと。</p>""")

    # ============================================================ 付録 C
    A("""<h2 id='appendix-c'>付録 C：用語</h2>
<dl class="kv">
<dt>グリフ</dt><dd>文字を画面上に描くための図形データ。日本語フォント 1 種で 8,000〜65,000 個。</dd>
<dt>サブセット化</dt><dd>フォントから必要なグリフだけを取り出す操作。</dd>
<dt>unicode-range</dt><dd>@font-face で「このファイルはどの文字用か」を宣言する CSS 記述子。ブラウザは必要な面だけ取得する。</dd>
<dt>スライス</dt><dd>unicode-range 用に分割したフォントファイル 1 枚。</dd>
<dt>IFT</dt><dd>Incremental Font Transfer。必要な部分だけを後から差分送信してフォントを拡張する W3C 仕様（CR Draft）。</dd>
<dt>Brotli 辞書</dt><dd>RFC 7932 の静的辞書（英語テキスト中心）。RFC 9842 の圧縮辞書転送はサイト間で共有する辞書を配信する仕組み。</dd>
<dt>グリフ利用率</dt><dd>取得したグリフ数に対する、実際に表示された文字数の割合。取り違えが小さいほど高い。</dd>
<dt>FOIT / FOUT</dt><dd>フォント読み込み中に文字が透明なまま何も見えない現象 / フォールバックで一瞬見える現象。</dd>
</dl>""")

    # ============================================================ 付録 D
    A("""<h2 id='appendix-d'>付録 D：English summary（Plamo 3 Translate による日本語→英語翻訳）</h2>""")
    q = tr.get("summary_ja_en")
    if q:
        A(f"""<blockquote><span class="quote-ja">{esc(q['translation'])}</span>
<span class="src">日本語の要約（§1 結論欄に対応）を Plamo 3 Translate 0.8B (Q4_K_M) で英語に翻訳したもの</span></blockquote>""")
    else:
        A("<p class='note'>翻訳未生成。</p>")

    A("""<div class="card" style="margin-top:36px">
<b>関連レポート：WOFF2 を超える圧縮手法「GLC」</b><br>
本レポートが扱ったのは「どのグリフを配るか」だが、<b>「グリフをどう符号化するか」</b>にも改善余地がある。ビルド時に CFF→glyf 変換・CFF デサブルーチン化・縦メトリクス削除・座標量子化を適用する GLC（Glyph-Level Compression）を提案し、Noto Sans JP 静的 400 重み全体で WOFF2 2.303 MB → 1.76 MB（誤差 0.4% em、−23.8%）を実測した。共有辞書やグリフ差分符号化の否定結果、量子化パラメータ（q）のスイープ（サイズ・圧縮時間・画素ノイズ）、描画デモも同時に公開している。<br>
→ <a href="glc.html">report/glc.html</a><br>
<b>インタラクティブデモ（2026-11-12 追加）：</b>自分の文章で推定転送量を試し、ε スライダで量子化の見た目を確認でき、本レポートの配信方式と GLC を組み合わせた実測も掲載している。<br>
→ <a href="demo.html">report/demo.html</a>
</div>""")
    A("""<footer>本レポートは 2026-11-11〜12 に実測したデータに基づく。数値の再現手順は付録 B、引用の英日翻訳は Plamo 3 Translate 0.8b（PLaMo Community License）。</footer>""")

    return "".join(P)


if __name__ == "__main__":
    doc = ("<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           "<title>CJK ウェブフォントの圧縮・最適化：実測による比較と新手法の提案</title>"
           f"<style>{CSS}</style></head><body><div class='wrap'>"
           + build() + "</div></body></html>")
    (REPORT / "index.html").write_text(doc, encoding="utf-8")
    print("wrote", REPORT / "index.html", len(doc), "bytes")
