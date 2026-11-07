#!/usr/bin/env python3
"""Generate conservative, per-part GRBL toolpaths for the ESP32 MVP acrylic panels.

Defaults are an explicit starting point, not a substitute for checking the actual
controller, cutter, material, workholding, and machine coordinate setup.
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "gcode"

# Starter settings for a common 3018 Pro setup. Edit to match the actual machine.
TOOL_DIAMETER = 3.175  # mm, assumed single-flute end mill
MATERIAL_THICKNESS = 2.8  # mm, confirmed acrylic sheet thickness
STEP_DOWN = 0.35  # mm/pass
FINAL_DEPTH = 3.15  # mm, 0.35 mm into a sacrificial spoilboard
TAB_THICKNESS = 0.5  # mm of stock left at the perimeter tabs
TAB_WIDTH = 6.0  # mm
FEED = 300  # mm/min, conservative starter value for acrylic
PLUNGE = 80  # mm/min
SPINDLE_S = 1000  # assumes GRBL $30=1000; verify before running
SAFE_Z = 5.0
STOCK_MARGIN = 5.0

R = TOOL_DIAMETER / 2
DEPTHS = [round(i * STEP_DOWN, 3) for i in range(1, math.ceil((FINAL_DEPTH - 1e-9) / STEP_DOWN))]
DEPTHS.append(FINAL_DEPTH)


def cross(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def offset_polygon(poly: list[tuple[float, float]], distance: float) -> list[tuple[float, float]]:
    """Offset a simple CCW polygon using miter joins; positive is outside."""
    shifted: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        # For CCW input the right-hand normal points outside.
        nx, ny = dy / length, -dx / length
        shifted.append(((a[0] + distance * nx, a[1] + distance * ny), (dx, dy)))

    result: list[tuple[float, float]] = []
    for i in range(len(poly)):
        p1, d1 = shifted[i - 1]
        p2, d2 = shifted[i]
        denom = cross(d1, d2)
        if abs(denom) < 1e-9:
            result.append(p2)
            continue
        t = cross((p2[0] - p1[0], p2[1] - p1[1]), d2) / denom
        result.append((p1[0] + t * d1[0], p1[1] + t * d1[1]))
    return result


def xy(p: tuple[float, float]) -> str:
    return f"X{p[0]:.3f} Y{p[1]:.3f}"


def add_pass_header(lines: list[str], depth: float, start: tuple[float, float]) -> None:
    lines.extend([f"G0 Z{SAFE_Z:.3f}", f"G0 {xy(start)}", f"G1 Z{-depth:.3f} F{PLUNGE}"])


def cut_loop(lines: list[str], poly: list[tuple[float, float]], depth: float) -> None:
    add_pass_header(lines, depth, poly[0])
    lines.extend(f"G1 {xy(p)} F{FEED}" for p in poly[1:])
    lines.append(f"G1 {xy(poly[0])} F{FEED}")


def cut_circle(lines: list[str], center: tuple[float, float], nominal_diameter: float) -> None:
    radius = nominal_diameter / 2 - R
    if radius <= 0:
        raise ValueError("Cutter is too large for one of the mounting holes")
    start = (center[0] + radius, center[1])
    for depth in DEPTHS:
        add_pass_header(lines, depth, start)
        lines.append(f"G2 {xy(start)} I{-radius:.3f} J0.000 F{FEED}")


def cut_slot(lines: list[str], center: tuple[float, float], length: float, width: float) -> None:
    """Mill an obround slot with two parallel passes, one-flute tool assumed."""
    end = length / 2 - R
    half_spacing = max(0.0, width / 2 - R)
    for depth in DEPTHS:
        for yoff in (-half_spacing, half_spacing):
            start = (center[0] - end, center[1] + yoff)
            finish = (center[0] + end, center[1] + yoff)
            add_pass_header(lines, depth, start)
            lines.append(f"G1 {xy(finish)} F{FEED}")


def cut_outer_with_tabs(lines: list[str], poly: list[tuple[float, float]]) -> None:
    # Cut full depth in steps while preserving a thin bottom skin.
    for depth in DEPTHS[:-2]:
        cut_loop(lines, poly, depth)

    depth = DEPTHS[-1]
    shallow_z = -(MATERIAL_THICKNESS - TAB_THICKNESS)
    add_pass_header(lines, depth, poly[0])
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        length = math.dist(a, b)
        if length < TAB_WIDTH + 8:
            lines.append(f"G1 {xy(b)} F{FEED}")
            continue
        direction = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        t0 = (length - TAB_WIDTH) / 2
        t1 = (length + TAB_WIDTH) / 2
        tab_start = (a[0] + direction[0] * t0, a[1] + direction[1] * t0)
        tab_end = (a[0] + direction[0] * t1, a[1] + direction[1] * t1)
        lines.append(f"G1 {xy(tab_start)} F{FEED}")
        lines.append(f"G1 Z{shallow_z:.3f} F{PLUNGE}")
        lines.append(f"G1 {xy(tab_end)} F{FEED}")
        lines.append(f"G1 Z{-depth:.3f} F{PLUNGE}")
        lines.append(f"G1 {xy(b)} F{FEED}")
    lines.append(f"G1 {xy(poly[0])} F{FEED}")


def start_job(name: str, blank: tuple[float, float]) -> list[str]:
    return [
        f"({name})",
        "(GRBL 1.1 starter file; check controller and spindle settings before use)",
        f"(Blank: {blank[0]:.1f} x {blank[1]:.1f} mm; XY zero: blank lower-left)",
        "(Z zero: top surface; acrylic 2.8 mm; 3.175 mm single-flute tool assumed)",
        f"(Feed {FEED} mm/min; plunge {PLUNGE}; stepdown {STEP_DOWN}; final Z {-FINAL_DEPTH})",
        f"(S{SPINDLE_S} assumes GRBL $30=1000; confirm spindle PWM scale)",
        "(Secure stock to spoilboard; tabs hold the outside profile for cleanup)",
        "G21 G90 G17 G94 G54",
        "G40 G49 G80",
        "M5",
        f"G0 Z{SAFE_Z:.3f}",
        f"M3 S{SPINDLE_S}",
        "G4 P2",
    ]


def finish_job(lines: list[str]) -> list[str]:
    lines.extend([f"G0 Z{SAFE_Z:.3f}", "M5", "M30"])
    return lines


def write_job(filename: str, lines: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / filename).write_text("\n".join(lines) + "\n", encoding="ascii")


def front_job() -> None:
    # The 5 mm margin gives the outside toolpath room on a 155 x 102 mm blank.
    panel_x, panel_y = STOCK_MARGIN, STOCK_MARGIN
    lines = start_job("FRONT PANEL - ESP32 MVP", (155, 102))
    windows = [
        [(panel_x + 22, panel_y + 24), (panel_x + 46, panel_y + 24),
         (panel_x + 46, panel_y + 68), (panel_x + 22, panel_y + 68)],
        [(panel_x + 79, panel_y + 36), (panel_x + 106, panel_y + 36),
         (panel_x + 106, panel_y + 56), (panel_x + 79, panel_y + 56)],
    ]
    for win in windows:
        toolpath = offset_polygon(win, -R)
        for depth in DEPTHS:
            add_pass_header(lines, depth, toolpath[0])
            lines.extend(f"G1 {xy(p)} F{FEED}" for p in toolpath[1:])
            lines.append(f"G1 {xy(toolpath[0])} F{FEED}")

    # M3 mounting/retention holes, Ø4.2 mm to suit the assumed 3.175 mm cutter.
    for x in (panel_x + 7, panel_x + 138):
        for y in (panel_y + 14, panel_y + 78):
            cut_circle(lines, (x, y), 4.2)
    # Adjustable display retention slots, Ø/width suitable for this cutter.
    slots = [(18,20),(51,20),(18,72),(51,72),(75,31),(110,31),(75,61),(110,61)]
    for x, y in slots:
        cut_slot(lines, (panel_x + x, panel_y + y), 9.2, 4.2)

    outline = [(panel_x, panel_y), (panel_x + 145, panel_y),
               (panel_x + 145, panel_y + 92), (panel_x, panel_y + 92)]
    cut_outer_with_tabs(lines, offset_polygon(outline, R))
    write_job("esp32_mvp_front_grbl.nc", finish_job(lines))


def rear_job() -> None:
    x0, y0 = STOCK_MARGIN, STOCK_MARGIN
    lines = start_job("REAR PANEL - ESP32 MVP", (155, 92))
    # Cable notch opens through the lower edge; the polygon includes the notch.
    outline = [(x0,y0),(x0+57.5,y0),(x0+57.5,y0+9),(x0+87.5,y0+9),
               (x0+87.5,y0),(x0+145,y0),(x0+145,y0+82),(x0,y0+82)]
    for x in (x0 + 7, x0 + 138):
        for y in (y0 + 12, y0 + 70):
            cut_circle(lines, (x, y), 4.2)
    cut_outer_with_tabs(lines, offset_polygon(outline, R))
    write_job("esp32_mvp_rear_grbl.nc", finish_job(lines))


def side_job() -> None:
    x0, y0 = STOCK_MARGIN, STOCK_MARGIN
    lines = start_job("SIDE CHEEK - CUT TWO", (92, 128))
    profile = [(x0,y0),(x0+82,y0),(x0+82,y0+14),
               (x0+28.4,y0+118),(x0,y0+31)]
    for x, y in ((12,7),(70,7),(7.3,43.3),(27,104.2)):
        cut_circle(lines, (x0+x, y0+y), 4.2)
    cut_outer_with_tabs(lines, offset_polygon(profile, R))
    write_job("esp32_mvp_side_grbl.nc", finish_job(lines))


if __name__ == "__main__":
    front_job()
    rear_job()
    side_job()
    print(f"Generated GRBL starter toolpaths in {OUT}")
