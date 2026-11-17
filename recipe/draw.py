"""Draw the wiring pictures for the recipe at the top of the guide: one per course. Schematic, not to scale: find a
pin on your board by the number printed next to it.

    python recipe/draw.py        # writes recipe/*.svg
"""
from pathlib import Path

HERE = Path(__file__).parent
RED, BLACK, SIGNAL, BLUE = "#d64541", "#2c2c30", "#e8a013", "#2f6fbf"
STYLE = ('<style>text{fill:#1b1b1f;font:14px system-ui,-apple-system,Segoe UI,sans-serif}.s{font-size:12px;fill:#5d5f66}'
         '.b{font-weight:700}.w{fill:#fff}.pin{font:600 13px ui-monospace,Menlo,monospace;fill:#fff}</style>')


def board(x, y, pins, h=None):
    """The ESP32 board with only the pins this course uses, down its left edge. Returns (svg, {pin: (x, y)})."""
    h = h or 40 + 34 * len(pins)
    out = [f'<rect x="{x}" y="{y}" width="150" height="{h}" rx="10" fill="#1d6b45"/>',
           f'<rect x="{x + 62}" y="{y + h / 2 - 26}" width="72" height="52" rx="6" fill="#c9c9cf"/>',
           f'<text x="{x + 98}" y="{y + h / 2 + 5}" text-anchor="middle" class="b" style="font-size:12px">ESP32-S3</text>']
    at = {}
    for i, p in enumerate(pins):
        py = y + 34 + 34 * i
        out.append(f'<circle cx="{x + 14}" cy="{py}" r="6" fill="#e8c547"/><text x="{x + 26}" y="{py + 5}" class="pin">{p}</text>')
        at[p] = (x + 14, py)
    return "".join(out), at


def wire(a, b, color, bend=70):
    (x0, y0), (x1, y1) = a, b
    return f'<path d="M{x0} {y0} C {x0 + bend} {y0}, {x1 - bend} {y1}, {x1} {y1}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round"/>'


def page(w, h, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">'
            f'<rect width="{w}" height="{h}" rx="14" fill="#f6f6f8"/>{STYLE}{body}</svg>\n')


def part(x, y, w, h, name, legs, fill, note=""):
    """A part with its legs down the right edge. Returns (svg, {leg: (x, y)})."""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}"/>',
           f'<text x="{x + 12}" y="{y - 10}" class="b">{name}</text>']
    if note:
        out.append(f'<text x="{x}" y="{y + h + 20}" class="s">{note}</text>')
    at = {}
    for i, leg in enumerate(legs):
        ly = y + (h / (len(legs) + 1)) * (i + 1)
        out.append(f'<circle cx="{x + w - 12}" cy="{ly}" r="5" fill="#e8c547"/><text x="{x + w - 24}" y="{ly + 5}" text-anchor="end" class="pin">{leg}</text>')
        at[leg] = (x + w - 12, ly)
    return "".join(out), at


def simple(name, title, legs, fill, note, sub):
    """One part, three wires to the board. legs: [(leg, board pin, colour)]."""
    p, pa = part(40, 70, 170, 110, title, [l for l, _, _ in legs], fill, note)
    b, ba = board(430, 44, [pin for _, pin, _ in legs])
    wires = "".join(wire(pa[l], ba[pin], col) for l, pin, col in legs)
    body = p + b + wires + f'<text x="320" y="216" text-anchor="middle" class="s">{sub}</text>'
    (HERE / name).write_text(page(640, 232, body, title))


simple("1-voice.svg", "passive buzzer", [("+", "3V3", RED), ("-", "GND", BLACK), ("S", "39", SIGNAL)], "#3a3f4a",
       "three legs, marked S", "red: power · dark: ground · yellow: the signal")
simple("2-arm.svg", "servo SG90", [("red", "5V", RED), ("brown", "GND", BLACK), ("orange", "17", SIGNAL)], "#2471a3",
       "one servo may run from USB", "the servo's own plug has three holes: push three wires into them")
simple("3-inside.svg", "potentiometer 10k", [("outer leg", "3V3", RED), ("outer leg ", "GND", BLACK), ("middle leg", "2", BLUE)], "#7d3c98",
       "turn it: 0 to 1", "the middle leg carries the number that goes into the model")

# the wheels: the board on top tells two drivers what to do, each driver turns its two motors, and the batteries
# feed the drivers through the breadboard's rail; every ground meets on that rail
def poly(points, color):
    return f'<path d="M' + " L".join(f"{x} {y}" for x, y in points) + f'" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>'


out = ['<rect x="260" y="30" width="200" height="92" rx="10" fill="#1d6b45"/><rect x="318" y="44" width="84" height="40" rx="6" fill="#c9c9cf"/>'
       '<text x="360" y="69" text-anchor="middle" class="b" style="font-size:12px">ESP32-S3</text>'
       '<text x="480" y="44" class="s">the board stays on USB</text><text x="480" y="124" class="s">and only sends signals</text>']
pins = {"4": 290, "5": 325, "6": 395, "7": 430}
for name, x in pins.items():
    out.append(f'<circle cx="{x}" cy="110" r="6" fill="#e8c547"/><text x="{x}" y="100" text-anchor="middle" class="pin">{name}</text>')
out.append('<circle cx="448" cy="60" r="6" fill="#e8c547"/><text x="438" y="64" text-anchor="end" class="pin" style="font-size:11px">GND</text>')
RAIL_P, RAIL_G = 458, 480
for side, x0, (pa, pb), outer in (("left", 110, ("4", "5"), (70, 48)), ("right", 440, ("6", "7"), (650, 672))):
    out.append(f'<rect x="{x0}" y="200" width="170" height="92" rx="10" fill="#a04000"/>'
               f'<text x="{x0 + 85}" y="262" text-anchor="middle" class="w b">L9110S, {side}</text>')
    for leg, lx, pin, col in (("A-IA", x0 + 55, pa, SIGNAL), ("A-IB", x0 + 115, pb, BLUE)):
        out.append(f'<path d="M{lx} 212 C {lx} 160, {pins[pin]} 170, {pins[pin]} 110" fill="none" stroke="{col}" stroke-width="4" stroke-linecap="round"/>'
                   f'<circle cx="{lx}" cy="212" r="5" fill="#e8c547"/><text x="{lx}" y="232" text-anchor="middle" class="pin" style="font-size:11px">{leg}</text>')
    edge = x0 + 12 if side == "left" else x0 + 158
    for leg, ly, rail, ox, col in (("VCC", 244, RAIL_P, outer[0], RED), ("GND", 272, RAIL_G, outer[1], BLACK)):
        out.append(poly([(edge, ly), (ox, ly), (ox, rail)], col) + f'<circle cx="{edge}" cy="{ly}" r="5" fill="#e8c547"/>'
                   f'<text x="{edge + (10 if side == "left" else -10)}" y="{ly + 4}" text-anchor="{"start" if side == "left" else "end"}" class="pin" style="font-size:11px">{leg}</text>')
    for k, mx in enumerate((x0 + 40, x0 + 130)):          # two motors, both on the same terminal
        out.append(f'<path d="M{x0 + 78} 292 C {x0 + 78} 318, {mx - 8} 316, {mx - 8} 342" fill="none" stroke="{RED}" stroke-width="3.5" stroke-linecap="round"/>'
                   f'<path d="M{x0 + 92} 292 C {x0 + 92} 322, {mx + 8} 318, {mx + 8} 342" fill="none" stroke="{BLACK}" stroke-width="3.5" stroke-linecap="round"/>'
                   f'<circle cx="{mx}" cy="364" r="24" fill="#e8c547" stroke="#8a7420" stroke-width="2"/><text x="{mx}" y="369" text-anchor="middle" class="s b">motor</text>')
    out.append(f'<text x="{x0 + 85}" y="412" text-anchor="middle" class="s">both {side} motors on MOTOR A</text>')
out.append(poly([(448, 60), (460, 60), (460, 90), (694, 90), (694, RAIL_G)], BLACK))
out.append(poly([(30, RAIL_P), (704, RAIL_P)], RED) + poly([(30, RAIL_G), (704, RAIL_G)], BLACK))
out.append(f'<text x="712" y="{RAIL_P + 5}" class="b">+</text><text x="712" y="{RAIL_G + 5}" class="s b">GND</text>')
out.append('<rect x="280" y="510" width="160" height="50" rx="10" fill="#3a3f4a"/><text x="360" y="541" text-anchor="middle" class="w b">2 × 18650</text>')
out.append(poly([(330, 510), (330, RAIL_P)], RED) + poly([(390, 510), (390, RAIL_G)], BLACK))
out.append('<text x="96" y="442" class="s">the breadboard rail: + from the batteries, and one ground for everything</text>')
(HERE / "5-wheels.svg").write_text(page(760, 580, "".join(out), "motors, two drivers, batteries and the board"))
print("drew", sorted(p.name for p in HERE.glob("*.svg")))
