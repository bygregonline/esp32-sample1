"""Generate dimensioned, IKEA-style assembly sheets from the enclosure CAD specs."""

from __future__ import annotations

import csv
import html
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "manuales"
OUT.mkdir(exist_ok=True)

INK = "#172b3a"
BLUE = "#236b91"
ORANGE = "#d27818"
MUTED = "#536773"
PAPER = "#f7f8f5"


def t(x: float, y: float, text: str, size: int = 22, weight: int = 400,
      fill: str = INK, anchor: str = "start") -> str:
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{html.escape(text)}</text>')


def rect(x: float, y: float, w: float, h: float, fill: str = "none",
         stroke: str = INK, sw: float = 3, rx: float = 0) -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def dim_h(x1: float, x2: float, y: float, label: str, ext_y1: float | None = None,
          ext_y2: float | None = None) -> str:
    parts = []
    if ext_y1 is not None:
        parts.append(f'<path d="M{x1} {ext_y1} V{y+8} M{x2} {ext_y2 if ext_y2 is not None else ext_y1} V{y+8}"/>')
    parts.append(f'<path d="M{x1} {y} H{x2}" marker-start="url(#arrow)" marker-end="url(#arrow)"/>')
    parts.append(t((x1+x2)/2, y-9, label, 20, 700, BLUE, "middle"))
    return '<g fill="none" stroke="'+BLUE+'" stroke-width="2">'+''.join(parts)+'</g>'


def dim_v(x: float, y1: float, y2: float, label: str, ext_x1: float | None = None,
          ext_x2: float | None = None) -> str:
    parts = []
    if ext_x1 is not None:
        parts.append(f'<path d="M{ext_x1} {y1} H{x-8} M{ext_x2 if ext_x2 is not None else ext_x1} {y2} H{x-8}"/>')
    parts.append(f'<path d="M{x} {y1} V{y2}" marker-start="url(#arrow)" marker-end="url(#arrow)"/>')
    parts.append(f'<text x="{x-10}" y="{(y1+y2)/2}" transform="rotate(-90 {x-10} {(y1+y2)/2})" '
                 f'font-size="20" font-weight="700" fill="{BLUE}" text-anchor="middle">{html.escape(label)}</text>')
    return '<g fill="none" stroke="'+BLUE+'" stroke-width="2">'+''.join(parts)+'</g>'


def header(title: str, subtitle: str, w: int, h: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="4.5" refY="4.5" orient="auto-start-reverse">'
        f'<path d="M0 0 L9 4.5 L0 9 Z" fill="{BLUE}"/></marker></defs>',
        '<style>text{font-family:Arial,Helvetica,sans-serif}</style>',
        f'<rect width="{w}" height="{h}" fill="{PAPER}"/>',
        rect(35, 28, w-70, 108, "#fff", "#ccd5d8", 2, 18),
        t(68, 78, title, 39, 700), t(68, 115, subtitle, 21, 400, MUTED),
    ]


def card(items: list[str], x: int, y: int, w: int, h: int, title: str) -> None:
    items.extend([rect(x, y, w, h, "#fff", "#ccd5d8", 2, 14), t(x+22, y+39, title, 25, 700)])


def save_svg_png(name: str, items: list[str]) -> None:
    items.append("</svg>")
    svg = OUT / f"{name}.svg"
    png = OUT / f"{name}.png"
    svg.write_text("\n".join(items), encoding="utf-8")
    subprocess.run(["rsvg-convert", str(svg), "-o", str(png)], check=True)


def dimensions_page() -> None:
    w, h = 1800, 1270
    a = header("01 · DIMENSIONES DE LA CARCASA", "Todas las cotas están en milímetros · esquemas ortográficos · no escalar desde la imagen", w, h)

    cards = [(45, 165, 410), (475, 165, 410), (905, 165, 410), (1335, 165, 420)]
    for (cx, cy, cw), title in zip(cards, ["FRENTE", "TRASERA", "LATERAL", "TAPA SUPERIOR"], strict=True):
        card(a, cx, cy, cw, 455, title)

    # Front elevation.
    x, y, s = 88, 250, 1.72
    fw, fh = 190*s, 110*s
    a.append(rect(x, y, fw, fh, "#eef1f1", INK, 3))
    lcd_x, lcd_y = x+28.78*s, y+30.02*s
    a.append(rect(lcd_x, lcd_y, 74.44*s, 49.96*s, "#dcecf1", BLUE, 3, 3))
    oled_x, oled_y = x+142*s, y+45*s
    a.append(rect(oled_x, oled_y, 27*s, 20*s, "#dcecf1", BLUE, 3, 3))
    a.append(dim_h(x, x+fw, y+fh+30, "190 mm", y+fh, y+fh))
    a.append(dim_v(x-22, y, y+fh, "110 mm", x, x))
    a.append(t(80, 578, "Ventanas: LCD 74.4 × 50 · OLED 27 × 20", 15, 400, MUTED))
    a.append(t(80, 598, "Panel de 3 mm · pitch LCD aún provisional", 15, 400, MUTED))

    # Rear elevation.
    x, y, s = 507, 250, 1.72
    rw, rh = 190*s, 110*s
    a.append(rect(x, y, rw, rh, "#eef1f1", INK, 3))
    for px in [34, 100]:
        a.append(rect(x+px*s, y+25*s, 56*s, 60*s, "#d9e2f0", BLUE, 2, 3))
        a.append(t(x+(px+28)*s, y+57*s, "56 × 60", 15, 700, BLUE, "middle"))
    a.append(f'<rect x="{x+85*s}" y="{y+95*s}" width="20" height="10" rx="5" fill="#fff" stroke="{ORANGE}" stroke-width="3"/>')
    a.append(dim_h(x, x+rw, y+rh+30, "190 mm", y+rh, y+rh))
    a.append(dim_v(x-20, y, y+rh, "110 mm", x, x))
    a.append(t(500, 578, "2 paneles · 56 × 60 × 3 mm · separación 10", 14, 400, MUTED))
    a.append(t(500, 598, "Ranura inferior de cable USB: 20 × 10 mm", 14, 700, ORANGE))

    # Side profile.
    ox, oy, s = 967, 490, 1.72
    pts = [(0,3),(100,3),(100,113.6),(34.02,113.6),(0,9)]
    path = " ".join(("M" if i == 0 else "L")+f"{ox+px*s},{oy-(pz-3)*s}" for i,(px,pz) in enumerate(pts))+" Z"
    a.append(f'<path d="{path}" fill="#e2e7e7" stroke="{INK}" stroke-width="3"/>')
    a.append(dim_h(ox, ox+100*s, oy+30, "100 mm", oy, oy))
    a.append(dim_v(ox+100*s+25, oy-(113.6-3)*s, oy, "110.6 mm", ox+100*s, ox+100*s))
    a.append(t(1010, 578, "Laterales × 2 · espesor 14 mm", 15, 400, MUTED))
    a.append(t(1010, 598, "Inclinación del frente: 18°", 15, 700, BLUE))

    # Dedicated plan view of the inset lid, with its four counterbores.
    x, y, s = 1350, 300, 1.95
    tw, th = 190*s, 64.98*s
    a.append(rect(x, y, tw, th, "#eef1f1", INK, 3))
    a.append(f'<rect x="{x+14.5*s}" y="{y+2*s}" width="{161*s}" height="{60.98*s}" fill="none" stroke="{MUTED}" stroke-width="2" stroke-dasharray="7 6"/>')
    for px in [7,183]:
        for py in [12,52.98]:
            a.append(f'<circle cx="{x+px*s}" cy="{y+py*s}" r="7.2" fill="#fff" stroke="{ORANGE}" stroke-width="2.5"/>')
    a.append(dim_h(x, x+tw, y+th+38, "190 mm", y+th, y+th))
    a.append(dim_v(x-22, y, y+th, "65.0 mm", x, x))
    a.append(t(1350, 540, "4 asientos M3 · Ø7.2 × 4 mm", 15, 700, ORANGE))
    a.append(t(1350, 564, "Borde a centro: 7 mm × 12 mm", 15, 400, MUTED))
    a.append(t(1350, 588, "Lengüeta inferior: 3 mm (línea punteada)", 14, 400, MUTED))

    # Detail band with thicknesses and screw-head seat section.
    card(a, 45, 650, 1710, 490, "ESPESORES Y DETALLE DEL ASIENTO DE TORNILLO")
    a.extend([t(78, 730, "PIEZAS", 21, 700),
              t(78, 777, "Frontal y trasera · 3 mm", 18),
              t(78, 817, "Base · 3 mm", 18),
              t(78, 857, "Tapa · 7 mm + lengüeta 3 mm", 18),
              t(78, 897, "Clip solar · 16 × 10 × 6 mm aprox.", 18),
              t(78, 937, "Ranuras de correas ESP32 · 3 × 10 mm", 18),
              t(78, 977, "Ranura base · 24 × 9 mm", 18),
              t(78, 1035, "CONFIRMAR: M3, inserto y patrón de agujeros del LCD.", 17, 700, ORANGE)])
    # Enlarged cutaway: the head rests on a real shoulder inside the counterbore.
    a.append(t(860, 730, "CORTE DE TAPA · M3 Y TAPÓN", 21, 700))
    a.append(rect(1000, 790, 330, 168, "#e8edef", INK, 3))
    a.append(f'<rect x="{1100}" y="{790}" width="130" height="96" fill="#fff" stroke="{ORANGE}" stroke-width="3"/>')
    a.append(f'<rect x="{1134}" y="{886}" width="62" height="72" fill="#fff" stroke="{BLUE}" stroke-width="3"/>')
    a.append(rect(1115, 814, 100, 72, "#d7dcdf", INK, 2, 6))
    a.append(rect(1100, 790, 130, 24, "#fff", ORANGE, 2, 4))
    a.append(t(1370, 816, "Tapón Ø7 × 1", 16, 700, ORANGE))
    a.append(t(1370, 856, "Asiento Ø7.2 × 4", 16, 700, ORANGE))
    a.append(t(1370, 896, "Cabeza M3 ref. Ø5.5 × 3", 16))
    a.append(t(1370, 936, "Orificio pasante Ø3.4", 16, 700, BLUE))
    a.append(t(1370, 976, "Hombro de apoyo = 3 mm", 16, 700, BLUE))
    a.append(f'<path d="M1080 890 H1005 M1180 965 H1005" fill="none" stroke="{BLUE}" stroke-width="2" marker-end="url(#arrow)"/>')
    a.append(t(860, 1055, "La cabeza apoya en el escalón; el tornillo aprieta contra el inserto del lateral.", 17, 400, MUTED))
    a.append(t(860, 1090, "Coloca los tapones al terminar el apriete.", 17, 700, ORANGE))
    save_svg_png("dimensiones-mm", a)


ROWS = [
    ("A", "Panel frontal", "1", "190 × 110 × 3", "Ventana LCD y OLED"),
    ("B", "Panel posterior", "1", "190 × 110 × 3", "Ranura USB 20 × 10"),
    ("C", "Base", "1", "190 × 100 × 3", "Ranuras para correas ESP32"),
    ("D", "Tapa encajada", "1", "190 × 65.0 × 7", "Alojamientos de cabeza M3"),
    ("E", "Lateral triangular", "2", "Perfil 100 × 110.6; ancho 14", "Insertos térmicos M3"),
    ("F", "Clip solar", "6", "16 × 10 × 6 aprox.", "Retención de panel sin perforarlo"),
    ("G", "Tapón de tapa", "4", "Ø7 × 1", "Se instala después de apretar"),
    ("H", "Placa ESP32-S3", "1", "Según modelo comprado", "Fijar con 2 correas"),
    ("I", "LCD SPI ILI9488 3.5 in", "1", "PCB ref. 98 × 56.34", "Pitch de agujeros provisional"),
    ("J", "OLED SSD1306", "1", "Ventana 27 × 20", "Medir PCB real"),
    ("K", "Panel solar Steren PS-003", "2", "56 × 60 × 3", "Medida de referencia"),
    ("L", "Tornillo M3 × 8 Allen", "16", "Ø cabeza estándar 5.5 × 3", "12 carcasa + 4 tapa; confirmar largo"),
    ("M", "Inserto térmico M3", "16", "Alojamiento CAD Ø4.2 × 9", "Elegir inserto y ajustar al fabricante"),
    ("N", "Tornillo y tuerca M2", "6 + 6", "Longitud según panel y clip", "Clips solares"),
    ("O", "Fijación M2.5 LCD", "4 juegos", "Longitud según PCB", "Tornillo + tuerca si el PCB lo requiere"),
    ("P", "Fijación OLED", "4 juegos", "Compatible con ranura 2.6", "M2 o correa según el PCB"),
    ("Q", "Correa plástica", "2", "Ancho máx. 3 mm", "Sujeción de ESP32 a la base"),
    ("R", "Cable de alimentación USB", "1", "Conector debe pasar por 20 × 10", "Longitud según uso"),
]


def materials_page() -> None:
    w, h = 1800, 1330
    a = header("LISTA DE MATERIALES", "Carcasa ESP32 · cantidades para 1 unidad · cotas en mm · piezas comerciales sujetas al modelo comprado", w, h)
    card(a, 45, 160, 1710, 1095, "COMPONENTES, PIEZAS IMPRESAS Y TORNILLERÍA")
    x0, y0 = 70, 245
    widths = [70, 430, 105, 445, 570]
    heads = ["ID", "PIEZA", "CANT.", "MEDIDA / TAMAÑO", "NOTA DE COMPRA O MONTAJE"]
    x = x0
    for width, label in zip(widths, heads, strict=True):
        a.append(rect(x, y0, width, 47, "#e5edf0", "#c3cdd1", 1))
        a.append(t(x+12, y0+31, label, 17, 700, INK))
        x += width
    row_h = 47
    for i, row in enumerate(ROWS):
        y = y0+47+i*row_h
        x = x0
        bg = "#fff" if i%2 == 0 else "#f0f3f2"
        for width, value in zip(widths, row, strict=True):
            a.append(rect(x, y, width, row_h, bg, "#d7dfe1", 1))
            a.append(t(x+12, y+30, value, 16 if len(value)>36 else 17, 400,
                       BLUE if x == x0 else INK))
            x += width
    a.append(rect(70, 1153, 1660, 88, "#fff7e8", "#e2be82", 2, 10))
    a.append(t(90, 1188, "TORNILLERÍA DE LA TAPA", 18, 700, ORANGE))
    a.append(t(90, 1220, "La cabeza M3 apoya en el hombro de 3 mm; se aprieta en el inserto y luego se cubre con el tapón.", 17, 400))
    a.append(t(70, 1285, "No incluidos en este diseño mecánico: batería, controlador de carga solar, cableado y conectores eléctricos.", 16, 400, MUTED))
    save_svg_png("lista-materiales", a)

    with (OUT / "lista-materiales.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Pieza", "Cantidad", "Medida / tamaño", "Nota"])
        writer.writerows(ROWS)

    markdown = ["# Lista de materiales · carcasa ESP32", "",
                "Cantidades para una unidad. Las piezas impresas siguen el CAD; valida las piezas comerciales con sus fichas técnicas antes de fabricar.", "",
                "| ID | Pieza | Cantidad | Medida / tamaño | Nota |", "|---|---|---:|---|---|"]
    markdown.extend("| " + " | ".join(row) + " |" for row in ROWS)
    markdown.extend(["", "El CAD incluye los agujeros y asientos. Confirma el largo de los M3 y las dimensiones del inserto térmico según las piezas que compres. No se incluyen batería ni controlador solar.", ""])
    (OUT / "lista-materiales.md").write_text("\n".join(markdown), encoding="utf-8")


def assembly_page() -> None:
    w, h = 1800, 1450
    a = header("MONTAJE · PASO A PASO", "Orden sugerido · flechas indican dirección de montaje · tornillos se muestran como cantidades, no instalados", w, h)
    cw, ch = 550, 580
    positions = [(45,160),(625,160),(1205,160),(45,775),(625,775),(1205,775)]
    titles = ["PREPARA LAS PIEZAS", "ARMA BASE Y LATERALES", "COLOCA FRENTE Y TRASERA", "MONTA LAS PANTALLAS", "FIJA LOS PANELES SOLARES", "CIERRA CON LA TAPA"]
    notes = [
        ["Identifica A–G en la lista de materiales.", "La tapa (D) encaja dentro de los laterales.", "No instales los tapones todavía."],
        ["Apoya C sobre una mesa.", "Alinea los dos laterales E con los bordes.", "Fija con 4 tornillos M3 × 8 desde abajo."],
        ["Coloca A al frente y B atrás.", "Alinea los orificios con los insertos.", "Aprieta 8 tornillos M3 × 8."],
        ["Fija el LCD desde el interior: 4 × M2.5.", "Ajusta la OLED en sus ranuras: 4 fijaciones.", "Asegura la placa con 2 correas en C."],
        ["Pon 2 paneles K sobre B.", "Retén con 6 clips F y tornillos/tuercas M2.", "Mantén libre el paso USB 20 × 10 mm."],
        ["Asienta D en los rebajes; tapa los laterales.", "Aprieta 4 tornillos M3 hasta el hombro.", "Presiona los 4 tapones G al final."],
    ]
    for i, ((x,y), title, lines) in enumerate(zip(positions,titles,notes,strict=True), start=1):
        card(a,x,y,cw,ch,f"{i:02d} · {title}")
        # Consistent visual construction illustrations.
        if i == 1:
            for j,(label,desc) in enumerate([("A–C","frente · trasera · base"),("D–E","tapa · laterales ×2"),("F–G","clips ×6 · tapones ×4")]):
                yy=y+110+j*85
                a.append(rect(x+35,yy,112,56,"#e8edef",INK,2,6))
                a.append(t(x+91,yy+37,label,22,700,BLUE,"middle"))
                a.append(t(x+170,yy+36,desc,18,400))
            icon_y=y+355
            a.append(rect(x+65,icon_y,420,70,"#f5f7f6", "#9babb1",2,8))
            a.append(t(x+275,icon_y+29,"M3 × 8: 16 piezas",20,700,ORANGE,"middle"))
            a.append(t(x+275,icon_y+55,"M2 solar: 6 · insertos M3: 16",17,400,INK,"middle"))
        elif i == 2:
            a.append(rect(x+105,y+125,345,175,"#dfe7e8",INK,3,8))
            a.append(t(x+278,y+220,"C · BASE",22,700,BLUE,"middle"))
            # Upright side walls as unfolded side profiles.
            a.append(f'<path d="M{x+165} {y+92} L{x+165} {y+135} M{x+390} {y+92} L{x+390} {y+135}" stroke="{ORANGE}" stroke-width="4" marker-end="url(#arrow)"/>')
            a.append(f'<path d="M{x+130} {y+350} L{x+130} {y+310} M{x+420} {y+350} L{x+420} {y+310}" stroke="{ORANGE}" stroke-width="4" marker-end="url(#arrow)"/>')
            a.append(t(x+275,y+390,"M3 × 8 · 4 tornillos",19,700,ORANGE,"middle"))
        elif i == 3:
            a.append(rect(x+105,y+125,345,50,"#e8edef",INK,3,6))
            a.append(t(x+278,y+158,"A · FRENTE",18,700,BLUE,"middle"))
            a.append(rect(x+105,y+305,345,50,"#e8edef",INK,3,6))
            a.append(t(x+278,y+338,"B · TRASERA",18,700,BLUE,"middle"))
            a.append(rect(x+185,y+195,185,80,"#f4f6f5",INK,3,8))
            a.append(t(x+278,y+242,"E × 2",20,700,BLUE,"middle"))
            a.append(f'<path d="M{x+278} {y+95} V{y+120} M{x+278} {y+395} V{y+360}" stroke="{ORANGE}" stroke-width="4" marker-end="url(#arrow)"/>')
            a.append(t(x+278,y+415,"M3 × 8 · 8 tornillos",19,700,ORANGE,"middle"))
        elif i == 4:
            a.append(rect(x+95,y+140,360,220,"#e8edef",INK,3,8))
            a.append(rect(x+155,y+190,175,100,"#dcecf1",BLUE,3,5))
            a.append(rect(x+365,y+215,60,50,"#dcecf1",BLUE,3,5))
            a.append(t(x+242,y+315,"LCD",18,700,BLUE,"middle"))
            a.append(t(x+395,y+286,"OLED",16,700,BLUE,"middle"))
            a.append(t(x+275,y+390,"LCD: 4 × M2.5 · OLED: 4 fijaciones",17,700,ORANGE,"middle"))
            a.append(t(x+275,y+422,"ESP32: 2 correas por ranuras de la base",16,400,INK,"middle"))
        elif i == 5:
            a.append(rect(x+105,y+160,345,220,"#e8edef",INK,3,8))
            a.append(rect(x+155,y+195,105,130,"#d9e2f0",BLUE,2,4))
            a.append(rect(x+295,y+195,105,130,"#d9e2f0",BLUE,2,4))
            a.append(t(x+207,y+265,"56 × 60",17,700,BLUE,"middle"))
            a.append(t(x+347,y+265,"56 × 60",17,700,BLUE,"middle"))
            for xx in [145,270,410]:
                for yy in [185,335]:
                    a.append(f'<circle cx="{x+xx}" cy="{y+yy}" r="8" fill="{ORANGE}"/>')
            a.append(f'<rect x="{x+260}" y="{y+345}" width="60" height="28" rx="14" fill="#fff" stroke="{ORANGE}" stroke-width="3"/>')
            a.append(t(x+275,y+405,"6 clips + 6 tornillos M2 + 6 tuercas",16,700,ORANGE,"middle"))
            a.append(t(x+275,y+435,"Deja libre la ranura USB de la parte baja",15,400,INK,"middle"))
        else:
            a.append(rect(x+100,y+230,350,105,"#e8edef",INK,3,8))
            a.append(t(x+275,y+290,"CARCASA",20,700,BLUE,"middle"))
            a.append(rect(x+115,y+105,320,55,"#dfe6e7",INK,3,6))
            a.append(t(x+275,y+140,"D · TAPA 190 × 65 mm",17,700,BLUE,"middle"))
            a.append(f'<path d="M{x+275} {y+170} V{y+215}" stroke="{ORANGE}" stroke-width="4" marker-end="url(#arrow)"/>')
            a.append(t(x+275,y+370,"M3: cabeza Ø5.5 × 3 → asiento Ø7.2 × 4",15,700,ORANGE,"middle"))
            a.append(t(x+275,y+400,"Hombro de 3 mm: tope para apretar",15,400,INK,"middle"))
            a.append(t(x+275,y+430,"Poner tapón al final · cable por ranura USB",15,400,INK,"middle"))
        for j, line in enumerate(lines):
            a.append(t(x+24,y+ch-100+j*27,"• "+line,16,400,MUTED))
    save_svg_png("montaje-paso-a-paso", a)


def manual_page(number: str, title: str, detail: str, instructions: list[str], drawing: list[str]) -> None:
    w, h = 1600, 1000
    a = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<defs><marker id="blackArrow" markerWidth="13" markerHeight="13" refX="11" refY="6.5" orient="auto">'
        '<path d="M1 1 L12 6.5 L1 12" fill="none" stroke="#111" stroke-width="2"/></marker>'
        '<marker id="filledArrow" markerWidth="13" markerHeight="13" refX="11" refY="6.5" orient="auto">'
        '<path d="M1 1 L12 6.5 L1 12 Z" fill="#111"/></marker></defs>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#111}.thin{fill:none;stroke:#111;stroke-width:2}.part{fill:#f7f7f7;stroke:#111;stroke-width:3}.detail{fill:#fff;stroke:#111;stroke-width:2}.label{font-size:19px;font-weight:700}.body{font-size:22px}.small{font-size:17px}</style>',
        '<rect width="1600" height="1000" fill="#fff"/>',
        t(62, 104, number, 88, 700, "#111"),
        t(170, 78, title.upper(), 36, 700, "#111"),
        t(170, 116, detail, 19, 400, MUTED),
        '<path d="M50 145 H1550" stroke="#111" stroke-width="2"/>',
        '<rect x="48" y="815" width="1504" height="140" rx="4" fill="#f7f7f7" stroke="#111" stroke-width="2"/>',
    ]
    a.extend(drawing)
    for i, instruction in enumerate(instructions):
        yy = 856+i*35
        a.append(f'<circle cx="83" cy="{yy-8}" r="15" fill="#111"/>')
        a.append(t(83, yy-2, str(i+1), 15, 700, "#fff", "middle"))
        a.append(t(115, yy, instruction, 20, 400, "#111"))
    a.append("</svg>")
    svg = OUT / f"paso-{number}.svg"
    png = OUT / f"paso-{number}.png"
    svg.write_text("\n".join(a), encoding="utf-8")
    subprocess.run(["rsvg-convert", str(svg), "-o", str(png)], check=True)


def iso_point(x: float, y: float, z: float, ox: float = 620, oy: float = 700) -> tuple[float, float]:
    return (ox + 2.5*x - 1.1*y, oy + 0.14*x + 0.8*y - 2*z)


def world_polygon(points: list[tuple[float, float, float]], fill: str = "#f7f7f7",
                  stroke: str = "#111", width: int = 3, dash: str = "") -> str:
    coords = [iso_point(*p) for p in points]
    path = " ".join(("M" if i == 0 else "L")+f"{x:.1f},{y:.1f}" for i,(x,y) in enumerate(coords))+" Z"
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<path d="{path}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>'


def world_line(points: list[tuple[float, float, float]], stroke: str = "#111", width: int = 2,
               dash: str = "", marker: str = "") -> str:
    coords = [iso_point(*p) for p in points]
    path = " ".join(("M" if i == 0 else "L")+f"{x:.1f},{y:.1f}" for i,(x,y) in enumerate(coords))
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    marker_attr = f' marker-end="url(#{marker})"' if marker else ""
    return f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="{width}"{dash_attr}{marker_attr}/>'


def front_pt(x: float, v: float, y_offset: float = 0) -> tuple[float,float,float]:
    # Front panel local Y is tilted 72 degrees back from the horizontal.
    return (x, y_offset+v*0.309, 9+v*0.951)


def rear_pt(x: float, v: float, y_offset: float = 0) -> tuple[float,float,float]:
    return (x, 100+y_offset, 113.616-v)


def front_panel_lines(offset: float = 0, screen_modules: bool = False,
                      include_panel: bool = True) -> list[str]:
    q = [front_pt(0,0,offset),front_pt(190,0,offset),front_pt(190,110,offset),front_pt(0,110,offset)]
    items = [world_polygon(q, "#f7f7f7")] if include_panel else []
    # LCD and OLED apertures as seen through the tilted front.
    def opening(x1: float, v1: float, x2: float, v2: float, yoff: float = offset) -> str:
        return world_polygon([front_pt(x1,v1,yoff),front_pt(x2,v1,yoff),front_pt(x2,v2,yoff),front_pt(x1,v2,yoff)], "#fff", "#111", 2)
    if include_panel:
        items += [opening(28.78,30.02,103.22,79.98),opening(142,45,169,65)]
    if screen_modules:
        # Boards sit immediately behind the front plate; offset inward along the face.
        def behind(x: float, v: float) -> tuple[float,float,float]:
            p=front_pt(x,v,9)
            return (p[0],p[1]+5,p[2]-1.6)
        items.append(world_polygon([behind(16,26.83),behind(114,26.83),behind(114,83.17),behind(16,83.17)],"#e4e4e4","#111",2))
        items.append(world_polygon([behind(142,45),behind(169,45),behind(169,65),behind(142,65)],"#ddd","#111",2))
        for x in [20,110]:
            for v in [32,78]:
                px,py=iso_point(*behind(x,v))
                items.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#fff" stroke="#111" stroke-width="2"/>')
    return items


def base_and_sides(lift: float = 0) -> list[str]:
    items=[world_polygon([(0,0,3),(190,0,3),(190,100,3),(0,100,3)],"#ededed")]
    profile=[(0,3),(100,3),(100,113.616),(34.02,113.616),(0,9)]
    for x in [-14-lift,190+lift]:
        pts=[(x,y,z+lift) for y,z in profile]
        items.append(world_polygon(pts,"#f7f7f7"))
    return items


def rear_panel_lines(offset: float = 0, show_solar: bool = False) -> list[str]:
    items=[world_polygon([rear_pt(0,0,offset),rear_pt(190,0,offset),rear_pt(190,110,offset),rear_pt(0,110,offset)],"#f7f7f7")]
    # cable pass-through
    items.append(world_polygon([rear_pt(85,95,offset),rear_pt(105,95,offset),rear_pt(105,105,offset),rear_pt(85,105,offset)],"#fff","#111",2))
    if show_solar:
        for sx in [34,100]:
            items.append(world_polygon([rear_pt(sx,25,offset+3),rear_pt(sx+56,25,offset+3),rear_pt(sx+56,85,offset+3),rear_pt(sx,85,offset+3)],"#e4e4e4","#111",2))
        for sx in [29,90,161]:
            for sy in [38,72]:
                pts=[rear_pt(sx-5,sy-5,offset+6),rear_pt(sx+5,sy-5,offset+6),rear_pt(sx+5,sy+5,offset+6),rear_pt(sx-5,sy+5,offset+6)]
                items.append(world_polygon(pts,"#fff","#111",2))
    return items


def top_panel_lines(lift: float = 0, caps: bool = False) -> list[str]:
    z=113.616+lift
    items=[world_polygon([(0,35.02,z),(190,35.02,z),(190,100,z),(0,100,z)],"#f4f4f4")]
    # Inner tongue line on the underside.
    items.append(world_polygon([(14.5,37.02,z-0.2),(175.5,37.02,z-0.2),(175.5,98,z-0.2),(14.5,98,z-0.2)],"none","#555",1,"7 6"))
    for x in [7,183]:
        for y in [47.02,88]:
            px,py=iso_point(x,y,z+0.1)
            items.append(f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="8" ry="5" fill="{"#ddd" if caps else "#fff"}" stroke="#111" stroke-width="2"/>')
    return items


def draw_ikea_steps() -> None:
    # Step 1: seat the two side panels on the base; show the matching fastener detail.
    d=base_and_sides(22)
    d += [world_line([(0,12,10),(0,12,32)],marker="filledArrow"),
          world_line([(190,88,10),(190,88,32)],marker="filledArrow")]
    # Four base screws below the two side cheeks.
    for x,y in [(7,12),(7,88),(183,12),(183,88)]:
        p1=iso_point(x,y,-16); p2=iso_point(x,y,0)
        d.append(f'<path d="M{p1[0]:.1f} {p1[1]:.1f} L{p2[0]:.1f} {p2[1]:.1f}" stroke="#111" stroke-width="4" marker-end="url(#filledArrow)"/>')
    d += [t(1020,255,"E × 2",22,700),t(1020,295,"C · BASE",22,700),t(1020,335,"4 × M3 × 8",21,700)]
    # Magnified assembly bubble, screw, insert and hex key.
    d.append('<circle cx="1305" cy="545" r="165" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append(t(1305,415,"DETALLE · UNIÓN",18,700,"#111","middle"))
    d.append(rect(1180,510,250,65,"#eee","#111",3,2))
    d.append(rect(1180,610,250,70,"#f7f7f7","#111",3,2))
    d.append('<path d="M1305 465 V607" stroke="#111" stroke-width="5" marker-end="url(#filledArrow)"/>')
    d.append('<circle cx="1305" cy="478" r="15" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append('<path d="M1305 463 L1305 440 L1375 440 L1375 468" fill="none" stroke="#111" stroke-width="7"/>')
    d.append('<path d="M1375 440 A58 58 0 0 1 1418 478" fill="none" stroke="#111" stroke-width="4" marker-end="url(#blackArrow)"/>')
    manual_page("01","Une base y laterales","Vista explotada · utiliza los insertos térmicos M3 en los laterales",[
        "Alinea los dos laterales E sobre los bordes de la base C.",
        "Aprieta cuatro tornillos M3 × 8 desde abajo, dos por lateral.",
        "La cabeza apoya en la base; no fuerces el inserto térmico."],d)

    # Step 2: front and rear panels slide into side supports.
    d=base_and_sides(0)
    d += front_panel_lines(-24)
    d += rear_panel_lines(24)
    d += [world_line([(95,-32,62),(95,-3,62)],marker="filledArrow"),
          world_line([(95,132,62),(95,103,62)],marker="filledArrow")]
    d += [t(1040,285,"A · FRENTE",21,700),t(1040,330,"B · TRASERA",21,700)]
    d.append('<circle cx="1290" cy="555" r="150" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append(t(1290,432,"ALINEA LOS ORIFICIOS",17,700,"#111","middle"))
    d.append('<path d="M1210 510 L1260 555 M1370 510 L1320 555" fill="none" stroke="#111" stroke-width="3" marker-end="url(#filledArrow)"/>')
    d.append('<circle cx="1260" cy="555" r="12" fill="#fff" stroke="#111" stroke-width="3"/><circle cx="1320" cy="555" r="12" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append('<path d="M1260 555 H1320" stroke="#111" stroke-width="4"/>')
    manual_page("02","Fija frente y trasera","Las dos placas encajan entre los laterales y apoyan sobre la base",[
        "Pon A al frente y B en la parte posterior; deja la ranura USB abajo.",
        "Haz coincidir los orificios de las placas con los insertos laterales.",
        "Aprieta cuatro M3 × 8 en cada placa."],d)

    # Step 3: display modules attach from inside the front panel.
    d=front_panel_lines(-18,False)
    d += front_panel_lines(7,True,False)
    d += [t(1040,310,"LCD · 4 × M2.5",21,700),t(1040,350,"OLED · 4 fijaciones",20,700)]
    d.append('<circle cx="1285" cy="555" r="155" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append(t(1285,430,"VISTA DESDE DENTRO",17,700,"#111","middle"))
    d.append('<rect x="1200" y="480" width="170" height="115" rx="4" fill="#eee" stroke="#111" stroke-width="3"/>')
    d.append('<rect x="1235" y="500" width="105" height="70" fill="#fff" stroke="#111" stroke-width="2"/>')
    for x in [1222,1348]:
        for y in [492,583]:
            d.append(f'<circle cx="{x}" cy="{y}" r="7" fill="#fff" stroke="#111" stroke-width="2"/>')
    d.append('<path d="M1170 540 H1220 M1410 540 H1360" stroke="#111" stroke-width="4" marker-end="url(#filledArrow)"/>')
    manual_page("03","Monta las pantallas","Los módulos se fijan por la cara interior del panel frontal",[
        "Centra el LCD ILI9488 detrás de la ventana grande y usa sus cuatro soportes.",
        "Ajusta la OLED en las ranuras; el patrón depende de la placa comprada.",
        "Comprueba que las pantallas queden niveladas antes de cerrar."],d)

    # Step 4: attach two solar panels and six clips to the rear.
    d=rear_panel_lines(0,False)
    for sx in [34,100]:
        d.append(world_polygon([rear_pt(sx,25,8),rear_pt(sx+56,25,8),rear_pt(sx+56,85,8),rear_pt(sx,85,8)],"#e5e5e5","#111",3))
    for sx in [29,95,161]:
        for sy in [38,72]:
            d.append(world_polygon([rear_pt(sx-5,sy-5,14),rear_pt(sx+5,sy-5,14),rear_pt(sx+5,sy+5,14),rear_pt(sx-5,sy+5,14)],"#fff","#111",2))
    d += [t(1050,285,"K × 2",22,700),t(1050,325,"F × 6",22,700),t(1050,365,"6 × M2 + tuerca",20,700)]
    d.append('<circle cx="1300" cy="555" r="155" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append(t(1300,430,"DETALLE DEL CLIP",17,700,"#111","middle"))
    d.append('<rect x="1185" y="500" width="230" height="100" fill="#eee" stroke="#111" stroke-width="3"/>')
    d.append('<rect x="1245" y="480" width="115" height="75" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append('<path d="M1220 500 V475 H1255 M1350 555 H1385 V580" fill="none" stroke="#111" stroke-width="6"/>')
    d.append('<path d="M1300 455 V535" stroke="#111" stroke-width="4" marker-end="url(#filledArrow)"/>')
    d.append('<circle cx="1300" cy="570" r="12" fill="#fff" stroke="#111" stroke-width="3"/>')
    manual_page("04","Sujeta los paneles solares","La placa trasera recibe seis clips; no perfores los paneles",[
        "Coloca los dos paneles K de 56 × 60 mm sobre la cara posterior.",
        "Pon un clip F en cada uno de los seis puntos de fijación.",
        "Aprieta seis tornillos M2 con sus tuercas y deja libre el paso USB."],d)

    # Step 5: mount electronics to base and route USB cable through rear slot.
    d=base_and_sides(0)
    d += front_panel_lines(0,False)
    d += rear_panel_lines(0,False)
    d.append(world_polygon([(58,35,6),(132,35,6),(132,66,6),(58,66,6)],"#e5e5e5","#111",3))
    d.append(world_polygon([(76,42,8),(111,42,8),(111,61,8),(76,61,8)],"#fff","#111",2))
    # two cable ties and cable route through the bottom rear opening
    for xx in [66,124]:
        d.append(world_line([(xx,31,5),(xx,70,5)],"#111",3))
    d.append('<path d="M905 662 C1000 680 1018 738 1120 745 C1175 748 1200 720 1218 692" fill="none" stroke="#111" stroke-width="6" marker-end="url(#filledArrow)"/>')
    d += [t(1050,300,"ESP32-S3",22,700),t(1050,355,"2 correas",20,700),t(1050,410,"USB por ranura 20 × 10",18,700)]
    manual_page("05","Fija la placa y pasa el cable","Haz estas conexiones antes de instalar la tapa superior",[
        "Sujeta la placa ESP32 a las ranuras de la base con dos correas.",
        "Guía el cable de alimentación por la abertura inferior de la trasera.",
        "Verifica que el cable y los módulos no queden atrapados."],d)

    # Step 6: inset top, M3 head stop, cap, and Allen key rotation.
    d=base_and_sides(0)+front_panel_lines(0,False)+rear_panel_lines(0,False)
    d += top_panel_lines(26,False)
    d.append('<path d="M750 385 V455 M850 385 V455" stroke="#111" stroke-width="4" marker-end="url(#filledArrow)"/>')
    d += [t(1040,270,"D · TAPA",22,700),t(1040,315,"4 × M3 × 8",22,700),t(1040,360,"4 tapones al final",19,700)]
    d.append('<circle cx="1300" cy="550" r="170" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append(t(1300,405,"AMPLIACIÓN · CORTE",18,700,"#111","middle"))
    d.append(rect(1175,500,250,100,"#eee","#111",3))
    d.append('<rect x="1250" y="500" width="100" height="58" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append('<rect x="1286" y="558" width="28" height="42" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append('<rect x="1278" y="600" width="44" height="28" fill="#ddd" stroke="#111" stroke-width="2"/>')
    d.append(rect(1265,525,70,33,"#ccc","#111",2,5))
    d.append('<rect x="1267" y="480" width="66" height="20" fill="#fff" stroke="#111" stroke-width="3"/>')
    d.append(t(1300,475,"tapón",14,700,"#111","middle"))
    d.append(t(1300,682,"hombro de 3 mm",16,700,"#111","middle"))
    d.append('<path d="M1300 480 V550 M1300 462 L1300 442 L1372 442 L1372 465" fill="none" stroke="#111" stroke-width="6"/>')
    d.append('<path d="M1372 442 A60 60 0 0 1 1416 480" fill="none" stroke="#111" stroke-width="4" marker-end="url(#blackArrow)"/>')
    manual_page("06","Encaja y fija la tapa","La tapa entra entre los paneles y cubre los laterales",[
        "Asienta D dentro de los rebajes; la cara superior queda a ras.",
        "Aprieta cuatro M3 hasta que la cabeza apoye en el hombro de 3 mm.",
        "Presiona los cuatro tapones G después de apretar los tornillos."],d)


def main() -> None:
    dimensions_page()
    materials_page()
    assembly_page()
    draw_ikea_steps()
    print(f"Manual PNGs and BOM written to {OUT}")


if __name__ == "__main__":
    main()
