"""Validate the seven release families against the pinned Noto Sans inputs."""

import hashlib
import unittest

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

from build import OUTPUT, ROOT, SOURCE_DIR, SOURCES

STATIC_FAMILIES = {
    "Noto Sans ST": 85,
    "Noto Sans ST Width 800": 80,
    "Noto Sans ST Width 825": 82.5,
    "Noto Sans ST Width 850": 85,
    "Noto Sans ST Width 875": 87.5,
    "Noto Sans ST Width 900": 90,
}
VARIABLE_FAMILY = "Noto Sans ST Variable"
WEIGHTS = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold"}
LICENSE_SHA256 = "cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a"


def style_name(weight, italic):
    if not italic:
        return WEIGHTS[weight]
    return "Italic" if weight == 400 else f"{WEIGHTS[weight]} Italic"


def folder(family):
    return OUTPUT / family.replace(" ", "")


def unicode_maps(font):
    return {
        (table.platformID, table.platEncID, table.language, table.format): table.cmap
        for table in font["cmap"].tables if table.isUnicode()
    }


def outline(glyphs, name):
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    return pen.value


class BuiltFonts(unittest.TestCase):
    def test_output_families_and_licenses(self):
        families = (*STATIC_FAMILIES, VARIABLE_FAMILY)
        self.assertEqual(set(OUTPUT.iterdir()), {folder(family) for family in families})
        for family in families:
            with self.subTest(family=family):
                prefix = folder(family).name
                if family == VARIABLE_FAMILY:
                    files = {f"{prefix}.ttf", f"{prefix}-Italic.ttf"}
                else:
                    files = {
                        f"{prefix}-{style_name(weight, italic).replace(' ', '')}.ttf"
                        for weight in WEIGHTS for italic in (False, True)
                    }
                self.assertEqual({path.name for path in folder(family).iterdir()}, files | {"LICENSE"})
                license_data = (folder(family) / "LICENSE").read_bytes()
                self.assertEqual(hashlib.sha256(license_data).hexdigest(), LICENSE_SHA256)
                self.assertEqual(license_data, (ROOT / "LICENSE").read_bytes())

    def check_metadata(self, font, source, family, weight, italic, width):
        names = font["name"]
        style = style_name(weight, italic)
        if weight in (400, 700):
            self.assertEqual(names.getDebugName(1), family)
            self.assertEqual(names.getDebugName(2), style)
        else:
            self.assertEqual(names.getDebugName(1), f"{family} {WEIGHTS[weight]}")
            self.assertEqual(names.getDebugName(2), "Italic" if italic else "Regular")
        self.assertEqual(names.getDebugName(16), family)
        self.assertEqual(names.getDebugName(17), style)
        self.assertEqual(names.getDebugName(4), family if style == "Regular" else f"{family} {style}")
        self.assertTrue(names.getDebugName(3).endswith(f";wdth={width:g}"))
        for name_id in (0, 7, 13, 14):
            self.assertEqual(names.getDebugName(name_id), source["name"].getDebugName(name_id))

        version = names.getDebugName(5)
        self.assertTrue(version.startswith(f"{source['name'].getDebugName(5)}; ttfautohint"))
        self.assertIn("-a qsn", version)
        self.assertIn("-x 0", version)
        for tag in ("cvt ", "fpgm", "prep"):
            self.assertTrue(font.reader[tag])
        programs = (getattr(font["glyf"][name], "program", None) for name in font.getGlyphOrder())
        self.assertTrue(any(program and program.getBytecode() for program in programs))
        self.assertEqual(font["head"].modified, source["head"].modified)
        self.assertEqual(font["head"].macStyle & 3, int(weight == 700) | (int(italic) << 1))
        os2 = font["OS/2"]
        self.assertEqual((os2.usWidthClass, os2.usWeightClass), (5, weight))
        selection = int(italic) | ((weight == 700) << 5) | ((weight == 400 and not italic) << 6) | (1 << 8)
        self.assertEqual(os2.fsSelection & 0x0361, selection)
        self.assertEqual(unicode_maps(font), unicode_maps(source))
        self.assertEqual(font.getGlyphOrder(), source.getGlyphOrder())

        variable = family == VARIABLE_FAMILY
        stat = font["STAT"].table
        axes = stat.DesignAxisRecord.Axis
        self.assertEqual([axis.AxisTag for axis in axes], ["wght", "ital", "wdth"] if variable else ["wght", "ital"])
        values = stat.AxisValueArray.AxisValue
        weight_values = [value for value in values if value.AxisIndex == 0]
        self.assertEqual([value.Value for value in weight_values], list(WEIGHTS) if variable else [weight])
        standard = next((value for value in weight_values if value.Value == 400), None)
        if standard:
            self.assertEqual((standard.Format, standard.LinkedValue, standard.Flags), (3, 700, 2))
        slope, = (value for value in values if value.AxisIndex == 1)
        self.assertEqual(slope.Value, int(italic))
        self.assertEqual(getattr(slope, "LinkedValue", None), None if italic else 1)

    def compare_geometry(self, font, location, source, width, weight, tolerance):
        actual = font.getGlyphSet(location=location)
        expected = source.getGlyphSet(location={"wdth": width, "wght": weight})
        cmap = source.getBestCmap()
        for character in "aAeÉxÅАЁёЗфΕάह":
            name = cmap[ord(character)]
            self.assertAlmostEqual(actual[name].width, expected[name].width, delta=tolerance, msg=name)
            commands = outline(actual, name)
            upstream = outline(expected, name)
            self.assertEqual(len(commands), len(upstream), name)
            for (op, points), (expected_op, expected_points) in zip(commands, upstream):
                self.assertEqual((op, len(points)), (expected_op, len(expected_points)), name)
                for point, expected_point in zip(points, expected_points):
                    if point is None or expected_point is None:
                        self.assertIs(point, expected_point, name)
                    else:
                        for value, expected_value in zip(point, expected_point):
                            self.assertAlmostEqual(value, expected_value, delta=tolerance, msg=name)

    def test_metadata_hinting_and_interpolation(self):
        ps_names = []
        for italic, (_, cached_file, digest) in SOURCES.items():
            offset = 5 if italic else 0
            path = SOURCE_DIR / cached_file
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with TTFont(path) as source:
                for family, width in STATIC_FAMILIES.items():
                    prefix = folder(family).name
                    source_width = width + offset
                    for weight in WEIGHTS:
                        ps_name = f"{prefix}-{style_name(weight, italic).replace(' ', '')}"
                        path = folder(family) / f"{ps_name}.ttf"
                        with self.subTest(font=path.name), TTFont(path, checkChecksums=2) as font:
                            font.ensureDecompiled()
                            self.check_metadata(font, source, family, weight, italic, source_width)
                            self.assertEqual(font["name"].getDebugName(6), ps_name)
                            for tag in ("fvar", "avar", "gvar", "HVAR", "MVAR"):
                                self.assertNotIn(tag, font)
                            self.compare_geometry(font, None, source, source_width, weight, 2)
                            ps_names.append(ps_name)

                suffix = "-Italic" if italic else ""
                prefix = folder(VARIABLE_FAMILY).name
                path = folder(VARIABLE_FAMILY) / f"{prefix}{suffix}.ttf"
                with self.subTest(font=path.name), TTFont(path, checkChecksums=2) as font:
                    font.ensureDecompiled()
                    self.check_metadata(font, source, VARIABLE_FAMILY, 400, italic, 85 + offset)
                    names = font["name"]
                    axes = {axis.axisTag: axis for axis in font["fvar"].axes}
                    self.assertEqual(set(axes), {"wght", "wdth"})
                    weight = axes["wght"]
                    width = axes["wdth"]
                    self.assertEqual((weight.minValue, weight.defaultValue, weight.maxValue), (300, 400, 900))
                    self.assertAlmostEqual(width.minValue, 80 * 100 / 85, delta=0.00002)
                    self.assertEqual(width.defaultValue, 100)
                    self.assertAlmostEqual(width.maxValue, 90 * 100 / 85, delta=0.00002)
                    stat = font["STAT"].table
                    width_stat, = (v for v in stat.AxisValueArray.AxisValue if v.AxisIndex == 2)
                    self.assertEqual(stat.DesignAxisRecord.Axis[2].AxisNameID, width.axisNameID)
                    self.assertEqual(names.getDebugName(width_stat.ValueNameID), "Normal")
                    self.assertEqual(
                        (width_stat.RangeMinValue, width_stat.NominalValue, width_stat.RangeMaxValue),
                        (width.minValue, width.defaultValue, width.maxValue),
                    )
                    instances = font["fvar"].instances
                    self.assertEqual([i.coordinates for i in instances], [{"wght": w, "wdth": 100} for w in WEIGHTS])
                    ps_prefix = f"{prefix}{'Italic' if italic else ''}"
                    self.assertEqual(names.getDebugName(25), ps_prefix)
                    self.assertEqual(names.getDebugName(6), f"{ps_prefix}-Regular")
                    for instance in instances:
                        value = instance.coordinates["wght"]
                        self.assertEqual(names.getDebugName(instance.subfamilyNameID), style_name(value, italic))
                        ps_name = names.getDebugName(instance.postscriptNameID)
                        self.assertEqual(ps_name, f"{ps_prefix}-{WEIGHTS[value]}")
                        ps_names.append(ps_name)
                    for upright_width in (80, 82.5, 85, 87.5, 90):
                        for value in (300, 350, 400, 500, 550, 600, 700, 800, 900):
                            location = {"wdth": upright_width * 100 / 85, "wght": value}
                            self.compare_geometry(font, location, source, upright_width + offset, value, 3)

        self.assertEqual(len(ps_names), 56)
        self.assertEqual(len(set(ps_names)), 56)
        for name in ps_names:
            self.assertRegex(name, r"^[A-Za-z0-9-]{1,63}$")
