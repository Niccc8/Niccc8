#!/usr/bin/env python3
"""Build every self-hosted visual used by the profile README.

    python3 scripts/build_assets.py --fonts <dir> --figures <dir>

Outputs (all into assets/):
  typing-dark.svg / typing-light.svg      animated typing banner (Fira Code, outlined)
  wave-top-*.svg / wave-bottom-*.svg      animated wave dividers
  card-silicon-*.svg                      RVBL-2 signoff card
  card-verification-*.svg                 verification ledger card
  fig-rvbl2.jpg, fig-devchip-board.svg     figures for the two featured projects

Edit the DATA section below when a number changes, then re-run. Every number in
DATA is taken from the linked project repository; keep it that way.

Requirements: pip install fonttools brotli uharfbuzz pillow
Fonts: `npm pack @fontsource/fira-code` and extract; pass the extracted
`files/` folder as --fonts.
"""
from __future__ import annotations

import argparse
import base64
import io
import shutil
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# ════════════════════════════════════════════════════════════════════════════
# DATA (edit here)
# ════════════════════════════════════════════════════════════════════════════

TYPING_LINES = [
    "Nicholas Choong",
    "RTL Design | Computer Architecture | RISC-V",
]

SILICON_CARD = {
    "title": "RVBL-2 Silicon Signoff",
    "rows": [
        ("chip",  "Die area (Sky130A)",    "0.404 mm²"),
        ("cells", "Std cells / flip-flops", "17,708 / 1,393"),
        ("clock", "Setup slack, worst",     "+2.25 ns"),
        ("check", "DRC · LVS",              "0 · match"),
        ("isa",   "ISA coverage",           "47 / 47"),
    ],
}

VERIFICATION_CARD = {
    "title": "Verification Ledger",
    "rows": [
        ("tb",    "RVBL-2 reference RTL",     "7,384"),
        ("tb",    "RVBL-2 exported netlist",  "15,281"),
        ("eq",    "Lockstep comparisons",     "410,400"),
        ("tb",    "×72 CPU regression",       "21,662"),
        ("check", "RV32I compliance",         "126 / 126"),
    ],
    "ring_value": "0",
    "ring_label": "failures",
}

# ════════════════════════════════════════════════════════════════════════════
# Palettes. Dark mirrors github-readme-stats "github_dark" with the original
# README's #0d1117 background; light mirrors its default theme.
# ════════════════════════════════════════════════════════════════════════════

CARD = {
    "dark":  dict(bg="#0d1117", border="#0d1117", title="#58a6ff", text="#c9d1d9",
                  icon="#1f6feb", muted="#8b949e", ring_bg="#1f6feb33"),
    "light": dict(bg="#fffefe", border="#e4e2e2", title="#2f80ed", text="#434d58",
                  icon="#4c71f2", muted="#6e7781", ring_bg="#2f80ed33"),
}
TYPING = {"dark": "#FFFFFF", "light": "#1a1a2e"}
WAVE = {
    # left -> right gradient, plus a faint crest line
    "dark":  dict(a="#161b22", b="#1c2a52", back="#2b3f78", crest="#58a6ff"),
    "light": dict(a="#0f0f0f", b="#1a1a2e", back="#3a3f6b", crest="#58a6ff"),
}

# ════════════════════════════════════════════════════════════════════════════
# Text shaping (HarfBuzz) -> SVG outlines
# ════════════════════════════════════════════════════════════════════════════


class Shaper:
    def __init__(self, woff: Path):
        self.tt = TTFont(woff)
        buf = io.BytesIO()
        self.tt.flavor = None
        self.tt.save(buf)
        self.font = hb.Font(hb.Face(hb.Blob(buf.getvalue())))
        self.upem = self.tt["head"].unitsPerEm
        self.glyphset = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()

    def shape(self, text: str, size: float, x: float, y: float):
        """Return (path_d, per-cluster cumulative x edges)."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.font, buf, {"kern": True, "liga": True, "calt": True})
        s = size / self.upem
        pen_x, parts, edges = x, [], [x]
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            sp = SVGPathPen(self.glyphset)
            tp = TransformPen(sp, (s, 0, 0, -s, pen_x + pos.x_offset * s, y - pos.y_offset * s))
            self.glyphset[self.order[info.codepoint]].draw(tp)
            if d := sp.getCommands():
                parts.append(d)
            pen_x += pos.x_advance * s
            edges.append(pen_x)
        return " ".join(parts), edges


# ════════════════════════════════════════════════════════════════════════════
# 1. Typing banner (replaces readme-typing-svg; SMIL works inside <img>)
# ════════════════════════════════════════════════════════════════════════════

def typing_svg(shaper: Shaper, mode: str, W=800, H=56, size=26,
               type_s=1.7, hold_s=1.9, erase_s=0.6, gap_s=0.25) -> str:
    """Typing banner. The cycle is rotated so that its first frame shows line 1
    fully typed: anything that only displays frame 0 still shows the name."""
    color = TYPING[mode]
    slot = type_s + hold_s + erase_s + gap_s
    T = slot * len(TYPING_LINES)
    shift = type_s  # t=0 lands at the start of line 1's hold
    baseline = H / 2 + size * 0.36
    label = " | ".join(TYPING_LINES).replace("->", "→")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'role="img" aria-label="{label}">', f'<title>{label}</title>']

    def rotate(events):
        """events: sorted [(t, value)] describing a step function on [0, T).
        Returns keyTimes/values for the same function shifted left by `shift`."""
        def at(t):
            v = events[0][1]
            for et, ev in events:
                if et <= t + 1e-9:
                    v = ev
            return v
        pts = sorted({0.0} | {round((et - shift) % T, 6) for et, _ in events})
        kts = ";".join(f"{t / T:.5f}" for t in pts)
        return kts, [at((t + shift) % T) for t in pts]

    for i, line in enumerate(TYPING_LINES):
        _, probe = shaper.shape(line, size, 0, 0)
        x0 = (W - probe[-1]) / 2
        d, edges = shaper.shape(line, size, x0, baseline)
        n = len(edges) - 1
        s0 = i * slot
        ev = [(0.0, 0.0)]
        ev += [(s0 + type_s * k / n, edges[k] - x0) for k in range(1, n + 1)]
        ev += [(s0 + type_s + hold_s + erase_s * (n - k) / n, edges[k] - x0) for k in range(n - 1, -1, -1)]
        ev.sort()
        kts, widths = rotate(ev)
        wv = ";".join(f"{v:.2f}" for v in widths)
        cv = ";".join(f"{x0 + v + 2:.2f}" for v in widths)
        vk, vis = rotate([(0.0, 0), (s0, 1), (s0 + type_s + hold_s + erase_s, 0)])
        vv = ";".join(str(v) for v in vis)
        out.append(f'<clipPath id="c{i}"><rect x="{x0:.2f}" y="0" height="{H}" width="{widths[0]:.2f}">'
                   f'<animate attributeName="width" calcMode="discrete" dur="{T:.2f}s" '
                   f'repeatCount="indefinite" keyTimes="{kts}" values="{wv}"/></rect></clipPath>')
        out.append(f'<path clip-path="url(#c{i})" fill="{color}" d="{d}"/>')
        out.append(f'<g opacity="{vis[0]}"><animate attributeName="opacity" calcMode="discrete" dur="{T:.2f}s" '
                   f'repeatCount="indefinite" keyTimes="{vk}" values="{vv}"/>'
                   f'<rect x="{x0 + widths[0] + 2:.2f}" y="{baseline - size * 0.78:.2f}" width="2.5" '
                   f'height="{size * 0.98:.2f}" fill="{color}">'
                   f'<animate attributeName="x" calcMode="discrete" dur="{T:.2f}s" repeatCount="indefinite" '
                   f'keyTimes="{kts}" values="{cv}"/>'
                   f'<animate attributeName="opacity" values="1;0" keyTimes="0;0.5" calcMode="discrete" '
                   f'dur="0.9s" repeatCount="indefinite"/></rect></g>')
    out.append("</svg>")
    return "\n".join(out)


# ════════════════════════════════════════════════════════════════════════════
# 2. Wave dividers (replaces capsule-render "waving")
# ════════════════════════════════════════════════════════════════════════════

def _wave_path(W, base, amp, periods, phase=0.0, top=True, H=80):
    """Smooth periodic wave over 2W (for seamless horizontal scrolling)."""
    import math
    pts = []
    steps = 240
    for k in range(steps + 1):
        x = 2 * W * k / steps
        y = base + amp * math.sin(2 * math.pi * periods * x / W + phase)
        pts.append((x, y))
    d = f"M0 {0 if top else H} L" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    d += f" L{2 * W} {0 if top else H} Z"
    return d, pts


def wave_svg(mode: str, top: bool, W=1200, H=80) -> str:
    c = WAVE[mode]
    flip = "" if top else f' transform="translate(0 {H}) scale(1 -1)"'
    back, _ = _wave_path(W, 50, 9, 1.0, 1.3)
    front, crest = _wave_path(W, 44, 12, 1.0, 0.0)
    crest_d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in crest)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" preserveAspectRatio="none" role="img" aria-label="wave divider">
<defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="{c['a']}"/><stop offset="1" stop-color="{c['b']}"/></linearGradient>
<style>.s{{animation:m 14s linear infinite}}.b{{animation-duration:22s;animation-direction:reverse}}@keyframes m{{from{{transform:translateX(0)}}to{{transform:translateX(-{W}px)}}}}@media (prefers-reduced-motion:reduce){{.s{{animation:none}}}}</style></defs>
<g{flip}>
<g class="s b"><path d="{back}" fill="{c['back']}" opacity="0.9"/></g>
<g class="s"><path d="{front}" fill="url(#g)"/><path d="{crest_d}" fill="none" stroke="{c['crest']}" stroke-opacity="0.55" stroke-width="1.2"/></g>
</g></svg>'''


# ════════════════════════════════════════════════════════════════════════════
# 3. Stat cards in github-readme-stats geometry (495 × 195)
# ════════════════════════════════════════════════════════════════════════════

ICONS = {  # 16×16 viewBox, stroke-based
    "chip":  '<rect x="4" y="4" width="8" height="8" rx="1"/><path d="M6 1v3M10 1v3M6 12v3M10 12v3M1 6h3M1 10h3M12 6h3M12 10h3"/>',
    "cells": '<rect x="1.5" y="1.5" width="5" height="5"/><rect x="9.5" y="1.5" width="5" height="5"/><rect x="1.5" y="9.5" width="5" height="5"/><rect x="9.5" y="9.5" width="5" height="5"/>',
    "clock": '<circle cx="8" cy="8" r="6.5"/><path d="M8 4v4l2.5 2.5"/>',
    "check": '<circle cx="8" cy="8" r="6.5"/><path d="M5 8.2l2 2 4-4.4"/>',
    "isa":   '<path d="M5 3L1.5 8 5 13M11 3l3.5 5-3.5 5M9.5 2l-3 12"/>',
    "tb":    '<path d="M2 3h12M2 8h12M2 13h7"/><path d="M11 11.5l1.5 1.5 2.5-3"/>',
    "eq":    '<path d="M3 5.5h10M3 10.5h10"/><path d="M1.5 2.5v11M14.5 2.5v11" stroke-dasharray="1.5 1.5"/>',
}

FONT_STACK = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"


def _card_shell(mode, title, body, W=495, H=195):
    c = CARD[mode]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none" role="img" aria-labelledby="t">
<title id="t">{title}</title>
<style>
.header{{font:600 18px {FONT_STACK};fill:{c['title']}}}
.stat{{font:600 14px {FONT_STACK};fill:{c['text']}}}
.bold{{font-weight:700}}
.icon{{stroke:{c['icon']};fill:none;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}}
.ringlabel{{font:400 12px {FONT_STACK};fill:{c['muted']}}}
.ringvalue{{font:800 26px {FONT_STACK};fill:{c['text']}}}
.ring-bg{{stroke:{c['ring_bg']};fill:none;stroke-width:6}}
.ring{{stroke:{c['title']};fill:none;stroke-width:6}}
</style>
<rect x="0.5" y="0.5" rx="10" width="{W-1}" height="{H-1}" fill="{c['bg']}" stroke="{c['border']}"/>
<g transform="translate(25 35)"><text class="header" x="0" y="0">{title}</text></g>
{body}
</svg>'''


def _rows(rows):
    out = []
    for i, (icon, label, value) in enumerate(rows):
        y = 55 + i * 25
        out.append(f'<g transform="translate(25 {y})">'
                   f'<svg class="icon" x="0" y="-13" viewBox="0 0 16 16" width="16" height="16">{ICONS[icon]}</svg>'
                   f'<text class="stat" x="25" y="0">{label}:</text>'
                   f'<text class="stat bold" x="215" y="0">{value}</text></g>')
    return "\n".join(out)


def silicon_card(mode: str, die_b64: str) -> str:
    body = _rows(SILICON_CARD["rows"])
    # die thumbnail inside the "rank" ring position
    body += f'''
<g transform="translate(400 100)">
<clipPath id="die"><circle cx="0" cy="0" r="37"/></clipPath>
<circle class="ring-bg" cx="0" cy="0" r="40"/>
<circle class="ring" cx="0" cy="0" r="40"/>
<image x="-37" y="-37" width="74" height="74" clip-path="url(#die)" preserveAspectRatio="xMidYMid slice"
 href="data:image/jpeg;base64,{die_b64}" xlink:href="data:image/jpeg;base64,{die_b64}"/>
<text class="ringlabel" x="0" y="62" text-anchor="middle">Sky130 die</text>
</g>'''
    return _card_shell(mode, SILICON_CARD["title"], body)


def verification_card(mode: str) -> str:
    body = _rows(VERIFICATION_CARD["rows"])
    body += f'''
<g transform="translate(400 100)">
<circle class="ring-bg" cx="0" cy="0" r="40"/>
<circle class="ring" cx="0" cy="0" r="40"/>
<text class="ringvalue" x="0" y="9" text-anchor="middle">{VERIFICATION_CARD['ring_value']}</text>
<text class="ringlabel" x="0" y="62" text-anchor="middle">{VERIFICATION_CARD['ring_label']}</text>
</g>'''
    return _card_shell(mode, VERIFICATION_CARD["title"], body)


# ════════════════════════════════════════════════════════════════════════════
# 4. Figures
# ════════════════════════════════════════════════════════════════════════════

def die_b64(gds_png: Path, px: int) -> str:
    im = Image.open(gds_png).convert("RGB")
    w, h = im.size
    im = im.crop((10, 22, w - 10, h - 30))
    side = min(im.size)
    im = im.crop(((im.width - side) // 2, (im.height - side) // 2,
                  (im.width + side) // 2, (im.height + side) // 2)).resize((px, px), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=78, optimize=True)
    return base64.b64encode(b.getvalue()).decode()


def rvbl2_figure(gds_png: Path, wave_png: Path, out: Path, H=520, gap=16):
    """Die render and firmware waveform side by side, same height."""
    die = Image.open(io.BytesIO(base64.b64decode(die_b64(gds_png, H))))
    wave = Image.open(wave_png).convert("RGB")
    wave = wave.resize((int(wave.width * H / wave.height), H), Image.LANCZOS)
    canvas = Image.new("RGB", (die.width + gap + wave.width, H), "white")
    canvas.paste(die, (0, 0))
    canvas.paste(wave, (die.width + gap, 0))
    canvas.save(out, "JPEG", quality=82, optimize=True, progressive=True)


def resized(src: Path, out: Path, width: int):
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    if out.suffix == ".png":
        im.save(out, "PNG", optimize=True)
    else:
        im.save(out, "JPEG", quality=82, optimize=True, progressive=True)


# ════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", type=Path, required=True, help="@fontsource/fira-code files/ dir")
    ap.add_argument("--figures", type=Path, required=True,
                    help="folder holding clones of the project repos")
    a = ap.parse_args()
    ASSETS.mkdir(exist_ok=True)

    fira = Shaper(a.fonts / "fira-code-latin-700-normal.woff")
    R = a.figures
    gds = R / "rvbl2-riscv-cpu-core/report/figures/gds_layout.png"
    thumb = die_b64(gds, 160)

    for mode in ("dark", "light"):
        (ASSETS / f"typing-{mode}.svg").write_text(typing_svg(fira, mode))
        (ASSETS / f"wave-top-{mode}.svg").write_text(wave_svg(mode, True))
        (ASSETS / f"wave-bottom-{mode}.svg").write_text(wave_svg(mode, False))
        (ASSETS / f"card-silicon-{mode}.svg").write_text(silicon_card(mode, thumb))
        (ASSETS / f"card-verification-{mode}.svg").write_text(verification_card(mode))

    rvbl2_figure(gds, R / "rvbl2-riscv-cpu-core/report/figures/wave_firmware.png",
                 ASSETS / "fig-rvbl2.jpg")
    shutil.copy(R / "devchip-fpga-board-toolkit/docs/img/hardware.svg", ASSETS / "fig-devchip-board.svg")

    for p in sorted(ASSETS.iterdir()):
        print(f"{p.stat().st_size / 1024:7.1f} KB  {p.name}")


if __name__ == "__main__":
    main()
