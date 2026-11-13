#!/usr/bin/env python3
"""Round 4, item 4 probe 2: price the crudest mitigation (M3 exemption).

The design study's cheapest-to-implement protection is M3 from
docs/gvar-aware-quantiser-design.md: leave the tail glyphs' default
outlines unquantised (exempt them) and quantise everything else. If even
this crude version (a) caps the wght-900 error and (b) keeps the single
file below Arm A's two-weight total, the gvar-aware route clears its
bar with room for the cheaper M1/M2 mitigations to spare.

Tail set: glyphs whose VF-safe error exceeds 16 units at wght 900 or at
wght 400 (from iup_amplification.py's measurement, recomputed here for
the 400 arm). The exempted font is built exactly like
glyphcodec.process_variable_font except the tail glyphs are skipped by
the quantiser; hinting is stripped the same way, gvar untouched.

Output: measure/out/iup_mitigation_probe.json; the built font is kept
at measure/out/vf/vf_safe_q8_m3.ttf for inspection.
Usage:  .venv/bin/python measure/iup_mitigation_probe.py
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.instancer import instantiateVariableFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VF = HERE / "out" / "vf"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))
import glyphcodec  # noqa: E402
from iup_amplification import describe, glyph_errors  # noqa: E402

OUT = HERE / "out" / "iup_mitigation_probe.json"
BUILT = VF / "vf_safe_q8_m3.ttf"
GRID = 8
THRESH = 16


def woff2_bytes(path: Path) -> int:
    f = TTFont(str(path))
    f.flavor = "woff2"
    buf = io.BytesIO()
    f.save(buf)
    return buf.tell()


def instance(font, w: int):
    f = TTFont(font) if isinstance(font, (str, Path)) else font
    instantiateVariableFont(f, {"wght": w}, inplace=True)
    return f


def main() -> int:
    # --- tail set: err > THRESH at 900 (stored) union err > THRESH at 400
    stored = json.loads((HERE / "out" / "iup_amplification.json")
                        .read_text(encoding="utf-8"))
    tail = {t["glyph"] for t in stored["tail_over_16_at_900"]}
    e400, _ = glyph_errors(VF / "arm_b2_vfsafe_400.ttf", VF / "stock_400.ttf")
    tail |= {g for g, e in e400.items() if e > THRESH}
    print(f"tail glyphs exempted: {len(tail)}")

    # --- build the M3 font: process_variable_font minus the tail
    font = TTFont(str(ROOT / "fonts" / "NotoSansJP[wght].ttf"),
                  recalcBBoxes=False, recalcTimestamp=False)
    glyf = font["glyf"]
    n_quant = 0
    for gn in font.getGlyphOrder():
        if gn not in glyf.glyphs:
            continue
        g = glyf[gn]
        if g.numberOfContours > 0 and gn not in tail:
            if glyphcodec.quantize_glyph(g, GRID):
                n_quant += 1
                try:
                    g.recalcBounds(glyf)
                except Exception:  # noqa: BLE001
                    pass
    for tag in ("fpgm", "prep", "cvt ", "cvar"):
        if tag in font:
            del font[tag]
    for gn in font.getGlyphOrder():
        if gn not in glyf.glyphs:
            continue
        g = glyf[gn]
        if hasattr(g, "program"):
            try:
                g.program = Program()
            except Exception:  # noqa: BLE001
                pass
    font.save(str(BUILT))
    print(f"built {BUILT} (quantised {n_quant} glyphs)")

    size_m3 = woff2_bytes(BUILT)
    size_b2 = woff2_bytes(VF / "vf_safe_q8.ttf")
    print(f"WOFF2: B2 {size_b2:,}  B2+M3 {size_m3:,}  "
          f"delta {size_m3 - size_b2:+,} B")

    # --- verify: instance the M3 font at 100/400/900, compare to stock
    result = {"provenance": {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime()),
                             "tail_threshold_units": THRESH,
                             "tail_glyphs": len(tail)},
              "woff2": {"b2": size_b2, "b2_m3": size_m3,
                        "delta_bytes": size_m3 - size_b2},
              "errors": {}}
    import tempfile
    for w in (100, 400, 900):
        with tempfile.NamedTemporaryFile(suffix=".ttf") as fh:
            instance(BUILT, w).save(fh.name)
            errs, _ = glyph_errors(Path(fh.name), VF / f"stock_{w}.ttf")
        d = describe(errs)
        result["errors"][str(w)] = d
        print(f"wght {w}: {d}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
