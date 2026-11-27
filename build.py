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
    400: "Regular",
    500: "Medium",
    600: "SemiBold",
    700: "Bold",
}
ELIDABLE = 0x0002
HINTING_MODE = "qsn"
BASE_FAMILY = "Noto Sans ST"
VARIABLE_FAMILY = "Noto Sans ST Variable"
VARIABLE_WEIGHT_RANGE = (300, 900)
WIDTHS = (80, 82.5, 85, 87.5, 90)
NORMAL_WIDTH = 85
ITALIC_WIDTH_OFFSET = 5
OUTPUT = ROOT / "dist" / "release"


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
    # Leave room for the slope and weight in a 63-character PS name.
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
        ps_prefix = f"{prefix}{'Italic' if italic else ''}"
        ps_name = f"{ps_prefix}-{WEIGHTS[weight]}"
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

    variation_axes = {axis.axisTag: axis for axis in font["fvar"].axes} if variable else {}
    weights = WEIGHTS if variable else (weight,)

    weight_values = []
    for value in weights:
        entry = {"name": WEIGHTS[value], "value": value}
        if value == 400:
            entry.update(flags=ELIDABLE, linkedValue=700)
        weight_values.append(entry)

    italic_value = {"name": "Italic", "value": 1} if italic else {
        "name": "Regular", "value": 0, "flags": ELIDABLE, "linkedValue": 1,
    }
    stat_axes = [
        {"tag": "wght", "name": "Weight", "values": weight_values},
        {"tag": "ital", "name": "Italic", "values": [italic_value]},
    ]
    if variable:
        width_axis = variation_axes["wdth"]
        stat_axes.append({
            "tag": "wdth",
            "name": "Width",
            "values": [{
                "name": "Normal",
                "nominalValue": width_axis.defaultValue,
                "rangeMinValue": width_axis.minValue,
                "rangeMaxValue": width_axis.maxValue,
                "flags": ELIDABLE,
            }],
        })
    buildStatTable(font, stat_axes, elidedFallbackName="Regular", macNames=False)

    if variable:
        fvar = font["fvar"]
        for axis in font["STAT"].table.DesignAxisRecord.Axis:
            if axis.AxisTag in variation_axes:
                variation_axes[axis.AxisTag].axisNameID = axis.AxisNameID
        defaults = {tag: axis.defaultValue for tag, axis in variation_axes.items()}
        # Name the four weights at the new Normal width.
        fvar.instances = []
        for instance_weight in weights:
            instance = NamedInstance()
            instance.coordinates = {**defaults, "wght": instance_weight}
            fvar.instances.append(instance)
            if instance_weight == weight:
                instance.subfamilyNameID = 17
                instance.postscriptNameID = 6
                continue
            instance_style = style_name(instance_weight, italic)
            instance_ps = f"{ps_prefix}-{WEIGHTS[instance_weight]}"
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


def verify_variable_hinting(original, hinted):
    for tag in ("fvar", "gvar", "avar", "HVAR", "MVAR", "GDEF", "GPOS", "GSUB", "cmap", "hmtx", "hhea", "OS/2", "STAT"):
        if tag in original and (tag not in hinted or original.reader[tag] != hinted.reader[tag]):
            raise ValueError(f"ttfautohint changed the variable font's {tag} table.")
    if original.getGlyphOrder() != hinted.getGlyphOrder():
        raise ValueError("ttfautohint changed the variable glyph order.")

    before, after = original["glyf"], hinted["glyf"]
    for name in original.getGlyphOrder():
        a, b = before[name], after[name]
        if a.numberOfContours != b.numberOfContours:
            raise ValueError(f"ttfautohint changed the number of contours in {name}.")
        if a.isComposite():
            matches = [vars(component) for component in a.components] == [
                vars(component) for component in b.components
            ]
        else:
            matches = a.getCoordinates(before) == b.getCoordinates(after)
        if not matches:
            raise ValueError(f"ttfautohint changed the variable glyph geometry in {name}.")


def save_hinted(font, destination, stage, hinter):
    unhinted = stage / "unhinted.ttf"
    hinted_file = stage / "hinted.ttf"
    font.save(unhinted)
    subprocess.run(
        [hinter, "--detailed-info", f"--stem-width-mode={HINTING_MODE}",
         "--increase-x-height=0", str(unhinted), str(hinted_file)],
        check=True,
    )
    with TTFont(hinted_file, recalcTimestamp=False) as hinted:
        if "fvar" in font:
            with TTFont(unhinted) as original:
                verify_variable_hinting(original, hinted)
        # ttfautohint sets the modification time to the current time.
        hinted["head"].modified = font["head"].modified
        hinted.save(destination)


def build_variable(source, italic):
    offset = ITALIC_WIDTH_OFFSET if italic else 0
    widths = (WIDTHS[0] + offset, NORMAL_WIDTH + offset, WIDTHS[-1] + offset)
    font = instantiateVariableFont(
        source, {"wdth": widths, "wght": VARIABLE_WEIGHT_RANGE}
    )
    width_axis = next(axis for axis in font["fvar"].axes if axis.axisTag == "wdth")
    # Both slopes share one slider. Its normalized coordinates map to the
    # italic design five upstream width points above the upright design.
    width_axis.minValue = WIDTHS[0] * 100 / NORMAL_WIDTH
    width_axis.defaultValue = 100
    width_axis.maxValue = WIDTHS[-1] * 100 / NORMAL_WIDTH
    set_metadata(
        font, VARIABLE_FAMILY, postscript_prefix(VARIABLE_FAMILY), widths[1], 400, italic, variable=True
    )
    return font


def build(output):
    hinter = shutil.which("ttfautohint")
    if hinter is None:
        raise ValueError("Install ttfautohint and add it to PATH.")
    static_families = {width: f"{BASE_FAMILY} Width {width * 10:.0f}" for width in WIDTHS}
    families = (BASE_FAMILY, VARIABLE_FAMILY, *static_families.values())
    inputs = {italic: source_path(italic) for italic in SOURCES}
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as directory:
        stage = Path(directory)
        folders = {family: stage / postscript_prefix(family) for family in families}
        for folder in folders.values():
            folder.mkdir()
            shutil.copyfile(ROOT / "LICENSE", folder / "LICENSE")

        for italic, path in inputs.items():
            with TTFont(path, recalcTimestamp=False) as source:
                variable = build_variable(source, italic)
                suffix = "-Italic" if italic else ""
                variable_path = folders[VARIABLE_FAMILY] / f"NotoSansSTVariable{suffix}.ttf"
                save_hinted(variable, variable_path, stage, hinter)

                for width, family in static_families.items():
                    prefix = postscript_prefix(family)
                    source_width = width + ITALIC_WIDTH_OFFSET if italic else width
                    for weight in WEIGHTS:
                        static = instantiateVariableFont(source, {"wdth": source_width, "wght": weight})
                        set_metadata(static, family, prefix, source_width, weight, italic, variable=False)
                        destination = folders[family] / f"{static['name'].getDebugName(6)}.ttf"
                        save_hinted(static, destination, stage, hinter)
                        if width == NORMAL_WIDTH:
                            # The base family and Width 850 share the same hinted design.
                            with TTFont(destination, recalcTimestamp=False) as base:
                                set_metadata(base, BASE_FAMILY, postscript_prefix(BASE_FAMILY),
                                             source_width, weight, italic, variable=False)
                                base.save(folders[BASE_FAMILY] / f"{base['name'].getDebugName(6)}.ttf")
                    print(f"Built {family} {'italic' if italic else 'upright'}.", flush=True)

        for folder in folders.values():
            destination = output / folder.name
            destination.mkdir(exist_ok=True)
            for file in sorted(folder.iterdir()):
                file.replace(destination / file.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Output directory (default: dist/release)")
    args = parser.parse_args()
    try:
        build(args.output)
    except (OSError, URLError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build failed: {error}\n")
    print(f"Built two variable and 48 static fonts in {args.output.resolve()}")


if __name__ == "__main__":
    main()
