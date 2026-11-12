#!/usr/bin/env python3
"""Estimate the potential of a *shared* compression dictionary for CJK fonts.

Method (upper-bound estimate, not a deployable format today):
  * take the glyf (outline) table of several CJK fonts
  * cut them into 64 KiB samples, train a Zstandard dictionary on them
  * compress a held-out font's glyf / whole sfnt with and without the dictionary
Also reports Brotli with a custom dictionary (prefix dictionary only) for comparison.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
OUT = ROOT / "measure" / "out"
OUT.mkdir(parents=True, exist_ok=True)

TRAIN = [
    ("Noto Sans JP", "fonts/NotoSansJP[wght].ttf"),
    ("Noto Serif JP", "fonts/NotoSerifJP[wght].ttf"),
    ("Noto Sans SC", "fonts/NotoSansSC[wght].ttf"),
    ("Noto Sans KR", "fonts/NotoSansKR[wght].ttf"),
    ("Source Han Sans JP", "fonts/SourceHanSansJP-Full-Regular.otf"),
]
TARGETS = [
    ("Noto Sans JP (target)", "measure/out/NotoSansJP-Regular.ttf"),
    ("Zen Kaku Gothic New", "fonts/ZenKakuGothicNew-Regular.ttf"),
    ("Nanum Gothic", "fonts/NanumGothic-Regular.ttf"),
]
CHUNK = 65536


def glyf_bytes(path):
    f = TTFont(path, lazy=True)
    for tag in ("glyf", "CFF "):
        if tag in f.reader.tables:
            data = f.reader.file.read if False else None
            f2 = TTFont(path, lazy=False)
            tbl = f2.reader.tables[tag]
            raw = f2.reader.file.getdata(tag) if hasattr(f2.reader.file, "getdata") else None
            if raw is None:
                f2.reader.file.seek(tbl.offset)
                raw = f2.reader.file.read(tbl.length)
            f2.close()
            f.close()
            return tag, raw
    f.close()
    return None, None


def zstd_compress(data: bytes, level=19) -> int:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        path = f.name
    out = path + ".zst"
    subprocess.run(["zstd", "-19", "-q", "-f", path, "-o", out], check=True)
    n = os.path.getsize(out)
    os.unlink(path)
    os.unlink(out)
    return n


def zstd_compress_dict(data: bytes, dict_path: str, level=19) -> int:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        path = f.name
    out = path + ".zst"
    subprocess.run(["zstd", "-19", "-q", "-f", "-D", dict_path, path, "-o", out], check=True)
    n = os.path.getsize(out)
    os.unlink(path)
    os.unlink(out)
    return n


def brotli_compress(data: bytes, q=11) -> int:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        path = f.name
    out = path + ".br"
    subprocess.run(["brotli", "-q", str(q), "-f", path, "-o", out], check=True)
    n = os.path.getsize(out)
    os.unlink(path)
    os.unlink(out)
    return n


def brotli_compress_dict(data: bytes, dict_path: str, q=11) -> int:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        path = f.name
    out = path + ".br"
    subprocess.run(["brotli", "-q", str(q), "-f", "-D", dict_path, path, "-o", out], check=True)
    n = os.path.getsize(out)
    os.unlink(path)
    os.unlink(out)
    return n


def main():
    tmp = Path(tempfile.mkdtemp(prefix="fontdict-"))
    samples_dir = tmp / "samples"
    samples_dir.mkdir()
    n_samples = 0
    for name, rel in TRAIN:
        tag, data = glyf_bytes(ROOT / rel)
        if not data:
            continue
        for i in range(0, len(data), CHUNK):
            (samples_dir / f"{name.replace(' ', '_')}_{i:08d}.bin").write_bytes(data[i:i + CHUNK])
            n_samples += 1
    print(f"training samples: {n_samples}", flush=True)
    dict_path = str(tmp / "cjk.dict")
    r = subprocess.run(["zstd", "--train", f"--maxdict={1 << 20}", "-q",
                        f"--output-dir-flat={samples_dir}", dict_path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # zstd wants a directory of samples as positional args
        files = sorted(str(p) for p in samples_dir.iterdir())
        r = subprocess.run(["zstd", "--train", f"--maxdict={1 << 20}", "-q", "-o", dict_path] + files,
                           capture_output=True, text=True)
    if r.returncode != 0:
        print("zstd --train failed:", r.stderr[-500:])
        return
    dsize = os.path.getsize(dict_path)
    print(f"dictionary: {dsize} bytes", flush=True)

    rows = []
    for name, rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            continue
        tag, data = glyf_bytes(p)
        if not data:
            continue
        plain = zstd_compress(data)
        withdict = zstd_compress_dict(data, dict_path)
        br = brotli_compress(data)
        brdict = brotli_compress_dict(data, dict_path)
        sfnt = p.read_bytes()
        sf_plain = zstd_compress(sfnt)
        sf_dict = zstd_compress_dict(sfnt, dict_path)
        rows.append({
            "target": name,
            "outline_table": tag,
            "outline_raw_bytes": len(data),
            "plain_bytes": plain,
            "dict_bytes": withdict,
            "saving": 1 - withdict / plain,
            "brotli_bytes": br,
            "brotli_dict_bytes": brdict,
            "brotli_dict_saving": 1 - brdict / br,
            "sfnt_zstd_bytes": sf_plain,
            "sfnt_zstd_dict_bytes": sf_dict,
            "sfnt_zstd_saving": 1 - sf_dict / sf_plain,
        })
        print(f"{name:24s} glyf {len(data)/1e6:.1f}MB  zstd {plain/1e6:.2f} -> {withdict/1e6:.2f} MB "
              f"({rows[-1]['saving']*100:.1f}% 減)  brotli {br/1e6:.2f} -> {brdict/1e6:.2f} MB "
              f"({rows[-1]['brotli_dict_saving']*100:.1f}% 減)", flush=True)

    out = {
        "method": ("CJK フォントの輪郭テーブルから 64 KiB サンプルを作り Zstandard 辞書を学習し、"
                   "held-out フォントで辞書あり／なしを比較した上限試算。"),
        "note": ("実運用では WOFF2（Brotli 済み）に外部辞書を適用する手段がないため、"
                 "そのまま使える技術ではない。フォントを sfnt のまま配信し RFC 9842 の圧縮辞書転送"
                 "（Chrome の dcb/dcz）を使う場合の実装_gradient の目安。"),
        "dictionary_bytes": dsize,
        "samples": n_samples,
        "rows": rows,
    }
    (OUT / "shared_dictionary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("wrote", OUT / "shared_dictionary.json")


if __name__ == "__main__":
    main()
