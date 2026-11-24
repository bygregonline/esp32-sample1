"""Render the three ESP32 wiring views and one board view per component.

All signal endpoints are derived from MODULES and BOARD_LEFT/BOARD_RIGHT. The
photographic view embeds cropped component photos; its wires and the technical
view share the same geometry and contact points.
"""

from __future__ import annotations

import base64
import html
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISUALS = ROOT / "docs" / "visuals"
PARTS = VISUALS / "components"

BOARD_LEFT = (
    "3V3",
    "3V3",
    "RST",
    "4",
    "6",
    "15",
    "16",
    "17",
    "18",
    "8",
    "3",
    "46",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "5V",
)
BOARD_RIGHT = (
    "GND",
    "TX",
    "RX",
    "1",
    "2",
    "40",
    "39",
    "38",
    "37",
    "36",
    "35",
    "0",
    "45",
    "48",
    "47",
    "21",
    "20",
    "19",
    "GND",
)

POWER = "#dc2d35"
GROUND = "#1b3048"
COLORS = {
    "voltage.S": "#9854b5",
    "dht.DATA": "#c87517",
    "oled.SDA": "#2d9b6b",
    "oled.SCL": "#167b75",
    "lcd.CS": "#a054ad",
    "lcd.MOSI": "#176bd0",
    "lcd.SCK": "#00a5c0",
    "lcd.DC": "#e87d26",
    "lcd.RST": "#78933a",
    "bmp.SDA": "#2d9b6b",
    "bmp.SCL": "#167b75",
    "gps.RX": "#d4831a",
    "gps.TX": "#e2a817",
}


@dataclass(frozen=True)
class Pin:
    name: str
    net: str
    y: int


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    subtitle: str
    side: str
    box: tuple[int, int, int, int]
    photo: str
    photo_box: tuple[int, int, int, int]
    pins: tuple[Pin, ...]


MODULES = (
    Module(
        "voltage",
        "Módulo de voltaje 0–25 V",
        "Batería → IN+ / IN−",
        "left",
        (25, 180, 425, 155),
        "voltage",
        (43, 240, 173, 90),
        (Pin("VCC", "3V3", 235), Pin("GND", "GND", 265), Pin("S", "GPIO4", 295)),
    ),
    Module(
        "dht",
        "DHT11 · temperatura / humedad",
        "Frente: VCC · DATA · NC · GND",
        "left",
        (25, 350, 425, 190),
        "dht11",
        (55, 420, 86, 111),
        (
            Pin("VCC", "3V3", 420),
            Pin("DATA", "GPIO6", 450),
            Pin("NC", "NC", 480),
            Pin("GND", "GND", 510),
        ),
    ),
    Module(
        "oled",
        "OLED SSD1306",
        "I²C · 128 × 64",
        "left",
        (25, 555, 425, 180),
        "oled",
        (45, 620, 170, 100),
        (
            Pin("VCC", "3V3", 590),
            Pin("GND", "GND", 620),
            Pin("SDA", "GPIO8", 650),
            Pin("SCL", "GPIO9", 680),
        ),
    ),
    Module(
        "lcd",
        "LCD ST7789V2",
        "SPI · 170 × 320",
        "left",
        (25, 750, 425, 380),
        "lcd",
        (50, 825, 119, 228),
        (
            Pin("VCC", "3V3", 790),
            Pin("GND", "GND", 820),
            Pin("BL", "3V3", 850),
            Pin("SCK", "GPIO12", 880),
            Pin("MOSI", "GPIO11", 930),
            Pin("CS", "GPIO10", 980),
            Pin("DC", "GPIO13", 1030),
            Pin("RST", "GPIO14", 1080),
        ),
    ),
    Module(
        "bmp",
        "BMP280 3.3 V",
        "I²C dedicado · 0x76 / 0x77",
        "right",
        (1550, 250, 525, 260),
        "bmp280",
        (1933, 335, 108, 102),
        (
            Pin("VCC", "3V3", 330),
            Pin("GND", "GND", 370),
            Pin("SDA", "GPIO1", 410),
            Pin("SCL", "GPIO2", 450),
        ),
    ),
    Module(
        "gps",
        "GPS GY-NEO6MV2",
        "Conector: VCC · RX · TX · GND",
        "right",
        (1550, 570, 525, 260),
        "gps_neo6mv2",
        (1875, 655, 168, 143),
        (
            Pin("VCC", "3V3", 655),
            Pin("RX", "GPIO17", 690),
            Pin("TX", "GPIO18", 725),
            Pin("GND", "GND", 760),
        ),
    ),
)

BY_KEY = {module.key: module for module in MODULES}
assert len(BY_KEY) == len(MODULES)
assert tuple(pin.name for pin in BY_KEY["gps"].pins) == ("VCC", "RX", "TX", "GND")
assert tuple(pin.name for pin in BY_KEY["dht"].pins) == ("VCC", "DATA", "NC", "GND")
for module in MODULES:
    for pin in module.pins:
        if pin.net.startswith("GPIO"):
            gpio = pin.net.removeprefix("GPIO")
            assert gpio in BOARD_LEFT or gpio in BOARD_RIGHT, (module.key, pin)

PHOTO_CACHE: dict[str, str] = {}


def photo_data(name: str) -> str:
    if name not in PHOTO_CACHE:
        PHOTO_CACHE[name] = base64.b64encode((PARTS / f"{name}.png").read_bytes()).decode("ascii")
    return PHOTO_CACHE[name]


class Svg:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.items = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<defs><style>text{font-family:Arial,Helvetica,sans-serif;fill:#11233e}.title{font-size:28px;font-weight:700}.sub{font-size:14px}.head{font-size:18px;font-weight:700}.lab{font-size:14px;font-weight:700}.tiny{font-size:12px}.boardlab{font-size:12px;font-weight:700;fill:#fff}.note{font-size:13px}</style></defs>",
            f'<rect width="{width}" height="{height}" fill="#f5f8fc"/>',
        ]

    def add(self, markup: str) -> None:
        self.items.append(markup)

    def text(
        self,
        x: float,
        y: float,
        value: str,
        cls: str = "lab",
        *,
        anchor: str = "start",
        color: str | None = None,
    ) -> None:
        style = f' style="fill:{color}"' if color else ""
        self.add(
            f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}" dominant-baseline="middle"{style}>{html.escape(value)}</text>'
        )

    def line(self, d: str, color: str, width: float = 3, *, insulated: bool = False) -> None:
        if insulated:
            self.add(
                f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{width + 5}" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        self.add(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'
        )

    def dot(self, x: float, y: float, color: str, radius: float = 4) -> None:
        self.add(
            f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{color}" stroke="#fff" stroke-width="1.3"/>'
        )

    def photo(self, name: str, box: tuple[int, int, int, int]) -> None:
        x, y, width, height = box
        self.add(
            f'<image x="{x}" y="{y}" width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{photo_data(name)}"/>'
        )

    def finish(self) -> str:
        return "\n".join((*self.items, "</svg>", ""))


def board_row(net: str) -> tuple[str, int]:
    gpio = net.removeprefix("GPIO")
    if gpio in BOARD_LEFT:
        return "left", BOARD_LEFT.index(gpio)
    return "right", BOARD_RIGHT.index(gpio)


def draw_board(svg: Svg, *, photo: bool, breadboard: bool) -> None:
    if breadboard:
        for x in (575, 1105):
            svg.add(
                f'<rect x="{x}" y="150" width="270" height="985" rx="15" fill="#fff" stroke="#bbcbd9" stroke-width="3"/>'
            )
    svg.add(
        '<rect x="845" y="145" width="260" height="985" rx="17" fill="#15538e" stroke="#0a3560" stroke-width="4"/>'
    )
    if photo:
        svg.photo("esp_chip", (895, 253, 160, 207))
        svg.photo("esp_usb", (896, 1008, 158, 63))
    else:
        svg.add(
            '<rect x="895" y="253" width="160" height="207" rx="8" fill="#293a49" stroke="#8fa7b9" stroke-width="3"/>'
        )
        svg.text(975, 340, "ESP32-S3", "head", anchor="middle", color="#fff")
        svg.text(975, 366, "WROOM-1 N16R8", "tiny", anchor="middle", color="#fff")
        svg.add(
            '<rect x="900" y="1008" width="60" height="47" rx="5" fill="#cfd4d8"/><rect x="990" y="1008" width="60" height="47" rx="5" fill="#cfd4d8"/>'
        )
    for index, (left, right) in enumerate(zip(BOARD_LEFT, BOARD_RIGHT, strict=False)):
        y = 180 + 50 * index
        if breadboard:
            for x0, x1, holes in (
                (700, 850, (700, 730, 760, 790, 820)),
                (1100, 1250, (1130, 1160, 1190, 1220, 1250)),
            ):
                svg.line(f"M{x0} {y} H{x1}", "#c9d5df", 1.6)
                for hole in holes:
                    svg.dot(hole, y, "#27394b", 3.3)
        svg.dot(850, y, "#e9bb3d", 5)
        svg.dot(1100, y, "#e9bb3d", 5)
        svg.text(871, y, left, "boardlab")
        svg.text(1079, y, right, "boardlab", anchor="end")


def draw_rails(svg: Svg) -> None:
    for x, color in ((610, POWER), (650, GROUND), (1330, POWER), (1370, GROUND)):
        svg.line(f"M{x} 165 V1115", color, 5)
    svg.line("M610 165 V117 H1330 V165", POWER, 4)
    svg.line("M650 165 V140 H1370 V165", GROUND, 4)
    for x, label in ((610, "3V3"), (650, "GND"), (1330, "3V3"), (1370, "GND")):
        svg.text(x, 158, label, "lab", anchor="middle")
    svg.text(970, 111, "puente 3V3", "tiny", anchor="middle")
    svg.text(1000, 135, "puente GND", "tiny", anchor="middle")
    for x, y, color in (
        (610, 117, POWER),
        (1330, 117, POWER),
        (650, 140, GROUND),
        (1370, 140, GROUND),
    ):
        svg.dot(x, y, color)


def draw_card(svg: Svg, module: Module, *, photo: bool) -> None:
    x, y, width, height = module.box
    svg.add(
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="13" fill="#fff" stroke="#b7c8d9" stroke-width="2"/>'
    )
    svg.text(x + 17, y + 29, module.title, "head")
    svg.text(x + 17, y + 53, module.subtitle, "tiny")
    if photo:
        svg.photo(module.photo, module.photo_box)
    else:
        px, py, pw, ph = module.photo_box
        svg.add(
            f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="8" fill="#e8eef4" stroke="#c2d1de"/>'
        )
        svg.text(px + pw / 2, py + ph / 2, module.key.upper(), "lab", anchor="middle")
    for pin in module.pins:
        if module.side == "left":
            svg.text(x + width - 20, pin.y, pin.name, "lab", anchor="end")
        else:
            svg.text(x + 21, pin.y, pin.name, "lab")


def wire_endpoint(module: Module) -> int:
    x, _, width, _ = module.box
    return x + width if module.side == "left" else x


def draw_power(svg: Svg, module: Module, pin: Pin) -> None:
    start = wire_endpoint(module)
    rail = (
        (610 if pin.net == "3V3" else 650)
        if module.side == "left"
        else (1330 if pin.net == "3V3" else 1370)
    )
    color = POWER if pin.net == "3V3" else GROUND
    svg.line(f"M{start} {pin.y} H{rail}", color, 3.3, insulated=True)
    svg.dot(rail, pin.y, color)


def draw_signal(svg: Svg, module: Module, pin: Pin, *, breadboard: bool) -> None:
    side, row = board_row(pin.net)
    target_y = 180 + 50 * row
    target_x = (
        (700 if side == "left" else 1250) if breadboard else (850 if side == "left" else 1100)
    )
    color = COLORS[f"{module.key}.{pin.name}"]
    start = wire_endpoint(module)
    if module.key == "gps":
        # The real GPIO17/18 headers are on the left. These two insulated jumpers
        # run above the power bridges and end only on the marked left-side row.
        lane_y, lane_x, outer_x = (83, 515, 1460) if pin.name == "RX" else (96, 530, 1475)
        d = f"M{start} {pin.y} H{outer_x} V{lane_y} H{lane_x} V{target_y} H{target_x}"
    elif module.side == side == "left":
        offset = {"dht": 525, "oled": 515, "lcd": 505}.get(module.key, 515)
        if module.key == "lcd":
            offset += {"SCK": 0, "MOSI": 12, "CS": 24, "DC": 36, "RST": 48}[pin.name]
        elif module.key == "oled":
            offset += 14 if pin.name == "SCL" else 0
        d = f"M{start} {pin.y} H{offset} V{target_y} H{target_x}"
    elif module.side == side == "right":
        offset = 1460 if pin.name == "SDA" else 1440
        d = f"M{start} {pin.y} H{offset} V{target_y} H{target_x}"
    else:
        raise AssertionError((module.key, pin.name, side))
    svg.line(d, color, 3.1, insulated=True)
    svg.dot(target_x, target_y, color)


def draw_resistor(svg: Svg, x: int, y: int, width: int, height: int, label: str) -> None:
    svg.add(
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="3" fill="#fff1ca" stroke="#775a25" stroke-width="2"/>'
    )
    svg.text(x + width / 2, y + height / 2 + 1, label, "tiny", anchor="middle")


def draw_voltage_divider(svg: Svg, module: Module, *, breadboard: bool) -> None:
    target_x = 700 if breadboard else 850
    svg.line("M450 295 H500 V330 H525", COLORS["voltage.S"], 3.1, insulated=True)
    draw_resistor(svg, 525, 320, 42, 20, "12 kΩ")
    svg.line(f"M567 330 H{target_x}", COLORS["voltage.S"], 3.1, insulated=True)
    svg.dot(585, 330, COLORS["voltage.S"])
    svg.dot(target_x, 330, COLORS["voltage.S"])
    svg.line("M585 330 V315", GROUND, 3.1, insulated=True)
    draw_resistor(svg, 577, 285, 16, 30, "")
    svg.text(603, 300, "10 kΩ", "tiny")
    svg.line("M585 285 V275 H650", GROUND, 3.1, insulated=True)
    svg.dot(650, 275, GROUND)


def draw_dht_pullup(svg: Svg, *, breadboard: bool) -> None:
    target_x = 700 if breadboard else 850
    svg.line(f"M450 450 H525 V380 H{target_x}", COLORS["dht.DATA"], 3.1, insulated=True)
    svg.dot(550, 380, COLORS["dht.DATA"])
    svg.dot(target_x, 380, COLORS["dht.DATA"])
    svg.line("M550 380 V355 H560", POWER, 3.1, insulated=True)
    draw_resistor(svg, 560, 345, 40, 20, "4.7k")
    svg.line("M600 355 H610", POWER, 3.1, insulated=True)
    svg.dot(610, 355, POWER)


def render_main(name: str, *, photo: bool, breadboard: bool) -> None:
    svg = Svg(2100, 1215)
    title = {
        "diagrama-conexiones-esp32": "ESP32-S3 · conexiones por componente",
        "diagrama-conexiones-esp32-protoboard": "ESP32-S3 · montaje en protoboard con componentes",
        "diagrama-tecnico-esp32-protoboard": "ESP32-S3 · esquema técnico de protoboard",
    }[name]
    svg.text(30, 38, title, "title")
    svg.text(
        30,
        66,
        "GPIO verificados: LCD 10–14 · OLED 8/9 · DHT11 6 · GPS 17/18 · BMP280 1/2 · ADC 4",
        "sub",
    )
    if not breadboard:
        svg.text(
            30,
            89,
            "Las líneas de color terminan en los pines rotulados; solo los círculos indican contacto.",
            "tiny",
        )
    draw_board(svg, photo=photo, breadboard=breadboard)
    draw_rails(svg)
    # Board supplies both left and right power buses.
    dest_left, dest_right = (700, 1250) if breadboard else (850, 1100)
    svg.line(f"M610 180 H{dest_left}", POWER, 3.4, insulated=True)
    svg.dot(610, 180, POWER)
    svg.dot(dest_left, 180, POWER)
    svg.line(f"M{dest_right} 180 H1370", GROUND, 3.4, insulated=True)
    svg.dot(1370, 180, GROUND)
    svg.dot(dest_right, 180, GROUND)
    for module in MODULES:
        draw_card(svg, module, photo=photo)
    for module in MODULES:
        for pin in module.pins:
            if pin.net in ("3V3", "GND"):
                draw_power(svg, module, pin)
            elif pin.net == "NC":
                continue
            elif module.key == "voltage":
                draw_voltage_divider(svg, module, breadboard=breadboard)
            elif module.key == "dht":
                draw_dht_pullup(svg, breadboard=breadboard)
            else:
                draw_signal(svg, module, pin, breadboard=breadboard)
    svg.add(
        '<rect x="25" y="1150" width="2050" height="49" rx="9" fill="#fff" stroke="#b7c8d9" stroke-width="2"/>'
    )
    footer = "Riel rojo = 3V3 · riel oscuro = GND · cruces con borde blanco = cables aislados"
    if breadboard:
        footer += " · cada fila de cinco agujeros une solo su lado"
    svg.text(43, 1175, footer + ".", "note")
    svg.text(2025, 1175, "Comprueba la serigrafía del módulo GPS", "tiny", anchor="end")
    (VISUALS / f"{name}.svg").write_text(svg.finish())


def component_photo_box(module: Module) -> tuple[int, int, int, int]:
    return {
        "voltage": (65, 335, 240, 128),
        "dht": (88, 312, 145, 220),
        "oled": (64, 315, 255, 190),
        "lcd": (80, 292, 160, 300),
        "bmp": (89, 325, 185, 175),
        "gps": (70, 325, 245, 208),
    }[module.key]


def render_component(module: Module) -> None:
    svg = Svg(1250, 720)
    svg.text(32, 43, f"{module.title} → ESP32-S3 N16R8", "title")
    svg.text(
        32, 72, "Una señal por GPIO; etiquetas alineadas con las posiciones de la placa.", "sub"
    )
    svg.add(
        '<rect x="35" y="175" width="445" height="465" rx="14" fill="#fff" stroke="#b7c8d9" stroke-width="2"/>'
    )
    svg.text(55, 205, module.title, "head")
    svg.text(55, 232, module.subtitle, "tiny")
    svg.photo(module.photo, component_photo_box(module))
    svg.add(
        '<rect x="695" y="120" width="260" height="530" rx="16" fill="#15538e" stroke="#0a3560" stroke-width="4"/>'
    )
    svg.photo("esp_chip", (755, 205, 138, 178))
    svg.photo("esp_usb", (760, 568, 134, 54))

    def yrow(index: int) -> float:
        return 145 + 26.5 * index

    for i, (left, right) in enumerate(zip(BOARD_LEFT, BOARD_RIGHT, strict=False)):
        y = yrow(i)
        svg.dot(700, y, "#e9bb3d", 4.4)
        svg.dot(950, y, "#e9bb3d", 4.4)
        svg.text(721, y, left, "boardlab")
        svg.text(929, y, right, "boardlab", anchor="end")
    # One shared power bus per supply, both tied to actual board power pads.
    svg.line("M570 585 V145 H700", POWER, 3.1, insulated=True)
    svg.dot(700, 145, POWER)
    svg.text(580, 125, "3V3", "tiny")
    svg.line("M950 145 H1065 V108 H610 V585", GROUND, 3.1, insulated=True)
    svg.dot(950, 145, GROUND)
    svg.text(1030, 100, "GND", "tiny")
    first = 268 if len(module.pins) > 4 else 302
    spacing = 39 if len(module.pins) > 4 else 69
    pin_y = {pin.name: first + spacing * i for i, pin in enumerate(module.pins)}
    for i, pin in enumerate(module.pins):
        py = pin_y[pin.name]
        svg.text(445, py, pin.name, "lab", anchor="end")
        if pin.net == "NC":
            svg.dot(480, py, "#a9b3bd", 3)
            continue
        if pin.net in ("3V3", "GND"):
            color = POWER if pin.net == "3V3" else GROUND
            bus = 570 if pin.net == "3V3" else 610
            svg.line(f"M480 {py} H{bus}", color, 3.1, insulated=True)
            svg.dot(bus, py, color)
            continue
        side, index = board_row(pin.net)
        ty = yrow(index)
        color = COLORS[f"{module.key}.{pin.name}"]
        if module.key == "voltage":
            svg.line(f"M480 {py} H523 V{ty} H545", color, 3, insulated=True)
            draw_resistor(svg, 545, int(ty - 10), 43, 20, "12 kΩ")
            svg.line(f"M588 {ty} H700", color, 3, insulated=True)
            svg.dot(700, ty, color)
            svg.dot(600, ty, color)
            svg.line(f"M600 {ty} V{ty + 18}", GROUND, 3, insulated=True)
            draw_resistor(svg, 592, int(ty + 18), 16, 33, "")
            svg.text(615, ty + 35, "10 kΩ", "tiny")
            svg.line(f"M600 {ty + 51} H610", GROUND, 3, insulated=True)
            svg.dot(610, ty + 51, GROUND)
        elif side == "left":
            lane = 535 + 13 * i
            svg.line(f"M480 {py} H{lane} V{ty} H700", color, 3, insulated=True)
            svg.dot(700, ty, color)
        else:
            lane = 535 + 13 * i
            outer = 1045 + 14 * i
            svg.line(f"M480 {py} H{lane} V111 H{outer} V{ty} H950", color, 3, insulated=True)
            svg.dot(950, ty, color)
        if module.key == "dht" and pin.name == "DATA":
            # Pull-up from DATA to the 3V3 bus, with the resistor in series.
            svg.line(f"M570 {ty} V{ty - 22}", POWER, 3, insulated=True)
            draw_resistor(svg, 562, int(ty - 53), 16, 31, "")
            svg.text(580, ty - 39, "4.7 kΩ", "tiny")
            svg.line(f"M570 {ty - 53} V145", POWER, 3, insulated=True)
            svg.dot(570, ty, POWER)
    detail = {
        "lcd": "CS 10 · MOSI 11 · SCK 12 · DC 13 · RST 14 · BL 3V3",
        "oled": "SDA 8 · SCL 9 · alimentación 3V3 / GND",
        "dht": "DATA 6 · pull-up 4.7 kΩ a 3V3 · NC sin conectar",
        "gps": "TX GPS → GPIO18 (RX ESP) · RX GPS ← GPIO17 (TX ESP)",
        "bmp": "SDA 1 · SCL 2 · alimentación 3V3 / GND",
        "voltage": "S → 12 kΩ → GPIO4; nodo GPIO4 → 10 kΩ → GND",
    }[module.key]
    svg.add('<rect x="35" y="663" width="1180" height="40" rx="8" fill="#fff" stroke="#b7c8d9"/>')
    svg.text(55, 683, detail, "note")
    name = f"diagrama-componente-{module.key}-esp32"
    (VISUALS / f"{name}.svg").write_text(svg.finish())


def main() -> None:
    render_main("diagrama-conexiones-esp32", photo=True, breadboard=False)
    render_main("diagrama-conexiones-esp32-protoboard", photo=True, breadboard=True)
    render_main("diagrama-tecnico-esp32-protoboard", photo=False, breadboard=True)
    for module in MODULES:
        render_component(module)
    for stem in (
        "diagrama-conexiones-esp32",
        "diagrama-conexiones-esp32-protoboard",
        "diagrama-tecnico-esp32-protoboard",
        *(f"diagrama-componente-{module.key}-esp32" for module in MODULES),
    ):
        subprocess.run(
            ["rsvg-convert", str(VISUALS / f"{stem}.svg"), "-o", str(VISUALS / f"{stem}.png")],
            check=True,
        )
    print("Generated 3 overview diagrams and 6 component diagrams")


if __name__ == "__main__":
    main()
