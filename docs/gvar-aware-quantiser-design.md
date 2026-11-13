# Design study: a gvar-aware quantiser for variable fonts

Round 4, item 4 — design only, no production code. Status: study with one
measured prototype (§6). Companion measurements: `docs/round3-2026-11-12.md`
§3 (the problem), `measure/iup_amplification.py` (the prototype),
`measure/weight_cost.py` (the prices used in §7).

## 要約 (Japanese summary)

可変フォント（variable font）をそのまま量子化すると、デフォルトウェイト
での誤差は量子化グリッドの半分（grid 8 で 4 ユニット）以下に収まるのに、
他のウェイトでは最大 138 ユニットまで誤差が増幅する（ラウンド3 §3 実測）。
原因は gvar の IUP（未参照点の補間）で、補間比率がデフォルト輪郭の座標
そのものから計算されるため、近接した参照点ペアがあると比率が悪条件に
なり、小さな丸めが大きな移動誤差に変換される。本稿はこの増幅をグリフ
単位で「証明書」として計算し、安全なグリフは独立丸め、危険なグリフだけ
を (a) 参照点ペアの共同丸め、(b) 敏感な点の明示デルタへの昇格、で処理
する共同量子化の設計を示す。誤差 bound の証明スケッチ、コストモデル、
そして実装に値するかの判定基準（§7 のバー）を定める。プロトタイプ実測
では増幅は少数のグリフに集中しており（§6）、設計の前提は支持されたが、
実装判断は §8 の条件付き結論に従う。

## 1. Summary (English)

Independent rounding of a variable font's default outline is safe at the
default weight (error ≤ grid/2 by construction) and unsafe elsewhere:
round 3 measured a worst-case point error of 138 units at wght 900
against 4 units at the default, on Noto Sans JP at grid 8, while the
*mean* error stayed ≈ 2.6 units at both weights. This study explains the
amplification mechanism (IUP interpolation ratios computed from the
quantised geometry, §3), derives a per-glyph sufficient condition
("certificate") under which independent rounding provably keeps the
rendered error ≤ ε at every weight (§4), and designs the mitigations for
glyphs that fail the certificate: joint rounding of near-degenerate
referenced pairs, and promotion of sensitive interpolated points to
explicit gvar deltas (§5). A cost model (§6) and the bar the approach
must clear to be worth implementing (§7) close the study. The verdict
(§8) is conditional: the route is promising exactly when the failing
tail is small, which the prototype (§6) checks on the real font.

## 2. What round 3 measured (the problem statement)

All figures from `docs/round3-2026-11-12.md` §3, Noto Sans JP variable
font, GLC grid 8 unless stated:

- Arm B2 ("VF-safe": quantise the default outline and the gvar deltas of
  a live variable font) shrinks the full-axis WOFF2 by only **−8.6%**
  (re-verified in round 4 from the surviving artifacts:
  <!--PROTO:b2size-->), against **−23.8%** for a static instance
  quantised at one weight.
- Error at the default weight (400): max **4 units** per coordinate —
  exactly grid/2, as guaranteed by construction.
- Error at wght 900: worst **138 units**; at wght 100: 4 units. Mean
  error ≈ **2.6 units** at every weight. Zero point-count mismatches at
  all nine weights (the quantised font instances cleanly).
- Grid 2 spot check: worst error at 900 is still **88 units** and the
  file size barely moves (~0.1%). Finer grids buy accuracy very
  inefficiently — the tail is not a "grid too coarse" problem.

Two facts drive the whole design: (i) the mean error does not grow, so
most points at most weights are fine; (ii) the worst case grows ~35× and
barely responds to a 4× finer grid, so the failure is geometric, not
statistical. §3 identifies the mechanism; §6 verifies on the real font
that the blow-up is concentrated in a small tail of glyphs.

## 3. Mechanism: why independent rounding amplifies

### 3.1 The variation model in one paragraph

A glyph's rendered outline at weight `w` is `p(w) = p⁰ + Δ(w)`, where
`p⁰` is the default outline stored in `glyf` and `Δ(w)` is interpolated
from the `gvar` table's per-tuple deltas. For most points, a tuple
stores an explicit delta. For the remaining points, the delta is
**inferred by IUP** (interpolate untouched points): on each contour, an
untouched point's movement is interpolated from the movements of the two
nearest *referenced* (explicit-delta) points flanking it — separately
per axis, with the interpolation ratio computed from the point's
**coordinates in the default outline**.

Concretely, per axis, if referenced points `r₁, r₂` have default
coordinates `x₁ ≤ x ≤ x₂` and movements `d₁, d₂`, an untouched point at
`x` moves by

```
d = d₁ + (d₂ − d₁) · t,   t = (x − x₁) / (x₂ − x₁)   (x strictly between)
```

and by the nearer endpoint's movement when `x` lies outside `[x₁, x₂]`
(the per-axis clamping is what makes IUP well-defined for arbitrary
outlines). Two properties matter: the ratio `t` is a function of the
**default geometry**, and `t` is ill-conditioned when `x₂ − x₁` is
small.

### 3.2 The two error channels

Quantisation replaces `p⁰` by `q⁰ = p⁰ + e`, `|e|∞ ≤ g/2` (grid `g`),
and rounds referenced deltas, `δ̂ = δ + η`, `|η|∞ ≤ g/2`. The rendered
error at weight `w` decomposes into:

- **Channel (b) — bounded, ≈ g.** The point's own rounding `eᵢ`, plus
  the referenced endpoints' movement errors interpolated with weights in
  `[0, 1]` (a convex combination when `x` is strictly between, so the
  interpolated error is ≤ max(|η₁|, |η₂|) ≤ g/2). Total from this
  channel: ≤ g/2 + g/2 = g in the worst case, ~g/2 typically. This is
  the channel the mean error (≈2.6 units at g=8) reflects.

- **Channel (a) — ratio perturbation, unbounded.** The renderer computes
  `t̂` from the *quantised* coordinates `x̂ = x + e`. Perturbing
  numerator and denominator of `t` by up to `g/2` each gives, for
  `|x₂ − x₁| > g`,

  ```
  |t̂ − t| ≲ g / |x₂ − x₁|        (for |t| ≤ 1)
  ```

  and the induced movement error is `|d₂ − d₁| · |t̂ − t|`. When two
  referenced points nearly coincide on an axis (`|x₂ − x₁|` of a few
  units — common where a contour folds, at sharp joins, or where two
  on-curve points stack vertically/horizontally) while their movements
  differ by hundreds of units (a stem edge that travels vs. its neighbour
  that does not), the error is `|Δd| · g / |Δx|` — arbitrarily large as
  `|Δx| → 0`. At `|Δx| ≤ g` the ratio is not even approximately
  preserved: quantisation can swap the points' order or merge them,
  changing which side of the segment a point interpolates on.

Channel (a) explains every round-3 observation: the worst case (138)
with an unmoved mean (rare geometry, huge local factor); the weak
response to grid 2 (88 — once `|Δx|` is comparable to `g`, shrinking `g`
4× does not shrink the ill-conditioning proportionally, because the
number of near-degenerate pairs at scale `g` also shrinks); and the
growth towards the axis extremes (movements `|Δd|` are largest at
wght 100/900, smallest near the default 400 — hence 4 units at 100 is
luck of small deltas there, and the design must budget for the extremes).

A secondary contributor: IUP runs **per axis**, so a point between its
referenced neighbours on x but outside them on y (or vice versa) mixes
clamped and interpolated behaviour; quantisation can flip a point across
a boundary on one axis only. This is bounded by the same certificate
machinery (the spacing term is checked per axis).

## 4. A computable certificate for independent rounding

Goal: decide, per glyph, whether independent rounding at grid `g`
provably keeps the rendered error `≤ ε` at **every** weight, with
`ε = g/2` to match the static flow's guarantee at its shipped weight.

For a glyph, consider every tuple (axis peak) that moves it, every
untouched point `i`, and each axis. Let `r₁, r₂` be its IUP referenced
neighbours on that axis at that tuple, with default spacing
`s = |x₂ − x₁|` and movement spread `D = |d₂ − d₁|` at the tuple's peak
(movements scale linearly between peaks, so the peak is the worst case
for `D`; spacing is weight-independent). From §3.2:

**Lemma (channel bounds).** If `s > g`, the rendered per-coordinate
error of point `i` at any weight is at most

```
err(i) ≤ g/2  (own)  +  g/2  (endpoint movements)  +  D · g / s  (ratio)
        = g + D·g/s.
```

*Proof sketch.* Own error: `|eᵢ| ≤ g/2`. Endpoint contribution: the
interpolated movement with perturbed endpoints is a convex combination
of `δ̂₁, δ̂₂` when the quantised ratio `t̂ ∈ [0,1]`; each `|η| ≤ g/2`, so
this term is ≤ g/2. (If `t̂` falls outside `[0,1]` the axis clamps to the
nearer endpoint — movement error still ≤ g/2, but the *clamping
decision* can differ from the unquantised one; the difference is charged
to the ratio term, since a clamp flip requires `x` within `g` of an
endpoint, where `|t̂ − t|` is again governed by `g/s`.) Ratio term:
`|t̂ − t| ≤ (g/2 · (1 + |t|)) / (s − g/2) ≤ g/s` for `|t| ≤ 1` and
`s > g` up to lower-order terms; multiplied by the movement spread `D`
gives `D·g/s`. Summing the three terms gives the bound. ∎ (Sketch: the
clamp-flip accounting and the `s ≤ g` regime are the two places a full
proof must be careful; both are handled by the mitigations in §5 rather
than by the bound.)

**Certificate.** First, an honest observation about budgets: the static
flow's `g/2` guarantee exists because a static font has only the "own"
channel. A variable font has the endpoint channel as well, so even with
a zero ratio term the worst case is `g`, and no budget below `g` can be
certified for *any* glyph with IUP points. The design therefore uses a
two-level criterion:

- **Hard certificate (provable), budget `ε_hard = 2g`** — 16 units at
  g=8, i.e. 0.8% of the 2048-unit em. By the lemma, independent rounding
  is certified for a glyph iff for every untouched point, axis and
  tuple

  ```
  D·g/s ≤ ε_hard − g = g        ⟺        D ≤ s,
  ```

  and no referenced pair has `s ≤ g` on an axis where `D > 0`. In
  words: **independent rounding is provably safe (within 2g) wherever
  no IUP interpolation amplifies movement faster than the referenced
  points spread apart** — the movement spread never exceeds the
  geometric spacing it is interpolated across.

- **Empirical target (verified), budget `ε_target = g`** — 8 units at
  g=8, twice the static per-coordinate bound. The shipped font must
  additionally *measure* within this at every sampled weight (§5.1
  step 4). The lemma is loose by a large factor in practice — round 3's
  measured mean error was 2.6 units where the lemma's constant term
  alone is g — so the certificate's job is to *find the tail cheaply*,
  and the empirical check is the operative gate. A glyph that fails the
  certificate is not necessarily broken; it is a glyph the proof cannot
  vouch for, and §5 spends bytes exactly there.

## 5. Design: joint rounding with an IUP-aware budget

### 5.1 Pipeline

1. **Certify.** For each glyph, compute the worst ratio term
   `R_G = max D·g/s` over untouched points, axes and tuples, and flag
   referenced pairs with `s ≤ g, D > 0`. Cost: O(points × tuples) from
   the stock font; no rendering.
2. **Independent-round** glyphs with `R_G ≤ ε_hard − g` (= g at
   ε_hard = 2g) and no degenerate pair. Expected: the overwhelming
   majority (§6 measures the tail on the real font).
3. **Mitigate** flagged glyphs, cheapest first (§5.2), re-certifying
   after each step.
4. **Verify empirically**: instance the quantised VF at every tuple peak
   and at axis midpoints; assert per-point error ≤ ε_target = g at all
   sampled weights and zero point-count mismatches (the round-3 harness
   already does exactly this measurement). Sampling cannot prove the
   between-peaks behaviour, but movements are piecewise-linear in `w`
   and spacings are weight-independent, so the ratio term is maximised
   at peaks — midpoints guard the implementation, peaks bound the
   theory.

### 5.2 Mitigations, in order of increasing cost

- **M1 — joint rounding of a degenerate referenced pair.** When
  `s = |x₂ − x₁|` is small, round the pair *together*: choose on-grid
  `q₁, q₂` minimising the rendered-error contribution, with a preference
  for preserving the spacing `q₂ − q₁ ≈ s` (including `q₂ − q₁ = 0`…
  no — merging changes topology of the interpolation; prefer preserving
  the sign and rounding the *midpoint* and *spacing* as a unit: spacing
  snapped to the nearest grid multiple ≥ g when `D > 0`, since
  `s ≥ g` makes `|t̂ − t| ≤ ~1` and typically ≪). The search space is
  tiny (the pair's coordinates within ±g). This fixes the geometry
  without touching gvar.
- **M2 — promotion.** Give the sensitive untouched point an explicit
  delta in the offending tuple(s), quantised like other referenced
  deltas. Its channel-(a) term vanishes identically (no ratio is
  computed for it); neighbours that interpolated *through* it now use it
  as a referenced endpoint, which can only shrink their spans' `D/s`
  (re-certify). Cost: the delta values in gvar for that point × tuples
  (see §6 for the byte model).
- **M3 — exemption.** Leave the glyph's default outline unquantised
  (full precision) and quantise only its deltas. Then `e = 0`, ratios
  are computed from exact geometry, and only channel (b)'s endpoint
  term (`≤ g/2`) survives. Cost: the glyph forfeits its glyf-side GLC
  gain. Reserve for glyphs where M1+M2 still fail certification
  (expected: none to a handful).

### 5.3 What changes vs. today's `tools/glc.py --quantize-variable`

- gvar can no longer be rounded tuple-value-by-tuple-value blindly:
  delta rounding interacts with the certificate (promotions insert new
  deltas; M1 constrains glyf rounding). The quantiser becomes a joint
  optimiser over (glyf defaults, gvar deltas) with a per-glyph budget —
  an order of magnitude more machinery than `glyphcodec`'s independent
  rounding, and it needs the instancing verifier in the loop per font.
- glyf-side behaviour for certified glyphs is unchanged, so the
  measured GLC gains on simple glyphs carry over.

## 6. Cost model and the prototype measurement

Costs of the design, per font:

- **Certificate computation**: negligible (one pass over gvar).
- **M1**: free in bytes (defaults stay on-grid); tiny search per pair.
- **M2**: each promotion stores a delta (2 coordinates) for one point in
  one tuple. In gvar's encoding, shared tuple records and IUP-based
  delta compression mean a promoted point costs roughly its packed
  delta size — order 2–4 bytes per tuple it joins. A glyph needing `p`
  promotions across `t` tuples costs ≈ `3·p·t` bytes.
- **M3**: forfeits that glyph's glyf quantisation gain (per-glyph,
  measurable with the existing pipeline).

Whether this is cheap depends entirely on the tail size, which is an
empirical question. **Prototype** (`measure/iup_amplification.py`, run
on round 3's surviving artifacts — no new quantisation): per-glyph max
outline error of the VF-safe quantised font at the default (400) vs. at
wght 900, over all simple glyphs of Noto Sans JP:

<!--PROTO:tail-->

Reading of the prototype: <!--PROTO:verdict-reading-->

## 7. The bar (from round 3 §3, priced in round 4)

A gvar-aware quantiser is worth implementing only if the shipped font
simultaneously:

1. **Error**: worst per-coordinate point error ≤ **g** (= 8 units at
   grid 8; the two-channel budget of §4) at *every* weight 100–900 —
   against B2's measured 138 — with mean error no worse than B2's
   ≈ 2.6 units, and zero point-count mismatches at all weights.
2. **Size**: one file, all weights, smaller than what a site otherwise
   ships for the weights it actually uses. Round 4's usage analysis
   (docs/round4-2026-11-13.md §2) says that is two weights for almost
   every site, so the bar is **< Arm A's {400,700} GLC total**
   (<!--PROTO:armA700-->), while covering all nine weights. B2's
   unprotected file is <!--PROTO:b2size2-->, so the protection budget —
   everything M1–M3 may cost before the route stops winning — is
   <!--PROTO:budget-->.
3. **No regressions**: glyf-side GLC gains retained on certified
   glyphs; the font instances cleanly with fontTools and renders
   identically to B2 at the default weight (same defaults for certified
   glyphs).

## 8. Verdict

<!--PROTO:verdict-->

## References

- Microsoft, *OpenType Font Variations — IUP interpolation of deltas*
  (TrueType instruction / gvar specification): the per-axis interpolation
  rule of §3.1.
- `docs/round3-2026-11-12.md` §3 — the measurements this study explains.
- `measure/variable_glc.py`, `measure/variable_glc_spotcheck.py` — the
  round-3 arms (B2 = "VF-safe") and their harness.
- `tools/glyphcodec.py` (`quantize_glyf`, `quantize_variation_data`) —
  the independent-rounding quantiser this design would replace for VFs.
