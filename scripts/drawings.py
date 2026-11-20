"""Export the SAPR-001 drawing set from its checked mechanical profile."""
import argparse
import json
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from eskd import FONT_NAME, FONT_PATH, font_size, frame, pdf_frame, register_font

ROOT = Path(__file__).resolve().parents[1]
H = json.loads((ROOT / "hardware/profile.json").read_text(encoding="utf-8"))["enclosure_mm"]
W, D, B = (H[key] for key in ("length", "width", "base_height"))
WALL, FLOOR, LID = (H[key] for key in ("wall", "floor", "lid_thickness"))
STUD, SLOT = H["studs"], H["lid_slots"]


def mm_text(value):
    return f"{value:g}".replace(".", ",")


class Sheet:
    def __init__(self, canvas):
        self.c = canvas

    def text(self, x, y, label, h=2.5, centered=False):
        self.c.setFont(FONT_NAME, font_size(h))
        (self.c.drawCentredString if centered else self.c.drawString)(x * mm, y * mm, label)

    def line(self, x1, y1, x2, y2, weight=0.25, style="solid"):
        self.c.setLineWidth(weight * mm)
        patterns = {"hidden": (2, 1), "center": (6, 1, 0.6, 1)}
        self.c.setDash([v * mm for v in patterns.get(style, ())])
        self.c.line(x1 * mm, y1 * mm, x2 * mm, y2 * mm)
        self.c.setDash([])

    def rect(self, x, y, w, h, weight=0.5, style="solid"):
        for a, b, c, d in ((x,y,x+w,y),(x+w,y,x+w,y+h),(x+w,y+h,x,y+h),(x,y+h,x,y)):
            self.line(a, b, c, d, weight, style)

    def circle(self, x, y, r, weight=0.5):
        self.c.setLineWidth(weight * mm)
        self.c.circle(x * mm, y * mm, r * mm, stroke=1, fill=0)

    def arrow(self, x, y, direction):
        for offset in (-0.65, 0.65):
            if direction in ("left", "right"):
                self.line(x, y, x + (2.4 if direction == "left" else -2.4), y + offset)
            else:
                self.line(x, y, x + offset, y + (2.4 if direction == "down" else -2.4))

    def hdim(self, x1, x2, y, source, label):
        extension = y + (2 if y > source else -2)
        for x in (x1, x2):
            self.line(x, source, x, extension)
        self.line(x1, y, x2, y)
        self.arrow(x1, y, "left")
        self.arrow(x2, y, "right")
        if x2 - x1 < 8:
            self.line(x2, y, x2 + 7, y)
            self.text(x2 + 3.8, y + 1.2, label, centered=True)
        else:
            self.text((x1 + x2) / 2, y + 1.2, label, centered=True)

    def vdim(self, y1, y2, x, source, label):
        extension = x + (2 if x > source else -2)
        for y in (y1, y2):
            self.line(source, y, extension, y)
        self.line(x, y1, x, y2)
        self.arrow(x, y1, "down")
        self.arrow(x, y2, "up")
        if y2 - y1 < 6:
            self.line(x, y2, x, y2 + 5)
            self.line(x - 7, y2 + 5, x, y2 + 5)
            self.text(x - 4.2, y2 + 6, label, centered=True)
            return
        self.c.saveState()
        self.c.translate((x - 1.4) * mm, (y1 + y2) / 2 * mm)
        self.c.rotate(90)
        self.text(0, 0, label, centered=True)
        self.c.restoreState()

    def hatch(self, x, y, w, h, slope):
        self.hatched_section(x, y, [(0, 0), (w, 0), (w, h), (0, h)], slope)

    def hatched_section(self, x, y, outline, slope=1):
        path = self.c.beginPath()
        path.moveTo((x + outline[0][0]) * mm, (y + outline[0][1]) * mm)
        for a, b in outline[1:]:
            path.lineTo((x + a) * mm, (y + b) * mm)
        path.close()
        width, height = (max(vertex[axis] for vertex in outline) for axis in (0, 1))
        self.c.saveState()
        self.c.clipPath(path, stroke=0)
        offset = -height + 1.5
        while offset < width + height:
            self.line(x + offset, y, x + offset + slope * height, y + height, 0.18)
            offset += 2.4
        self.c.restoreState()
        self.c.setLineWidth(0.5 * mm)
        self.c.drawPath(path)

    def leader(self, x, y, end_x, end_y, position):
        self.c.setLineWidth(0.25 * mm)
        self.c.circle(x * mm, y * mm, 0.45 * mm, stroke=0, fill=1)
        self.line(x, y, end_x, end_y)
        self.line(end_x, end_y, end_x + 10, end_y)
        self.text(end_x + 5, end_y + 1.0, str(position), 3.5, centered=True)

    def notes(self, x, y, title, lines, width):
        self.text(x, y, title, 3.5)
        y -= 7
        for line in lines:
            words = line.split()
            segment = ""
            for word in words:
                candidate = (segment + " " + word).strip()
                if segment and pdfmetrics.stringWidth(candidate, FONT_NAME, font_size(2.5)) / mm > width:
                    self.text(x, y, segment)
                    y -= 5
                    segment = word
                else:
                    segment = candidate
            self.text(x, y, segment)
            y -= 5
        return y

    def frame(self, code, name, material="", scale="2:1"):
        pdf_frame(self.c, frame(420, 297, code, name, material=material, scale=scale))

    def trace(self, x, y, width, label):
        for a, b in ((x - 5, x), (x + width, x + width + 5)):
            self.line(a, y, b, y, 0.7)
        for stop in (x - 4, x + width + 4):
            self.line(stop, y - 5, stop, y)
            self.arrow(stop, y, "up")
            self.text(stop - 0.5, y - 9, label, 3.5, centered=True)


def plan(s, x, y, scale=2, kind="base"):
    s.rect(x, y, W * scale, D * scale)
    is_lid = kind == "lid"
    for a, b in STUD["centers"]:
        cx, cy = x + scale * a, y + scale * b
        if not is_lid:
            s.circle(cx, cy, scale * STUD["diameter"] / 2)
        s.circle(cx, cy, scale * STUD["clearance_diameter" if is_lid else "pilot_diameter"] / 2)
        for px, py in ((5, 0), (0, 5)):
            s.line(cx - px, cy - py, cx + px, cy + py, 0.18, "center")
    if is_lid:
        for b in SLOT["y"]:
            s.rect(x + scale * SLOT["x"], y + scale * b, scale * SLOT["length"], scale * SLOT["width"])
        return
    s.rect(x + scale * WALL, y + scale * WALL, scale * (W - 2 * WALL), scale * (D - 2 * WALL))
    for feature in H["supports"]:
        a, b, _ = feature["min"]
        c, d, _ = feature["max"]
        s.rect(x + scale * a, y + scale * b, scale * (c - a), scale * (d - b), 0.35)
    for port in H["ports"]:
        a = 0 if port["side"] == "left" else W - WALL
        s.rect(x + scale * a, y + scale * port["y"], scale * WALL, scale * port["width"], 0.25, "hidden")
    if kind == "assembly":
        for feature in H["modules"]:
            a, b, _ = feature["min"]
            c, d, _ = feature["max"]
            s.rect(x + scale * a, y + scale * b, scale * (c - a), scale * (d - b), 0.25, "hidden")
            if feature["ref"] != "A1 USB":
                s.text(x + scale * (a + c) / 2, y + scale * (b + d) / 2,
                       f'{feature["ref"]} {feature["name"]}', centered=True)
        end = H["modules"][0]["max"][0]
        s.rect(x + scale * end, y + scale * 16.03, scale * 13, scale * 27.94, 0.25, "center")
        s.text(x + scale * (end + 6.5), y + scale * 29, "Антенна", centered=True)


def side_view(s, x, y, side, closed):
    height = B + LID if closed else B
    s.rect(x, y, D, height)
    if closed:
        s.line(x, y + B, x + D, y + B, 0.5)
    for p in (port for port in H["ports"] if port["side"] == side):
        # Projection convention: +Z up, looking +X from the left, -X from the right.
        offset = D - p["y"] - p["width"] if side == "left" else p["y"]
        s.rect(x + offset, y + p["z"], p["width"], p["height"])
    s.vdim(y, y + height, x + D + 8, x + D, mm_text(height))


def section(s, x, y, closed):
    # The base is one solid. Preserve continuous hatching across the floor, walls and bosses.
    right = W - WALL
    base = [(0, 0), (W, 0), (W, B), (right, B), (right, FLOOR)]
    if closed:
        base += [(67, FLOOR), (67, 25), (65, 25), (65, FLOOR)]
    else:
        r = STUD["pilot_diameter"] / 2
        stop = B - STUD["depth"]
        for center in (107, 8):
            base += [(center+4, FLOOR), (center+4, B), (center+r, B), (center+r, stop),
                     (center-r, stop), (center-r, B), (center-4, B), (center-4, FLOOR)]
    base += [(WALL, FLOOR), (WALL, B), (0, B)]
    s.hatched_section(x, y, base)
    if closed:
        s.hatch(x, y + B, SLOT["x"], LID, slope=-1)
        end = SLOT["x"] + SLOT["length"]
        s.hatch(x + end, y + B, W - end, LID, slope=-1)
        sensor = H["modules"][3]
        a, _, z = sensor["min"]
        b, _, top = sensor["max"]
        s.rect(x + a, y + z, b - a, top - z, 0.25, "hidden")
        s.leader(x + 45, y + 1.5, x + 30, y + 12, 1)
        s.leader(x + 45, y + B + 1.5, x + 36, y + 42, 2)
    else:
        for a in (8, 107):
            s.line(x + a, y + 14, x + a, y + 35, 0.18, "center")
        s.vdim(y + B - STUD["depth"], y + B, x + 22, x + 8, "11")
        s.vdim(y, y + FLOOR, x + 45, x + 53, "3")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=FONT_PATH)
    args = parser.parse_args()
    register_font(args.font)
    c = Canvas(str(ROOT / "outputs/SAPR-001-drawings.pdf"), (420 * mm, 297 * mm), invariant=True)
    c.setTitle("САПР.001.000. Чертежи контроллера")
    s = Sheet(c)
    x, y = 47, 108

    s.frame("САПР.001.000 СБ", "Контроллер вентиляции\nСборочный чертёж")
    plan(s, x, y, kind="assembly")
    s.hdim(x, x + W * 2, 97, y, "115*")
    s.vdim(y, y + D * 2, 33, x, "80*")
    s.trace(x, y + 124, 2 * W, "А")
    s.leader(x + 16, y + 16, x + 39, y + 8, 3)
    s.leader(x + 80, y + 76, x + 91, y + 91, 4)
    s.leader(x + 168, y + 135, x + 155, y + 147, 5)
    s.leader(x + 154, y + 36, x + 133, y + 55, 6)
    side_view(s, 307, 217, "left", True)
    s.text(306, 257, "Вид слева (1:1)", 3.5)
    s.notes(302, 200, "Технические требования", (
        "1. * Размеры для справок.",
        "2. Платы поз. 4–6 установить на опоры. Зафиксировать съёмной электроизоляционной лентой.",
        "3. Проложить жгут по Э3 с разгрузкой натяжения. Проёмы защитить втулками поз. 15.",
        "4. Оставить отверстия над A2 и зону антенны A1 свободными.",
        "5. Крышку установить щелями над A2 и закрепить четырьмя винтами поз. 3.",
        "6. Вид сверху дан со снятой крышкой. Платы показаны габаритами.",
        "7. Вентилятор и источники питания подключаются снаружи.",), 105)
    s.text(48, 79, "А–А (1:1)", 3.5)
    section(s, 48, 23, True)
    c.showPage()

    s.frame("САПР.001.001", "Основание", H["material"])
    plan(s, x, y + 2)
    s.hdim(x, x + W * 2, 99, y + 2, "115")
    s.vdim(y + 2, y + 2 + D * 2, 33, x, "80")
    s.trace(x, y + 18, 2 * W, "Б")
    side_view(s, 308, 225, "right", False)
    s.text(306, 262, "Вид справа (1:1)", 3.5)
    next_y = s.notes(300, 211, "Размеры от баз X, Y и Z", (
        "Стойки 4 отв. Ø2,6 ±0,10, глубина 11. Наружный Ø8.",
        "Центры X/Y: 8/8, 107/8, 8/72, 107/72.",
        "Слева проём 18×14, Y = 21, Z = 5.",
        "Справа проёмы 14×13 и 12×11, Y = 10 и 29, Z = 6.",
        "Стенки и дно 3. От левого нижнего угла вида X направлена вправо, Y вверх. База Z — дно.",
        "Координаты объёмов опор X / Y / Z:",), 112)
    for f in H["supports"]:
        intervals = ["–".join(map(mm_text, p)) for p in zip(f["min"], f["max"])]
        s.text(300, next_y, f'{f["ref"]}: ' + " / ".join(intervals), 2.5)
        next_y -= 4.7
    s.notes(300, next_y - 1, "Требования к детали", (
        "Неуказанные линейные отклонения ±0,3.",
        "Печать дном на столе. Удалить заусенцы.",
        "Пилотные отверстия проверить пробой крепежа.",), 110)
    s.text(48, 79, "Б–Б (1:1)", 3.5)
    section(s, 48, 29, False)
    c.showPage()

    s.frame("САПР.001.002", "Крышка", H["material"])
    plan(s, x, y, kind="lid")
    s.hdim(x, x + W * 2, 97, y, "115")
    s.vdim(y, y + D * 2, 33, x, "80")
    s.rect(289, 216, W, LID)
    s.vdim(216, 216 + LID, 410, 404, "3")
    s.text(289, 229, "Вид спереди (1:1)", 3.5)
    s.notes(296, 191, "Крепление и вентиляция", (
        "4 отв. Ø3,3 с верхним отклонением +0,2.",
        "Центры отверстий от нижнего левого угла (X/Y): 8/8, 107/8, 8/72, 107/72.",
        "5 щелей 26×2. Начало по X = 77.",
        "Координаты нижних кромок по Y: 53, 57, 61, 65, 69.",
        "Толщина 3. Неуказанные линейные отклонения ±0,3.",
        "Печатать плоской стороной на столе. Очистить щели и кромки.",), 109)
    c.showPage()
    c.save()


if __name__ == "__main__":
    main()
