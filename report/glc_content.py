#!/usr/bin/env python3
"""Build the Japanese report for the proposed GLC (Glyph-Level Compression) method."""
from __future__ import annotations

import json
from pathlib import Path

from build_report import (CSS, esc, fmt_int, kb, load, mb, svg_grouped_bars, svg_hbar,
                          svg_lines, svg_stacked_single)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "measure" / "out"
REPORT = ROOT / "report"


def read_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def translations():
    out = {}
    p = REPORT / "translation_output.jsonl"
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
    glc = load("glc_bench.json", []) or []
    full = load("glc_fullfont.json", []) or []
    rend = load("glc_render.json", []) or []
    gc = load("gc_bench.json", []) or []
    delta = load("delta_probe.json", []) or []
    sdict = load("shared_dictionary.json", {}) or {}
    fs = load("font_sizes.json", []) or []
    tr = translations()

    def stage(font, name):
        for r in glc:
            if r["font"] == font and r["stage"].startswith(name):
                return r
        return None

    fonts = ["Noto Sans JP", "M PLUS 1p", "Zen Kaku Gothic New", "Nanum Gothic", "Source Han Sans JP"]
    P = []
    A = P.append

    # ============================================================ header
    A("""<header class="top">
<h1>WOFF2 を超える CJK フォント圧縮手法「GLC」の提案と実測</h1>
<p class="sub">既存形式のまま 8〜42% 小さくする、ビルド時前処理パイプライン（Glyph-Level Compression）</p>
<p class="meta">測定日 2026-11-11〜12 ／ 対象: Noto Sans JP, Noto Serif JP, M PLUS 1p, Zen Kaku Gothic New, Nanum Gothic, Source Han Sans JP, LXGW WenKai ／ 英日翻訳: pfnet/plamo-3-translate-0.8b</p>
</header>""")

    # ============================================================ 結論
    A("<h2 id='summary'>1. 結論</h2>")
    A("""<div class="card">
<dl class="kv">
<dt>読み手</dt><dd>Web フォントのパイプライン（フォントのビルド、CDN 配信、キャッシュ設計）を担う人。圧縮アルゴリズム自体を詳しく知らないが、「WOFF2 にすれば終わり」と思っている節がある人</dd>
<dt>結論</dt><dd><b>WOFF2 は日本語フォントに対してすでに上限に近い</b>（3,000 文字のサブセットで 11.8 ビット/点、1 ファイル配信で 4.35 MB）。 それでも上回る余力は<b>3 つの場所</b>にある。(1) CFF フォントは WOFF2 の内容依存変換の対象外で、圧縮率が 70% に留まる、(2) 輪郭座標の精度指定が不要である、(3) 縦書きメトリクスなどの不要テーブルが残る。これらをビルド時前処理として<b>1 つのパイプライン（GLC）</b>にまとめ、<b>出力は普通の WOFF2 のまま</b>にする。実測で Noto Sans JP 静的 400 重み全体は 2.303 MB → <b>1.76 MB（−23.8%、誤差 0.4% em）</b>、CFF の Source Han Sans JP は 553 KiB → <b>380 KiB（−31.4%）</b>。</dd>
<dt>頼みたいこと</dt><dd>自サイトのフォントのビルドに GLC を組み込むか判断する材料として、§5 の数値と §7 の安全弁（変換前後を両方エンコードして小さい方を採用する）を確認し、1 フォントで試す。</dd>
</dl>
</div>""")

    base = stage("Noto Sans JP", "WOFF2 (baseline)")
    g4 = stage("Noto Sans JP", "GLC-4 quant4")
    g8 = stage("Noto Sans JP", "GLC-4 quant8")
    shs = stage("Source Han Sans JP", "GLC-4 quant8")
    shs_base = stage("Source Han Sans JP", "WOFF2 (baseline)")
    fullmap = {r["variant"]: r for r in full}
    fsweep = load("glc_fullsweep.json", []) or []
    def frow(fam, g):
        return next((r for r in fsweep if r["font"] == fam and r["grid"] == g), None)
    fb = frow("Noto Sans JP (static 400)", 0) or {}
    f8 = frow("Noto Sans JP (static 400)", 8) or {}
    sw = load("glc_sweep.json", []) or []
    def srow(fam, g):
        return next((r for r in sw if r["font"] == fam and r["grid"] == g), None)
    ns8 = srow("Noto Sans JP", 8) or {}
    shs8 = srow("Source Han Sans JP", 8) or {}
    shs_base = stage("Source Han Sans JP", "WOFF2 (baseline)") or {}
    A(f"""<div class="kpis">
<div class="kpi"><div class="v">{(1-f8['bytes']/fb['bytes'])*100:.1f}% 減</div><div class="l">Noto Sans JP 静的 400 重み全体（17,936 グリフ）の WOFF2<br>{mb(fb.get('bytes',0))} → {mb(f8.get('bytes',0))}（誤差 0.4% em）</div></div>
<div class="kpi"><div class="v">{(1-shs8['subset_woff2_bytes']/shs_base['bytes'])*100:.1f}% 減</div><div class="l">CFF フォント（Source Han Sans JP）の 3,000 文字サブセット<br>{kb(shs_base['bytes'])} → {kb(shs8.get('subset_woff2_bytes',0))}（CFF→glyf 変換＋量子化 g=8）</div></div>
<div class="kpi"><div class="v">{(1-ns8.get('subset_woff2_bytes',0)/base['bytes'])*100:.1f}% 減</div><div class="l">TrueType フォント（Noto Sans JP）の 3,000 文字サブセット<br>{kb(base['bytes'])} → {kb(ns8.get('subset_woff2_bytes',0))}（量子化 g=8）</div></div>
<div class="kpi"><div class="v">31〜47 dB</div><div class="l">描画の PSNR（FreeType・ヒンティングなし・24px）。幾何誤差は最大でも格子幅の半分</div></div>
</div>""")

    A("""<nav class="toc"><b>目次</b><ol>
<li><a href="#summary">結論</a></li>
<li><a href="#limits">2. WOFF2 の限界はどこか（実測）</a></li>
<li><a href="#negative">3. 先に試して<b>だめだった</b> 3 つの案（負の結果）</a></li>
<li><a href="#method">4. 提案手法 GLC の構成</a></li>
<li><a href="#results">5. 実測結果</a></li>
<li><a href="#sweep">5.3 q（量子化パラメータ）スイープ：サイズ・時間・ノイズ</a></li>
<li><a href="#quality">6. 品質評価（誤差は隠さない）</a></li>
<li><a href="#demo">6.2 デモ：量子化で見た目が変わるか</a></li>
<li><a href="#ops">7. 運用と安全弁</a></li>
<li><a href="#limits2">8. 制約と残課題</a></li>
<li><a href="#appendix-a">付録 A：引用（Plamo 翻訳）</a></li>
<li><a href="#appendix-b">付録 B：再現手順</a></li>
<li><a href="#appendix-c">付録 C：English abstract（Plamo 翻訳）</a></li>
</ol></nav>""")

    # ============================================================ 2 限界
    A("<h2 id='limits'>2. WOFF2 の限界はどこか（実測）</h2>")
    A("""<p>「WOFF2 を超える」を主張する前に、まず WOFF2 がどこまで圧縮しているかを実測する必要がある。日本語フォントを 3,000 文字にサブセットして WOFF2 化し、輪郭点数あたりのコストを測った。</p>""")
    if gc:
        ref = next((r for r in gc if r["font"] == "Noto Sans JP" and r["variant"] == "ref"), None)
        if ref:
            A(f"""<div class="kpis">
<div class="kpi"><div class="v">{ref['bits_per_point']:.1f} bit</div><div class="l">Noto Sans JP: 3,000 文字の WOFF2 が 1 輪郭点あたり消費するバイト</div></div>
<div class="kpi"><div class="v">{ref['subset_points']:,}</div><div class="l">同サブセットに含まれる輪郭点数</div></div>
<div class="kpi"><div class="v">96 点</div><div class="l">1 グリフあたりの平均輪郭点数（漢字は約 11 本のストローク）</div></div>
<div class="kpi"><div class="v">0〜0.4%</div><div class="l">共有圧縮辞書で圧縮率が改善した幅（§3.2）</div></div>
</div>""")
    A("""<p>1 グリフあたり約 96 点、1 点あたり約 12 ビット。WOFF2 の内容依存変換（glyf / loca / hmtx）は点座標をグリフ内で差分符号化し、フラグ・点数・境界を種別ごとのサブストリームに分けて Brotli にかける。これを超える余地は 3 箇所に絞られる。</p>""")
    A(table(["限界", "実測", "影響"], [
        ["<b>CFF には内容依存変換が無い</b><br>WOFF2 の変換対象は glyf / loca / hmtx のみ",
         "Source Han Sans JP（CFF）16.56 MB → WOFF2 11.56 MB（<b>69.8%</b>）",
         "中国語フォント（Source Han 系など）は WOFF2 化してもサイズが大きい"],
        ["<b>輪郭座標の精度が固定</b><br>TrueType は整数座標で、1000 upm なら 1 単位の分解能",
         "量子化すると 3,000 文字サブセットで <b>−13〜33%</b>（§5）",
         "画面サイズでは 0.2〜0.8% em に相当し、実質的に不可視"],
        ["<b>不要テーブルが残る</b><br>vhea / vmtx（縦書きメトリクス）など",
         "vhea / vmtx 削除で <b>−0.7%</b>（472.9 → 469.8 KiB）",
         "横書き専用のサイトには純粋な削減余地"],
        ["<b>Brotli の静的辞書は英語中心</b><br>RFC 7932 の 122 KB 辞書は英文テキスト用",
         "共有辞書（§3.2）でも改善は 0〜0.4%",
         "辞書を足す方向では CJK は伸びない"],
    ]))

    # ============================================================ 3 negative
    A("<h2 id='negative'>3. 先に試して<b>だめだった</b> 3 つの案（負の結果）</h2>")
    A("""<p>「WOFF2 を、结构的に上回る」ことを目指して 3 つの案を実装して実測した。いずれも<b>期待どおりにはならず</b>、結果として現在の GLC の構成に反映している（採用しない判断の根拠として重要なので公開する）。</p>""")
    if delta:
        rows = []
        for r in delta:
            rows.append([esc(r["font"]), fmt_int(r["simple_glyphs"]),
                         f"{r['twin_ratio']*100:.1f}%",
                         f"{r['naive_coord_bits']/8/1024:.1f} KiB",
                         f"{r['delta_coord_bits']/8/1024:.1f} KiB",
                         f"{r['est_ratio_delta_vs_naive']*100:.0f}%"])
        A("<h3>3.1 案1：グリフ差分符号化（Δ-Glyph）</h3>")
        A("<p>「同じ構造のグリフを参照元として差分だけを送る」方式。構造的に同じ（輪郭数と各輪郭の点数も同じ）相手（twins）=\"twins\" を抽出し、残差サイズを測った。</p>")
        A(table(["フォント", "単純グリフ数", "双子を持つグリフ", "座標の絶対符号化", "双子差分符号化", "比率"],
                rows, numeric_cols=(1, 2, 3, 4, 5),
                caption="<span class='tag meas'>実測</span> 「双子」は輪郭数と各輪郭の点数が完全に一致する相手。双子を持つグリフは 14〜37% しかなく、残差も絶対座標と大差ない（100% 超え＝悪化したものもある）。WOFF2 の変換がグリフ内差分符号化を既に行っているため、方式が二重になっている。"))
        A("""<p><b>結論：採用しない。</b>差分符号化の余地は WOFF2 の変換が既に吸収しており、さらにグリフ間で共有できる構造がない。</p>""")

    A("<h3>3.2 案2：サイト間共有圧縮辞書</h3>")
    if sdict.get("rows"):
        rows = []
        for r in sdict["rows"]:
            rows.append([esc(r["target"]), kb(r["outline_raw_bytes"]), kb(r["plain_bytes"]),
                         kb(r["dict_bytes"]), f"{r['saving']*100:+.1f}%"])
        A(table(["対象", "輪郭テーブル", "辞書なし", "共有辞書あり", "削減"], rows, numeric_cols=(1, 2, 3, 4),
                caption="<span class='tag meas'>実測</span> 5 種の CJK フォントの輪郭から 64 KiB サンプルを作り 1 MiB の Zstandard 辞書を学習、held-out の 3 フォントで比較。"))
    A("""<p><b>結論：採用しない。</b>漢字の輪郭はフォント間でバイト単位で共通化していない（同じ漢字でも設計ごとに輪郭が違う）ため、辞書の効果は 0〜0.4% に留まる。CJK では「圧縮をきびしくする」方向より「配る輪郭を減らす/ぼかす」方向の方が効く。</p>""")

    A("<h3>3.3 案3：輪郭の正準化（可逆・形状保存）</h3>")
    if gc:
        rows = []
        for fam in ["Noto Sans JP", "M PLUS 1p", "Zen Kaku Gothic New", "Nanum Gothic"]:
            ref = next((r for r in gc if r["font"] == fam and r["variant"] == "ref"), None)
            can = next((r for r in gc if r["font"] == fam and r["variant"] == "canon"), None)
            if ref and can:
                rows.append([esc(fam), kb(ref["woff2_bytes"]), kb(can["woff2_bytes"]),
                             f"{(can['woff2_bytes']/ref['woff2_bytes']-1)*100:+.1f}%"])
        A(table(["フォント", "元", "正準化後", "サイズ変化"], rows, numeric_cols=(1, 2, 3),
                caption="<span class='tag meas'>実測</span> 輪郭の開始点と輪郭順を正規化する処理。幾何誤差は厳密に 0（形状保存）で確認した。"))
    A("""<p><b>結論：採用しない。</b>サイズに効果がない（−7% 〜 +1.6% と振れる）。さらに、輪郭順が変わるとラスタライザの被覆率の積算順が変わり、FreeType（ヒンティングなし）でも 0.05〜0.16% の画素差が発生した（形状は同一だが、端のアンチエイリアス強度が変わる）。<b>「可逆で安全」を優先して捨てた案</b>として記録する。</p>""")

    # ============================================================ 4 method
    A("<h2 id='method'>4. 提案手法 GLC の構成</h2>")
    A("""<p>GLC は「<b>出力を普通の WOFF2 ファイルとして保ったまま、ビルド時に 4 段の前処理を通す</b>」手法である。ブラウザ側の変更はゼロ、既存の CDN・キャッシュ戦略もそのまま使える。</p>""")
    A(table(["段", "処理", "対象", "可逆性", "実測効果"], [
        ["<b>GLC-0</b>", "CFF（3 次ベジェ）→ glyf（2 次ベジェ）へ変換し、WOFF2 の内容依存変換を使えるようにする",
         "CFF フォント", "不可逆（cu2qu、誤差予算 0.1% em）", "−16.8%"],
        ["<b>GLC-1</b>", "CFF のサブルーチンを展開する（デサブルーチン化）",
         "CFF フォント", "可逆", "−6.4%"],
        ["<b>GLC-2</b>", "縦書き用テーブル（vhea / vmtx）を削除",
         "横書き専用サイト", "可逆（用途による）", "−0.7%"],
        ["<b>GLC-3</b>", "輪郭の正準化（参考実装あり）",
         "任意", "可逆", "±0%（不採用）"],
        ["<b>GLC-4</b>", "座標を指定格子へ量子化（誤差予算で格子幅を決める／BBOx は保持）",
         "任意", "<b>不可逆</b>（誤差は格子幅の半分に厳密に収まる）", "−8〜33%"],
    ]))
    A("""<h3>4.1 誤差予算から格子幅を決める</h3>
<p>GLC-4 の格子幅 <i>g</i> は「許容誤差 ε（em 単位）」から <i>g</i> = 2ε × unitsPerEm で決める。Noto Sans JP（upm 1000）では ε=0.2% なら g=4、ε=0.4% なら g=8、ε=0.8% なら g=16。丸めにより<b>最大誤差は厳密に g/2 以下</b>に収まる（実測で最大 2 / 4 / 8 単位と一致）。</p>
<p>画面上の見え方は ε × 文字サイズで決まる。24px で ε=0.4% なら 0.096px 未満であり、グリフの位置が 1 ピクセルずれる量は生じない。</p>""")
    A("""<p><b>BBOx を保持することが重要。</b>TrueType では adv（文字送り幅）は輪郭の BBOx から算出される phantom point に依存するため、量子化で BBOx が 1 単位動くと adv も同じだけ動き、行の折り返し位置が変わる可能性がある。そこで GLC-4 は、xMin / xMax / yMin / yMax を達成する点を元の座標に固定し、BBOx を厳密に保つ。この処理を入れる前（ 単なる丸めのみ）では、輪郭の<B>位置</B>ずれが画素差の主因になっていた（PSNR 26 dB 相当）。固定後は位置ずれがなくなり、PSNR は 47 dB（g=2）から 31 dB（g=16）へ、サイズとのトレードオフが素直に出る関係になった（実測値）。<b>代价</b>も明示しておく。BBOx を固定すると端点だけが格子から外れるため圧縮率は下がり、g=8 の全体 WOFF2 は 1.667 MB（固定なし）→ 1.76 MB（固定あり）で約 5% 悪化する。<b>行の折り返しが変わる類の変更は避けたい</b>という要件なら、この 5% は妥当な対価である。</p>""")
    A("""<h3>4.2 実装</h3>
<pre><code># 1) CFF フォントを glyf に変換（quadratic 化、誤差予算 0.1% em）
python tools/cff2glyf.py -i SourceHanSansJP.otf -o shs.ttf --max-err-ratio 0.001

# 2) 輪郭座標を量子化（g = 2 * eps * upm）
python tools/glyphcodec.py -i in.ttf -o out.ttf --grid 8

# 3) WOFF2 化（既存コマンドのまま）
pyftsubset out.ttf --flavor=woff2 --no-hinting --text-file=page.txt --output-file=page.woff2</code></pre>
<p class="note">出力が普通の WOFF2 なので、<code>@font-face</code> の書き換えも CDN の設定も不要。</p>""")

    # ============================================================ 5 results
    A("<h2 id='results'>5. 実測結果</h2>")
    A("<h3>5.1 フォント全体（Noto Sans JP 静的 400 重み、17,936 グリフ）</h3>")
    rows = []
    fsweep = load("glc_fullsweep.json", []) or []
    frows = [r for r in fsweep if r["font"] == "Noto Sans JP (static 400)"]
    base_b = frows[0]["bytes"] if frows else 0
    for r in frows:
        name = {0: "WOFF2（現状）", 2: "GLC-4 量子化 g=2（誤差 0.1% em）",
                4: "GLC-4 量子化 g=4（誤差 0.2% em）", 8: "GLC-4 量子化 g=8（誤差 0.4% em）",
                16: "GLC-4 量子化 g=16（誤差 0.8% em）", 32: "GLC-4 量子化 g=32（誤差 1.6% em）"}.get(r["grid"], f"g={r['grid']}")
        rows.append([esc(name), mb(r["bytes"]),
                     f"{(r['bytes']/base_b-1)*100:+.1f}%",
                     f"{r['encode_s']:.0f} s"])
    A(table(["方式", "WOFF2 サイズ", "サイズ変化", "WOFF2 化時間"], rows, numeric_cols=(1, 2, 3),
            caption="<span class='tag meas'>実測</span> 同じフォント全体を WOFF2 化したもの。Brotli q11。"))

    A("<h3>5.2 3,000 文字のサブセット（実際のページに近い粒度）</h3>")
    rows = []
    for fam in fonts:
        b = stage(fam, "WOFF2 (baseline)")
        if not b:
            continue
        r4 = stage(fam, "GLC-4 quant4")
        r8 = stage(fam, "GLC-4 quant8")
        r16 = stage(fam, "GLC-4 quant16")
        d1 = stage(fam, "GLC-1")
        d0 = stage(fam, "GLC-0")
        def pct(r):
            return f"{(r['bytes']/b['bytes']-1)*100:+.1f}%" if r else "—"
        rows.append([esc(fam), kb(b["bytes"]),
                     pct(d1), pct(d0),
                     pct(r4), pct(r8), pct(r16),
                     f"{r8['bytes']/1024:.0f} KiB" if r8 else "—"])
    A(table(["フォント", "WOFF2", "GLC-1", "GLC-0", "GLC-4 g=4", "GLC-4 g=8", "GLC-4 g=16", "g=8 の絶対値"],
            rows, numeric_cols=(1, 2, 3, 4, 5, 6, 7),
            caption="<span class='tag meas'>実測</span> 上記 3,000 文字を日本語・韓国語の実ページから採った文字集合。GLC-1 / GLC-0 は CFF 専用。"))

    groups = []
    for fam in fonts:
        b = stage(fam, "WOFF2 (baseline)")
        r8 = stage(fam, "GLC-4 quant8")
        if b and r8:
            groups.append((fam.replace(" Sans", " Sans").replace(" Gothic New", " Gothic"),
                           [b["bytes"]/1024, r8["bytes"]/1024]))
    if groups:
        A(f"""<figure>{svg_grouped_bars(groups, [("WOFF2", "#c9c9d4"), ("GLC-4 (g=8)", "#2f5fd0")], "3,000 文字サブセットの WOFF2 サイズ", "KiB", height=280)}
<figcaption>Source Han Sans JP のみ CFF 由来のため GLC-0（glyf 変換）が加算されている。Nanum Gothic（韓国語）は g=4 で逆に大きくなる（§7 の安全弁が効く領域）。</figcaption></figure>""")

    A("<h2 id='sweep'>5.3 q（量子化パラメータ）スイープ：サイズ・時間・ノイズ</h2>")
    sweep = load("glc_sweep.json", []) or []
    fullsweep = load("glc_fullsweep.json", []) or []
    bq = load("glc_brotli_q.json", []) or []
    def prep_for(row):
        """preparation time (quantisation of the whole font); fall back to the
        full-font sweep when the intermediate TTF was cached."""
        if row.get("prep_s"):
            return row["prep_s"]
        fsw = load("glc_fullsweep.json", []) or []
        fam_map = {"Noto Sans JP": "Noto Sans JP (static 400)", "M PLUS 1p": "M PLUS 1p"}
        hit = next((x for x in fsw if x["font"] == fam_map.get(row["font"]) and x["grid"] == row["grid"]), None)
        return hit["prep_s"] if hit else row.get("prep_s", 0)

    if sweep:
        primary = "Noto Sans JP"
        rows = []
        grids = sorted({r["grid"] for r in sweep if r["font"] == primary})
        base_size = next((r["subset_woff2_bytes"] for r in sweep
                          if r["font"] == primary and r["grid"] == 0), None)
        for g in grids:
            r = next((x for x in sweep if x["font"] == primary and x["grid"] == g), None)
            if not r:
                continue
            n24 = next((n for n in r["noise"] if n["px"] == 24), None)
            n48 = next((n for n in r["noise"] if n["px"] == 48), None)
            eps = "—" if g == 0 else f"{g/2/1000*100:.1f}% em"
            rows.append([
                f"g={g}", eps,
                kb(r["subset_woff2_bytes"]),
                f"{(r['subset_woff2_bytes']/base_size-1)*100:+.1f}%" if base_size else "—",
                f"{prep_for(r):.0f} s", f"{r['subset_encode_s']:.1f} s",
                f"{r['max_err_units']} u",
                f"{n24['changed_pct']:.3f}%" if n24 else "—",
                (f"{n24['psnr_db']:.1f} dB" if n24 and n24["psnr_db"] != float("inf") else "∞"),
                f"{n48['changed_pct']:.3f}%" if n48 else "—",
            ])
        A("<h3>5.3.1 主指標（Noto Sans JP、3,000 文字サブセット）</h3>")
        A(table(["量子化", "誤差上限", "WOFF2", "サイズ変化", "前処理時間", "WOFF2 化時間",
                 "幾何誤差", "画素変化率 (24px)", "PSNR (24px)", "画素変化率 (48px)"],
                rows, numeric_cols=(2, 3, 4, 5, 6, 7, 8, 9),
                caption="<span class='tag meas'>実測</span> 幾何誤差は 1000 upm のフォントで g/2 単位に一致する（実測値と設計値が一致）。前処理時間は TTF 生成の実測値。"))
        series = []
        colors = {"Noto Sans JP": "#2f5fd0", "M PLUS 1p": "#9bb4e8",
                  "Nanum Gothic": "#e0a45c", "Source Han Sans JP": "#5aa469"}
        for fam in ["Noto Sans JP", "M PLUS 1p", "Nanum Gothic", "Source Han Sans JP"]:
            rs = {r["grid"]: r for r in sweep if r["font"] == fam}
            if not rs:
                continue
            gs = sorted(rs)
            grids = gs
            series.append((fam.replace("Source Han Sans JP", "Source Han Sans JP (CFF)"),
                           colors[fam], [rs[g]["subset_woff2_bytes"] / 1024 for g in gs]))
        if series:
            A(f"""<figure>{svg_lines(series, [f"g={g}" for g in grids], "量子化パラメータと WOFF2 サイズ（3,000 文字サブセット）", "KiB", xlabel="量子化格子幅 g（1 単位 = upm/1000）")}
<figcaption>Noto Sans JP は g=8 付近で収束し、g=16 以降はサイズ低下が緩やかになる。Nanum Gothic（韓国語）は g=4 で一旦大きくなる（安全弁が効く領域）。Source Han Sans JP は CFF 由来のため GLC-0 の効果が既に含まれる。</figcaption></figure>""")
        noise_series = []
        for fam in ["Noto Sans JP", "M PLUS 1p", "Nanum Gothic"]:
            rs = {r["grid"]: r for r in sweep if r["font"] == fam}
            if not rs:
                continue
            gs = sorted(rs)
            vals = []
            for g in gs:
                n = next((x for x in rs[g]["noise"] if x["px"] == 24), None)
                vals.append(n["changed_pct"] if n else None)
            noise_series.append((fam, colors[fam], vals))
        if noise_series:
            A(f"""<figure>{svg_lines(noise_series, [f"g={g}" for g in grids], "量子化ノイズ（24px 描画で濃淡が変わった画素の割合）", "%", xlabel="量子化格子幅 g")}
<figcaption>ノイズは格子幅にほぼ比例して増える。g=8 で 10.3%、g=16 で 11.2%。差が集中しているのは輪郭の縁のアンチエイリアスで、PSNR は 37 dB（g=8）／31 dB（g=16）。</figcaption></figure>""")

    A("<h3>5.3.2 フォント全体のサイズと時間（サブセットなし）</h3>")
    if fullsweep:
        rows = []
        fams = sorted({r["font"] for r in fullsweep})
        for fam in fams:
            rs = {r["grid"]: r for r in fullsweep if r["font"] == fam}
            base = rs.get(0, {}).get("bytes")
            for g in sorted(rs):
                r = rs[g]
                rows.append([esc(fam), f"g={g}", mb(r["bytes"]),
                             f"{(r['bytes']/base-1)*100:+.1f}%" if base else "—",
                             f"{r['prep_s']:.0f} s", f"{r['encode_s']:.0f} s",
                             f"{r['total_s']:.0f} s"])
        A(table(["フォント", "量子化", "WOFF2", "サイズ変化", "前処理時間", "WOFF2 化時間", "合計"],
                rows, numeric_cols=(2, 3, 4, 5, 6),
                caption="<span class='tag meas'>実測</span> サブセットせず全グリフを WOFF2 化した場合。前処理（量子化）と WOFF2 化はビルド時に 1 回だけ実行される。"))
    if bq:
        A("<h3>5.3.3 Brotli の品質 q 値（別の軸）</h3>")
        rows = []
        for r in bq:
            rows.append([f"q={r['brotli_q']}", kb(r["bytes"]),
                         f"{r['encode_s']:.1f} s",
                         f"{(r['bytes']/bq[-1]['bytes']-1)*100:+.1f}%"])
        A(table(["Brotli q", "WOFF2 サイズ", "エンコード時間", "サイズ変化"], rows, numeric_cols=(1, 2, 3),
                caption="<span class='tag meas'>実測</span> 同じ量子化済みフォント（g=8）の WOFF2 化で Brotli の品質を変えた場合。q=11 が既定。"))
        A("""<p>Brotli の q を上げる効果と、量子化（g）を上げる効果は性質が異なる。q は<b>可逆</b>で描画に一切影響しないが、q=5 から 11 までの差は 8%（q=4 との差なら 14%）、一方で符号化時間は 2.4→4.1 秒と増える。量子化は<b>不可逆</b>だが効果が大きい（10〜40%）。<b>実運用では q は既定の 11 のままでよい</b>（圧縮時間を大力发展して 8% を得るより、量子化の安全弁に労力を使うべき）。</p>""")

    A("<h3>5.3.4 ビルドコストと回収</h3>")
    A("""<p>量子化はビルド時に 1 回だけ実行する。実測で Noto Sans JP 静的 400 重み全体（17,936 グリフ）の前処理は 10〜40 秒、量子化済み TTF の WOFF2 化は約 20 秒。対して 1 ページあたりの削減は 64〜880 KiB（3,000 文字サブセットの実測値）。</p>
<p>仮に 1 ページの転送量が 100 KiB 減り、接続速度 5 Mbps（= 625 KB/s）なら、1 ページあたり 0.16 秒の短縮になる。ビルドコスト 60 秒を回収するには<b>約 380 ページビュー</b>が必要。PV の多いメディアでは初日に回収するが、更新が少ない静的サイトでもビルド自動化を前提とすれば、CLS の増減は発生しないため（hmtx を変えない）、回収达不到でも表示の破綻は起きない。</p>""")

    # ============================================================ 5.3 sweep
    A("<h2 id='sweep'>5.3 q（量子化パラメータ）スイープ：サイズ・時間・ノイズ</h2>")
    sweep = load("glc_sweep.json", []) or []
    fullsweep = load("glc_fullsweep.json", []) or []
    bq = load("glc_brotli_q.json", []) or []
    if sweep:
        primary = "Noto Sans JP"
        rows = []
        grids = sorted({r["grid"] for r in sweep if r["font"] == primary})
        base_size = next((r["subset_woff2_bytes"] for r in sweep
                          if r["font"] == primary and r["grid"] == 0), None)
        for g in grids:
            r = next((x for x in sweep if x["font"] == primary and x["grid"] == g), None)
            if not r:
                continue
            n24 = next((n for n in r["noise"] if n["px"] == 24), None)
            n48 = next((n for n in r["noise"] if n["px"] == 48), None)
            eps = "—" if g == 0 else f"{g/2/1000*100:.1f}% em"
            rows.append([
                f"g={g}", eps,
                kb(r["subset_woff2_bytes"]),
                f"{(r['subset_woff2_bytes']/base_size-1)*100:+.1f}%" if base_size else "—",
                f"{prep_for(r):.0f} s", f"{r['subset_encode_s']:.1f} s",
                f"{r['max_err_units']} u",
                f"{n24['changed_pct']:.3f}%" if n24 else "—",
                (f"{n24['psnr_db']:.1f} dB" if n24 and n24["psnr_db"] != float("inf") else "∞"),
                f"{n48['changed_pct']:.3f}%" if n48 else "—",
            ])
        A("<h3>5.3.1 主指標（Noto Sans JP、3,000 文字サブセット）</h3>")
        A(table(["量子化", "誤差上限", "WOFF2", "サイズ変化", "前処理時間", "WOFF2 化時間",
                 "幾何誤差", "画素変化率 (24px)", "PSNR (24px)", "画素変化率 (48px)"],
                rows, numeric_cols=(2, 3, 4, 5, 6, 7, 8, 9),
                caption="<span class='tag meas'>実測</span> 幾何誤差は 1000 upm のフォントで g/2 単位に一致する（実測値と設計値が一致）。前処理時間は TTF 生成の実測値。"))
        series = []
        colors = {"Noto Sans JP": "#2f5fd0", "M PLUS 1p": "#9bb4e8",
                  "Nanum Gothic": "#e0a45c", "Source Han Sans JP": "#5aa469"}
        for fam in ["Noto Sans JP", "M PLUS 1p", "Nanum Gothic", "Source Han Sans JP"]:
            rs = {r["grid"]: r for r in sweep if r["font"] == fam}
            if not rs:
                continue
            gs = sorted(rs)
            grids = gs
            series.append((fam.replace("Source Han Sans JP", "Source Han Sans JP (CFF)"),
                           colors[fam], [rs[g]["subset_woff2_bytes"] / 1024 for g in gs]))
        if series:
            A(f"""<figure>{svg_lines(series, [f"g={g}" for g in grids], "量子化パラメータと WOFF2 サイズ（3,000 文字サブセット）", "KiB", xlabel="量子化格子幅 g（1 単位 = upm/1000）")}
<figcaption>Noto Sans JP は g=8 付近で収束し、g=16 以降はサイズ低下が緩やかになる。Nanum Gothic（韓国語）は g=4 で一旦大きくなる（安全弁が効く領域）。Source Han Sans JP は CFF 由来のため GLC-0 の効果が既に含まれる。</figcaption></figure>""")
        noise_series = []
        for fam in ["Noto Sans JP", "M PLUS 1p", "Nanum Gothic"]:
            rs = {r["grid"]: r for r in sweep if r["font"] == fam}
            if not rs:
                continue
            gs = sorted(rs)
            vals = []
            for g in gs:
                n = next((x for x in rs[g]["noise"] if x["px"] == 24), None)
                vals.append(n["changed_pct"] if n else None)
            noise_series.append((fam, colors[fam], vals))
        if noise_series:
            A(f"""<figure>{svg_lines(noise_series, [f"g={g}" for g in grids], "量子化ノイズ（24px 描画で濃淡が変わった画素の割合）", "%", xlabel="量子化格子幅 g")}
<figcaption>ノイズは格子幅にほぼ比例して増える。g=8 で 10.3%、g=16 で 11.2%。差が集中しているのは輪郭の縁のアンチエイリアスで、PSNR は 37 dB（g=8）／31 dB（g=16）。</figcaption></figure>""")

    A("<h3>5.3.2 フォント全体のサイズと時間（サブセットなし）</h3>")
    if fullsweep:
        rows = []
        fams = sorted({r["font"] for r in fullsweep})
        for fam in fams:
            rs = {r["grid"]: r for r in fullsweep if r["font"] == fam}
            base = rs.get(0, {}).get("bytes")
            for g in sorted(rs):
                r = rs[g]
                rows.append([esc(fam), f"g={g}", mb(r["bytes"]),
                             f"{(r['bytes']/base-1)*100:+.1f}%" if base else "—",
                             f"{r['prep_s']:.0f} s", f"{r['encode_s']:.0f} s",
                             f"{r['total_s']:.0f} s"])
        A(table(["フォント", "量子化", "WOFF2", "サイズ変化", "前処理時間", "WOFF2 化時間", "合計"],
                rows, numeric_cols=(2, 3, 4, 5, 6),
                caption="<span class='tag meas'>実測</span> サブセットせず全グリフを WOFF2 化した場合。前処理（量子化）と WOFF2 化はビルド時に 1 回だけ実行される。"))
    if bq:
        A("<h3>5.3.3 Brotli の品質 q 値（別の軸）</h3>")
        rows = []
        for r in bq:
            rows.append([f"q={r['brotli_q']}", kb(r["bytes"]),
                         f"{r['encode_s']:.1f} s",
                         f"{(r['bytes']/bq[-1]['bytes']-1)*100:+.1f}%"])
        A(table(["Brotli q", "WOFF2 サイズ", "エンコード時間", "サイズ変化"], rows, numeric_cols=(1, 2, 3),
                caption="<span class='tag meas'>実測</span> 同じ量子化済みフォント（g=8）の WOFF2 化で Brotli の品質を変えた場合。q=11 が既定。"))
        A("""<p>Brotli の q を上げる効果と、量子化（g）を上げる効果は性質が異なる。q は<b>可逆</b>で描画に一切影響しないが、q=5 から 11 までの差は 8%（q=4 との差なら 14%）、一方で符号化時間は 2.4→4.1 秒と増える。量子化は<b>不可逆</b>だが効果が大きい（10〜40%）。<b>実運用では q は既定の 11 のままでよい</b>（圧縮時間を大力发展して 8% を得るより、量子化の安全弁に労力を使うべき）。</p>""")

    A("<h3>5.3.4 ビルドコストと回収</h3>")
    A("""<p>量子化はビルド時に 1 回だけ実行する。実測で Noto Sans JP 静的 400 重み全体（17,936 グリフ）の前処理は 10〜40 秒、量子化済み TTF の WOFF2 化は約 20 秒。対して 1 ページあたりの削減は 64〜880 KiB（3,000 文字サブセットの実測値）。</p>
<p>仮に 1 ページの転送量が 100 KiB 減り、接続速度 5 Mbps（= 625 KB/s）なら、1 ページあたり 0.16 秒の短縮になる。ビルドコスト 60 秒を回収するには<b>約 380 ページビュー</b>が必要。PV の多いメディアでは初日に回収するが、更新が少ない静的サイトでもビルド自動化を前提とすれば、CLS の増減は発生しないため（hmtx を変えない）、回収达不到でも表示の破綻は起きない。</p>""")

    # ============================================================ 6 quality
    A("<h2 id='quality'>6. 品質評価（誤差は隠さない）</h2>")
    rows = []
    for r in rend:
        if r["grid"] in (0, 4, 8, 16):
            x = r["render"][1] if len(r["render"]) > 1 else r["render"][0]
            rows.append([esc(r["font"]), f"g={r['grid']}",
                         f"{x['changed_pct']:.3f}%", f"{x['max_diff']}",
                         "0（形状保存）" if r["grid"] == 0 else "≤ g/2 単位"])
    A(table(["フォント", "量子化", "画素が変化した割合（24px）", "最大画素差", "幾何誤差の上限"],
            rows, numeric_cols=(1, 2, 3),
            caption="<span class='tag meas'>実測</span> FreeType 2.13.2、ヒンティング無効（FT_LOAD_NO_HINTING）、日本語 120 文字。描画結果が異なるのは主に輪郭端のアンチエイリアス。"))
    A("""<p>読み方は 2 つある。<b>幾何的には</b>誤差は格子幅の半分（0.2〜0.8% em）に厳密に収まっており、24px 描画で 0.05〜0.19px に相当する。<b>画素的には</b>0.03〜0.36% の画素が端で濃淡が変わり、最大 255/255（縁が 1 ピクセル分ずれるケース）となるが、形状の破綻ではない。</p>
<p>正準化（g=0）だけ Noto Sans JP で 0.05〜0.16% の差が出るのは、輪郭順の変化によりラスタライザの被覆率の積算順が変わるためで、<b>形状そのものは同一</b>（幾何誤差 0）である。</p>""")

    # ============================================================ 6.2 demo
    A("<h2 id='demo'>6.2 デモ：量子化で見た目が変わるか</h2>")
    demo = load("glc_demo.json", []) or []
    if demo:
        import base64
        A("""<p>同じ文章を、元のフォントと量子化後のフォントで FreeType（ヒンティング無効・24px）で描画した比較。上段が 24px の全体描画、下段が「描写質量」の 6 倍拡大（左: 元のフォント／中央: 量子化後／右: 差分を 6 倍強調）。</p>""")
        A("""<p class="note">比較画像は PNG として本レポートに埋め込まれている（外部参照なし）。拡大はニアレスト補間のため、画素の濃淡の変化がそのまま見える。</p>""")
        for d in demo:
            g = d["grid"]
            p = ROOT / "report" / "assets" / d["file"]
            if not p.exists():
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            if g == 0:
                cap = "元フォント（g=0、基準）"
                detail = "変換前のフォントそのもの。"
            else:
                eps = g / 2 / 1000 * 100
                cap = f"g={g}（誤差上限 {eps:.1f}%）"
                sw = next((r for r in (load("glc_sweep.json", []) or [])
                           if r["font"] == "Noto Sans JP" and r["grid"] == g), None)
                if sw:
                    n24 = next((n for n in sw["noise"] if n["px"] == 24), None)
                    detail = (f"24px 描画で濃淡が変わった画素 {n24['changed_pct']:.1f}%、"
                              f"PSNR {n24['psnr_db']:.1f} dB、幾何誤差 最大 {sw['max_err_units']} 単位"
                              f"（{sw['max_err_units']/1000*100:.1f}% em）。")
                else:
                    detail = ""
            A(f"""<figure><img alt="量子化 g={g} の描画比較" src="data:image/png;base64,{b64}">
<figcaption><b>{esc(cap)}</b> — {esc(detail)} 下段右の差分強調で白く光るのは輪郭の縁だけで、字面全体は崩れていない。</figcaption></figure>""")
    A("""<h3>6.3 ノイズをどう読むか</h3>
<ul>
<li><b>幾何誤差には上限がある。</b>丸めによる誤差は格子幅の半分（g=8 なら 4/1000 em = 0.4%）を超えない。24px なら 0.096px 未満で、グリフの位置が 1 ピクセル動くことはない。</li>
<li><b>画素差が小さいのは、差が縁に集中しているため。</b>量子化で輪郭が 0.05〜0.2px ほど動くと、覆域の濃淡（0〜255）が変わる。24px 描画で濃淡が変わった画素は g=2 で 7.0%、g=8 で 10.3%、g=16 で 11.2% だが、差の中身は縁の 1 画素分の濃淡であり、文字として読めない変化ではない。</li>
<li><b>PSNR で読む。</b>実測（Noto Sans JP、24px、120 文字）は g=2 が 47.4 dB、g=4 が 42.7 dB、g=8 が 37.2 dB、g=16 が 31.2 dB、g=32 が 25.6 dB。目安は「g=4（0.2% em）までは本文で確実に気にならない、g=8（0.4% em）は大見出しで目を凝らすと差が出る、g=16（0.8% em）以上は CI の画素差監視をしてから採用」となる。</li>
<li><b>最終判定は安全弁に任せる。</b>見た目が許容できるかは機械では断定できないため、実運用では描画差を CI で監視し、閾値を超えた格子幅は採用しない（§7）。</li>
</ul>""")

    A("<h2 id='ops'>7. 運用と安全弁</h2>")
    A("""<p>量子化は不可逆であり、<b>フォントによっては悪化することもある</b>。実測で Nanum Gothic（韓国語）は g=4 で WOFF2 が 7.0% <b>大きくなった</b>（座標の丸めが TrueType の short/long ベクトル表現の選択を変え、フラグ列が大きくなったため）。したがって GLC は必ず次の安全弁を伴わなければならない。</p>""")
    A("""<ol class="steps">
<li><b>変換前と変換後の両方を WOFF2 化して、小さい方を採用する</b>（ビルドスクリプトで自動化）。これにより「悪化しない」ことが保証される。</li>
<li><b>誤差予算は用途で決める</b>。本文は 0.2〜0.4% em（16〜24px）、見出しやロゴなど注視される文字だけ 0.1% em に切る。</li>
<li><b>回帰テストで画素差を監視する</b>。代表文字列を 16/24/32/48px で描画し、画素差率と最大差を記録する。CI で閾値を超えたらビルドを落とす。</li>
<li><b>フォントごとに格子幅を探索する</b>。g=2,4,8,16 を試して最良を選ぶ。機械的かつ安全。</li>
<li><b>キャッシュはそのまま使える</b>。出力は同一 URL の WOFF2 なので、共有 CDN と既存の Cache-Control 戦略を変更不要。</li>
</ol>""")
    A("""<h3>7.1 副作用と運用上の注意</h3>
<ul>
<li><b>CLS / FOUT への影響はない</b>。量子化で変わるのは輪郭形状のみであり、ascender / descender / advance width は変えない（hmtx は触らない）。メトリクス互換の size-adjust は不要。</li>
<li><b>座標分解能の限界</b>。upm が大きいフォント（1000/2048）ほど同じ g でも誤差が小さくなる。逆に upm 400 のフォントでは g=8 は 2% em になるので、g は upm 比例で決めること。</li>
<li><b>ライセンス</b>。変換後のフォントの配布条件は元のフォントのライセンスに従う（OFL の場合、変換・再配布の要件は変換前のフォントと同等）。CFF→glyf 変換は形状を変えるため、元フォントが「改変不可」を条件にする場合は注意が必要。</li>
<li><b>可変フォント</b>。gvar の差分も量子化の対象にすべきだが、実装は未着手（§8）。</li>
</ul>""")

    # ============================================================ 8 limits
    A("<h2 id='limits2'>8. 制約と残課題</h2>")
    A(table(["制約 / 課題", "内容", "次の手"], [
        ["<b>不可逆である</b>", "GLC-0（cubic→quadratic）と GLC-4（量子化）は形状を変える。厳密な同定性は失われる",
         "誤差は表のように厳密に管理できる；必要なら GLC-4 のみを使い GLC-0 は CFF フォントに限定する"],
        ["<b>可変フォントに未対応</b>", "gvar の差分テーブルは量子化していない。可変フォントでは gvar がサイズの大半を占める可能性がある",
         "gvar にも同じ格子を適用し、インスタンス間の整合性を保つ"],
        ["<b>CFF2 / COLRv1 は対象外</b>", "可変 CFF2 とカラーグリフは別系統",
         "CFF2 には GLC-0 の派生が必要; COLRv1 はビットマップ層を持つため別手法"],
        ["<b>量子化はフォント毎の性質に依存</b>", "韓国語フォントでは g=4 で悪化した",
         "安全弁（変換前後の比較）を必須とし、g を upm 比例で探索する"],
        ["<b>実装上の落とし穴</b>", "CFF→glyf 変換では sfnt バージョンを TrueType（0x00010000）に切り替えないと、ブラウザと FreeType は 'OTTO' と解釈し CFF テーブルを探すため<b>フォントを読み飛ばす</b>（本レポートの実装で実際に発生し、FreeType で検出した）",
         "変換時に sfntVersion を書き換える。検証は fontTools だけでなく必ず FreeType / 実ブラウザで行う"],
        ["<b>標準ではない</b>", "GLC は前処理であり、WOFF2 の仕様変更は不要。形式そのものは既存の WOFF2 のまま",
         "ビルドパイプラインへの組み込みで普及可能。仕様提案は不要"],
    ]))
    A("""<p>要するに、<b>WOFF2 を「上回る」のではなく、WOFF2 に足りない前処理を足す</b>方法である。形式を変えずに済むため、標準化の障壁はゼロで、実装はビルドスクリプト数行とフォントのビルド時間（実測: 量子化の前処理は 17,936 グリフで数十秒、量子化済み TTF の WOFF2 化は 20 秒）だけである。</p>""")

    # ============================================================ appendix A
    A("<h2 id='appendix-a'>付録 A：引用（Plamo 3 Translate による英日翻訳）</h2>")
    A("""<p>以下の引用は W3C WOFF2 仕様（2024-08-08 改訂 W3C 推奨）からのもので、英語原文を <b>pfnet/plamo-3-translate-0.8b（Q4_K_M）</b>で日本語訳した。原文も併記する。</p>""")
    for qid, src, sec in [
        ("woff2_desubr", "W3C WOFF File Format 2.0、5.4 章「CFF table processing and de-subroutinization」", "https://www.w3.org/TR/WOFF2/#5-4-cff"),
        ("woff2_functionality", "W3C WOFF File Format 2.0、5 章「Compressed data format」", "https://www.w3.org/TR/WOFF2/#5"),
        ("woff2_substreams", "W3C WOFF File Format 2.0、5.1 章「Transformed glyf table format」", "https://www.w3.org/TR/WOFF2/#5-1"),
        ("woff2_mtx", "W3C WOFF File Format 2.0、5.1 章（MicroType Express との関係）", "https://www.w3.org/TR/WOFF2/#5-1"),
        ("woff2_hinting", "W3C WOFF File Format 2.0、5.1 章（再構築後のサイズについて）", "https://www.w3.org/TR/WOFF2/#5-1"),
    ]:
        q = quote(tr, qid, src, sec)
        if q:
            A(q)

    # ============================================================ appendix B
    A("""<h2 id='appendix-b'>付録 B：再現手順</h2>
<pre><code># 依存（uv 管理）
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python fonttools brotli numpy pillow freetype-py

# 1) 方式比較（3,000 文字サブセット × 全段）
.venv/bin/python measure/glc_final.py

# 2) フォント全体のサイズ
.venv/bin/python measure/glc_fullfont.py

# 3) 品質（FreeType・ヒンティング無効）
.venv/bin/python measure/glc_render.py

# 4) 負の結果（Δ-Glyph / 共有辞書 / 輪郭正準化）
.venv/bin/python measure/delta_probe.py
.venv/bin/python measure/shared_dictionary.py
.venv/bin/python measure/gc_bench.py

# 5) レポート生成
.venv/bin/python report/glc_content.py</code></pre>
<p class="note">量子化の誤差は「輪郭の点集合に対する Hausdorff 距離」で評価している（<code>measure/glc_final.py</code> の <code>shape_error</code>）。点順が変わっても過大評価しないよう、輪郭の集合どうしを突き合わせている。</p>""")

    # ============================================================ appendix C
    A("""<h2 id='appendix-c'>付録 C：English abstract（Plamo 3 Translate による日本語→英語翻訳）</h2>""")
    q = tr.get("glc_summary_ja_en")
    if q:
        A(f"""<blockquote><span class="quote-ja">{esc(q['translation'])}</span>
<span class="src">本レポートの要約（§1 結論欄に対応）を Plamo 3 Translate 0.8B (Q4_K_M) で英語に翻訳したもの</span></blockquote>""")
    else:
        A("<p class='note'>翻訳未生成。</p>")

    A("""<div class="card" style="margin-top:36px">
<b>インタラクティブデモ（2026-11-12 追加）</b><br>
GLC は <code>tools/glc.py</code> として単一の CLI になり、配信方式（サブセット／共有ベース）と GLC を組み合わせた実測も追加した。デモでは自分の文章で推定転送量を試し、ε スライダで量子化の見た目と容量のトレードオフを確認できる。<br>
→ <a href="demo.html">report/demo.html</a> ／ <a href="index.html">report/index.html</a>（配信方式のレポート）
</div>""")

    A("""<footer>本レポートは 2026-11-11〜12 の実測に基づく。実測スクリプトと中間データは <code>measure/</code> に、引用の英日翻訳は Plamo 3 Translate 0.8b（PLaMo Community License）による。</footer>""")

    return "".join(P)


if __name__ == "__main__":
    doc = ("<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
           "<meta name='viewport' content='width=device-width,initial-scale=1'>"
           "<title>WOFF2 を超える CJK フォント圧縮手法「GLC」の提案と実測</title>"
           f"<style>{CSS}</style></head><body><div class='wrap'>"
           + build() + "</div></body></html>")
    (REPORT / "glc.html").write_text(doc, encoding="utf-8")
    print("wrote", REPORT / "glc.html", len(doc), "bytes")
