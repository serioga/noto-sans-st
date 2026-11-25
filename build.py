"""Build Noto Sans ST from the pinned official Noto Sans variable fonts."""

import argparse
import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._f_v_a_r import NamedInstance
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "sources"
UPSTREAM_VERSION = "2.015"
UPSTREAM_COMMIT = "2984c575fdce412ee02b2baaba67672b9a9434d8"
UPSTREAM_URL = f"https://raw.githubusercontent.com/google/fonts/{UPSTREAM_COMMIT}/ofl/notosans/"
SOURCES = {
    False: (
        "NotoSans[wdth,wght].ttf",
        "NotoSans-upstream.ttf",
        "bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d",
    ),
    True: (
        "NotoSans-Italic[wdth,wght].ttf",
        "NotoSans-Italic-upstream.ttf",
        "58e6e0ebd1931b29a365aa2d3e2ee9a9e831a3af7cf3ad1462d4e72154f0b291",
    ),
}
WEIGHTS = {
    100: "Thin",
    200: "ExtraLight",
    300: "Light",
    400: "Regular",
    500: "Medium",
    600: "SemiBold",
    700: "Bold",
    800: "ExtraBold",
    900: "Black",
}
ELIDABLE = 0x0002
DEFAULT_HINTING = "qsn"


def source_path(italic):
    remote, local, digest = SOURCES[italic]
    path = SOURCE_DIR / local
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return path

    print(f"Downloading {remote} from Noto Sans {UPSTREAM_VERSION}", flush=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    with urlopen(UPSTREAM_URL + quote(remote), timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"SHA-256 mismatch for {remote}")
    with TemporaryDirectory(dir=SOURCE_DIR) as directory:
        download = Path(directory) / local
        download.write_bytes(data)
        download.replace(path)
    return path


def postscript_prefix(family):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", family):
        raise ValueError("Family must start with an ASCII letter or digit and use only ASCII letters, digits, spaces, periods, hyphens, or underscores.")
    prefix = re.sub(r"[^A-Za-z0-9]", "", family)
    if prefix.lower() == "notosans":
        raise ValueError("Use a family name distinct from the upstream Noto Sans.")
    # Leave room for "VariableItalic-ExtraLight" in a 63-character PS name.
    if len(prefix) > 38:
        raise ValueError("Family may contain at most 38 letters and digits.")
    return prefix


def style_name(weight, italic):
    if not italic:
        return WEIGHTS[weight]
    if weight == 400:
        return "Italic"
    return f"{WEIGHTS[weight]} Italic"


def set_metadata(font, family, prefix, width, weight, italic, variable):
    style = style_name(weight, italic)
    legacy_family = family
    legacy_style = style
    if weight not in (400, 700):
        legacy_family = f"{family} {WEIGHTS[weight]}"
        legacy_style = "Italic" if italic else "Regular"

    if variable:
        ps_prefix = f"{prefix}Variable{'Italic' if italic else ''}"
        ps_name = f"{ps_prefix}-{WEIGHTS[weight]}"
        full_name = f"{family}{' Italic' if italic else ''} Variable"
    else:
        ps_name = f"{prefix}-{style.replace(' ', '')}"
        full_name = family if weight == 400 and not italic else f"{family} {style}"

    names = font["name"]
    for name_id in (1, 2, 3, 4, 6, 16, 17, 18, 20, 21, 22, 25):
        names.removeNames(nameID=name_id)
    ids = {
        1: legacy_family,
        2: legacy_style,
        3: f"{UPSTREAM_VERSION};GOOG;{ps_name};wdth={width:g}",
        4: full_name,
        6: ps_name,
        16: family,
        17: style,
    }
    if variable:
        ids[25] = ps_prefix
    for name_id, value in ids.items():
        names.setName(value, name_id, 3, 1, 0x409)

    weight_values = []
    for value in WEIGHTS if variable else (weight,):
        entry = {"name": WEIGHTS[value], "value": value}
        if value == 400:
            entry.update(flags=ELIDABLE, linkedValue=700)
        weight_values.append(entry)

    italic_value = {"name": "Italic", "value": 1} if italic else {
        "name": "Regular", "value": 0, "flags": ELIDABLE, "linkedValue": 1,
    }
    buildStatTable(
        font,
        [
            {"tag": "wght", "name": "Weight", "values": weight_values},
            {"tag": "ital", "name": "Italic", "values": [italic_value]},
        ],
        elidedFallbackName="Regular",
        macNames=False,
    )

    if variable:
        fvar = font["fvar"]
        fvar.axes[0].axisNameID = font["STAT"].table.DesignAxisRecord.Axis[0].AxisNameID
        # Instancing drops upstream named instances outside the pinned width.
        fvar.instances = []
        for instance_weight, weight_name in WEIGHTS.items():
            instance = NamedInstance()
            instance.coordinates = {"wght": instance_weight}
            fvar.instances.append(instance)
            if instance_weight == weight:
                instance.subfamilyNameID = 17
                instance.postscriptNameID = 6
                continue
            instance_style = style_name(instance_weight, italic)
            instance_ps = f"{ps_prefix}-{weight_name}"
            instance.subfamilyNameID = names.addName(instance_style, platforms=((3, 1, 0x409),))
            instance.postscriptNameID = names.addName(instance_ps, platforms=((3, 1, 0x409),))
    names.removeUnusedNames(font)

    bold = weight == 700
    regular = weight == 400 and not italic
    os2 = font["OS/2"]
    os2.usWidthClass = 5
    os2.usWeightClass = weight
    # Synchronize Italic, Bold, Regular, WWS and Oblique with the new names.
    os2.fsSelection &= ~0x0361
    os2.fsSelection |= int(italic) | (bold << 5) | (regular << 6) | (1 << 8)
    font["head"].macStyle = (font["head"].macStyle & ~0x3) | int(bold) | (italic << 1)


def save_static(font, destination, stage, hinter, hinting):
    if hinter is None:
        font.save(destination)
        return

    unhinted = stage / "unhinted.ttf"
    hinted_file = stage / "hinted.ttf"
    font.save(unhinted)
    subprocess.run(
        [hinter, "--detailed-info", f"--stem-width-mode={hinting}",
         "--increase-x-height=0", str(unhinted), str(hinted_file)],
        check=True,
    )
    with TTFont(hinted_file, recalcTimestamp=False) as hinted:
        # ttfautohint sets the modification time to the current time.
        hinted["head"].modified = font["head"].modified
        hinted.save(destination)


def build(family, width, output, hinting=DEFAULT_HINTING):
    prefix = postscript_prefix(family)
    if not 62.5 <= width <= 100:
        raise ValueError("Width must be in the upstream wdth range [62.5, 100].")

    hinter = None
    if hinting != "none":
        hinter = shutil.which("ttfautohint")
        if hinter is None:
            raise ValueError("Install ttfautohint and add it to PATH, or build with --hinting none.")

    inputs = {italic: source_path(italic) for italic in SOURCES}
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as directory:
        stage = Path(directory)
        (stage / "variable").mkdir()
        (stage / "static").mkdir()
        for italic, path in inputs.items():
            with TTFont(path, recalcTimestamp=False) as source:
                variable = instantiateVariableFont(source, {"wdth": width})
                set_metadata(variable, family, prefix, width, 400, italic, variable=True)
                suffix = "Italic-Variable" if italic else "Variable"
                variable.save(stage / "variable" / f"{prefix}-{suffix}.ttf")

                for weight in WEIGHTS:
                    static = instantiateVariableFont(source, {"wdth": width, "wght": weight})
                    set_metadata(static, family, prefix, width, weight, italic, variable=False)
                    destination = stage / "static" / f"{static['name'].getDebugName(6)}.ttf"
                    save_static(static, destination, stage, hinter, hinting)

        shutil.copyfile(ROOT / "LICENSE", stage / "LICENSE")
        for kind in ("variable", "static"):
            (output / kind).mkdir(exist_ok=True)
            for file in sorted((stage / kind).iterdir()):
                file.replace(output / kind / file.name)
        (stage / "LICENSE").replace(output / "LICENSE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", default="Noto Sans ST", help="Font family name (default: %(default)s)")
    parser.add_argument("--width", type=float, default=85, help="Pinned upstream wdth coordinate (default: %(default)s)")
    parser.add_argument(
        "--hinting", choices=("qsn", "qsq", "qss", "none"), default=DEFAULT_HINTING,
        help="ttfautohint preset for static fonts (default: %(default)s)",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="Output directory (default: dist)")
    args = parser.parse_args()
    try:
        build(args.family.strip(), args.width, args.output, args.hinting)
    except (OSError, URLError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build failed: {error}\n")
    print(f"Built 2 variable and 18 static fonts in {args.output.resolve()}")


if __name__ == "__main__":
    main()
