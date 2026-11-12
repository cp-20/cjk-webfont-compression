#!/usr/bin/env python3
"""Download the third-party assets the measurements need.

  * the 15 CJK fonts listed in fonts/manifest.json (with SHA-256 verification)
  * the PLaMo 3 Translate GGUF used for the EN<->JA translation
  * optionally the llama.cpp build used to run it

Usage:
    python scripts/fetch_assets.py --fonts
    python scripts/fetch_assets.py --model
    python scripts/fetch_assets.py --all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "fonts" / "manifest.json"

MODEL = {
    "url": "https://huggingface.co/pfnet/plamo-3-translate-0.8b-GGUF/resolve/main/"
           "plamo-3-translate-0.8b-Q4_K_M.gguf",
    "sha256": "70891ec70dc7ab4205745a38307867c2881b99239f20327927633abfe4bc9ec6",
    "path": "models/plamo-0.8b-Q4_K_M.gguf",
    "license": "PLaMo Community License (https://plamo.preferredai.jp/info/plamo-community-license-en)",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  GET {url}", flush=True)
    with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dest)


def fetch_fonts(force: bool = False) -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ok = 0
    for f in data["fonts"]:
        dest = ROOT / f["local_path"]
        if dest.exists() and not force:
            print(f"  skip {f['id']} (exists)")
            continue
        download(f["source_url"], dest)
        digest = sha256(dest)
        if digest != f["sha256"]:
            print(f"  !! SHA-256 mismatch for {f['id']}: {digest} != {f['sha256']}", file=sys.stderr)
        else:
            print(f"  ok  {f['id']} ({dest.stat().st_size:,} bytes)")
        ok += 1
    print(f"fonts: {ok} downloaded")
    return ok


def fetch_model(force: bool = False) -> int:
    dest = ROOT / MODEL["path"]
    if dest.exists() and not force:
        print("  skip model (exists)")
        return 0
    download(MODEL["url"], dest)
    digest = sha256(dest)
    if digest != MODEL["sha256"]:
        print(f"  !! SHA-256 mismatch: {digest}", file=sys.stderr)
    else:
        print(f"  ok  model ({dest.stat().st_size:,} bytes)")
    return 1


def build_llama_cpp() -> int:
    dest = ROOT / "tools" / "llama.cpp"
    if not dest.exists():
        subprocess.run(["git", "clone", "--depth", "1",
                        "https://github.com/ggml-org/llama.cpp.git", str(dest)], check=True)
    subprocess.run(["cmake", "-S", str(dest), "-B", str(dest / "build"),
                    "-DCMAKE_BUILD_TYPE=Release", "-DGGML_CUDA=OFF", "-DLLAMA_CURL=OFF"], check=True)
    subprocess.run(["cmake", "--build", str(dest / "build"), "--target", "llama-server",
                    "-j", "16"], check=True)
    print("  ok  llama.cpp build")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", action="store_true")
    ap.add_argument("--model", action="store_true")
    ap.add_argument("--llama", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not (args.fonts or args.model or args.llama or args.all):
        ap.print_help()
        return 1
    if args.fonts or args.all:
        print("fonts:")
        fetch_fonts(args.force)
    if args.model or args.all:
        print("model:")
        fetch_model(args.force)
    if args.llama or args.all:
        print("llama.cpp:")
        build_llama_cpp()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
