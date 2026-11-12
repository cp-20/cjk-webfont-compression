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
from glyphcodec import process_font  # noqa: E402

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
        if info["variable"] and not args.instance:
            ap.error("variable font: pass --instance (e.g. --instance wght=400); "
                     "quantising a variable font in place would corrupt its gvar deltas")

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

        # ---- GLC-2: drop vertical metrics
        if not args.keep_vertical:
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
        if has_glyf and (grid > 0 or args.canonical):
            dst = work / "step4.ttf"
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
    if args.report_json:
        Path(args.report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
