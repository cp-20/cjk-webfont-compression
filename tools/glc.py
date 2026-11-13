#!/usr/bin/env python3
"""GLC (Glyph-Level Compression) as one runnable pipeline.

Until now the GLC pipeline only existed implicitly, scattered across the
benchmark scripts in measure/ (glc_final.py, glc_sweep.py, glc_fullfont.py,
glc_fullsweep.py), each re-implementing a slightly different subset of the
stages. This tool consolidates them into a single CLI:

  GLC-0  CFF -> glyf conversion (cu2qu, error budget in % of em)
  GLC-1  CFF de-subroutinisation (WOFF2 spec section 5.4)   [subset stage]
  GLC-2  drop vertical metrics (vhea / vmtx)
  GLC-3  lossless outline canonicalisation (off by default: measured a wash)
  GLC-4  error-bounded coordinate quantisation, bbox preserved

plus the mandatory safety valve: the stock encoding (same character
coverage, no GLC stages) is produced as well, and the *smaller* of the two
files is written to the output path -- quantisation makes some fonts grow
(Nanum Gothic: +10.5 % at grid 4), so GLC must never be a regression.

The output is a plain WOFF2 file. No browser changes are required.

Examples:
    # reproduce the published headline: Noto Sans JP static 400, full font
    python tools/glc.py -i 'fonts/NotoSansJP[wght].ttf' --instance wght=400 \
        --epsilon 0.4 -o noto400-glc.woff2

    # CFF font, 3,000-character subset from a text file, all stages
    python tools/glc.py -i fonts/SourceHanSansJP-Regular.otf \
        --subset-file page.txt --epsilon 0.4 -o han-glc.woff2

    # explicit quantisation grid instead of an epsilon
    python tools/glc.py -i fonts/MPLUS1p-Regular.ttf --grid 8 -o mplus.woff2

Variable fonts: the recommended flow is --instance per weight you ship
(each instance keeps the GLC-4 guarantee, error <= grid/2 everywhere).
--quantize-variable instead quantises the default outlines in place and
keeps gvar -- one file for all weights, measurably smaller than stock
(Noto Sans JP: -8.6 % at grid 8), but the guarantee does NOT survive:
gvar's IUP interpolation of untouched points amplifies the perturbation
away from the default weight (max point error 4 units at wght=100 but
138 units at wght=900, grid 8; mean error stays ~2.6 units). See
measure/variable_glc.py and docs/round3-2026-11-12.md before using it.

--quantize-variable-protected adds M3 tail exemption (design study
docs/gvar-aware-quantiser-design.md §5/§8, implemented in round 5):
it builds the unprotected quantised font, instances it at the fvar
peaks, exempts every glyph whose interpolated error exceeds 2*grid,
rebuilds, and re-measures until the bound holds (max 3 rounds). On
Noto Sans JP at grid 8: 231 of 17,932 glyphs (1.3 %) exempted, peak
max error 138 -> 16 units (wght=900; 77 -> 11 at wght=500, 4 at the
wght=100 default), for +8,744 B (+0.22 %) over the unprotected file
(3,974,768 B vs 3,966,024 B; -8.6 % vs the 4,350,080 B stock WOFF2).
The protected single file still loses on size to the two static
instances real pages need (Arm A {400,700}: 3,544,244 B), so it only
wins for >= 3-weight delivery; --instance per weight remains the
recommended flow.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cff2glyf import cff_to_glyf  # noqa: E402
from glyphcodec import (process_font, process_variable_font,  # noqa: E402
                        vf_glyph_errors_at, vf_sample_locations)

CFF_ERR_RATIO = 0.001  # GLC-0 budget: 0.1 % of em, as published


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{r.stderr[-800:]}")


def woff2_encode(src: Path, dst: Path) -> int:
    run([sys.executable, "-m", "fontTools.ttLib.woff2", "compress",
         str(src), "-o", str(dst)])
    return dst.stat().st_size


def subset_font(src: Path, dst: Path, unicodes: list[int] | None,
                desubroutinize: bool) -> None:
    """Subset with the same options the published measurements used."""
    cmd = [sys.executable, "-m", "fontTools.subset", str(src),
           "--no-hinting", "--layout-features=*",
           "--name-IDs=1,2,3,4,5,6", "--name-languages=*",
           "--notdef-outline", "--recalc-bounds",
           f"--output-file={dst}"]
    if unicodes is not None:
        cmd.insert(3, "--unicodes=" + ",".join(f"U+{c:04X}" for c in unicodes))
    if desubroutinize:
        cmd.append("--desubroutinize")
    run(cmd)


from fontTools.ttLib import TTFont  # noqa: E402


def font_info(path: Path) -> dict:
    f = TTFont(str(path), lazy=True)
    info = {"upm": f["head"].unitsPerEm,
            "cff": "CFF " in f or "CFF2" in f,
            "variable": "fvar" in f,
            "glyphs": f["maxp"].numGlyphs}
    f.close()
    return info


def loc_label(loc: dict) -> str:
    return ",".join(f"{k}={v:g}" for k, v in sorted(loc.items()))


def measure_vf_errors(stock: Path, quant: Path, locations: list[dict]):
    """Worst per-glyph error of `quant` vs `stock` over all locations.

    Returns (per_glyph_max, rows, mismatches): rows has one entry per
    location with that location's max error; mismatches is the total
    point-count mismatch count over locations (must stay 0).
    """
    per_glyph: dict[str, float] = {}
    rows = []
    mismatches = 0
    for loc in locations:
        errs, mm = vf_glyph_errors_at(str(stock), str(quant), loc)
        mismatches += mm
        rows.append({"location": loc_label(loc),
                     "max_error_units": max(errs.values(), default=0)})
        for name, e in errs.items():
            if e > per_glyph.get(name, 0):
                per_glyph[name] = e
    return per_glyph, rows, mismatches


def process_variable_font_protected(src: Path, dst: Path, grid: int,
                                    drop_vertical: bool, work: Path) -> dict:
    """--quantize-variable plus M3 tail exemption (design study §5/§8).

    Build the unprotected quantised font, instance it at the fvar peaks
    (vf_sample_locations) against the stock font, exempt every glyph
    whose interpolated error exceeds the bound 2*grid, rebuild, and
    verify. Exempt glyphs keep their exact default outlines, so their
    own error collapses to ~0 and no other glyph's error changes; the
    verify pass re-measures everything anyway and the loop repeats
    (max 3 rounds) if anything still exceeds the bound.
    """
    bound = 2 * grid
    stock_font = TTFont(str(src))
    locations = vf_sample_locations(stock_font)
    stock_font.close()

    unprot = work / "vf_unprotected.ttf"
    stats = process_variable_font(str(src), str(unprot), grid=grid,
                                  drop_vertical=drop_vertical)
    unprot_bytes = woff2_encode(unprot, work / "vf_unprotected.woff2")
    per_glyph, rows_before, mm_before = measure_vf_errors(src, unprot, locations)

    exempt: set[str] = set()
    cur_ttf, cur_stats = unprot, stats
    rows_after = rows_before
    mm_after = mm_before
    for _ in range(3):
        new = {g for g, e in per_glyph.items() if e > bound}
        if not new - exempt:
            break
        exempt |= new
        cur_ttf = work / "vf_protected.ttf"
        cur_stats = process_variable_font(str(src), str(cur_ttf), grid=grid,
                                          drop_vertical=drop_vertical,
                                          exempt=exempt)
        per_glyph, rows_after, mm_after = measure_vf_errors(src, cur_ttf,
                                                            locations)
    shutil.copyfile(cur_ttf, dst)
    prot_bytes = woff2_encode(cur_ttf, work / "vf_protected.woff2")
    worst_after = max((r["max_error_units"] for r in rows_after), default=0)
    return {
        **cur_stats,
        "protected": True,
        "bound_units": bound,
        "exempt_glyphs": len(exempt),
        "sample_locations": [r["location"] for r in rows_after],
        "max_error_before": {r["location"]: r["max_error_units"]
                             for r in rows_before},
        "max_error_after": {r["location"]: r["max_error_units"]
                            for r in rows_after},
        "worst_max_error_after_units": worst_after,
        "bound_met": worst_after <= bound,
        "point_count_mismatches_before": mm_before,
        "point_count_mismatches_after": mm_after,
        "unprotected_woff2_bytes": unprot_bytes,
        "protected_woff2_bytes": prot_bytes,
    }


def arm_a_reference(src: Path, grid: int, keep_vertical: bool,
                    work: Path) -> dict | None:
    """Arm A reference price: GLC instances at wght 400 + 700, summed.

    The published recommendation (round 4) is instancing {400, 700};
    the protected single file is only worth its size if it competes
    with that bundle. Returns None for fonts without a wght axis.
    Mirrors this CLI's own --instance flow (instance -> drop vertical
    -> process_font -> WOFF2).
    """
    f = TTFont(str(src), lazy=True)
    if "fvar" not in f:
        f.close()
        return None
    axes = list(f["fvar"].axes)
    axis = next((a for a in axes if a.axisTag == "wght"), None)
    f.close()
    if axis is None:
        return None
    weights = sorted({min(max(w, axis.minValue), axis.maxValue)
                      for w in (400.0, 700.0)})
    total = 0
    per = {}
    for w in weights:
        inst = work / f"arma_{w:g}.ttf"
        # Pin every axis (others at their defaults): pinning wght alone
        # would leave a multi-axis font variable, and the "instance"
        # price would not be a static instance's price.
        pins = [f"{a.axisTag}={(w if a.axisTag == 'wght'
                                else a.defaultValue):g}" for a in axes]
        run([sys.executable, "-m", "fontTools.varLib.instancer", str(src),
             *pins, "-o", str(inst)])
        if not keep_vertical:
            drop_vertical(inst)
        out = work / f"arma_{w:g}_glc.ttf"
        process_font(str(inst), str(out), canonical=False, grid=grid)
        per[f"wght={w:g}"] = woff2_encode(out, work / f"arma_{w:g}.woff2")
        total += per[f"wght={w:g}"]
    return {"weights": per, "total_woff2_bytes": total}


def drop_vertical(path: Path) -> None:
    from fontTools.ttLib import TTFont
    f = TTFont(str(path))
    for tag in ("vhea", "vmtx"):
        if tag in f:
            del f[tag]
    f.save(str(path))
    f.close()


def resolve_grid(args, upm: int) -> int:
    if args.grid is not None:
        return args.grid
    if args.no_quantize:
        return 0
    eps = args.epsilon if args.epsilon is not None else 0.4  # % of em
    return max(0, round(2 * eps / 100 * upm))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="GLC: build-time Glyph-Level Compression, output stays WOFF2.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input", required=True, help="input font (.ttf/.otf, may be variable)")
    ap.add_argument("-o", "--output", help="output .woff2 (default: <input>.glc.woff2)")
    ap.add_argument("--instance", action="append", default=[], metavar="AXIS=VALUE",
                    help="pin a variable-font axis, e.g. --instance wght=400 (repeatable)")
    ap.add_argument("--quantize-variable", action="store_true",
                    help="quantise a variable font's default outlines in place, keeping gvar "
                         "(one file, all weights; the GLC-4 max-error guarantee does NOT hold "
                         "away from the default weight -- see docstring)")
    ap.add_argument("--quantize-variable-protected", action="store_true",
                    help="like --quantize-variable, plus M3 tail protection: measure the "
                         "interpolated error at the fvar peaks, exempt the glyphs that "
                         "exceed 2*grid units (their default outlines stay exact), rebuild "
                         "and verify (experimental; measured numbers in the docstring)")
    ap.add_argument("--subset-file", help="file whose characters define the subset")
    ap.add_argument("--subset-text", help="literal characters defining the subset")
    ap.add_argument("--unicodes", help="comma list like U+3042,U+4E00-4E10")
    ap.add_argument("--desubroutinize", action="store_true",
                    help="GLC-1: de-subroutinise CFF charstrings (needs the subset stage; "
                         "with no subset arguments the full cmap is used)")
    ap.add_argument("--no-cff2glyf", action="store_true",
                    help="skip GLC-0 (CFF input then stays CFF; GLC-4 will not apply)")
    ap.add_argument("--cff-error", type=float, default=CFF_ERR_RATIO,
                    help="GLC-0 cu2qu error budget as a fraction of em (default 0.001 = 0.1%%)")
    ap.add_argument("--keep-vertical", action="store_true",
                    help="skip GLC-2 (keep vhea/vmtx)")
    ap.add_argument("--canonical", action="store_true",
                    help="GLC-3: lossless canonicalisation (measured a wash; off by default)")
    ap.add_argument("--epsilon", type=float, default=None, metavar="PCT",
                    help="GLC-4 error budget in %% of em; grid = 2*eps*upm (default 0.4)")
    ap.add_argument("--grid", type=int, default=None,
                    help="GLC-4 explicit grid width in font units (overrides --epsilon)")
    ap.add_argument("--no-quantize", action="store_true", help="skip GLC-4")
    ap.add_argument("--no-safety-valve", action="store_true",
                    help="always write the GLC output, even if it is larger than stock")
    ap.add_argument("--no-stage-sizes", action="store_true",
                    help="do not WOFF2-encode after every stage (faster, less detail)")
    ap.add_argument("--report-json", help="also write a machine-readable report here")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        ap.error(f"input not found: {src}")
    out_path = Path(args.output) if args.output else src.with_suffix(".glc.woff2")

    unicodes: list[int] | None = None
    if args.subset_file:
        text = Path(args.subset_file).read_text(encoding="utf-8")
        unicodes = sorted({ord(c) for c in text if not c.isspace()})
    elif args.subset_text:
        unicodes = sorted({ord(c) for c in args.subset_text if not c.isspace()})
    elif args.unicodes:
        unicodes = []
        for part in args.unicodes.split(","):
            part = part.strip().upper().removeprefix("U+")
            if "-" in part:
                a, b = part.split("-", 1)
                unicodes.extend(range(int(a, 16), int(b, 16) + 1))
            elif part:
                unicodes.append(int(part, 16))
        unicodes = sorted(set(unicodes))

    stages: list[dict] = []

    def note(stage: str, ttf: Path | None, note_text: str = "") -> None:
        row = {"stage": stage, "note": note_text}
        if ttf is not None and ttf.exists():
            row["ttf_bytes"] = ttf.stat().st_size
            if not args.no_stage_sizes:
                w = ttf.with_suffix(".stage.woff2")
                row["woff2_bytes"] = woff2_encode(ttf, w)
                w.unlink(missing_ok=True)
        stages.append(row)

    with tempfile.TemporaryDirectory(prefix="glc-") as td:
        work = Path(td)
        cur = work / "step0.ttf"
        shutil.copyfile(src, cur)

        info = font_info(cur)
        protected = bool(args.quantize_variable_protected)
        vf_mode = bool(info["variable"] and (args.quantize_variable or protected)
                       and not args.instance)
        if info["variable"] and not args.instance and not vf_mode:
            ap.error("variable font: pass --instance (e.g. --instance wght=400) for the "
                     "guaranteed per-weight flow, --quantize-variable to quantise the "
                     "default outlines in place (max-error guarantee lost), or "
                     "--quantize-variable-protected for the peak-verified variant "
                     "(see docstring)")
        if vf_mode and (unicodes is not None or args.desubroutinize):
            ap.error("--quantize-variable covers the full font; subsetting a variable "
                     "font is out of scope (instance it first, then subset the instance)")
        if vf_mode and info["cff"]:
            ap.error("--quantize-variable supports glyf variable fonts only (not CFF2)")

        # ---- stage: instance (not a GLC stage, just an input normalisation)
        if args.instance:
            dst = work / "step1.ttf"
            cmd = [sys.executable, "-m", "fontTools.varLib.instancer", str(cur),
                   *args.instance, "-o", str(dst)]
            run(cmd)
            cur = dst
            note("instance " + ",".join(args.instance), cur)
            info = font_info(cur)

        # ---- subset stage (also the vehicle for GLC-1)
        if unicodes is not None or args.desubroutinize:
            dst = work / "step2.ttf"
            subset_font(cur, dst, unicodes, args.desubroutinize and info["cff"])
            cur = dst
            label = "subset" + (f" ({len(unicodes)} chars)" if unicodes is not None else " (full cmap)")
            if args.desubroutinize and info["cff"]:
                label += " + GLC-1 desubroutinise"
            note(label, cur)
            info = font_info(cur)

        # stock candidate for the safety valve: same coverage, no GLC stages
        stock_w = work / "stock.woff2"
        stock_bytes = woff2_encode(cur, stock_w)
        note("stock WOFF2 (safety-valve reference)", None, f"{stock_bytes:,} B")

        # ---- GLC-0: CFF -> glyf
        if info["cff"] and not args.no_cff2glyf:
            dst = work / "step3.ttf"
            stats = cff_to_glyf(str(cur), str(dst), max_err_ratio=args.cff_error)
            cur = dst
            note("GLC-0 CFF->glyf (cu2qu)", cur,
                 f"budget {args.cff_error * 100:.2f}% em, {stats['points']:,} points")
            info = font_info(cur)

        # ---- GLC-2: drop vertical metrics (in vf_mode this happens inside
        #      process_variable_font, which must control the save itself)
        if not args.keep_vertical and not vf_mode:
            before = cur.stat().st_size
            drop_vertical(cur)
            note("GLC-2 drop vhea/vmtx", cur, f"TTF {before:,} -> {cur.stat().st_size:,} B")

        # ---- GLC-3 + GLC-4 (glyphcodec.process_font; also strips TT hinting,
        #      exactly as in the published pipeline)
        grid = resolve_grid(args, info["upm"])
        _probe = TTFont(str(cur), lazy=True)
        has_glyf = "glyf" in _probe
        _probe.close()
        err_stats = {}
        if has_glyf and (grid > 0 or (args.canonical and not vf_mode)):
            dst = work / "step4.ttf"
            if vf_mode and protected:
                vf_src = cur  # vf_mode forbids earlier stages: still pristine
                err_stats = process_variable_font_protected(
                    vf_src, dst, grid=grid,
                    drop_vertical=not args.keep_vertical, work=work)
                err_stats["arm_a_reference"] = arm_a_reference(
                    vf_src, grid, args.keep_vertical, work)
                cur = dst
                worst_before = max(err_stats["max_error_before"].values(),
                                   default=0)
                note(f"GLC-4 quantise VARIABLE PROTECTED grid={grid} "
                     f"(eps {grid / (2 * info['upm']) * 100:.2f}% em)", None,
                     f"{err_stats.get('quantized', 0):,} simple glyphs quantised, "
                     f"{err_stats.get('exempt_glyphs', 0)} tail glyphs exempted "
                     f"(M3); peak max error {worst_before} -> "
                     f"{err_stats.get('worst_max_error_after_units', 0)} units "
                     f"(bound {err_stats.get('bound_units', 0)}); protected WOFF2 "
                     f"{err_stats.get('protected_woff2_bytes', 0):,} B vs unprotected "
                     f"{err_stats.get('unprotected_woff2_bytes', 0):,} B")
            elif vf_mode:
                err_stats = process_variable_font(
                    str(cur), str(dst), grid=grid,
                    drop_vertical=not args.keep_vertical)
                cur = dst
                note(f"GLC-4 quantise VARIABLE grid={grid} "
                     f"(eps {grid / (2 * info['upm']) * 100:.2f}% em)", cur,
                     f"{err_stats.get('quantized', 0):,} simple glyphs quantised, "
                     f"{err_stats.get('composites_kept', 0):,} composites kept; "
                     "max-error guarantee does not hold away from the default weight")
            else:
                err_stats = process_font(str(cur), str(dst), canonical=args.canonical, grid=grid)
                cur = dst
                label = []
                if args.canonical:
                    label.append("GLC-3 canonical")
                if grid > 0:
                    label.append(f"GLC-4 quantise grid={grid} "
                                 f"(eps {grid / (2 * info['upm']) * 100:.2f}% em)")
                note(" + ".join(label), cur,
                     f"max point error {err_stats.get('max_point_error_units', 0)} units")

        glc_w = work / "glc.woff2"
        glc_bytes = woff2_encode(cur, glc_w)

        # ---- safety valve
        kept = "glc"
        if not args.no_safety_valve and stock_bytes <= glc_bytes:
            kept = "stock"
            shutil.copyfile(stock_w, out_path)
        else:
            shutil.copyfile(glc_w, out_path)

    final_bytes = out_path.stat().st_size
    report = {
        "input": str(src), "output": str(out_path),
        "variable_quantized": vf_mode,
        "variable_protected": bool(vf_mode and protected),
        "upm": info["upm"], "grid": grid if has_glyf else 0,
        "stock_woff2_bytes": stock_bytes, "glc_woff2_bytes": glc_bytes,
        "kept": kept, "final_bytes": final_bytes,
        "delta_vs_stock_pct": round(100 * (1 - final_bytes / stock_bytes), 2),
        "stages": stages, "process_stats": err_stats,
    }
    print(f"\n{'stage':46s} {'WOFF2':>12s}")
    print("-" * 60)
    for s in stages:
        w = s.get("woff2_bytes")
        print(f"{s['stage']:46s} {f'{w:,}' if w else '':>12s}  {s.get('note', '')}")
    print("-" * 60)
    print(f"stock WOFF2 : {stock_bytes:>10,} B")
    print(f"GLC   WOFF2 : {glc_bytes:>10,} B")
    print(f"kept        : {kept} -> {out_path} ({final_bytes:,} B, "
          f"{report['delta_vs_stock_pct']:+.1f}% vs stock)")
    if vf_mode and protected:
        arm_a = err_stats.get("arm_a_reference") or {}
        print("NOTE: variable font quantised in place WITH M3 tail protection\n"
              "(experimental). Glyphs whose interpolated error at the fvar peaks\n"
              f"exceeded {err_stats.get('bound_units', 0)} units were exempted from\n"
              "quantisation; the rebuilt font was re-measured at the same peaks:\n"
              f"  max error before: {err_stats.get('max_error_before', {})}\n"
              f"  max error after : {err_stats.get('max_error_after', {})}\n"
              f"  exempt glyphs   : {err_stats.get('exempt_glyphs', 0)}\n"
              f"  size            : protected {err_stats.get('protected_woff2_bytes', 0):,} B "
              f"vs unprotected {err_stats.get('unprotected_woff2_bytes', 0):,} B"
              + (f" vs Arm A {{400,700}} instances "
                 f"{arm_a.get('total_woff2_bytes', 0):,} B" if arm_a else "")
              + "\n--instance per weight remains the recommended flow.")
    elif vf_mode:
        print("NOTE: variable font quantised in place. Mean outline error stays at the\n"
              "static level at every weight, but the MAX point error grows away from\n"
              "the default weight (gvar IUP interpolation): measured 4 units at the\n"
              "default vs 138 units at wght=900 for grid 8 on Noto Sans JP.\n"
              "For a guaranteed error bound, use --instance per weight instead.")
    if args.report_json:
        Path(args.report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
