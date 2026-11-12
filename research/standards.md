# CJK Web Font Compression — Standards Research Notes

**Prepared:** 11 November 2026  
**Scope:** authoritative W3C, IETF, WHATWG and OpenType material relevant to delivering large Chinese/Japanese/Korean (CJK) web fonts, plus browser-support evidence.  
**Status legend:** **REC** = W3C Recommendation; **CRD** = W3C Candidate Recommendation Draft (not a REC); **WD** = W3C Working Draft; **STD** = IETF Internet Standard; **Standards Track** = IETF standards-track RFC; **Informational/Experimental** = not standards-track.  
**Evidence rule:** specifications are quoted or paraphrased from the cited documents; browser versions come from MDN browser-compat-data (BCD) and caniuse data retrieved on 11 November 2026. Percentages are caniuse global usage estimates, not traffic-weighted measurements. Uncertain points are explicitly marked **[uncertain]**.

---

## 1. Bottom line

### 1.1 What can be relied on in production today

| Layer | Standard / mechanism | Status | Practical CJK role |
|---|---|---|---|
| Font container | **WOFF2** | W3C REC, 08 Aug 2024 | Default delivery format. Brotli-compressed, optional `glyf`/`loca`/`hmtx` transforms. Broad support (~97.4% global). |
| Font container | **WOFF1** | W3C REC, 13 Dec 2012 | Legacy fallback only. zlib/DEFLATE, no outline transform; materially weaker than WOFF2. |
| Font format | **OpenType 1.9.1** (`glyf`, CFF/CFF2, variable fonts, COLRv1) | Microsoft vendor specification, 2024 | Defines the font data itself. `glyf` fonts benefit from WOFF2 transforms; CFF/CFF2 do not. |
| HTTP compression | **Brotli (RFC 7932)** | IETF Informational, Jul 2016 | Used inside WOFF2 and as `Content-Encoding: br`. Static dictionary and up to 16 MiB window. |
| CSS | **CSS Fonts 4** (`unicode-range`, `font-display`, CORS fetch) | W3C WD, 04 Nov 2026 | Script/block subsetting, loading policy, cross-origin rules. Widely implemented despite WD status. |
| CSS | **CSS Fonts 5** (`size-adjust`, metric-based `font-size-adjust`) | W3C WD, 04 Nov 2026 | Fallback metric matching to reduce CJK layout shift. Support is narrower than Fonts 4. |
| HTTP | **RFC 9110 Range**, **RFC 9111 caching** | STD 97 / STD 98, Jun 2022 | Byte-range serving and cache behavior; necessary plumbing for range-based schemes, but not a browser font-loading API by themselves. |
| HTTP | **HTTP/2 (RFC 9113)**, **HTTP/3 (RFC 9114)** | Standards Track, Jun 2022 | Multiplexed patch/subset requests; HTTP/2 ~97.4%, HTTP/3 ~94.96%. |
| HTTP | **RFC 9218 priority** | Standards Track, Jun 2022 | Hints for ordering font and patch requests; server support varies. |
| HTML | **`<link rel=preload as=font>`** | WHATWG HTML Living Standard, 11 Nov 2026 | Starts the font fetch earlier. Mature support in all major engines. |
| HTTP | **`Link: rel=preload`**, **103 Early Hints** | HTML LS; RFC 8297 Experimental, Dec 2017 | Can start font fetch before HTML body. 103 preload is **not** supported by Safari per BCD. |
| Media type | **RFC 8081 `font/*`** | Standards Track, Feb 2017 | Correct MIME types (`font/woff2`, `font/otf`, `font/collection`, etc.). |

### 1.2 What is experimental or limited

| Mechanism | Status | Why it is not a safe baseline |
|---|---|---|
| **Incremental Font Transfer (IFT)** | W3C **CRD**, 13 Oct 2026; Chromium status **Proposed**, Firefox/Safari **No signal** | No shipping browser implementation as of 11 Nov 2026. Server/encoder complexity is substantial. The strongest technical fit for CJK, but not deployable as a transparent web standard today. |
| **Compression Dictionary Transport** (`dcb`/`dcz`) | IETF **Standards Track RFC 9842**, Sep 2025 | Chrome/Edge 130+ only; Firefox 145+ behind a preference; Safari none. HTTPS-only, same-origin/CORS constraints, and the dictionary must be fetched/cached first. |
| **PFE “Range Request” font streaming** | Research method evaluated in W3C PFE Note (2020), not a browser standard | Requires a preprocessed font and browser font-engine support for piecewise glyph loading. No mainstream browser exposes this as normal `@font-face` behavior. |
| **COLRv1 color fonts** | OpenType 1.9.1 feature; Chrome 98+/Firefox 107+; **Safari no** | Useful progressive enhancement, not a cross-browser requirement. |
| **103 Early Hints with preload** | RFC 8297 Experimental | Chrome 103+, Firefox 123+; **Safari does not act on preload in 103** per BCD. CDN support varies. |

**Key conclusion:** a new CJK delivery method can rely today on WOFF2 + Brotli + `unicode-range` + `font-display` + preload + CORS + HTTP/2/3 + standard caching. It can *prototype* IFT and dictionary transport, but must feature-detect and provide a whole-font fallback. It cannot assume IFT, `dcb`/`dcz`, range-request font streaming, 103 preload, or COLRv1 are universally available.

---

## 2. Method and evidence

- Primary specifications were fetched from W3C (`w3.org/TR`), IETF (`rfc-editor.org`), WHATWG (`html.spec.whatwg.org`, `fetch.spec.whatwg.org`) and Microsoft OpenType (`learn.microsoft.com/typography/opentype/spec`).
- Browser versions are from MDN BCD (JSON) and caniuse feature JSON, both queried on 11 November 2026. BCD gives first supporting version; caniuse gives a current global-usage estimate.
- Numbers from the W3C PFE evaluation are simulation results from 2020. They used HTTP/2 + Brotli, did **not** use WOFF2 table transforms, and removed hinting in some runs. Treat them as directional evidence, not as benchmarks of a WOFF2/IFT production stack.
- Spec status and browser data change frequently. Re-check before publication.

---

## 3. Container and compression standards

### 3.1 WOFF2 — WOFF File Format 2.0

| Field | Value |
|---|---|
| Specification | *WOFF File Format 2.0* |
| Status / date | W3C Recommendation, **08 August 2024** |
| URL | https://www.w3.org/TR/WOFF2/ |
| Current version | https://www.w3.org/TR/2024/REC-WOFF2-20240808/ |

**What it enables.** WOFF2 is an sfnt wrapper: a 48-byte header, table directory, optional collection directory, one Brotli-compressed font-data stream, and optional metadata/private blocks. It is not a progressive format; the whole WOFF2 file must be downloaded before the font can be used.

**Transforms.** WOFF2 defines optional transforms for `glyf`, `loca` and `hmtx` tables. The `glyf` transform separates glyph substreams, uses compact point encodings, and can preserve the `OVERLAP_SIMPLE` flag via an optional `overlapSimpleBitmap`. The `loca` transform is tied to transformed `glyf`; `hmtx` can omit left-side-bearing arrays when they match `xMin`. There is **no CFF or CFF2 transform**: CFF data is Brotli-compressed as-is. The spec notes that de-subroutinizing CFF before WOFF2 encoding can improve compressed size by about 5–10%, while increasing the uncompressed CFF size by about 10%; this is an external preprocessing step, not part of WOFF2.

**CJK relevance.** WOFF2 is the correct default for CJK fonts. For `glyf`-based CJK fonts, the outline transform can help; for CFF CJK fonts (common for Japanese/Chinese commercial families), only Brotli applies. A full CJK font is still large: the PFE study measured a median CJK font of **1,834,496 bytes** raw and **768,492 bytes** as WOFF2, with a 95th percentile of about **5.52 MB** raw / **2.75 MB** WOFF2.

**Constraints.**
- Whole-file download; no partial rendering from a WOFF2 URL.
- WOFF2's `glyf`/`loca` transform is lossless in rendering but not byte-identical on decode; `DSIG` is removed by conforming encoders.
- If an IFT font is WOFF2-encoded with transformed `glyf`/`loca`, **Table Keyed** IFT patches must not modify those tables; **Glyph Keyed** patches may. This is a real implementation constraint for combining IFT with WOFF2.
- Do not serve WOFF2 with `Content-Encoding: br`; it is already Brotli-compressed.

**Browser support (BCD).** Chrome 36, Edge 14, Firefox 39, Safari 10 (Safari note: macOS 10.12+). caniuse: **97.4%** global.

---

### 3.2 WOFF1 — WOFF File Format 1.0

| Field | Value |
|---|---|
| Specification | *WOFF File Format 1.0* |
| Status / date | W3C Recommendation, **13 December 2012** |
| URL | https://www.w3.org/TR/WOFF/ |

**What it enables.** An sfnt wrapper with per-table zlib/DEFLATE compression, optional metadata and private blocks. No outline transforms and no Brotli. It reduced font transfer sizes compared with raw sfnt, but is superseded by WOFF2.

**CJK relevance.** Only a legacy fallback. For large CJK fonts, WOFF2's Brotli plus `glyf` transform is materially better; WOFF1 should not be the primary format in a new delivery method.

**Browser support (BCD).** Chrome 6, Edge 12, Firefox 3.5, IE 9, Safari 5.1. caniuse: **97.57%** global (slightly higher than WOFF2 because of old browsers).

---

### 3.3 OpenType 1.9.1 — the underlying font format

| Field | Value |
|---|---|
| Specification | *OpenType font file*, version **1.9.1** (Microsoft) |
| Status / date | Vendor specification; overview page dated **29 May 2024**; COLR page dated **30 May 2024** |
| URL | https://learn.microsoft.com/en-us/typography/opentype/spec/otff |
| COLR page | https://learn.microsoft.com/en-us/typography/opentype/spec/colr |

OpenType is not a W3C/IETF standard. It is the sfnt-based font format that browsers and operating systems implement. Relevant pieces:

**Outlines.**
- `glyf` + `loca`: TrueType quadratic outlines. These are the tables WOFF2 can transform.
- `CFF `: Compact Font Format 1.0, cubic PostScript outlines, often subroutinized.
- `CFF2`: Compact Font Format 2.0, used for variable PostScript outlines. WOFF2 does not transform CFF/CFF2.

**Variable fonts.** OpenType variations use `fvar` (axes), `gvar` (TrueType glyph deltas), `avar`, `HVAR`/`MVAR`/`VVAR`, and `STAT`. CFF2 carries variation data for PostScript outlines. The OpenType overview explicitly notes that a variable font is functionally equivalent to multiple non-variable fonts, and that variable fonts need not be in a collection. For CJK, a full variable font can be very large; subsetting/instancing is usually necessary.

**COLRv1.** The COLR table defines color glyphs using layered glyph compositions. Version 0 supports solid-color layers; **version 1 adds gradient fills, affine transforms, compositing/blending, and variation-aware paint tables**. The spec describes COLRv1 as supporting “gradient fills … as well as more complex fills using other graphic operations, including affine transformations and various blending modes.” It is more compact than bitmap/SVG color approaches for large repertoires, but Safari does not support COLRv1 per current BCD/caniuse data.

**Collections.** TTC/OTC files can share tables across faces; the OpenType spec gives the example of Japanese fonts that share identical kanji designs but have different kana designs. This can reduce package size, but web delivery usually selects one face, and browser support for loading TTC/OTC directly via `@font-face` is not uniform **[uncertain]**.

**CJK relevance.** The format choice drives compressibility: `glyf` CJK fonts can use WOFF2's outline transform; CFF/CFF2 fonts rely on Brotli and possibly de-subroutinization. Variable CJK fonts can replace multiple weight files but are large; subset before delivery. COLRv1 is a progressive enhancement for color glyphs, not a baseline requirement.

**Browser support.** Variable font `format("variations")`: Chrome 66, Edge 17, Firefox 62, Safari 11 (BCD). CFF2 support is part of modern OpenType engines but is not separately tracked in BCD **[uncertain]**; test target browsers. COLRv1: Chrome 98, Firefox 107, Safari **no**; caniuse **81.07%**.

---

### 3.4 Brotli — RFC 7932

| Field | Value |
|---|---|
| Specification | *Brotli Compressed Data Format* |
| Status / date | IETF **Informational**, July 2016 |
| URL | https://www.rfc-editor.org/rfc/rfc7932.html |

**What it enables.** A lossless compression format combining LZ77, Huffman coding and a built-in static dictionary. The sliding window is a power of two minus 16, from 1 KiB − 16 B up to **16 MiB − 16 B**. The static dictionary is a fixed word list with word transformations; it is not a CJK-specific dictionary, so CJK text/font binary data should not be expected to get special dictionary gains.

**CJK relevance.** Brotli is the compression engine inside WOFF2 and the `br` HTTP content coding. For raw TTF/OTF, `Content-Encoding: br` can reduce transfer, but WOFF2 is usually better because it also applies font-aware transforms and avoids double compression. For already-WOFF2 resources, `br` is redundant.

**Constraints.** RFC 7932 is Informational, not Standards Track, but `br` is universally implemented in current browsers. Compression is only as good as the window and dictionary; a 16 MiB window cannot exploit long-range matches beyond that, and the whole resource still has to be decompressed before use (unless the browser supports incremental decoding, which is not a font-level API).

**Browser support.** caniuse `br`: **97.37%** global.

---

### 3.5 Shared Brotli (RFC 9841) and Compression Dictionary Transport (RFC 9842)

#### Shared Brotli

| Field | Value |
|---|---|
| Specification | *Shared Brotli Compressed Data Format* |
| Status / date | IETF **Informational**, September 2025; **updates RFC 7932** |
| URL | https://www.rfc-editor.org/rfc/rfc9841.html |

Shared Brotli adds shared dictionaries, large-window support and a container format to Brotli. It is the underlying data format for `dcb`. It is not directly exposed to web authors as a font format; its practical web use is through Compression Dictionary Transport.

#### Compression Dictionary Transport

| Field | Value |
|---|---|
| Specification | *Compression Dictionary Transport* |
| Status / date | IETF **Standards Track**, September 2025 |
| URL | https://www.rfc-editor.org/rfc/rfc9842.html |

**What it enables.** An HTTP response can be designated as a compression dictionary for future responses. The server sends `Use-As-Dictionary: match="…"`; the client later sends `Available-Dictionary: :<SHA-256>:`, and the server can respond with `Content-Encoding: dcb` or `dcz`. A `Link: <…>; rel="compression-dictionary"` relation can prefetch a dictionary.

**`dcb` — Dictionary-Compressed Brotli.**
- 36-byte fixed header: 4-byte magic `0xff 0x44 0x43 0x42` + 32-byte SHA-256 of the dictionary.
- Shared Brotli stream using the external dictionary as a prefix dictionary.
- Compression window **at most 16 MB**; clients announcing `dcb` must decompress up to a 16 MB window.
- The full dictionary is available during compression/decompression **independent of the compression window**, so delta compression can work for resources larger than 16 MB.

**`dcz` — Dictionary-Compressed Zstandard.**
- 40-byte fixed header: 8-byte magic + 32-byte SHA-256.
- Zstandard stream with a raw external dictionary.
- Clients must support a window of at least **8 MB or 1.25× the dictionary size, whichever is greater, up to 128 MB**.

**Negotiation and constraints.**
- The dictionary and response must be same-origin, or cross-origin with a successful CORS check.
- Compression dictionary transport **MUST only be used in secure contexts (HTTPS)**.
- Cacheable responses **MUST** include `Vary: accept-encoding, available-dictionary`.
- Dictionaries are treated like cookies for storage/partitioning/privacy; they can become a tracking vector if abused.
- The dictionary must be fetched and cached before it can help; first visits get no benefit.

**CJK relevance.** A large CJK font version can serve as a dictionary for a later version, or a common glyph-outline blob can be shared across several font files on the same origin. This is attractive for versioned CJK families and font CDNs, but only Chromium currently implements it by default. It compresses HTTP responses, not font tables; it does not replace WOFF2.

**Browser support (BCD).** `Link rel=compression-dictionary`: Chrome **130**, Edge **130** (Chromium mirror), Firefox **145+ behind the `network.http.dictionaries.enable` preference**, Safari **no**. Treat cross-browser support as experimental.

---

## 4. Progressive / incremental delivery

### 4.1 PFE — Progressive Font Enrichment evaluation (history)

| Field | Value |
|---|---|
| Specification | *Progressive Font Enrichment: Evaluation Report* |
| Status / date | W3C **Working Group Note**, **15 October 2020** |
| URL | https://www.w3.org/TR/PFE-evaluation/ |

**What it was.** PFE was the W3C Web Fonts WG's investigation into serving only the parts of a font a page needs, without breaking layout. The report evaluated two server-assisted methods against whole-font WOFF2 and `unicode-range` subsetting:

1. **Patch Subset** — the client requests a font for a set of codepoints; the server sends a Brotli-compressed font, then later sends Brotli binary patches as more codepoints are needed. This requires an intelligent server that can subset all OpenType tables without breaking layout and retain the compression dictionary.
2. **Range Request** — the client downloads a preprocessed font with glyph outlines moved to the end (composites flattened, CFF de-subroutinized), then requests table/glyph byte ranges with HTTP/2 `Range` requests. Any standard server can serve the bytes, but the font must be preprocessed and glyph outlines must be independent.

**CJK results (simulation, 2020).**

| Method | Median byte reduction, CJK | Page-load cost result |
|---|---:|---|
| Patch Subset | **~90%** (65% on 2G) | Median **55% improvement on 3G**; improvement on 4G+; regression on 2G |
| Range Request | **~80%** (80% on 2G) | Improvement on 4G+; **regression on 3G and 2G** |
| `unicode-range` | **~50%** | Improvement on 4G+; regression on 3G and 2G |

**Other script results.** For alphabetic languages, Patch Subset saved ~50% of bytes, `unicode-range` ~43%, Range Request ~21%; Range Request consistently worsened page-load cost, and on 2G whole-font WOFF2 was best. For Arabic/Indic shaping languages, Patch Subset saved ~55% of bytes but Range Request was consistently slower; on 2G the whole font was best.

**Why it matters.** PFE is the empirical basis for the claim that CJK fonts benefit disproportionately from incremental delivery: the glyph outlines dominate the file, so fetching only needed outlines can remove most bytes. It is also the evidence that **`unicode-range` alone is not enough**: splitting a font into ranges can break kerning, ligatures and other layout rules that cross subset boundaries.

**Caveats.**
- PFE is a **WG Note**, not a standard. “Patch Subset” is a research method, not the current IFT wire format.
- The simulations used HTTP/2 + Brotli, not WOFF2 transforms; hinting was removed in some runs; results are not directly comparable to a modern WOFF2/IFT deployment.
- The cost model assumed a 3.5 s “too slow” threshold and a 400 ms “too fast” floor. Different networks/content can change the crossover points.
- On 2G, every progressive method regressed versus whole-font WOFF2 in the median; the fixed cost of extra round trips dominated.

---

### 4.2 IFT — Incremental Font Transfer

| Field | Value |
|---|---|
| Specification | *Incremental Font Transfer* |
| Status / date | W3C **Candidate Recommendation Draft**, **13 October 2026** |
| URL | https://www.w3.org/TR/IFT/ |
| Browser status | Chromium **Proposed** (chromestatus feature 5135917565214720, created 15 Apr 2026, updated 28 Apr 2026); Firefox **No signal**; Safari **No signal** |

**What it enables.** The client starts with a small subset and downloads patches as new text appears. The spec explicitly positions IFT as an improvement over `unicode-range` because it can retain layout rules across increments:

> “Incremental transfer improves on unicode-range by avoiding damage to layout (kerning, ligatures, etc) rules, meaning it can efficiently support fine grained increments to latin and to complex scripts like Indic or Arabic.”

**Architecture.**
- The initial font contains an **IFT table** (or IFTX extension) with a patch map: subset definitions → patch URLs, patch formats and invalidation modes.
- The client runs an extension algorithm: it determines the required codepoints/layout features/design space, selects patches, fetches them (possibly in parallel), and applies them to the current subset.
- The spec recommends an HTTP server capable of multiplexing (HTTP/2 or HTTP/3) because multiple patches are commonly fetched in parallel.
- Patch fetches use Fetch with the same CORS settings as the initial font; cross-origin patch URLs require the host to opt in with appropriate access-control headers.
- IFT fonts are subject to the same per-origin restriction as ordinary web fonts; a font must not be accessible to another document/origin.

**Patch formats.**

| Format | What it does | Invalidation / limits |
|---|---|---|
| **Table Keyed** (§6.2) | A collection of Brotli-encoded binary diffs against individual font tables. Can patch any table. | At least partially invalidating; patch graph can grow exponentially with the number of segments; good when non-outline data is sizable and few patches suffice. |
| **Glyph Keyed** (§6.3) | Opaque blobs each associated with a glyph ID and a table. Can encode `glyf`/`loca`, `gvar`, `CFF`, `CFF2`. | No invalidation; number of patches scales linearly with segments; limited to outline/variation data. Best when glyph outlines dominate. |

The spec recommends mixing them: use Table Keyed for non-outline tables with a small number of large segments, and Glyph Keyed for fine-grained glyph data. It explicitly notes that Glyph Keyed is the best fit for many CJK fonts because most of their bytes are glyph outlines.

**Constraints and risks.**
- **No shipping browser**: as of 11 Nov 2026 Chromium is “Proposed”, not enabled by default; Firefox and Safari have no signal. A production service must ship a whole-font fallback.
- **Encoder/server complexity**: the server must segment the font, generate patches, host a patch map, and preserve layout behavior. The spec devotes substantial text to encoder correctness and cache efficiency.
- **Patch graph/cache efficiency**: many segments mean many possible patch paths and lower CDN cache hit rates; the spec recommends limiting the number of segments and keeping default layout features in the base subset.
- **WOFF2 interaction**: if the IFT font is WOFF2 with transformed `glyf`/`loca`, Table Keyed patches must not modify those tables; Glyph Keyed patches can.
- **Privacy**: patch conditions can leak information about which characters a page uses; the spec recommends minimum group sizes (roughly 4–7) for privacy-sensitive encodings, and per-origin isolation.
- **2G/latency**: like PFE, many patch requests can lose to a single whole-font download on high-latency networks.

**CJK fit.** IFT is the most promising standards-track direction for CJK: Glyph Keyed patches match outline-dominated files, and the spec cites the PFE result that CJK fonts see large savings. But the absence of browser support makes it a prototype/PoC technology, not a baseline.

---

### 4.3 Range-request streaming vs. IFT

| Aspect | PFE Range Request | IFT |
|---|---|---|
| Standard status | Research method in a 2020 WG Note | W3C CRD, 2026 |
| Browser support | No mainstream `@font-face` implementation | No shipping browser |
| Server requirement | Any static server with byte ranges; font must be preprocessed | IFT-aware encoder/server and patch map |
| Granularity | Table/glyph byte ranges; glyph outlines moved to end | Table-level or glyph-level patches |
| Layout safety | Preserves tables; outlines independent after preprocessing | Designed to preserve layout rules across patches |
| Main weakness | Many small requests; no cross-request compression; preprocessing can enlarge font; 3G/2G regressions | Encoder complexity; patch graph/cache; no browser support |

For a new CJK method, Range Request is useful as an **HTTP-level primitive** (and is supported by static servers), but it is not a transparent browser font-delivery mechanism. IFT is the standardized evolution, but it is not deployable yet.

---

## 5. CSS font loading and rendering

### 5.1 CSS Fonts 4

| Field | Value |
|---|---|
| Specification | *CSS Fonts Module Level 4* |
| Status / date | W3C **Working Draft**, **04 November 2026** |
| URL | https://www.w3.org/TR/css-fonts-4/ |

Despite WD status, the core features are widely implemented. Relevant sections:

**`unicode-range` (§4.5).** Defines the codepoints a face may be used for; the union is a **hint** for whether to download a font for a text run. It is not a guarantee that the font contains every glyph; the effective character map is the intersection with the font's `cmap`. Multiple `@font-face` rules with different ranges create a composite face. For CJK, this is the standard way to split by script/block (e.g. Japanese kana/kanji, Chinese simplified/traditional, Korean Hangul), but over-splitting can break layout rules that cross boundaries.

**`font-display` (§4.9).** Controls the block/swap/failure timeline:

| Value | Behavior (CSS Fonts 4) | CJK practical effect |
|---|---|---|
| `auto` | UA-defined; many browsers behave similarly to `block` | Unpredictable; avoid for critical CJK text. |
| `block` | Short block period (3 s recommended), infinite swap period; invisible text until font loads | Can hide CJK text for seconds on slow networks. Use only for small, essential text. |
| `swap` | Extremely small block period (100 ms or less), infinite swap period; fallback immediately, swap when ready | FOUT; large metric differences can cause severe reflow. Pair with metric-matched fallback. |
| `fallback` | 100 ms or less block, short swap period (3 s recommended); fallback after that | Good compromise for body text; limits how long the font can displace fallback. |
| `optional` | If not available immediately, treat as expired; may never use the font; **must never** cause layout jump | Best for decorative CJK; avoids CLS but may never show the intended face. |

**CORS font fetching (§4.8.2).** Fonts are fetched with destination `"font"` and CORS mode `"cors"`. The spec notes: “fonts will typically not be loaded cross-origin unless authors specifically take steps to permit cross-origin loads.” Cross-origin font CDNs must send `Access-Control-Allow-Origin`. A preload for a font must use the same CORS mode (`crossorigin`) or the browser may fetch twice.

**Privacy (§15).** The spec warns that pairing `unicode-range` with distinct `src` URLs lets a third party infer which characters a page uses — a serious issue for large CJK repertoires:

> “careful pairing of unicode-range and distinct src urls allows the third-party to see which characters are used on a page, which is a privacy risk for large character repertoire scripts such as CJK.”

**Browser support (BCD).** `unicode-range`: Chrome 1, Edge 12, Firefox 36, IE 9, Safari 3.1; caniuse 97.4%. `font-display`: Chrome 60, Firefox 58, Safari 11.1.

---

### 5.2 CSS Fonts 5 — `size-adjust` and metric matching

| Field | Value |
|---|---|
| Specification | *CSS Fonts Module Level 5* |
| Status / date | W3C **Working Draft**, **04 November 2026** |
| URL | https://www.w3.org/TR/css-fonts-5/ |

**`size-adjust` descriptor (§4.4).** Defines a multiplier for glyph outlines and all metrics associated with the font, so different fonts can be harmonized at the same `font-size`. It scales glyph advances, baseline tables, and descriptor overrides, and therefore affects `ex`/`ch` units, but does **not** change the computed `font-size` (and thus `em` units). This is the most direct CSS tool for reducing CJK fallback/webfont metric mismatch.

**`font-size-adjust` (§3.4).** In Fonts 5 it can normalize a chosen metric (e.g. ex-height) rather than only a single aspect value. It is related to `size-adjust` but operates via the used font size.

**Support (BCD).** `size-adjust`: Chrome 92, Firefox 92, Safari 17; Opera Android not supported. `ascent-override`/`descent-override`/`line-gap-override` have narrower Safari support (BCD lists Safari “preview”), so test before relying on them for cross-browser CLS control. Note: `size-adjust` is a **CSS Fonts 5** feature, not CSS Fonts 4.

**CJK relevance.** CJK fallback fonts often have very different vertical metrics and glyph widths from the webfont. `size-adjust` can bring the fallback's apparent size closer, reducing reflow when `font-display: swap/fallback` eventually swaps. It does not reduce download size.

---

### 5.3 Practical CSS pattern

A conservative, production-safe CJK pattern:

```css
@font-face {
  font-family: "CJK Web";
  src: url("/fonts/cjk-subset.woff2") format("woff2");
  font-weight: 400;
  font-style: normal;
  font-display: swap;          /* or fallback for body text */
  unicode-range: U+3000-30FF, U+4E00-9FFF, U+FF00-FFEF;
  size-adjust: 100%;           /* tune against the fallback */
}

/* Optional early fetch; must match CORS mode. */
<link rel="preload"
      href="/fonts/cjk-subset.woff2"
      as="font"
      type="font/woff2"
      crossorigin>
```

For critical above-the-fold CJK text, consider `font-display: fallback` plus a metric-matched local fallback; for decorative text, `optional`. Do not preload every `unicode-range` subset — that defeats subsetting.

---

## 6. HTTP delivery standards

### 6.1 RFC 8081 — the `font` top-level media type

| Field | Value |
|---|---|
| Specification | *The “font” Top-Level Media Type* |
| Status / date | IETF **Standards Track**, February 2017 |
| URL | https://www.rfc-editor.org/rfc/rfc8081.html |

Registers `font/woff`, `font/woff2`, `font/ttf`, `font/otf`, `font/collection`, and `font/sfnt`. `application/font-woff` is deprecated in favor of `font/woff`. For CJK collections, `font/collection` is the correct type for TTC/OTC, though browser `@font-face` handling of collections is not uniform **[uncertain]**.

**Why it matters.** Correct MIME types let CDNs/browsers handle font responses consistently, enable proper caching and compression decisions, and avoid `application/octet-stream` fallbacks. The media type itself does not compress anything.

---

### 6.2 RFC 9110 — Range requests

| Field | Value |
|---|---|
| Specification | *HTTP Semantics* (STD 97) |
| Status / date | IETF **Internet Standard**, June 2022 |
| URL | https://www.rfc-editor.org/rfc/rfc9110.html |

Defines byte-range requests (`Range`, `Content-Range`, `206 Partial Content`, `If-Range`). A server **MAY** ignore `Range`, but origin servers and caches “ought to support byte ranges when possible” because they enable partial retrieval and recovery. For static font files, range support is common; for dynamically generated/patch responses, it may not be.

**CJK relevance.** Range requests are the transport primitive behind the PFE Range Request method: fetch the table directory, then request only the needed glyph-outline byte ranges. They are also useful for resumable downloads of large CJK fonts. But HTTP range support alone does not make a browser load a font progressively; the font engine must know how to assemble the pieces.

**Constraints.** Many small ranges cost round trips; range responses may not be compressed as a single stream; caches may store 206 responses only as incomplete 200s; and servers may ignore ranges. Range requests are best for large, static, preprocessed files, not for fine-grained per-glyph fetching on high-latency networks.

---

### 6.3 RFC 9111 — HTTP caching

| Field | Value |
|---|---|
| Specification | *HTTP Caching* (STD 98) |
| Status / date | IETF **Internet Standard**, June 2022 |
| URL | https://www.rfc-editor.org/rfc/rfc9111.html |

Caching rules for fresh/stale responses, validators, `Vary`, and partial content. A 206 response may be stored as an incomplete 200; a cache may combine ranges if they share the same strong validator, and must not serve an incomplete response as complete.

**CJK relevance.** Large font files and many subset/patch URLs need aggressive caching. Use content-hashed, immutable URLs with long `max-age`; use strong `ETag`/`Last-Modified` if ranges or patches are involved. For dictionary-compressed responses, `Vary: accept-encoding, available-dictionary` is mandatory. CDNs may handle 206/range caching differently; test the actual edge behavior.

**Constraint.** A cache is allowed to not store partial responses; range-based schemes cannot assume every intermediary will cache fragments. Patch URLs should be individually cacheable and immutable.

---

### 6.4 HTTP/2 and HTTP/3

| Field | Value |
|---|---|
| HTTP/2 | RFC 9113, Standards Track, June 2022, https://www.rfc-editor.org/rfc/rfc9113.html |
| HTTP/3 | RFC 9114, Standards Track, June 2022, https://www.rfc-editor.org/rfc/rfc9114.html |

HTTP/2 adds binary framing, multiplexed streams, header compression (HPACK), and flow control. HTTP/3 maps HTTP semantics onto QUIC, with stream multiplexing, per-stream flow control, and lower connection-establishment latency; it avoids TCP head-of-line blocking.

**CJK relevance.** IFT explicitly recommends a multiplexing server (HTTP/2 or HTTP/3) because multiple patches are often fetched in parallel. Multiplexing reduces the cost of concurrent subset/patch requests, but it does not eliminate round-trip latency or the fixed cost of many small requests. HTTP/3 can help on lossy mobile networks.

**Constraints.** Server push is not a dependable font-delivery mechanism (Chrome removed HTTP/2 push; HTTP/3 has no push). Prioritization is a hint, not a guarantee. HTTP/2 support is ~97.4%, HTTP/3 ~94.96% (caniuse), so HTTP/2 is the safer baseline; HTTP/3 is a progressive optimization.

---

### 6.5 RFC 9218 — Extensible Prioritization Scheme

| Field | Value |
|---|---|
| Specification | *Extensible Prioritization Scheme for HTTP* |
| Status / date | IETF **Standards Track**, June 2022 |
| URL | https://www.rfc-editor.org/rfc/rfc9218.html |

Defines the `Priority` header and HTTP/2/HTTP/3 frames with `urgency` (0–7, default 3; lower is more urgent) and `incremental` (Boolean). It lets clients express relative response precedence and whether a response can be processed incrementally.

**CJK relevance.** The initial font or above-the-fold subset should be more urgent than background patches or prefetches; patch streams can be marked appropriately. But browser/server support and actual scheduling vary, and fonts are usually already high priority because they block text rendering. Treat RFC 9218 as an optimization hint, not a control plane.

---

### 6.6 `Link: rel=preload` and 103 Early Hints

**`rel=preload`.** Defined in the WHATWG HTML Living Standard (last updated 11 November 2026), link type “preload”: the UA preemptively fetches and caches a resource according to `as` and `fetchpriority`. For fonts, use `as="font"`, `type="font/woff2"`, and `crossorigin` (to match the CORS font fetch). Browser support for `<link rel=preload as=font>` (BCD): Chrome 50, Firefox 85, Safari 11.1.

**HTTP `Link` header.** HTML defines “process a link header” and applies link types to `Link` headers, so `Link: </font.woff2>; rel=preload; as=font; crossorigin` is specified. Browser support for the header form is less consistently documented than the element form **[uncertain]**; test Safari in particular. Prefer the HTML element where the document is available, and use 103/`Link` only as an optimization.

**103 Early Hints (RFC 8297).** Experimental, December 2017: an informational response can carry header fields (typically `Link: rel=preload`) before the final response; the client may speculatively fetch while waiting. BCD support: Chrome 103, Firefox 120, Safari 17 for the status code, **but** 103 **preload** support is Chrome 103, Firefox 123, **Safari no**. Chrome/Safari BCD notes say 103 is supported in HTTP/2 and later only.

**CJK relevance.** Early preload can hide some of the latency of a large font, but preloading a full CJK font can waste bandwidth if the page only needs a subset. Preload the exact initial subset/IFT resource, not every unicode-range file. 103 is useful when the server can emit hints before the HTML body; it is not a substitute for reducing bytes.

---

## 7. Browser support summary

Checked 11 November 2026. “BCD” = first version in MDN browser-compat-data; “caniuse” = global usage estimate.

| Feature | Chrome | Edge | Firefox | Safari | caniuse global | Source |
|---|---:|---:|---:|---:|---:|---|
| WOFF2 | 36 | 14 | 39 | 10 | 97.4% | BCD / caniuse |
| WOFF1 | 6 | 12 | 3.5 | 5.1 | 97.57% | BCD / caniuse |
| `unicode-range` | 1 | 12 | 36 | 3.1 | 97.4% | BCD / caniuse |
| `font-display` | 60 | 12 (mirror) | 58 | 11.1 | — | BCD |
| `size-adjust` | 92 | 92 (mirror) | 92 | 17 | — | BCD |
| Variable font `format("variations")` | 66 | 17 | 62 | 11 | — | BCD |
| COLRv1 | 98 | 98 (mirror) | 107 | **no** | 81.07% | BCD / caniuse |
| `<link rel=preload as=font>` | 50 | 79 (Blink) | 85 | 11.1 | 97.36% | BCD |
| 103 status | 103 | 103 (mirror) | 120 | 17 | — | BCD |
| 103 + preload | 103 | 103 (mirror) | 123 | **no** | — | BCD |
| `Link rel=compression-dictionary` | 130 | 130 | 145 (pref) | **no** | — | BCD |
| HTTP/2 | yes | yes | yes | yes | 97.4% | caniuse |
| HTTP/3 | yes | yes | yes | yes | 94.96% | caniuse |
| Brotli (`br`) | yes | yes | yes | yes | 97.37% | caniuse |
| IFT | **no** (Proposed) | **no** | **no signal** | **no signal** | — | chromestatus |

**Notes.**
- BCD “mirror” entries inherit the Chrome version for Chromium-based browsers; Edge/Opera versions may differ slightly.
- Safari’s WOFF2 support originally required macOS 10.12+.
- COLRv1 Safari absence is consistent across BCD and caniuse; do not rely on it for cross-browser color.
- caniuse percentages are estimates and change; use them for planning, not contractual guarantees.
- IFT browser status is from Chromium’s feature tracker, not BCD/caniuse.

---

## 8. Decision guidance for a new CJK delivery method

### 8.1 Can rely on today

1. **WOFF2 as the default container.** Serve `font/woff2` with long-lived immutable caching. Use WOFF1 only as a legacy fallback.
2. **Brotli inside WOFF2.** Do not double-compress WOFF2 with `Content-Encoding: br`.
3. **`unicode-range` subsetting by script/block.** Split CJK into sensible groups (e.g. kana, common kanji, extension blocks, Hangul), but keep layout features and avoid boundaries that break kerning/ligatures. Measure with real text.
4. **`font-display`.** Use `swap`/`fallback`/`optional` deliberately; `optional` is the only value that guarantees no layout jump from the webfont. Pair with `size-adjust` where supported.
5. **Preload the exact resource** that will be used (`<link rel=preload as=font type=font/woff2 crossorigin>`), not every subset. Use 103/`Link` only as an enhancement.
6. **CORS.** Configure `Access-Control-Allow-Origin` on font CDNs; use `crossorigin` on preload to avoid double fetches.
7. **HTTP/2 (and HTTP/3 where available) + standard caching.** HTTP/2 is the safe baseline; HTTP/3 is a progressive optimization.
8. **OpenType variable fonts** where they reduce the number of files; subset/instance to control size. COLRv1 only as progressive enhancement.

### 8.2 Can prototype, but must feature-detect

1. **IFT (Glyph Keyed + Table Keyed).** Best technical fit for CJK, but no shipping browser. Prototype with Chromium’s proposed implementation if available; always serve a whole-font fallback. Measure patch count, CDN cache hit rate, and first-visit vs. repeat-visit cost.
2. **Compression Dictionary Transport (`dcb`).** Useful for versioned CJK font families on Chromium; first visit pays for the dictionary. Test `Vary`, HTTPS, same-origin/CORS, and cache partitioning. Do not make it the only path.
3. **103 Early Hints preload.** Useful in Chrome/Firefox; Safari does not act on preload in 103. Keep the final HTML preload as a fallback.
4. **Range-request streaming.** Useful at the HTTP layer for resumable/partial downloads, but not a transparent `@font-face` mechanism. If building a custom renderer/WASM client, it is an option; otherwise use IFT.

### 8.3 Cannot rely on

- IFT being available in Safari/Firefox or default Chrome.
- `dcb`/`dcz` outside Chromium (Firefox is behind a preference; Safari none).
- 103 preload in Safari.
- Consistent HTTP `Link` header preload behavior across all browsers **[uncertain]**.
- COLRv1 in Safari.
- Range-request font loading as standard browser behavior.
- HTTP/2 server push for fonts.
- A specific CFF2 support version (not separately tracked; test).

### 8.4 Suggested baseline architecture

```
HTML/CSS
  ├─ <link rel=preload as=font type=font/woff2 crossorigin> for the exact above-the-fold subset
  ├─ @font-face with WOFF2, unicode-range, font-display: swap/fallback, size-adjust
  └─ local fallback with matched metrics

CDN
  ├─ font/woff2, immutable hashed URL, long max-age
  ├─ Brotli inside WOFF2; no Content-Encoding: br on .woff2
  ├─ Access-Control-Allow-Origin for cross-origin fonts
  └─ HTTP/2 + HTTP/3, standard cache validators

Optional experiments
  ├─ IFT glyph-keyed patches (Chromium prototype; whole-font fallback)
  ├─ dcb dictionary for versioned families (Chromium; first-visit cost)
  └─ 103 Early Hints preload (Chrome/Firefox; Safari fallback)
```

---

## 9. Verbatim quotes (10)

1. **IFT — why incremental transfer beats `unicode-range`**  
   > “Incremental transfer improves on unicode-range by avoiding damage to layout (kerning, ligatures, etc) rules, meaning it can efficiently support fine grained increments to latin and to complex scripts like Indic or Arabic.”  
   — https://www.w3.org/TR/IFT/ (Abstract)

2. **IFT — glyph keyed patches and CJK**  
   > “Glyph Keyed patches are most appropriate for fonts where the vast majority of data consists of glyph outlines, which is true of many existing CJK fonts.”  
   — https://www.w3.org/TR/IFT/#font-patch-formats-summary (choosing patch formats)

3. **PFE — CJK byte savings**  
   > “Patch Subset shows the largest reduction in bytes transferred (a median improvement of 90% on all but the slowest networks, dropping to 65% on 2G).”  
   — https://www.w3.org/TR/PFE-evaluation/#analysis-cjk-bytes

4. **PFE — CJK page-load cost on 3G**  
   > “On 3G networks, Patch Subset was still providing a median improvement of 55% while Unicode Range and Range Request had shifted to a performance regression in page load times.”  
   — https://www.w3.org/TR/PFE-evaluation/#analysis-cjk-cost

5. **CSS Fonts 4 — `unicode-range` is a hint**  
   > “The union of these ranges defines the set of codepoints that serves as a hint for user agents when deciding whether or not to download a font resource for a given text run.”  
   — https://www.w3.org/TR/css-fonts-4/#unicode-range-desc

6. **CSS Fonts 4 — CJK privacy risk of `unicode-range` + distinct URLs**  
   > “careful pairing of unicode-range and distinct src urls allows the third-party to see which characters are used on a page, which is a privacy risk for large character repertoire scripts such as CJK.”  
   — https://www.w3.org/TR/css-fonts-4/#privacy

7. **CSS Fonts 4 — `font-display: swap` timing**  
   > “Gives the font face an extremely small block period (100ms or less is recommended in most cases) and an infinite swap period.”  
   — https://www.w3.org/TR/css-fonts-4/#font-display-desc

8. **WOFF2 — Brotli compression**  
   > “The compression algorithm used for both the compressed font data stream and extended metadata block is Brotli.”  
   — https://www.w3.org/TR/WOFF2/ (WOFF2 overview)

9. **RFC 9111 — caching 206 responses**  
   > “Likewise, a 206 (Partial Content) response MAY be stored as if it were an incomplete 200 (OK) response.”  
   — https://www.rfc-editor.org/rfc/rfc9111.html#section-3.3

10. **RFC 9842 — `dcb` window**  
    > “The Shared Brotli stream is created using the referenced external dictionary and a compression window that is at most 16 MB in size.”  
    — https://www.rfc-editor.org/rfc/rfc9842.html#section-4

---

## 10. Uncertainty and open questions

1. **IFT timeline.** Chromium status is “Proposed” as of April 2026; no milestone is listed. It may ship, change, or stall. Do not promise IFT availability to stakeholders.
2. **IFT + WOFF2 details.** The spec allows WOFF2-encoded IFT fonts, but the transformed `glyf`/`loca` restriction on Table Keyed patches is easy to miss. Validate encoder output with the actual implementation.
3. **HTTP `Link` header preload in Safari.** HTML specifies processing of `Link` headers, but browser behavior for font preload via the header form is not well documented in BCD. Test; prefer `<link>` where possible.
4. **TTC/OTC in `@font-face`.** `font/collection` is registered, but browser support for selecting a face from a collection in a web font load is not uniform. Test; extracting a single face is safer.
5. **CFF2 support versions.** BCD does not separately track CFF2. Modern engines support it, but validate target browsers and fallback fonts.
6. **Compression dictionary Firefox support.** BCD lists Firefox 145 behind `network.http.dictionaries.enable`; this may change. Safari has no support.
7. **COLRv1 Safari.** Current BCD/caniuse say no. Re-check; Apple may add support.
8. **caniuse percentages.** Global usage estimates, not traffic-weighted; they can overstate support in specific markets (especially older Android/iOS in CJK regions).
9. **PFE numbers.** 2020 simulations, not production measurements; network models and font corpora may not match current conditions. Re-measure with the actual CJK fonts and audiences.
10. **CDN behavior.** Range/206 caching, 103 support, `Vary` handling, and priority honoring vary by CDN. Test the actual edge, not just the origin.

---

## 11. Reference list

| Document | Status / date | URL |
|---|---|---|
| WOFF File Format 2.0 | W3C REC, 2024-08-08 | https://www.w3.org/TR/WOFF2/ |
| WOFF File Format 1.0 | W3C REC, 2012-12-13 | https://www.w3.org/TR/WOFF/ |
| OpenType 1.9.1 (overview) | Microsoft spec, 2024-05-29 | https://learn.microsoft.com/en-us/typography/opentype/spec/otff |
| OpenType COLR | Microsoft spec, 2024-05-30 | https://learn.microsoft.com/en-us/typography/opentype/spec/colr |
| Incremental Font Transfer | W3C CRD, 2026-10-13 | https://www.w3.org/TR/IFT/ |
| PFE Evaluation Report | W3C WG Note, 2020-10-15 | https://www.w3.org/TR/PFE-evaluation/ |
| CSS Fonts 4 | W3C WD, 2026-11-04 | https://www.w3.org/TR/css-fonts-4/ |
| CSS Fonts 5 | W3C WD, 2026-11-04 | https://www.w3.org/TR/css-fonts-5/ |
| Brotli | IETF Informational, 2016-07 | https://www.rfc-editor.org/rfc/rfc7932.html |
| Shared Brotli | IETF Informational, 2025-09 | https://www.rfc-editor.org/rfc/rfc9841.html |
| Compression Dictionary Transport | IETF Standards Track, 2025-09 | https://www.rfc-editor.org/rfc/rfc9842.html |
| font top-level media type | IETF Standards Track, 2017-02 | https://www.rfc-editor.org/rfc/rfc8081.html |
| HTTP Semantics (Range) | IETF STD 97, 2022-06 | https://www.rfc-editor.org/rfc/rfc9110.html |
| HTTP Caching | IETF STD 98, 2022-06 | https://www.rfc-editor.org/rfc/rfc9111.html |
| HTTP/2 | IETF Standards Track, 2022-06 | https://www.rfc-editor.org/rfc/rfc9113.html |
| HTTP/3 | IETF Standards Track, 2022-06 | https://www.rfc-editor.org/rfc/rfc9114.html |
| Extensible Prioritization Scheme | IETF Standards Track, 2022-06 | https://www.rfc-editor.org/rfc/rfc9218.html |
| 103 Early Hints | IETF Experimental, 2017-12 | https://www.rfc-editor.org/rfc/rfc8297.html |
| HTML Living Standard (`preload`) | WHATWG LS, 2026-11-11 | https://html.spec.whatwg.org/multipage/links.html#link-type-preload |
| Fetch Standard (CORS) | WHATWG LS | https://fetch.spec.whatwg.org/ |
| Chromium IFT feature | Proposed, 2026 | https://chromestatus.com/feature/5135917565214720 |
| MDN browser-compat-data | Data, queried 2026-11-11 | https://github.com/mdn/browser-compat-data |
| caniuse | Data, queried 2026-11-11 | https://caniuse.com/ |
