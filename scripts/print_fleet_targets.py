"""Assemble the metric dock board and optional tabletop target in one A4 print job."""

import argparse
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from explorer4.paths import ROOT


def build(destination):
    source = ROOT / "assets/so101_donor_marker_7.svg"
    svg = ET.parse(source).getroot()
    rectangles = svg.findall("{*}g/{*}rect")
    cells = [(int(r.attrib["x"]), int(r.attrib["y"])) for r in rectangles]
    sheet = [
        "%!PS-Adobe-3.0",
        "<< /PageSize [595.27559055 841.88976378] >> setpagedevice",
        "72 25.4 div dup scale",
        "/Helvetica-Bold findfont 5 scalefont setfont",
        "15 272 moveto (Explorer 4.0 | Optional SO-101 tabletop target) show",
        "/Helvetica findfont 3.5 scalefont setfont",
        "15 255 moveto (Print at 100%. Measure the black square edge: 20 mm.) show",
        "15 246 moveto (Keep the white border. Use one copy on the cube for the marked-object test.) show",
        "15 237 moveto (Keep the docking sheet in the other room when measuring the tabletop cube.) show",
    ]
    pitch = 20 / 6
    for left in (23, 75):
        for x, y in cells:
            sheet.append(
                f"{left + x * pitch:.5f} {180 + (7 - y) * pitch:.5f} {pitch:.5f} {pitch:.5f} rectfill"
            )
    sheet += [
        "15 155 moveto (Scale check: the line below measures 100 mm between end ticks.) show",
        "0.3 setlinewidth newpath 20 141 moveto 120 141 lineto stroke",
        "newpath 20 139 moveto 20 143 lineto 120 139 moveto 120 143 lineto stroke",
        "showpage",
    ]
    with tempfile.TemporaryDirectory() as directory:
        optional = Path(directory) / "tabletop.pdf"
        subprocess.run(
            ["ps2pdf", "-dAutoRotatePages=/None", "-", str(optional)],
            input="\n".join(sheet).encode("ascii"),
            check=True,
        )
        subprocess.run(
            [
                "pdfunite",
                str(ROOT / "assets/peer_dock_180mm_A4.pdf"),
                str(optional),
                str(destination),
            ],
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
