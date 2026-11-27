# Noto Sans ST

These TrueType fonts are built from official Noto Sans v2.015. They retain
the upstream Unicode coverage, including Cyrillic, and use Normal stretch
classification in Windows.

## Build on Windows PowerShell

Run these commands from the project directory with Python 3.10 or later
and ttfautohint 1.8.4 on PATH.
[ttfautohint downloads](https://freetype.org/ttfautohint/)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe build.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The build downloads the pinned source files on the first run, verifies
their SHA-256 hashes, and caches them in `sources/`. It writes to
`dist/release/` by default. Use `--output` to choose another directory.
[Official distribution commit](https://github.com/google/fonts/commit/2984c575fdce412ee02b2baaba67672b9a9434d8)

## Font families

| Family name | Upright upstream width | Italic upstream width |
| --- | ---: | ---: |
| Noto Sans ST | 85 | 90 |
| Noto Sans ST Variable | 80–90, default 85 | 85–95, default 90 |
| Noto Sans ST Width 800 | 80 | 85 |
| Noto Sans ST Width 825 | 82.5 | 87.5 |
| Noto Sans ST Width 850 | 85 | 90 |
| Noto Sans ST Width 875 | 87.5 | 92.5 |
| Noto Sans ST Width 900 | 90 | 95 |

Every family has Regular, Medium, SemiBold, and Bold in upright and italic.
Each static family has eight TTF files. The variable family has two files
with four named weights per slope and a continuous weight axis from
300 to 900, defaulting to Regular (400).

Width labels refer to the upright design. Italic uses five additional
upstream width points in each family. The variable width slider runs from
approximately 94.12 to 105.88 for both slopes. Its Normal setting of 100
gives upstream width 85 upright and 90 italic. To convert an upright
upstream width to a slider value, multiply it by 100 and divide by 85.
[OpenType Width axis](https://learn.microsoft.com/en-us/typography/opentype/spec/dvaraxistag_wdth)

All families use `ttfautohint --stem-width-mode=qsn --increase-x-height=0`.
The variable hints are derived from its default outlines. The build checks
that hinting leaves the glyph geometry and variation tables intact.

## License

Copyright 2022 The Noto Project Authors. Each family includes the unchanged
SIL Open Font License 1.1 from the source distribution.
[Upstream release](https://github.com/notofonts/latin-greek-cyrillic/releases/tag/NotoSans-v2.015)
