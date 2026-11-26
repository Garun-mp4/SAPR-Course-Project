"""Generate the documented ESKD drawing sheet, list of elements and assembly specification."""
import csv
import json
from pathlib import Path
import re

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from eskd import FONT_NAME, font_size, frame, pdf_frame, register_font

ROOT = Path(__file__).resolve().parents[1]


def kicad_worksheet():
    items = frame(420, 297, "САПР.001.000 Э3", "Контроллер вентиляции\nСхема электрическая\nпринципиальная",
                  version="04")
    with (ROOT / "hardware/SAPR-001-ESKD.kicad_wks").open("w", encoding="utf-8", newline="\n") as f:
        f.write("(kicad_wks (version 20231118) (generator sapr_eskd)\n")
        f.write("  (setup (textsize 1.8 1.8) (linewidth 0.25) (textlinewidth 0.175)"
                " (left_margin 20) (right_margin 5) (top_margin 5) (bottom_margin 5))\n")
        for index, (kind, values) in enumerate(items, 1):
            if kind == "line":
                x1, y1, x2, y2, stroke = values
                f.write(f'  (line (name "L{index}") (start {x1-20:g} {292-y1:g} ltcorner)'
                        f' (end {x2-20:g} {292-y2:g} ltcorner) (linewidth {stroke:g}))\n')
            else:
                x, y, label, h, centered, rotation = values
                align = "(justify center)" if centered else "(justify left)"
                rotate = f" (rotate {rotation})" if rotation else ""
                quoted = json.dumps(label, ensure_ascii=False)
                f.write(f'  (tbtext {quoted} (name "T{index}") (pos {x-20:g} {292-y-h/2:g} ltcorner)'
                        f' (font (size {h*.77:g} {h:g})) {align}{rotate})\n')
        f.write(")\n")


def table_pdf(destination, code, name, widths, headers, records, notes, *, row_height=12, category_column=None, version="04"):
    canvas = Canvas(str(destination), (210 * mm, 297 * mm), invariant=True)
    canvas.setTitle(code)
    pdf_frame(canvas, frame(210, 297, code, name, form=2, paper="А4", version=version))
    start, top = 20, 292
    heights = [15] + [max(row_height, 2 + 4.4 * max(cell.count("\n") + 1 for cell in row))
                      for row in records]
    bottom = top - sum(heights)
    if bottom - (8 + (len(notes) - 1) * 5 if notes else 0) < 48:
        raise ValueError(f"{destination.name}: table overlaps the main inscription")
    canvas.setLineWidth(0.5 * mm)
    canvas.rect(start * mm, bottom * mm, 185 * mm, (top - bottom) * mm, stroke=1, fill=0)
    canvas.setLineWidth(0.25 * mm)
    column = start
    for width in widths[:-1]:
        column += width
        canvas.line(column * mm, bottom * mm, column * mm, top * mm)
    for index, (row, height) in enumerate(zip([headers, *records], heights)):
        y = top - height
        if y > bottom:
            canvas.line(start * mm, y * mm, 205 * mm, y * mm)
        column = start
        for col, (w, text) in enumerate(zip(widths, row)):
            if index == 0 and w <= 8:
                canvas.saveState()
                canvas.translate((column + w / 2 + .6) * mm, (y + height / 2) * mm)
                canvas.rotate(90)
                canvas.setFont(FONT_NAME, font_size(1.8))
                canvas.drawCentredString(0, 0, text)
                canvas.restoreState()
                column += w
                continue
            lines = text.split("\n")
            size = font_size(1.8 if w <= 10 or index == 0 and w <= 22 else 2.5)
            for offset, label in enumerate(lines):
                if pdfmetrics.stringWidth(label, FONT_NAME, size) > (w - 2) * mm:
                    raise ValueError(f"{destination.name}: table text exceeds column {col+1}: {label}")
                canvas.setFont(FONT_NAME, size)
                baseline = (top + y) / 2 + 2.2 * (len(lines) - 1) - 1.25 - 4.4 * offset
                if index == 0 or w < 22:
                    canvas.drawCentredString((column + w / 2) * mm, baseline * mm, label)
                else:
                    canvas.drawString((column + 1.3) * mm, baseline * mm, label)
                    if col == category_column and label and not any(row[:col] + row[col + 1:]):
                        left = (column + 1.3) * mm
                        canvas.line(left, (baseline - .7) * mm, left + pdfmetrics.stringWidth(label, FONT_NAME, size),
                                    (baseline - .7) * mm)
            column += w
        top = y
    canvas.setFont(FONT_NAME, font_size(2.5))
    for i, note in enumerate(notes):
        canvas.drawString(22 * mm, (bottom - 8 - i * 5) * mm, note)
    canvas.showPage()
    canvas.save()


def read_bom():
    with (ROOT / "hardware/bom.csv").open(encoding="utf-8", newline="") as source:
        return {row["Обозначение"]: row for row in csv.DictReader(source)}


def pe3():
    bom = read_bom()
    comments = {
        "A1": "WROOM-32E, 4 МБ", "A2": "I²C 3,3 В, питание LDO", "A3": "Mini SV, OFF",
        "C1": "±20 %, полярный", "F1": "T 0,5 А, 5×20",
        "G1": "Внешний, 12 В ±5 %", "G2": "Внешний, Micro-USB",
        "M1": "Внешний, 12 В, 0,07 А", "R1": "Подтяжка тахометра", "R2": "Подтяжка входа ON",
        "VD1": "Однонаправленный", "VD2": "Диод Шоттки", "X1": "1 +12 В, 2 GND", "X2": "1 GND, 2 +12 В\n3 TACH",
    }
    if set(comments) != set(bom):
        raise ValueError("Element list differs from BOM")
    holder = {"F1": "\nДержатель Schurter FDI 8601.2001.08"}
    records = [(ref, bom[ref]["Наименование"] + holder.get(ref, ""), bom[ref]["Кол-во"], note)
               for ref, note in sorted(comments.items(), key=lambda item: re.split(r"(\d+)", item[0]))]
    table_pdf(ROOT / "hardware/SAPR-001-PE3.pdf", "САПР.001.000 ПЭ3", "Контроллер вентиляции\nПеречень элементов",
              (20,110,10,45), ("Поз.\nобозначение", "Наименование", "Кол.", "Примечание"), records,
              ("К схеме САПР.001.000 Э3. Исполнение ответных частей и кабелей — в таблице монтажа.",), version="05")


def specification():
    bom = read_bom()
    purchases = [
        ("A1", "ESP32-DevKitC-32E V4", "Espressif"),
        ("A2", "SCD41 №5190", "Adafruit"),
        ("A3", "Mini MOSFET Switch SV №2811", "Pololu"),
        ("C1", "Конденсатор 47 мкФ, 25 В, ±20 %", ""),
        ("VD1", "Ограничитель SMAJ13A", ""),
        ("VD2", "Диод Шоттки SS14", ""),
        ("F1", "0218.500MXP + держатель\nSchurter FDI 8601.2001.08", ""),
        ("X1", "JST SMR-02V-B с контактами", ""),
        ("X2", "PC fan, 3 контакта, шаг 2,54 мм", ""),
        ("R1", "2,2 кОм ±5 %, 0,25 Вт", ""),
        ("R2", "10 кОм ±5 %, 0,25 Вт", ""),
    ]
    if {ref for ref, _, _ in purchases} != set(bom) - {"M1", "G1", "G2"}:
        raise ValueError("Purchases differ from the internal BOM")
    records = [
        ("","","","","Документация","",""),
        ("А3","","","САПР.001.000 СБ","Сборочный чертёж","", "4 листа"),
        ("А3","","","САПР.001.000 Э3","Схема электрическая\nпринципиальная","",""),
        ("А4","","","САПР.001.000 ПЭ3","Перечень элементов","",""),
        ("","","","","Детали","",""),
        ("А3","","1","САПР.001.001","Основание","1","PETG"),
        ("А3","","2","САПР.001.002","Крышка","1","PETG"),
        ("","","","","Программные изделия и базы данных","",""),
        ("","","","САПР.001-FW","Прошивка ESP32, редакция 02","1",""),
        ("","","","","Прочие изделия","",""),
        ("","","3","","Винт STP390300120S, Ø3×12","4","Проба"),
        *(("", "", str(position), "", name, bom[ref]["Кол-во"], " ".join(filter(None, [ref, supplier])))
          for position, (ref, name, supplier) in enumerate(purchases, start=4)),
        ("","","15","","Втулка вывода жгута","2","По месту"),
        ("","","","","Материалы","",""),
        ("","","16","","Лента электроизоляционная","Техн.",""),
        ("","","17","","Провод монтажный 0,25 мм²","Техн.",""),
    ]
    table_pdf(ROOT / "outputs/SAPR-001-specification.pdf", "САПР.001.000", "Контроллер вентиляции\nСпецификация",
              (6,6,8,70,63,10,22), ("Формат", "Зона", "Поз.", "Обозначение", "Наименование", "Кол.", "Примечание"), records,
              ("Внешние устройства G1, G2 и M1 подключаются по Э3 и таблице монтажа.",),
              row_height=8, category_column=4, version="05")


if __name__ == "__main__":
    register_font()
    kicad_worksheet()
    pe3()
    specification()
