#!/usr/bin/env python3
"""Batch translation with a local PLaMo 3 Translate llama-server.

Input JSONL records: {"id": "...", "text": "...", "direction": "en-ja"|"ja-en", "context": "..."}
Output JSONL appends: {"id", "direction", "source", "translation", "model", "elapsed_s"}

Usage:
  .venv/bin/python tools/translate.py \
      --input report/translation_input.jsonl \
      --output report/translation_output.jsonl \
      --server http://127.0.0.1:8080
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Iterable

import requests

DEFAULT_GLOSSARY = {
    "font subsetting": "フォントサブセット化",
    "subsetting": "サブセット化",
    "subsetting approach": "サブセット化方式",
    "de-subroutinized": "デサブルーチン化（サブルーチンを展開して平準化すること）",
    "de-subroutinize": "デサブルーチン化",
    "subroutinized": "サブルーチン化された",
    "de-subroutinise": "デサブルーチン化する",
    "de-subroutinising": "デサブルーチン化する",
    "desubroutinize": "デサブルーチン化する",
    "quantizing": "量子化する",
    "grid": "格子",
    "savings": "削減率",
    "glyph": "グリフ",
    "variable font": "バリアブルフォント",
    "incremental font transfer": "インクリメンタルフォント転送",
    "progressive font enrichment": "プログレッシブフォントエンリッチメント",
    "unicode-range": "unicode-range",
    "web font": "ウェブフォント",
    "font file": "フォントファイル",
    "compression": "圧縮",
    "Brotli": "Brotli",
    "WOFF2": "WOFF2",
    "OpenType": "OpenType",
    "TrueType": "TrueType",
    "CFF": "CFF",
    "cache": "キャッシュ",
    "latency": "レイテンシ",
    "first paint": "ファーストペイント",
}


def split_text(text: str, max_chars: int = 1800) -> list[str]:
    """Split on paragraph/sentence boundaries, keeping chunks under max_chars."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    paras = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    buf = ""
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p).strip()
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(p) <= max_chars:
            buf = p
        else:
            # split long paragraph on sentence enders
            parts = re.split(r"(?<=[.!?。！？])\s+", p)
            for s in parts:
                if len(buf) + len(s) + 1 <= max_chars:
                    buf = (buf + " " + s).strip()
                else:
                    if buf:
                        chunks.append(buf)
                    buf = s
    if buf:
        chunks.append(buf)
    return chunks


def build_system(direction: str) -> str:
    target = "ja" if direction == "en-ja" else "en"
    source = "en" if direction == "en-ja" else "ja"
    lines = ["[plamo-translate]", f"target_lang={target}", f"source_lang={source}"]
    if target == "ja":
        lines.append("form=polite")
    if direction == "en-ja":
        for k, v in DEFAULT_GLOSSARY.items():
            lines.append(f"glossary={k} => {v}")
    lines.append("---")
    lines.append(
        "Translate faithfully. Preserve technical terms, numbers, product names, "
        "and citations. Do not add explanations. Output only the translation."
    )
    return "\n".join(lines)


def translate_chunk(server: str, text: str, direction: str, timeout: int = 300) -> str:
    payload = {
        "model": "plamo-3-translate",
        "messages": [
            {"role": "system", "content": build_system(direction)},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": 4096,
        "stop": ["<|plamo:tag|>", "<|plamo:bos|>"],
    }
    r = requests.post(f"{server}/v1/chat/completions", json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--server", default="http://127.0.0.1:8080")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-chars", type=int, default=1800)
    args = ap.parse_args()

    done: set[str] = set()
    if os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        done.add(json.loads(line)["id"])
                    except Exception:
                        pass

    records = []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    if args.limit:
        records = records[: args.limit]

    out = open(args.output, "a", encoding="utf-8")
    ok = 0
    for rec in records:
        rid = rec["id"]
        if rid in done:
            continue
        direction = rec.get("direction", "en-ja")
        text = rec["text"]
        t0 = time.time()
        try:
            parts = split_text(text, args.max_chars)
            translated = []
            for part in parts:
                translated.append(translate_chunk(args.server, part, direction))
            result = "\n\n".join(translated)
            elapsed = round(time.time() - t0, 2)
            row = {
                "id": rid,
                "direction": direction,
                "source": text,
                "translation": result,
                "model": "pfnet/plamo-3-translate-0.8b Q4_K_M",
                "elapsed_s": elapsed,
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            ok += 1
            print(f"[ok] {rid} {elapsed}s {len(text)}->{len(result)} chars", flush=True)
        except Exception as e:
            print(f"[err] {rid}: {e}", file=sys.stderr, flush=True)
    out.close()
    print(f"done: {ok} translated", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
