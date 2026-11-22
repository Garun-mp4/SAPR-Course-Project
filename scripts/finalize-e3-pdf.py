"""Remove KiCad's PDF popup script and repair its invisible Unicode search text."""
import argparse
from pathlib import Path
import re

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


# KiCad 9 writes these UTF-16BE strings to a single-byte Helvetica font
# in rendering mode 3. The visible lettering is drawn separately as paths.
HIDDEN_TEXT = re.compile(rb"/KicadFont ([\d.]+ Tf 3 Tr [\d.]+ Tz) <[fF][eE][fF][fF]([\da-fA-F]+)> Tj")


def repair_search_text(writer, page):
    content = page.get_contents()
    data = content.get_data()
    strings = {match: bytes.fromhex(match.decode("ascii")).decode("utf-16-be")
               for _, match in HIDDEN_TEXT.findall(data)}
    if not strings:
        raise ValueError("Expected KiCad 9 Unicode text in the source PDF")
    extra = sorted({c for word in strings.values() for c in word if not c.isascii()})
    if len(extra) > 128:
        raise ValueError("The search font has more than 128 non-ASCII characters")
    codes = {chr(code): code for code in range(128)}
    codes.update({char: code for code, char in enumerate(extra, 128)})

    # Keep all printable ASCII widths and remap only the invisible text runs.
    mapping = [(code, char) for char, code in codes.items() if code >= 32]
    cmap = [
        "/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
        "/CIDSystemInfo << /Registry (SAPR) /Ordering (Unicode) /Supplement 0 >> def",
        "/CMapName /SaprText def", "/CMapType 2 def",
        "1 begincodespacerange", "<00> <FF>", "endcodespacerange",
    ]
    for i in range(0, len(mapping), 100):
        chunk = mapping[i:i + 100]
        cmap.append(f"{len(chunk)} beginbfchar")
        cmap.extend(f"<{code:02X}> <{char.encode('utf-16-be').hex().upper()}>" for code, char in chunk)
        cmap.append("endbfchar")
    cmap += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    unicode_map = DecodedStreamObject()
    unicode_map.set_data("\n".join(cmap).encode("ascii"))
    fonts = page["/Resources"]["/Font"]
    search_font = DictionaryObject(fonts["/KicadFont"])
    search_font[NameObject("/ToUnicode")] = writer._add_object(unicode_map)
    fonts[NameObject("/SaprText")] = search_font

    def encode(match):
        word = bytes(codes[c] for c in strings[match[2]])
        return b"/SaprText " + match[1] + b" <" + word.hex().encode("ascii") + b"> Tj"

    repaired = DecodedStreamObject()
    repaired.set_data(HIDDEN_TEXT.sub(encode, data))
    page.replace_contents(repaired.flate_encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Choose a different output path")
    source = PdfReader(args.input)
    writer = PdfWriter(clone_from=source)
    writer.pdf_header = source.pdf_header
    if len(writer.pages) != 1 or writer.pages[0].get("/Annots"):
        parser.error("Expected one sheet exported without property popups or hierarchical links")
    names = writer.root_object.get("/Names")
    if names:
        names.get_object().pop(NameObject("/JavaScript"), None)
    repair_search_text(writer, writer.pages[0])
    with args.output.open("wb") as destination:
        writer.write(destination)


if __name__ == "__main__":
    main()
