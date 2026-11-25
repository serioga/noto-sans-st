"""Validate default-build fonts against the pinned inputs and OpenType metadata."""

import hashlib
import unittest
from io import BytesIO

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from build import ROOT, SOURCE_DIR, SOURCES

FAMILY = "Noto Sans ST"
PREFIX = "NotoSansST"
DIST = ROOT / "dist"
STYLES = ("Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black")
WEIGHTS = dict(zip(range(100, 901, 100), STYLES))
LICENSE_SHA256 = "cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a"


def style_name(weight, italic):
    if not italic:
        return WEIGHTS[weight]
    return "Italic" if weight == 400 else f"{WEIGHTS[weight]} Italic"


def output_path(weight, italic, variable):
    if variable:
        suffix = "Italic-Variable" if italic else "Variable"
        return DIST / "variable" / f"{PREFIX}-{suffix}.ttf"
    suffix = style_name(weight, italic).replace(" ", "")
    return DIST / "static" / f"{PREFIX}-{suffix}.ttf"


def outline(glyphs, name):
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    return pen.value


class BuiltFonts(unittest.TestCase):
    def test_outputs_and_ofl(self):
        for variable in (False, True):
            expected = {
                output_path(weight, italic, variable)
                for italic in (False, True)
                for weight in ((400,) if variable else WEIGHTS)
            }
            directory = DIST / ("variable" if variable else "static")
            self.assertEqual(set(directory.glob("*.ttf")), expected)
        self.assertEqual(hashlib.sha256((DIST / "LICENSE").read_bytes()).hexdigest(), LICENSE_SHA256)
        self.assertEqual((DIST / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())

    def check_metadata(self, font, source, weight, italic, variable):
        names = font["name"]
        style = style_name(weight, italic)
        linked_to_regular = weight in (400, 700)
        self.assertEqual(names.getDebugName(1), FAMILY if linked_to_regular else f"{FAMILY} {WEIGHTS[weight]}")
        self.assertEqual(names.getDebugName(2), style if linked_to_regular else ("Italic" if italic else "Regular"))
        self.assertEqual(names.getDebugName(16), FAMILY)
        self.assertEqual(names.getDebugName(17), style)
        if variable:
            full_name = f"{FAMILY}{' Italic' if italic else ''} Variable"
        else:
            full_name = FAMILY if weight == 400 and not italic else f"{FAMILY} {style}"
        self.assertEqual(names.getDebugName(4), full_name)
        for name_id in (0, 7, 13, 14):
            self.assertEqual(names.getDebugName(name_id), source["name"].getDebugName(name_id))

        upstream_version = source["name"].getDebugName(5)
        version = names.getDebugName(5)
        if variable:
            self.assertEqual(version, upstream_version)
        else:
            self.assertTrue(version.startswith(f"{upstream_version}; ttfautohint"))
            self.assertIn("-a qsn", version)
            self.assertIn("-x 0", version)
            for tag in ("cvt ", "fpgm", "prep"):
                self.assertTrue(font.reader[tag])
            self.assertTrue(any(
                glyph.get("program") is not None and glyph["program"].getBytecode()
                for glyph in (font["glyf"][name].__dict__ for name in font.getGlyphOrder())
            ))

        self.assertEqual(font["OS/2"].usWidthClass, 5)
        self.assertEqual(font["OS/2"].usWeightClass, weight)
        selection = int(italic) | ((weight == 700) << 5) | ((weight == 400 and not italic) << 6) | (1 << 8)
        self.assertEqual(font["OS/2"].fsSelection & 0x0361, selection)
        self.assertEqual(font["head"].macStyle & 0x3, (weight == 700) | (italic << 1))

        stat = font["STAT"].table
        axes = stat.DesignAxisRecord.Axis
        self.assertEqual([(axis.AxisTag, axis.AxisOrdering) for axis in axes], [("wght", 0), ("ital", 1)])
        self.assertEqual(names.getDebugName(stat.ElidedFallbackNameID), "Regular")
        values = stat.AxisValueArray.AxisValue
        self.assertEqual(
            {(entry.AxisIndex, entry.Value) for entry in values},
            {(0, value) for value in (WEIGHTS if variable else (weight,))} | {(1, int(italic))},
        )
        for entry in values:
            if entry.AxisIndex == 0:
                expected_name = WEIGHTS[entry.Value]
                linked_value = 700 if entry.Value == 400 else None
            else:
                expected_name = "Italic" if italic else "Regular"
                linked_value = None if italic else 1
            self.assertEqual(names.getDebugName(entry.ValueNameID), expected_name)
            self.assertEqual(entry.Format, 3 if linked_value is not None else 1)
            self.assertEqual(entry.Flags, 2 if linked_value is not None else 0)
            self.assertEqual(getattr(entry, "LinkedValue", None), linked_value)

        prefix = f"{PREFIX}Variable{'Italic' if italic else ''}" if variable else PREFIX
        expected_ps = f"{prefix}-{WEIGHTS[weight] if variable else style.replace(' ', '')}"
        self.assertEqual(names.getDebugName(6), expected_ps)
        self.assertTrue(names.getDebugName(3).endswith(f";{expected_ps};wdth=85"))
        self.assertEqual(names.getDebugName(25), prefix if variable else None)
        if not variable:
            for tag in ("fvar", "avar", "gvar", "HVAR", "MVAR"):
                self.assertNotIn(tag, font)
            return [expected_ps]

        fvar = font["fvar"]
        self.assertEqual(len(fvar.axes), 1)
        axis = fvar.axes[0]
        self.assertEqual((axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue), ("wght", 100, 400, 900))
        self.assertEqual(axis.axisNameID, axes[0].AxisNameID)
        self.assertEqual(len(fvar.instances), 9)
        self.assertEqual({instance.coordinates["wght"] for instance in fvar.instances}, set(WEIGHTS))
        ps_names = []
        for instance in fvar.instances:
            instance_weight = instance.coordinates["wght"]
            self.assertEqual(instance.coordinates, {"wght": instance_weight})
            self.assertEqual(names.getDebugName(instance.subfamilyNameID), style_name(instance_weight, italic))
            instance_ps = names.getDebugName(instance.postscriptNameID)
            self.assertEqual(instance_ps, f"{prefix}-{WEIGHTS[instance_weight]}")
            ps_names.append(instance_ps)
        return ps_names

    def test_metadata_coverage_and_interpolation(self):
        ps_names = []
        for italic in (False, True):
            _, filename, digest = SOURCES[italic]
            path = SOURCE_DIR / filename
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            with TTFont(path, recalcTimestamp=False) as source:
                cmap = source.getBestCmap()
                self.assertTrue(all(ord(char) in cmap for char in "АБЯабяЁёЄєІіЇїҐґ"))
                for variable in (True, False):
                    for weight in ((400,) if variable else WEIGHTS):
                        path = output_path(weight, italic, variable)
                        with self.subTest(font=path.name), TTFont(path, checkChecksums=2) as font:
                            font.ensureDecompiled()
                            ps_names.extend(self.check_metadata(font, source, weight, italic, variable))
                            self.assertEqual(font.getBestCmap(), cmap)
                            self.assertEqual(font.getGlyphOrder(), source.getGlyphOrder())
                            self.assertEqual(font.getTableData("cmap"), source.getTableData("cmap"))
                            coordinates = {"wdth": 85}
                            if not variable:
                                coordinates["wght"] = weight
                            reference = instantiateVariableFont(source, coordinates)
                            with BytesIO() as data:
                                # Compare serialized tables before another parse and recompile.
                                reference.save(data)
                                data.seek(0)
                                with TTFont(data) as expected:
                                    self.assertEqual(font["head"].modified, expected["head"].modified)
                                    tags = ["hmtx", "GDEF", "GPOS", "GSUB"]
                                    if variable:
                                        tags.extend(("glyf", "gvar", "avar", "HVAR", "MVAR"))
                                    else:
                                        glyphs = font.getGlyphSet()
                                        expected_glyphs = expected.getGlyphSet()
                                        for name in expected.getGlyphOrder():
                                            self.assertEqual(outline(glyphs, name), outline(expected_glyphs, name), name)
                                    for tag in tags:
                                        if tag in expected:
                                            self.assertEqual(
                                                hashlib.sha256(font.reader[tag]).digest(),
                                                hashlib.sha256(expected.reader[tag]).digest(),
                                                f"{tag} differs from direct upstream interpolation",
                                            )
        self.assertEqual(len(ps_names), 36)
        self.assertEqual(len(set(ps_names)), 36)
        for name in ps_names:
            self.assertRegex(name, r"^[A-Za-z0-9-]{1,63}$")
