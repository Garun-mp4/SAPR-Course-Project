"""Produce editable DXF sheets and publish previews from the released PDFs."""
import argparse
from math import atan2, degrees
from pathlib import Path
from shutil import copyfile

import ezdxf
import pymupdf
from reportlab.lib.units import mm

from drawings import PDF_NAME, ROOT, SHEET_NAMES
from eskd import FONT_NAME, FONT_PATH, font_size, register_font

PACKAGE = ROOT / "Комплект проекта" / "Чертежи"


def export_dxf(source, destination):
    register_font()
    cap_height = font_size(1)
    doc = ezdxf.new("R2018", units=4)
    doc.styles.add(FONT_NAME, font=FONT_PATH.name)
    doc.linetypes.new("DASHED_SAPR", dxfattribs={"pattern": [3, 2, -1]})
    doc.linetypes.new("CENTER_SAPR", dxfattribs={"pattern": [8.6, 6, -1, .6, -1]})
    msp = doc.modelspace()
    with pymupdf.open(source) as pdf:
        if len(pdf) != len(SHEET_NAMES):
            raise ValueError("Unexpected number of mechanical sheets")
        for index, page in enumerate(pdf):
            layer = SHEET_NAMES[index]
            doc.layers.new(layer)
            dx, dy = index % 3 * 440, (1 - index // 3) * 317

            def xy(point):
                return (round(dx + point[0] / mm, 4),
                        round(dy + (page.rect.height - point[1]) / mm, 4))

            for path in page.get_drawings():
                items = path["items"]
                dash_count = len((path["dashes"] or "").split()) - 3
                pattern = {2: "DASHED_SAPR", 4: "CENTER_SAPR"}.get(dash_count, "CONTINUOUS")
                attrs = {"layer": layer, "linetype": pattern,
                         "lineweight": round((path["width"] or 2) / mm * 100)}
                if len(items) == 4 and all(item[0] == "c" for item in items):
                    bounds = path["rect"]
                    center = (bounds.x0 + bounds.width / 2, bounds.y0 + bounds.height / 2)
                    radius = round(bounds.width / (2 * mm), 4)
                    if abs(bounds.width - bounds.height) > 0.01:
                        raise ValueError("Expected circular path")
                    if path["type"] == "f":
                        attrs["lineweight"] = 70
                    msp.add_circle(xy(center), radius, dxfattribs=attrs)
                    continue
                for operation, start, end in items:
                    if operation != "l":
                        raise ValueError(f"Unsupported path operation {operation}")
                    msp.add_line(xy(start), xy(end), dxfattribs=attrs)

            for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]:
                for line in block["lines"]:
                    angle = degrees(atan2(-line["dir"][1], line["dir"][0]))
                    for span in line["spans"]:
                        msp.add_text(span["text"], dxfattribs={
                            "insert": xy(span["origin"]), "height": round(span["size"] / cap_height, 4),
                            "rotation": angle, "layer": layer, "style": FONT_NAME,
                        })
    doc.saveas(destination)


def publish():
    documents = (
        (ROOT / "outputs" / PDF_NAME, SHEET_NAMES),
        (ROOT / "outputs" / "SAPR-001-specification.pdf", ("specification",)),
        (ROOT / "hardware" / "SAPR-001-E3.pdf", ("E3",)),
        (ROOT / "hardware" / "SAPR-001-PE3.pdf", ("PE3",)),
    )
    for source, names in documents:
        with pymupdf.open(source) as pdf:
            if len(pdf) != len(names):
                raise ValueError(f"Unexpected page count in {source.name}")
            for page, name in zip(pdf, names):
                page.get_pixmap(dpi=150, alpha=False).save(PACKAGE / "PNG" / f"SAPR-001-{name}.png")
        copyfile(source, PACKAGE / "PDF" / source.name)
    for name in ("SAPR-001-E3.kicad_sch", "SAPR-001-ESKD.kicad_wks"):
        copyfile(ROOT / "hardware" / name, PACKAGE / "Редактируемые" / name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dxf", type=Path, required=True)
    args = parser.parse_args()
    export_dxf(ROOT / "outputs" / PDF_NAME, args.dxf)
    publish()
