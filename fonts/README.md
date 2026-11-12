# CJK Font Corpus

Curated Japanese, Simplified Chinese, and Korean font files for a technical
study of CJK web-font compression. The corpus contains 15 binaries: all 12
requested remote targets plus two local comparison fonts, with Source Han Sans
JP kept in both full and subset form.

Every value in `manifest.json` was read from the downloaded binary with
fontTools; no glyph counts or font metrics are estimated.

## Snapshot

- **15 font files**, **146,066,716 bytes** (139.3 MiB).
- 4 variable fonts, 11 static fonts.
- 12 TrueType `glyf` fonts (4 with `gvar`) and 3 CFF1 fonts. No CFF2.
- Download traffic was about **143.3 MB** (136.7 MiB), including the Adobe zip;
  the 300 MB budget was not approached.
- All 15 files reopen successfully in `fontTools.ttLib.TTFont`; 0 failures.

## Fonts

| # | File | Family | Region | Style | Glyphs | UPEM | Size (MiB) | Outlines |
|---:|---|---|---|---|---:|---:|---:|---|
| 1 | `NotoSansJP[wght].ttf` | Noto Sans JP | JP | Variable, wght 100–900 | 17,936 | 1000 | 9.15 | glyf + gvar |
| 2 | `NotoSerifJP[wght].ttf` | Noto Serif JP | JP | Variable, wght 200–900 | 17,923 | 1000 | 12.95 | glyf + gvar |
| 3 | `MPLUS1p-Regular.ttf` | M PLUS 1p | JP | Regular | 8,676 | 1000 | 1.68 | glyf |
| 4 | `ZenKakuGothicNew-Regular.ttf` | Zen Kaku Gothic New | JP | Regular | 7,792 | 1000 | 2.25 | glyf |
| 5 | `KosugiMaru-Regular.ttf` | Kosugi Maru | JP | Regular | 7,575 | 1024 | 3.40 | glyf |
| 6 | `ShipporiMincho-Regular.ttf` | Shippori Mincho | JP | Regular | 16,359 | 1000 | 8.28 | glyf |
| 7 | `SawarabiMincho-Regular.ttf` | Sawarabi Mincho | JP | Regular | 4,792 | 1000 | 3.49 | glyf |
| 8 | `NotoSansSC[wght].ttf` | Noto Sans SC | SC | Variable, wght 100–900 | 31,036 | 1000 | 16.95 | glyf + gvar |
| 9 | `NotoSansKR[wght].ttf` | Noto Sans KR | KR | Variable, wght 100–900 | 24,964 | 1000 | 9.93 | glyf + gvar |
| 10 | `LXGWWenKai-Regular.ttf` | LXGW WenKai | SC | Regular | 47,336 | 1000 | 24.73 | glyf |
| 11 | `NanumGothic-Regular.ttf` | NanumGothic | KR | Regular | 13,297 | 1000 | 1.96 | glyf |
| 12 | `SourceHanSansJP-Full-Regular.otf` | Source Han Sans | JP | Regular | 65,535 | 1000 | 15.79 | CFF1 |
| 13 | `SourceHanSansJP-Regular.otf` | Source Han Sans JP | JP | Regular | 17,944 | 1000 | 4.35 | CFF1 |
| 14 | `NotoSansCJK-Regular.ttc` | Noto Sans CJK JP | JP | Regular, TTC face 0/10 | 65,535 | 1000 | 18.58 | CFF1 |
| 15 | `ipaexg.ttf` | IPAexGothic | JP | Regular | 12,239 | 2048 | 5.82 | glyf |

Notes:

- Family names are the names stored in each font. The Google Fonts menu name
  for #11 is “Nanum Gothic”; the binary uses `NanumGothic`.
- The variable Noto files default to **Thin** (wght=100), except Noto Serif JP,
  which defaults to **ExtraLight** (wght=200). The default named instance is
  recorded in `default_instance`, and the full axis range is in `axes`.
- #12 is the full 65,535-glyph Japanese build from Adobe's `release` branch.
  #13 is the 17,944-glyph Adobe-Japan1 subset shipped as a release asset. Both
  are retained because the pair is a ready-made subsetting baseline.
- #14 is one 18.58 MiB collection containing 10 faces (five proportional and
  five monospaced); only face 0, Noto Sans CJK JP, is described here.
- The 65,535 figure for #12 and #14 is the maximum addressable glyph count in
  these formats, not an estimate.
- The two local comparison fonts were copied from
  `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` and
  `/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf`; those original paths
  are in `system_path`.

## Sources and fallbacks

| Source | Files | Notes |
|---|---:|---|
| `google/fonts` raw (`main`) | 10 | Noto Sans/Serif JP, M PLUS 1p, Zen Kaku Gothic New, Shippori Mincho, Sawarabi Mincho, Noto Sans SC/KR, Nanum Gothic |
| `lxgw/LxgwWenKai` release v1.530 | 1 | LXGW WenKai Regular |
| `adobe-fonts/source-han-sans` 2.005R | 2 | Full OTF from `release` branch; subset OTF extracted from `17_SourceHanSansJP.zip` |
| Local system fonts | 2 | Noto Sans CJK JP (TTC face 0) and IPAexGothic |

Path/subset issues resolved during collection:

1. **Kosugi Maru** is not under `ofl/`. It is Apache-2.0 and lives at
   `apache/kosugimaru/KosugiMaru-Regular.ttf` in `google/fonts`.
2. **LXGW WenKai** is not in `google/fonts` (only the `LXGWWenKaiTC` derivative
   is). The official upstream v1.530 release was used instead.
3. The official Adobe asset `17_SourceHanSansJP.zip` contains only
   `SubsetOTF/JP/*.otf`, not the full font. The full Japanese OTF was therefore
   also taken from the repository's `release` branch at
   `OTF/Japanese/SourceHanSans-Regular.otf`.

No target was ultimately skipped, no URL in the manifest is a 404, and no font
failed to open.

## Licensing

- **13 fonts: SIL Open Font License 1.1** (`OFL-1.1`).
- **Kosugi Maru: Apache License 2.0** (`Apache-2.0`).
- **IPAexGothic: IPA Font License 1.0** (SPDX `IPA`).

License texts are in `fonts/licenses/`. The local Noto CJK and IPAexGothic
entries use the Debian copyright files, which contain the upstream license
texts. Consult the original upstream notices before redistribution.

## Verification and manifest fields

Verification used the project virtualenv with fontTools 4.68.0. For every file:

1. The byte size and SHA-256 were computed from disk.
2. `TTFont(path)` opened the file (or `fontNumber=0` for the TTC).
3. `name`, `head`, `maxp`, and `cmap` were decompiled; `getBestCmap()` was
   parsed to count distinct Unicode codepoints.
4. The actual table directory and, where present, the `fvar` axes were read
   from the binary.

`manifest.json` records `family`, `style`, `license`, `source_url`,
`local_path`, `bytes`, `sha256`, `numGlyphs`, `unitsPerEm`, `tables`,
`has_glyf` / `has_CFF` / `has_CFF2` / `has_gvar`, `axes`, and the original
`name_table` strings, plus `cmap_unicode_codepoints` and TTC face information.
The top-level `verification.all_fonts_open` flag is `true` and `failures` is
empty.

## Layout

```text
fonts/
├── README.md
├── manifest.json
├── NotoSansJP[wght].ttf
├── NotoSerifJP[wght].ttf
├── MPLUS1p-Regular.ttf
├── ZenKakuGothicNew-Regular.ttf
├── KosugiMaru-Regular.ttf
├── ShipporiMincho-Regular.ttf
├── SawarabiMincho-Regular.ttf
├── NotoSansSC[wght].ttf
├── NotoSansKR[wght].ttf
├── LXGWWenKai-Regular.ttf
├── NanumGothic-Regular.ttf
├── SourceHanSansJP-Full-Regular.otf
├── SourceHanSansJP-Regular.otf
├── NotoSansCJK-Regular.ttc
├── ipaexg.ttf
└── licenses/          # 14 license/copyright texts
```
