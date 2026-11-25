# Noto Sans ST

Noto Sans ST is a TrueType derivative of the official Noto Sans v2.015 fonts.
By default, FontTools interpolates the original design at `wdth=85`. The build keeps the
upstream glyph coverage, including Cyrillic, and identifies the resulting
width as Normal through `OS/2.usWidthClass=5`. The width axis is fixed in
both builds.

## Build on Windows PowerShell

From the project directory, with Python 3.10 or later and `ttfautohint` on
PATH. The autohinter version used for this build is 1.8.4.
[ttfautohint downloads](https://freetype.org/ttfautohint/)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe build.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The first build downloads two source fonts from a pinned Google Fonts
distribution commit. Subsequent builds can run offline using the SHA-256-verified
cache in `sources/`. FontTools is version-pinned and the build preserves source
timestamps so repeated builds with the same tool versions use the same font data. The validation command
checks the default build. [Official distribution commit](https://github.com/google/fonts/commit/2984c575fdce412ee02b2baaba67672b9a9434d8)

## Outputs

| Directory | Contents |
| --- | --- |
| `dist/variable/` | `NotoSansST-Variable.ttf` and `NotoSansST-Italic-Variable.ttf`, with upright and italic styles and a continuous weight range of 100–900 |
| `dist/static/` | 18 faces covering Thin, ExtraLight, Light, Regular, Medium, SemiBold, Bold, ExtraBold, and Black in upright and italic |

Static fonts use `ttfautohint --stem-width-mode=qsn --increase-x-height=0`.
The autohinting step applies only to static fonts.

Both formats use the Noto Sans ST typographic family name. The variable fonts’
full names are **Noto Sans ST Variable** and **Noto Sans ST Italic Variable**.
For use in an app's font menu, select one format to avoid duplicate style
entries. The build writes files only.

## Configuration

```powershell
.\.venv\Scripts\python.exe build.py --family "Noto Sans Studio" --width 90 --output dist\studio
```

`--width` accepts values from 62.5 to 100. Use distinct family names and output
directories for builds you plan to keep alongside each other. Family names
start with an ASCII letter or digit and may also contain spaces, periods,
hyphens, and underscores. The PostScript prefix uses the letters and digits
from that name, with a maximum of 38.

`--hinting` selects `qsn` (default), `qsq`, or `qss` for static fonts.
Use `--hinting none` to build without ttfautohint.

## License

Copyright 2022 The Noto Project Authors. The SIL Open Font License 1.1 is in
`LICENSE` and is copied to the output directory. Keep it with redistributed
font files. [Noto Sans upstream release](https://github.com/notofonts/latin-greek-cyrillic/releases/tag/NotoSans-v2.015)
