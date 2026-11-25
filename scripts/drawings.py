"""Export the SAPR-001 drawing set from its checked mechanical profile."""
import argparse
import json
from math import hypot
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
FUSE_AXIS = ((69, 8.5), (109, 34.11738))
FUSE_DIAMETER = 11
FUSE_AXIS_Z = 21
SWITCH_TOP_Z = 8.416
SENSOR_BOARD = (77.05, 49.07, 25.4, 22.86)
SENSOR_BODY = (84.7, 56.212, 10.1, 10.1)
SWITCH_BOARD = (73.5, 11, 15.24, 15.24)
SWITCH_EXTENT = (77.27, 10.105, 7.7, 0.895)
USB_BOARD = (3.5, 16.03, 48.26, 27.94)
A1_MODULE = (32.224, 20.981, 25.5, 18)
PDF_NAME = "SAPR-001-drawings.pdf"
SHEET_NAMES = ("01-assembly", "02-base", "03-lid", "04-fan-installation",
               "05-board-installation", "06-harness-installation")


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

    def outline(self, xy, weight=0.5, style="solid"):
        for a, b in zip(xy, (*xy[1:], xy[0])):
            self.line(*a, *b, weight, style)

    def center_mark(self, x, y, reach=4):
        self.line(x - reach, y, x + reach, y, 0.18, "center")
        self.line(x, y - reach, x, y + reach, 0.18, "center")

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
        # Intersect each diagonal with the section, including the blind holes.
        offsets = [a - slope * b for a, b in outline]
        offset = min(offsets) + 1.2
        while offset < max(offsets):
            intersections = []
            for i, (_, b) in enumerate(outline):
                j = (i + 1) % len(outline)
                start, end = offsets[i], offsets[j]
                if min(start, end) <= offset < max(start, end):
                    t = (offset - start) / (end - start)
                    intersections.append(b + t * (outline[j][1] - b))
            intersections.sort()
            for y1, y2 in zip(intersections[::2], intersections[1::2]):
                self.line(x + offset + slope * y1, y + y1,
                          x + offset + slope * y2, y + y2, 0.18)
            offset += 2.4
        self.outline([(x + a, y + b) for a, b in outline])

    def leader(self, x, y, end_x, end_y, position):
        self.c.setLineWidth(0.25 * mm)
        self.c.circle(x * mm, y * mm, 0.45 * mm, stroke=0, fill=1)
        self.line(x, y, end_x, end_y)
        size = max(10, len(str(position)) * 2.8)
        self.line(end_x, end_y, end_x + size, end_y)
        self.text(end_x + size / 2, end_y + 1.0, str(position), 3.5, centered=True)

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

    def frame(self, code, name, material="", scale="2:1", sheet=1, sheets=1):
        pdf_frame(self.c, frame(420, 297, code, name, material=material, scale=scale,
                                version="05" if code.endswith(" СБ") else "04",
                                sheet=sheet, sheets=sheets))

    def trace(self, x, y, width, label):
        for a, b in ((x - 5, x), (x + width, x + width + 5)):
            self.line(a, y, b, y, 0.7)
        for stop in (x - 4, x + width + 4):
            self.line(stop, y - 5, stop, y)
            self.arrow(stop, y, "up")
            self.text(stop - 0.5, y - 9, label, 3.5, centered=True)


def corners(x, y, width, depth):
    return ((x, y), (x + width, y), (x + width, y + depth), (x, y + depth))


def fuse_corners():
    (ax, ay), (bx, by) = FUSE_AXIS
    length = hypot(bx - ax, by - ay)
    radius = FUSE_DIAMETER / 2
    nx, ny = -(by - ay) * radius / length, (bx - ax) * radius / length
    return ((ax + nx, ay + ny), (bx + nx, by + ny),
            (bx - nx, by - ny), (ax - nx, ay - ny))


def visible_edges(rect, cover):
    """Return portions of the rectangle's edges outside the clockwise cover."""
    for start, stop in zip(rect, (*rect[1:], rect[0])):
        lo, hi = 0.0, 1.0
        for a, b in zip(cover, (*cover[1:], cover[0])):
            # A point is inside when it is on the right of each cover edge.
            u, v = b[0] - a[0], b[1] - a[1]
            c0 = u * (a[1] - start[1]) - v * (a[0] - start[0])
            c1 = u * (a[1] - stop[1]) - v * (a[0] - stop[0])
            if max(c0, c1) < 0:
                lo = hi
                break
            if min(c0, c1) < 0:
                t = c0 / (c0 - c1)
                if c0 < 0:
                    lo = max(lo, t)
                else:
                    hi = min(hi, t)
        if hi <= lo:
            yield start, stop
            continue
        for a, b in ((0, lo), (hi, 1)):
            if b > a:
                yield tuple(p + a * (q - p) for p, q in zip(start, stop)), tuple(
                    p + b * (q - p) for p, q in zip(start, stop))


def plan(s, x, y, scale=2, kind="base"):
    s.rect(x, y, W * scale, D * scale)
    is_lid = kind == "lid"
    for a, b in STUD["centers"]:
        cx, cy = x + scale * a, y + scale * b
        if not is_lid:
            s.circle(cx, cy, scale * STUD["diameter"] / 2)
        s.circle(cx, cy, scale * STUD["clearance_diameter" if is_lid else "pilot_diameter"] / 2)
        s.center_mark(cx, cy, 5)
    if is_lid:
        for b in SLOT["y"]:
            s.rect(x + scale * SLOT["x"], y + scale * b, scale * SLOT["length"], scale * SLOT["width"])
        return
    s.rect(x + scale * WALL, y + scale * WALL, scale * (W - 2 * WALL), scale * (D - 2 * WALL))
    assembly = kind == "assembly"
    cover = fuse_corners() if assembly else ()
    for feature in H["supports"]:
        a, b, _ = feature["min"]
        c, d, _ = feature["max"]
        style = "hidden" if assembly and feature["ref"] != "Перегородка" else "solid"
        if assembly and feature["ref"] == "A3":
            for (a1, b1), (a2, b2) in visible_edges(corners(a, b, c - a, d - b), cover):
                s.line(x + scale * a1, y + scale * b1, x + scale * a2, y + scale * b2, 0.25, style)
        else:
            s.rect(x + scale * a, y + scale * b, scale * (c - a), scale * (d - b), 0.35, style)
    for port in H["ports"]:
        a = 0 if port["side"] == "left" else W - WALL
        s.rect(x + scale * a, y + scale * port["y"], scale * WALL, scale * port["width"], 0.25, "hidden")
    if not assembly:
        return

    for a, b, w, h in (USB_BOARD, A1_MODULE, SENSOR_BOARD, SENSOR_BODY,
                        (0.4, 26, 8.1, 8), (18, 60.5, 10, 4.5),
                        (29.5, 60.5, 4.5, 4.5), (111, 8.5, 5, 17), (111, 27.5, 5, 15)):
        s.rect(x + scale * a, y + scale * b, scale * w, scale * h, 0.35)
    s.line(x + scale * 50.874, y + scale * 20.981, x + scale * 50.874,
           y + scale * 38.981, style="hidden")
    for outline in (SWITCH_BOARD, SWITCH_EXTENT):
        for (a1, b1), (a2, b2) in visible_edges(corners(*outline), cover):
            s.line(x + scale * a1, y + scale * b1, x + scale * a2, y + scale * b2, 0.35)
    s.outline([(x + scale * a, y + scale * b) for a, b in cover], 0.5)
    for a, b, label in ((14, 29, "A1"), (80.5, 64, "A2"), (76.75, 22.4, "A3")):
        s.text(x + scale * a, y + scale * b, label, centered=True)


def side_view(s, x, y, side, closed, *, dimension=True, ports=True):
    height = B + LID if closed else B
    s.rect(x, y, D, height)
    if closed:
        s.line(x, y + B, x + D, y + B, 0.5)
    for p in (port for port in H["ports"] if ports and port["side"] == side):
        # Projection convention: +Z up, looking +X from the left, -X from the right.
        offset = D - p["y"] - p["width"] if side == "left" else p["y"]
        s.rect(x + offset, y + p["z"], p["width"], p["height"])
    if dimension:
        s.vdim(y, y + height, x + D + 8, x + D, mm_text(height) + ("*" if closed else ""))


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
        s.rect(x + SENSOR_BOARD[0], y + 8, SENSOR_BOARD[2], 1.57, 0.35)
        s.rect(x + SENSOR_BODY[0], y + 9.57, SENSOR_BODY[2], 6.309, 0.35)
        s.leader(x + 45, y + 1.5, x + 30, y + 12, 1)
        s.leader(x + 45, y + B + 1.5, x + 36, y + 42, 2)
    else:
        for a in (8, 107):
            s.line(x + a, y + 14, x + a, y + 35, 0.18, "center")
        s.vdim(y + B - STUD["depth"], y + B, x + 22, x + 8, "11")
        s.vdim(y, y + FLOOR, x + 45, x + 53, "3")


def fan_installation(s):
    s.frame("САПР.001.000 СБ", "Контроллер вентиляции\nВнешний монтаж", scale="1:1", sheet=2)
    s.text(42, 267, "M1 · Noctua NF-A8 FLX", 4)
    s.text(42, 258, "Монтажная плоскость, без накладок", 2.5)
    x, y, w, pitch = 53, 145, 80, 71.5
    inset = (w - pitch) / 2
    s.rect(x, y, w, w)
    s.circle(x + w / 2, y + w / 2, 36.5, 0.25)
    s.center_mark(x + w / 2, y + w / 2, 38)
    for a in (inset, w - inset):
        for b in (inset, w - inset):
            s.circle(x + a, y + b, 4.30 / 2)
            s.center_mark(x + a, y + b)
    s.hdim(x, x + w, 129, y, "80")
    s.vdim(y, y + w, 31, x, "80")
    s.hdim(x + inset, x + w - inset, 238, y + w - inset, "71,5")
    s.vdim(y + inset, y + w - inset, 147, x + w - inset, "71,5")
    s.leader(x + inset + 1.4, y + w - inset + 1.4, 65, 248, "4 отв. Ø4,3")
    s.rect(x, 83, w, 25)
    s.rect(x - .5, 82, w + 1, 27, 0.25, "hidden")
    s.vdim(83, 108, 145, x + w, "25")
    s.vdim(82, 109, 158, x + w + .5, "27")
    s.text(42, 70, "Штриховой контур — габарит с накладками 81 × 81 × 27.", 2.5)

    s.text(179, 267, "Подключение к контроллеру", 4)
    s.rect(213, 153, 115, 80)
    for a, b in STUD["centers"]:
        s.circle(213 + a, 153 + b, 5.3 / 2, 0.35)
    for b in SLOT["y"]:
        s.rect(213 + SLOT["x"], 153 + b, SLOT["length"], SLOT["width"], 0.35)
    s.text(270.5, 191, "Контроллер с крышкой", 3, centered=True)
    for a, b, xend, label in ((213, 183, 186, "G2"), (328, 170, 355, "X1 — G1"),
                               (328, 188, 355, "X2 — M1")):
        s.line(a, b, xend, b)
        s.text(xend + 2 if a < xend else xend - 9, b - 0.8, label, 2.8)
    s.notes(180, 138, "Требования к установке", (
        "M1 закрепить на отдельной поверхности. Крепёж и отверстие под поток выбрать по месту.",
        "Диаметр окружности на виде условный. Для присоединения использовать 4 отверстия рамки.",
        "Длина штатного кабеля 200 мм, с удлинителем 500 мм. Положение M1 на стенде выбирают по месту.",
        "Ориентацию потока определить по стрелке на рамке M1. Не направлять струю на щели над A2.",
        "G2 подключить к Micro-USB. Питание 12 В подавать через X1. Распиновка X1 и X2 — на листе 4.",), 220)


def board_installation(s):
    s.frame("САПР.001.000 СБ", "Контроллер вентиляции\nПосадка плат", scale="2:1", sheet=3)
    s.text(35, 268, "A1 · ESP32-DevKitC-32E V4", 4)
    s.text(165, 268, "A2 · Adafruit 5190", 4)
    s.text(293, 268, "A3 · Pololu 2811", 4)
    for x, y, board in ((37, 177, USB_BOARD), (170, 177, SENSOR_BOARD), (296, 177, SWITCH_BOARD)):
        width, depth = board[2:]
        s.rect(x, y, 2 * width, 2 * depth)
        s.hdim(x, x + 2 * width, y - 9, y, mm_text(width))
        dimension_x = x - 10 if board == USB_BOARD else x + 2 * width + 10
        s.vdim(y, y + 2 * depth, dimension_x, x if board == USB_BOARD else x + 2 * width, mm_text(depth))
    for x, y, board, feature in ((37, 177, USB_BOARD, A1_MODULE),
                                 (170, 177, SENSOR_BOARD, SENSOR_BODY),
                                 (296, 177, SWITCH_BOARD, SWITCH_EXTENT)):
        a, b, w, h = feature
        s.rect(x + 2 * (a - board[0]), y + 2 * (b - board[1]), 2 * w, 2 * h, 0.35)
    s.rect(37.4, 197.54, 12.04, 14.9, 0.35)
    s.text(52, 202, "Micro-USB", 2.5)
    s.line(131.75, 186.9, 131.75, 222.9, style="hidden")
    s.hdim(37, 145.45, 246, 222.9, "54,22*")
    s.text(37, 156, "* По модели с модулем WROOM-32E.", 2.5)
    s.text(194, 215, "SCD41", 2.5, centered=True)
    s.rect(170.13, 193.86, 9.9, 12, .25)
    s.rect(210.77, 193.86, 9.9, 12, .25)
    s.text(311, 182, "OFF", 2.5, centered=True)
    s.notes(35, 142, "Посадка A1", (
        "Плата без установленных гребёнок 2×19. Подключить провода сверху к площадкам по Э3.",
        "База платы X = 3,50; Y = 16,03; опорная плоскость Z = 6.",
        "Micro-USB развернуть к левой стенке. Проверить, что штекер входит через проём до упора.",
        "Выводы штатных гребёнок по 3D достигают Z = -2,63. Гребёнки снять, если они установлены.",
        "Осмотреть нижнюю сторону платы. Оставить зону антенны свободной от жгутов и металла.",), 119)
    s.notes(165, 142, "Посадка A2", (
        "База платы X = 77,05; Y = 49,07; низ платы Z = 8.",
        "Верх корпуса SCD41 по 3D — Z = 15,88. Чувствительный элемент находится под щелями крышки.",
        "Плату фиксировать по краям. Не заклеивать корпус датчика и не перегибать проводники.",
        "Подключение VIN, GND, SDA и SCL — по Э3. Проверить положение перемычек по Adafruit.",), 108)
    s.notes(293, 142, "Посадка A3", (
        "База платы X = 73,50; Y = 11,00; низ платы Z = 6.",
        "Габарит с выступом ключа 15,24 × 16,14 по STEP. Выступ направлен к стенке Y = 0.",
        "Переключатель в OFF. Подключить VIN, VOUT, GND и ON по Э3.",), 111)
    s.text(65, 85, "A1 · Проверка зазора в корпусе", 3.5)
    for z, label in ((6, "Z = 6, опора платы"), (3, "Z = 3, внутренняя поверхность дна"),
                     (0, "Z = 0, низ корпуса")):
        y = 58 + 2 * z
        s.line(65, y, 110, y, 0.5)
        s.text(114, y - 1, label)
    s.line(81, 70, 81, 52.74, 0.25, "hidden")
    s.line(81, 52.74, 110, 52.74, 0.25)
    s.text(114, 51.74, "Z = -2,63, нижний конец вывода")
    s.text(65, 43, "Штриховая линия — штатный вывод (2:1).")
    s.text(35, 32, "Размеры плат — по Espressif, Adafruit и Pololu. Размеры установки — в базах основания.", 2.5)


def harness_installation(s):
    s.frame("САПР.001.000 СБ", "Контроллер вентиляции\nКрепёж и жгуты", scale="", sheet=4)
    s.text(32, 267, "Крепление крышки", 4)
    x, y = 56, 183
    s.hatch(x - 20, y, 16.7, 6, -1)
    s.hatch(x + 3.3, y, 16.7, 6, -1)
    for side in (-1, 1):
        boss = [(8, -22), (8, 0), (3, 0), (3, -18), (2.6, -18), (2.6, -22)]
        s.hatched_section(x, y, [(side * a, b) for a, b in boss])
    s.hatch(x - 8, y - 28, 16, 6, 1)
    s.rect(x - 3, y - 18, 6, 24, 0.35)
    s.rect(x - 5.3, y + 6, 10.6, 4.6, 0.35)
    s.line(x, y - 32, x, y + 15, style="center")
    s.leader(x + 5.3, y + 8, 75, 208, "3")
    s.leader(x - 14, y + 4, 32, 205, "2")
    s.leader(x + 6, y - 10, 75, 177, "1")
    s.text(32, 146, "Узел, условно (2:1)", 2.5)
    s.notes(32, 135, "Поз. 3 · Screwerk STP390300120S", (
        "4 винта Ø3 × 12, головка Ø5,30, привод T10.",
        "Глубина посадки под крышкой 9 при пилоте 11. Пробу крепления выполнить на PETG.",), 118)

    s.text(163, 267, "Выводы на правой стенке", 4)
    side_view(s, 164, 207, "right", True, dimension=False, ports=False)
    s.rect(172.5, 211.5, 17, 16, 0.35)
    s.rect(191.5, 211.5, 15, 14, 0.35)
    for px, z, radius in ((181, 219.5, 2.65), (199, 218.5, 2.75)):
        s.circle(px, z, radius, 0.35)
        s.center_mark(px, z, 4)
    s.leader(176, 226.5, 163, 243, "X1")
    s.leader(202, 225, 214, 244, "X2")
    s.text(164, 196, "Вид справа (1:1). Втулки поз. 15.", 2.5)
    s.notes(163, 180, "Втулки и укладка", (
        "Посадочные проёмы 14 × 13 и 12 × 11. Габариты буртов по 3D — 17 × 16 и 15 × 14.",
        "Модельные проходы Ø5,3 и Ø5,5. Паз шириной 2,5 на стенку 3. Упругую посадку проверить на образце.",
        "Закрепить оба жгута от натяжения. Провода вести ниже Z = 30, оставляя свободными щели.",
        "F1 — закрытый держатель 5 × 20; запас места по 3D Ø11 × 47,5. Крепить в плюсовой ветви X1.",
        "C1 и VD1 включить короткими проводами у A3:VIN, VD2 — у A3:VOUT. R1 и R2 — по Э3.",
        "Длины жгутов определить по месту при доступе к разъёмам и предохранителю.",), 120)
    s.notes(295, 250, "X1 · JST SM, шаг 2,50", (
        "Контроллер — SMR-02V-B, источник — SMP-02V-BC.",
        "Контакт 1 — +12 В, контакт 2 — GND.",
        "Корпуса по JST: длины 18,2 и 11,7 соответственно.",
        "Нумерацию проверить со стороны сопряжения.",), 109)
    s.notes(295, 186, "X2 · PC fan, шаг 2,54", (
        "Ответная штыревая часть к штатному 3-контактному штекеру M1.",
        "1 — GND (чёрный), 2 — FAN_12V (красный), 3 — TACH (жёлтый).",
        "Ориентацию контакта 1 сверить по ключу, затем прозвонить жгут.",), 109)
    s.notes(32, 92, "Компоненты в жгуте", (
        "R1, R2: осевые DIN0207; C1: радиальный Ø6,3; VD1 и VD2: SMA.",
        "Габариты справочные. Номиналы и полярность — по Э3 и ПЭ3.",), 110)
    s.text(165, 108, "Габарит держателя F1 (1:1)", 3.5)
    s.rect(165, 88, 47.5, 11, 0.35)
    s.line(160, 93.5, 217.5, 93.5, 0.18, "center")
    s.hdim(165, 212.5, 81, 88, "47,5")
    s.vdim(88, 99, 223, 212.5, "Ø11")
    s.text(295, 122, "F1 над платой A3", 3.5)
    s.text(295, 114, "Вид справа, габариты (1:1)", 2.5)
    x, y = 296, 75
    ys = [p[1] for p in fuse_corners()]
    bottom = FUSE_AXIS_Z - FUSE_DIAMETER / 2
    s.rect(x + min(ys), y + bottom, max(ys) - min(ys), FUSE_DIAMETER, 0.35)
    s.text(x + 19, y + FUSE_AXIS_Z - 1, "F1", centered=True)
    _, by, _, depth = SWITCH_BOARD
    switch_y = SWITCH_EXTENT[1]
    s.rect(x + switch_y, y + 6, by + depth - switch_y, SWITCH_TOP_Z - 6, 0.35)
    s.text(x + 18, y + 1, "A3", centered=True)
    gap = bottom - SWITCH_TOP_Z
    s.vdim(y + SWITCH_TOP_Z, y + bottom, x + max(ys) + 21, x + by + depth, mm_text(round(gap, 1)) + "*")
    s.text(296, 67, "* Между корпусами по модели.", 2.5)
    s.text(296, 63, "Боковой зазор до стенки проверить на образце.", 2.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=FONT_PATH)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / PDF_NAME)
    args = parser.parse_args()
    register_font(args.font)
    c = Canvas(str(args.output), (420 * mm, 297 * mm), invariant=True)
    c.setTitle("САПР.001.000. Чертежи контроллера")
    s = Sheet(c)
    x, y = 47, 108

    s.frame("САПР.001.000 СБ", "Контроллер вентиляции\nСборочный чертёж", sheets=4)
    plan(s, x, y, kind="assembly")
    s.hdim(x, x + W * 2, 97, y, "115*")
    s.vdim(y, y + D * 2, 33, x, "80*")
    s.trace(x, y + 124, 2 * W, "А")
    s.text(x + 101, y + 148, "Вид сверху без крышки", 3.5, centered=True)
    s.leader(x + 80, y + 76, x + 91, y + 91, 4)
    s.leader(x + 168, y + 135, x + 154, y + 147, 5)
    s.leader(x + 147, y + 45, x + 126, y + 59, 6)
    s.leader(x + 186, y + 48, x + 192, y + 61, 10)
    s.leader(x + 224, y + 74, x + 235, y + 84, 15)
    side_view(s, 307, 217, "left", True)
    s.text(306, 257, "Вид слева (1:1)", 3.5)
    s.notes(302, 200, "Технические требования", (
        "1. * Размеры для справок.",
        "2. Установить платы на опоры по листу 3. A1 применять без штатных гребёнок.",
        "3. Закрепить платы съёмной изоляционной лентой, оставив открытыми датчик и антенну.",
        "4. Уложить жгуты по Э3 и листу 4. Разгрузить натяжение. Защитить вводы втулками поз. 15.",
        "5. Крышку закрепить винтами поз. 3. Щели над A2 оставить открытыми.",
        "6. Внешние устройства подключить по листу 2. На виде сверху показаны монтажные контуры.",
        "7. Проверить доступ к Micro-USB и F1, посадку крепежа и закрытие корпуса на собранном образце.",), 105)
    s.notes(302, 107, "Положение держателя F1", (
        "Поз. 10 расположена под углом в плане и выше платы A3. Зазор показан на листе 4.",), 105)
    s.text(48, 79, "А–А (1:1), по Y = 62 мм", 3.5)
    section(s, 48, 23, True)
    c.showPage()

    s.frame("САПР.001.001", "Основание", H["material"])
    plan(s, x, y + 2)
    s.hdim(x, x + W * 2, 99, y + 2, "115")
    s.vdim(y + 2, y + 2 + D * 2, 33, x, "80")
    s.trace(x, y + 18, 2 * W, "Б")
    side_view(s, 307, 236, "right", False)
    s.text(307, 274, "Вид справа (1:1)", 3.5)
    side_view(s, 307, 184, "left", False, dimension=False)
    s.text(307, 222, "Вид слева (1:1)", 3.5)
    next_y = s.notes(290, 173, "Размеры от баз X, Y и Z", (
        "4 стойки Ø8. Пилотные отверстия Ø2,6 ±0,10, глубина 11.",
        "Центры X/Y: 8/8, 107/8, 8/72, 107/72.",
        "Слева проём 18×14, Y = 21, Z = 5.",
        "Справа проёмы 14×13 и 12×11, Y = 10 и 29, Z = 6.",
        "Стенки и дно 3. На виде сверху X вправо, Y вверх. Начало в нижнем левом углу, Z = 0 на дне снаружи.",
        "Пределы опор и перегородок X / Y / Z:",), 120)
    for f in H["supports"]:
        intervals = ["–".join(map(mm_text, p)) for p in zip(f["min"], f["max"])]
        s.text(290, next_y, f'{f["ref"]}: ' + " / ".join(intervals), 2.5)
        next_y -= 4.7
    s.notes(172, 72, "Требования к детали", (
        "Неуказанные линейные отклонения ±0,3.",
        "Печать дном на столе. Удалить заусенцы.",
        "Пилотные отверстия проверить пробой крепежа.",), 56)
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
        "4 отв. Ø3,3 (+0,2 / 0).",
        "Центры отверстий от нижнего левого угла (X/Y): 8/8, 107/8, 8/72, 107/72.",
        "5 щелей 26×2. Начало по X = 77.",
        "Координаты нижних кромок по Y: 53, 57, 61, 65, 69.",
        "Толщина 3. Неуказанные линейные отклонения ±0,3.",
        "Печатать плоской стороной на столе. Очистить щели и кромки.",), 109)
    c.showPage()

    for draw in (fan_installation, board_installation, harness_installation):
        draw(s)
        c.showPage()
    c.save()


if __name__ == "__main__":
    main()
