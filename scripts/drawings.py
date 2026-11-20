"""Export the dimensioned SAPR-001 sheets in millimeters."""
import argparse
import json
import os
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "hardware/profile.json").read_text(encoding="utf-8"))
WIDTH = PROFILE["enclosure_mm"]["length"]
DEPTH = PROFILE["enclosure_mm"]["width"]
BASE = PROFILE["enclosure_mm"]["base_height"]
WALL = PROFILE["enclosure_mm"]["wall"]
THICKNESS = PROFILE["enclosure_mm"]["lid_thickness"]
CENTERS = ((8, 8), (107, 8), (8, 72), (107, 72))
SLOTS = (53, 57, 61, 65, 69)
MARKS = (
    (3.5, 16.03, 48.26, 27.94, "U1  ESP32"),
    (73.5, 11, 15.24, 15.24, "U3  Ключ"),
    (77, 49.1, 25.5, 22.8, "U2  SCD41"),
)


class Sheet:
    def __init__(self, canvas):
        self.c = canvas

    def text(self, x, y, label, size=3, centered=False):
        self.c.setFont("SheetText", size * mm)
        self.c.setFillGray(0)
        draw = self.c.drawCentredString if centered else self.c.drawString
        draw(x * mm, y * mm, label)

    def line(self, x1, y1, x2, y2, weight=0.22, dashed=False):
        self.c.setLineWidth(weight * mm)
        self.c.setDash([2 * mm, 1.2 * mm] if dashed else [])
        self.c.line(x1 * mm, y1 * mm, x2 * mm, y2 * mm)
        self.c.setDash([])

    def rect(self, x, y, w, h, weight=0.42, dashed=False, gray=None):
        self.c.setLineWidth(weight * mm)
        self.c.setDash([2.2 * mm, 1.2 * mm] if dashed else [])
        if gray is not None:
            self.c.setFillGray(gray)
        self.c.rect(x * mm, y * mm, w * mm, h * mm, stroke=1, fill=gray is not None)
        self.c.setDash([])

    def circle(self, x, y, r, weight=0.32):
        self.c.setLineWidth(weight * mm)
        self.c.circle(x * mm, y * mm, r * mm, stroke=1, fill=0)

    def hdim(self, x1, x2, y, datum, label):
        self.line(x1, datum, x1, y - 2)
        self.line(x2, datum, x2, y - 2)
        self.line(x1, y, x2, y)
        for base, step in ((x1, 2), (x2, -2)):
            self.line(base, y, base + step, y + 0.65)
            self.line(base, y, base + step, y - 0.65)
        self.text((x1 + x2) / 2, y + 1.6, label, 2.85, centered=True)

    def vdim(self, y1, y2, x, datum, label):
        extension = x + (2 if x > datum else -2)
        self.line(datum, y1, extension, y1)
        self.line(datum, y2, extension, y2)
        self.line(x, y1, x, y2)
        for base, step in ((y1, 2), (y2, -2)):
            self.line(x, base, x + 0.65, base + step)
            self.line(x, base, x - 0.65, base + step)
        self.c.saveState()
        self.c.translate((x - 1.5) * mm, (y1 + y2) / 2 * mm)
        self.c.rotate(90)
        self.text(0, 0, label, 2.85, centered=True)
        self.c.restoreState()

    def header(self, title, section, page, code):
        self.rect(13, 11, 395, 275, 0.5)
        self.text(24, 271, title, 5.8)
        self.text(24, 263, section, 3.3)
        self.rect(244, 11, 164, 24, 0.35)
        self.line(244, 22, 408, 22, 0.32)
        self.line(356, 11, 356, 22, 0.32)
        self.line(381, 11, 381, 22, 0.32)
        self.text(249, 26, "АГТУ   /   САПР-001   /   Контроллер вентиляции", 3.5)
        self.text(249, 15, f"{code}   |   Размеры в мм   |   Ред. 01", 2.9)
        self.text(360, 15, "А3", 2.9)
        self.text(385, 15, f"{page} / 3", 2.9)

    def plan(self, x, y, scale=2, lid=False, modules=True):
        self.rect(x, y, scale * WIDTH, scale * DEPTH)
        for a, b in CENTERS:
            cx, cy = x + scale * a, y + scale * b
            if not lid:
                self.circle(cx, cy, scale * 4)
            self.circle(cx, cy, scale * (1.65 if lid else 1.3))
            self.line(cx - 3.8, cy, cx + 3.8, cy, 0.18)
            self.line(cx, cy - 3.8, cx, cy + 3.8, 0.18)
        if lid:
            for b in SLOTS:
                self.rect(x + scale * 77, y + scale * b, scale * 26, scale * 2, 0.3)
            return

        self.rect(x + scale * WALL, y + scale * WALL,
                  scale * (WIDTH - 2 * WALL), scale * (DEPTH - 2 * WALL), 0.28)
        ledges = ((66, 44, 45, 2), (65, 44, 2, 32), (4, 15, 47, 3), (4, 40, 47, 3),
                   (73, 11, 17, 2), (73, 24, 17, 2), (77, 49, 26, 2), (76, 70, 26, 2))
        for a, b, w, h in ledges:
            self.rect(x + scale * a, y + scale * b, scale * w, scale * h, 0.26)
        self.rect(x, y + scale * 21, scale * WALL, scale * 18, 0.26, dashed=True)
        for b, span in ((10, 14), (29, 12)):
            self.rect(x + scale * (WIDTH - WALL), y + scale * b, scale * WALL, scale * span, 0.26, dashed=True)
        if modules:
            for a, b, w, h, name in MARKS:
                self.rect(x + scale * a, y + scale * b, scale * w, scale * h, 0.3, gray=0.94)
                self.text(x + scale * (a + w / 2), y + scale * (b + h / 2) - 1, name, 3, centered=True)
            self.rect(x + scale * 0.4, y + scale * 26, scale * 8.1, scale * 8, 0.24, dashed=True)
            self.rect(x + scale * 51.76, y + scale * 16.03, scale * 13, scale * 27.94, 0.2, dashed=True)
            self.text(x + scale * 58.2, y + scale * 29, "Антенна", 2.5, centered=True)


def rows(s, x, y, lines):
    for i, label in enumerate(lines):
        s.text(x, y - i * 5.5, label, 2.95)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf")
    args = parser.parse_args()
    pdfmetrics.registerFont(TTFont("SheetText", str(args.font)))
    canvas = Canvas(str(ROOT / "outputs/SAPR-001-drawings.pdf"), (420 * mm, 297 * mm), invariant=True)
    canvas.setTitle("САПР-001 — монтаж и детали корпуса")
    s = Sheet(canvas)

    x, y = 44, 66
    s.header("Корпус контроллера. Сборочный чертёж", "Монтаж модулей и внешние размеры", 1, "САПР-001 СБ")
    s.plan(x, y, scale=2)
    s.hdim(x, x + 2 * WIDTH, 52, y, "115")
    s.vdim(y, y + 2 * DEPTH, 33, x, "80")
    s.text(x, 233, "Вид сверху со снятой крышкой   М 2:1", 3.4)
    rx, ry = 308, 175
    s.rect(rx, ry, DEPTH, BASE + THICKNESS)
    s.line(rx, ry + BASE, rx + DEPTH, ry + BASE, 0.26)
    s.rect(rx + 21, ry + 5, 18, 14, 0.3)
    s.vdim(ry, ry + BASE + THICKNESS, 396, rx + DEPTH, "33")
    s.text(rx, ry + 40, "Левая сторона   М 1:1", 3.35)
    rows(s, 298, 147, [
        "01  Основание корпуса",
        "02  Съёмная крышка",
        "03  Четыре винта для пластика Ø3",
        "U1  ESP32-DevKitC V4",
        "U2  Датчик CO2 SCD41",
        "U3  Силовой ключ Pololu №2810",
    ])
    rows(s, 298, 101, [
        "Платы показаны габаритными телами.",
        "Фиксация на опорах изолирующей лентой.",
        "Вентилятор и источники питания внешние.",
        "Зону антенны оставить свободной.",
    ])
    canvas.showPage()

    s.header("Основание корпуса", "Монтажные опоры, стойки и проходы для кабелей", 2, "САПР-001.01")
    s.plan(x, y, scale=2, modules=False)
    s.hdim(x, x + 2 * WIDTH, 52, y, "115")
    s.vdim(y, y + 2 * DEPTH, 33, x, "80")
    s.text(x, 233, "Вид сверху   М 2:1", 3.4)
    rx, ry = 308, 179
    s.rect(rx, ry, DEPTH, BASE)
    s.rect(rx + 10, ry + 6, 14, 13, 0.32)
    s.rect(rx + 29, ry + 6, 12, 11, 0.32)
    s.vdim(ry, ry + BASE, 396, rx + DEPTH, "30")
    s.text(rx, ry + 36, "Правая сторона   М 1:1", 3.35)
    rows(s, 298, 161, [
        "Стенки и пол — 3.",
        "Стойки Ø8 с пилотными Ø2,6 × 11.",
        "Центры от угла XY:",
        "(8, 8), (107, 8), (8, 72), (107, 72).",
        "Проходы справа — 14 × 13 и 12 × 11.",
        "Их нижние кромки на высоте 6.",
        "Проход слева — 18 × 14 на высоте 5.",
    ])
    rows(s, 298, 109, [
        "Опоры U1 и U3 на 3 выше пола.",
        "Опоры U2 на 5 выше пола.",
        "Перегородки отсека U2 на 22 выше пола.",
        "Кромки проходов защитить втулками.",
    ])
    rows(s, 298, 78, [
        "Координаты опор и перегородок",
        "приведены в документации к сборке.",
    ])
    canvas.showPage()

    s.header("Съёмная крышка", "Отверстия крепления и вентиляции", 3, "САПР-001.02")
    s.plan(x, y, scale=2, lid=True)
    s.hdim(x, x + 2 * WIDTH, 52, y, "115")
    s.vdim(y, y + 2 * DEPTH, 33, x, "80")
    s.text(x, 233, "Вид сверху   М 2:1", 3.4)
    rx, ry = 286, 207
    s.rect(rx, ry, WIDTH, THICKNESS)
    s.text(rx, ry + 8, "Продольный вид   М 1:1", 3.35)
    rows(s, 298, 188, [
        "Толщина крышки — 3.",
        "Четыре сквозных отверстия Ø3,3.",
        "Центры от угла XY:",
        "(8, 8), (107, 8), (8, 72), (107, 72).",
        "Пять вентиляционных щелей 26 × 2.",
        "Начало каждой щели по X — 77.",
        "Нижние кромки по Y:",
        "53, 57, 61, 65, 69.",
    ])
    rows(s, 298, 135, [
        "При монтаже расположить щели над SCD41.",
        "Оставить свободный доступ воздуха.",
    ])
    canvas.showPage()
    canvas.save()


if __name__ == "__main__":
    main()
