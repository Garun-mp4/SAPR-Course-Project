"""Frame geometry for the ESKD PDF and KiCad releases (ГОСТ Р 2.104-2023, appendix Б)."""
import os
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_PATH = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/GOST_BU.ttf"
FONT_NAME = "GostTypeB"


def register_font(path=FONT_PATH):
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(path)))


def font_size(height):
    return height * mm * 1000 / pdfmetrics.getFont(FONT_NAME).face.capHeight


def frame(width, height, designation, name, *, material="", scale="", form=1, paper="А3", version="02",
          sheet=1, sheets=1):
    """Yield immutable page items in mm from the lower-left corner."""
    items = []

    def line(x1, y1, x2, y2, stroke=0.25):
        items.append(("line", (x1, y1, x2, y2, stroke)))

    def text(x, y, value, h=2.5, centered=True, rotation=0):
        if value:
            items.append(("text", (x, y, value, h, centered, rotation)))

    x = width - 190
    y = 5
    h = 55 if form == 1 else 40
    for args in ((20, 5, width - 5, 5), (20, 5, 20, height - 5),
                 (20, height - 5, width - 5, height - 5), (width - 5, 5, width - 5, height - 5)):
        line(*args, 0.5)
    line(x, y, x, y + h, 0.5)
    line(x, y + h, x + 185, y + h, 0.5)
    line(x + 65, y, x + 65, y + h, 0.5)

    roles = ("Утв.", "Н. контр.", "", "Т. контр.", "Пров.", "Разраб.") if form == 1 else (
        "Утв.", "Н. контр.", "", "Пров.", "Разраб.")
    top_roles = 5 * len(roles)
    for row in range(5, h, 5):
        line(x, y + row, x + 65, y + row)
    for col in (17, 40, 55):
        line(x + col, y, x + col, y + h)
    line(x + 7, y + top_roles, x + 7, y + h)
    for col, label in ((3.5, "Изм."), (12, "Лист"), (28.5, "№ докум."), (47.5, "Подп."), (60, "Дата")):
        text(x + col, y + top_roles + 1.6, label, 1.8)
    for index, role in enumerate(roles):
        text(x + 1, y + 5 * index + 1.2, role, 1.8, False)
    text(x + 18.0, y + top_roles - 3.6, "Сулейманов", 2.5, False)

    id_base = h - 15
    line(x + 65, y + id_base, x + 185, y + id_base, 0.5)
    line(x + 175, y + id_base, x + 175, y + h)
    line(x + 175, y + h - 5, x + 185, y + h - 5)
    text(x + 180, y + h - 3.5, "Вер.", 1.8)
    text(x + 180, y + id_base + 3.3, version, 2.5)
    text(x + 120, y + id_base + 4.3, designation, 5)
    line(x + 135, y, x + 135, y + id_base)
    name_lines = name.split("\n")
    if form == 1:
        line(x + 65, y + 15, x + 185, y + 15)
        for col in (150, 167):
            line(x + col, y + 20, x + col, y + 40)
        for col in (140, 145):
            line(x + col, y + 20, x + col, y + 35)
        line(x + 135, y + 35, x + 185, y + 35)
        line(x + 135, y + 20, x + 185, y + 20)
        line(x + 155, y + 15, x + 155, y + 20)
        for col, label in ((142.5, "Лит."), (158.5, "Масса"), (176, "Масштаб")):
            text(x + col, y + 36.6, label, 1.8)
        text(x + 176, y + 26, scale, 3.5)
        text(x + 145, y + 16.5, "Лист", 1.8)
        text(x + 167, y + 16.5, "Листов", 1.8)
        text(x + 145, y + 11.3, str(sheet))
        text(x + 180, y + 16.4, str(sheets) if sheet == 1 else "")
        text(x + 100, y + 5.5, material, 3.5)
        for i, label in enumerate(name_lines):
            text(x + 100, y + 29 - 4.6 * i, label, 3.5)
    else:
        for row in (15, 20):
            line(x + 135, y + row, x + 185, y + row)
        for col in (150, 165):
            line(x + col, y + 15, x + col, y + 25)
        for col in (140, 145):
            line(x + col, y + 15, x + col, y + 20)
        for col, label in ((142.5, "Лит."), (157.5, "Лист"), (175, "Листов")):
            text(x + col, y + 21.6, label, 1.8)
        text(x + 157.5, y + 16.5, str(sheet))
        text(x + 175, y + 16.5, str(sheets) if sheet == 1 else "")
        for i, label in enumerate(name_lines):
            text(x + 100, y + 14.5 - 4.6 * i, label, 3.5)

    text(x + 160, y + 5, "АГТУ · ДИНРБ-41", 2.5)
    text(x + 162, 1.6, f"Формат {paper}", 1.8)
    # Additional fields 19–23 are left available for registration.
    lower = 5
    for label, length in (("Инв. № подл.", 25), ("Подп. и дата", 35), ("Взам. инв. №", 25),
                          ("Инв. № дубл.", 25), ("Подп. и дата", 35)):
        upper = lower + length
        line(8, lower, 20, lower)
        line(8, lower, 8, upper)
        line(13, lower, 13, upper)
        text(11.5, (lower + upper) / 2, label, 1.8, rotation=90)
        lower = upper
    line(8, lower, 20, lower)
    if form == 1:
        line(20, height - 19, 90, height - 19)
        line(90, height - 19, 90, height - 5)
        text(55, height - 13, designation, 3.5, rotation=180)
    return items


def pdf_frame(canvas, items):
    for kind, values in items:
        if kind == "line":
            x1, y1, x2, y2, stroke = values
            canvas.setLineWidth(stroke * mm)
            canvas.line(x1 * mm, y1 * mm, x2 * mm, y2 * mm)
        else:
            x, y, label, h, centered, rotation = values
            canvas.saveState()
            canvas.translate(x * mm, y * mm)
            canvas.rotate(rotation)
            canvas.setFont(FONT_NAME, font_size(h))
            method = canvas.drawCentredString if centered else canvas.drawString
            method(0, 0, label)
            canvas.restoreState()
