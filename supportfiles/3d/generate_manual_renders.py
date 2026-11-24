"""Add assembly arrows to existing OpenSCAD PNGs without drawing screws.

Arrow targets are calibrated for the fixed 1600x1000 OpenSCAD cameras below.
Reinspect the targets if the case envelope or camera position changes.
"""

from __future__ import annotations

import base64
import html
import math
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE_W, PAGE_H = 1800, 1280
IMAGE_X, IMAGE_Y = 100, 170
NAVY = "#16324b"
AMBER = "#d27818"


def arrow(start: tuple[int, int], target: tuple[int, int], color: str) -> str:
    sx, sy = start
    tx, ty = target
    length = math.hypot(tx - sx, ty - sy)
    end_x = tx - 17 * (tx - sx) / length
    end_y = ty - 17 * (ty - sy) / length
    return (
        f'<path d="M{sx} {sy} L{end_x:.1f} {end_y:.1f}" '
        f'stroke="{color}" stroke-width="5" fill="none" '
        f'stroke-linecap="round" marker-end="url(#{"navy" if color == NAVY else "amber"})"/>'
        f'<circle cx="{tx}" cy="{ty}" r="16" fill="none" '
        f'stroke="{color}" stroke-width="4"/>'
    )


def add_key(items: list[str], x: int, y: int, color: str, label: str) -> None:
    items.append(
        f'<circle cx="{x}" cy="{y}" r="13" fill="none" stroke="{color}" stroke-width="4"/>'
        f'<path d="M{x + 29} {y} H{x + 83}" stroke="{color}" stroke-width="5" '
        f'marker-end="url(#{"navy" if color == NAVY else "amber"})"/>'
        f'<text x="{x + 111}" y="{y + 1}" class="legend">{html.escape(label)}</text>'
    )


def manual(
    stem: str,
    photo: str,
    step: str,
    title: str,
    subtitle: str,
    m3: list[tuple[tuple[int, int], tuple[int, int]]],
    other: list[tuple[tuple[int, int], tuple[int, int]]],
    other_label: str,
    note: str,
) -> None:
    png = base64.b64encode((HERE / photo).read_bytes()).decode("ascii")
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{PAGE_W}" height="{PAGE_H}" viewBox="0 0 {PAGE_W} {PAGE_H}">',
        "<defs><style>text{font-family:Arial,Helvetica,sans-serif;fill:#13283b}"
        ".title{font-size:42px;font-weight:700}.sub{font-size:23px}"
        ".legend{font-size:26px;font-weight:700;dominant-baseline:middle}"
        ".note{font-size:20px}</style>"
        f'<marker id="navy" markerWidth="14" markerHeight="14" refX="11" refY="7" '
        f'orient="auto"><path d="M1 1 L12 7 L1 13 Z" fill="{NAVY}"/></marker>'
        f'<marker id="amber" markerWidth="14" markerHeight="14" refX="11" refY="7" '
        f'orient="auto"><path d="M1 1 L12 7 L1 13 Z" fill="{AMBER}"/></marker></defs>',
        '<rect width="1800" height="1280" fill="#f8f9f6"/>',
        f'<image x="{IMAGE_X}" y="{IMAGE_Y}" width="1600" height="1000" '
        f'xlink:href="data:image/png;base64,{png}"/>',
        '<rect x="35" y="25" width="1730" height="132" rx="16" '
        'fill="#ffffff" stroke="#c9d3d9" stroke-width="3"/>',
        f'<rect x="58" y="48" width="78" height="78" rx="12" fill="{NAVY}"/>',
        f'<text x="97" y="102" text-anchor="middle" style="font-size:40px;font-weight:700;fill:#fff">{step}</text>',
        f'<text x="160" y="82" class="title">{html.escape(title)}</text>',
        f'<text x="160" y="122" class="sub">{html.escape(subtitle)}</text>',
    ]
    items.extend(arrow(start, target, NAVY) for start, target in m3)
    items.extend(arrow(start, target, AMBER) for start, target in other)
    items.extend(
        [
            '<rect x="40" y="1180" width="1720" height="76" rx="15" '
            'fill="#fff" stroke="#c9d3d9" stroke-width="3"/>',
        ]
    )
    add_key(items, 75, 1218, NAVY, "M3 × 4 · carcasa")
    if other_label:
        add_key(items, 610, 1218, AMBER, other_label)
    items.append(
        f'<text x="1740" y="1219" text-anchor="end" class="note">{html.escape(note)}</text>'
    )
    items.append("</svg>\n")
    svg_path = HERE / f"{stem}.svg"
    svg_path.write_text("\n".join(items))
    subprocess.run(["rsvg-convert", str(svg_path), "-o", str(HERE / f"{stem}.png")], check=True)


def at(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(x + IMAGE_X, y + IMAGE_Y) for x, y in points]


def pair(
    starts: list[tuple[int, int]], targets: list[tuple[int, int]]
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    return list(zip(starts, at(targets), strict=True))


def main() -> None:
    manual(
        "manual-front",
        "preview.png",
        "01",
        "Frontal · posición de tornillos",
        "Flechas hacia los orificios vacíos; los tornillos aún no están instalados.",
        pair(
            [(185, 310), (1615, 310), (180, 1080), (1620, 1080)],
            [(259, 259), (1341, 259), (248, 792), (1350, 792)],
        ),
        pair(
            [(380, 470), (1050, 470), (375, 910), (1050, 910)],
            [(330, 372), (899, 373), (325, 677), (899, 677)],
        ),
        "M2.5 × 4 · LCD",
        "Ranuras OLED: correas",
    )
    manual(
        "manual-back",
        "preview-back.png",
        "02",
        "Trasera · paneles solares",
        "Dos paneles Steren PS-003 de 56 × 60 mm; los clips van en los orificios marcados.",
        pair(
            [(180, 315), (1615, 315), (185, 1080), (1615, 1080)],
            [(230, 298), (1367, 298), (257, 825), (1342, 825)],
        ),
        pair(
            [(475, 560), (900, 560), (1325, 560), (481, 940), (900, 940), (1318, 940)],
            [(375, 469), (800, 469), (1225, 469), (381, 680), (800, 680), (1218, 680)],
        ),
        "M2 × 6 · clips solares",
        "Tuercas M2 por dentro",
    )
    manual(
        "manual-base",
        "preview-base.png",
        "03",
        "Base · unión a laterales",
        "Los cuatro M3 entran desde abajo en los insertos de las piezas laterales.",
        pair(
            [(310, 420), (1490, 420), (310, 970), (1490, 970)],
            [(403, 328), (1196, 328), (403, 671), (1196, 671)],
        ),
        [],
        "",
        "Ranuras centrales: ESP32",
    )
    manual(
        "manual-top",
        "preview-top-uncapped.png",
        "04",
        "Tapa superior · fijación",
        "Cuatro M3 entran por la tapa hacia los insertos de ambos laterales.",
        pair(
            [(355, 365), (590, 210), (1130, 495), (1500, 300)],
            [(477, 175), (591, 139), (1158, 307), (1254, 257)],
        ),
        [],
        "",
        "Tornillos aún sin instalar",
    )
    print("Generated four annotated assembly renders")


if __name__ == "__main__":
    main()
