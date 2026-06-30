import io
from typing import List

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import card_style as cs

CORNER_RADIUS = 22
MARGIN = 30
PADDING = 24

BANNER_HEIGHT = 90
SECTION_GAP = 22
HEADER_ROW_HEIGHT = 30
ROW_HEIGHT = 34

COLOR_BG = (255, 255, 255)
COLOR_BANNER_BG = (18, 22, 54)
COLOR_BANNER_TEXT = (255, 255, 255)
COLOR_HEADER_BG = (37, 56, 102)
COLOR_HEADER_TEXT = (255, 255, 255)
COLOR_ROW_EVEN = (255, 255, 255)
COLOR_ROW_ODD = (245, 246, 250)
COLOR_TEXT = (30, 30, 35)
COLOR_POSITIVE = (30, 140, 70)
COLOR_NEGATIVE = (180, 40, 40)
COLOR_DIVIDER = (228, 228, 233)
COLOR_SWATCH_BORDER = (255, 255, 255)

GOLD = (212, 175, 55)
SILVER = (158, 164, 174)
BRONZE = (173, 110, 65)
BADGE_TEXT = (255, 255, 255)
DEFAULT_RANK_COLOR = (90, 110, 160)

TEAM_COLORS = {
    "Parrots": (255, 0, 0),
    "Traders": (255, 192, 0),
    "Bees": (255, 255, 0),
    "Sniffers": (244, 176, 132),
    "Masons": (112, 48, 160),
    "Shepherds": (0, 176, 240),
    "Riptide": (180, 198, 231),
    "Slimes": (169, 208, 142),
    "Wardens": (0, 112, 192),
    "Vexes": (174, 170, 170),
    "Raiders": (89, 89, 89),
    "Devilbats": (192, 0, 0),
}
DEFAULT_TEAM_COLOR = (130, 130, 138)
_TEAM_COLORS_LOWER = {name.lower(): rgb for name, rgb in TEAM_COLORS.items()}


def _team_color(team_name: str):
    return _TEAM_COLORS_LOWER.get((team_name or "").strip().lower(), DEFAULT_TEAM_COLOR)


FONT_CANDIDATES_REGULAR = [
    "arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
FONT_CANDIDATES_BOLD = [
    "arialbd.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in (FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR):
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _tier_color(rank: int):
    if rank == 1:
        return GOLD
    if rank == 2:
        return SILVER
    if rank == 3:
        return BRONZE
    return DEFAULT_RANK_COLOR


def _fmt1(value: float) -> str:
    return f"{value:.1f}"


def _fmt0(value: float) -> str:
    return str(int(round(value)))


def _add_shadow_and_round(content: Image.Image, radius: int, margin: int) -> Image.Image:
    w, h = content.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    rounded = Image.new("RGBA", (w, h))
    rounded.paste(content, (0, 0), mask)

    canvas = Image.new("RGBA", (w + margin * 2, h + margin * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [margin + 4, margin + 8, margin + w + 4, margin + h + 8], radius=radius, fill=(0, 0, 0, 90)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))

    canvas = Image.alpha_composite(canvas, shadow)
    canvas.paste(rounded, (margin, margin), rounded)
    return canvas


STANDINGS_COLUMNS = [
    ("RK", 32, "c"),
    ("TEAM", 150, "l"),
    ("W-L", 50, "c"),
    ("PF", 55, "r"),
    ("PA", 55, "r"),
    ("DIFF", 55, "r"),
    ("PPG", 55, "r"),
    ("PA/G", 55, "r"),
    ("YD/G", 60, "r"),
    ("YDA/G", 65, "r"),
]

POWER_COLUMNS = [
    ("RK", 32, "c"),
    ("TEAM", 150, "l"),
    ("W-L", 50, "c"),
    ("DIFF", 55, "r"),
    ("POWER", 80, "r"),
]


def _table_width(columns) -> int:
    return sum(w for _, w, _ in columns)


def _draw_table_header(draw, x0, y0, columns, header_font):
    draw.rectangle([x0, y0, x0 + _table_width(columns), y0 + HEADER_ROW_HEIGHT], fill=COLOR_HEADER_BG)
    x = x0
    for title, width, align in columns:
        if align == "l":
            draw.text((x + 10, y0 + HEADER_ROW_HEIGHT / 2), title, font=header_font, fill=COLOR_HEADER_TEXT, anchor="lm")
        elif align == "r":
            draw.text((x + width - 10, y0 + HEADER_ROW_HEIGHT / 2), title, font=header_font, fill=COLOR_HEADER_TEXT, anchor="rm")
        else:
            draw.text((x + width / 2, y0 + HEADER_ROW_HEIGHT / 2), title, font=header_font, fill=COLOR_HEADER_TEXT, anchor="mm")
        x += width


def render_league_card(standings: List[dict], power_rankings: List[dict]) -> io.BytesIO:
    table_width = max(_table_width(STANDINGS_COLUMNS), _table_width(POWER_COLUMNS))
    card_width = table_width + PADDING * 2

    n_standings = max(len(standings), 1)
    n_power = max(len(power_rankings), 1)

    standings_height = HEADER_ROW_HEIGHT + n_standings * ROW_HEIGHT
    power_height = HEADER_ROW_HEIGHT + n_power * ROW_HEIGHT

    height = (
        BANNER_HEIGHT + PADDING + standings_height
        + SECTION_GAP + BANNER_HEIGHT - 10 + power_height
        + PADDING
    )

    content = Image.new("RGB", (card_width, height), COLOR_BG)
    draw = ImageDraw.Draw(content)

    title_font = _load_font(20, bold=True)
    section_font = _load_font(15, bold=True)
    header_font = _load_font(11, bold=True)
    name_font = _load_font(13, bold=True)
    cell_font = _load_font(13, bold=False)
    badge_font = _load_font(13, bold=True)

    cs.draw_header(content, draw, card_width, BANNER_HEIGHT, "LEAGUE STANDINGS", "Season Overview", title_font_size=22)

    y = BANNER_HEIGHT + PADDING
    x0 = PADDING

    draw.text((x0, y - 6), "STANDINGS", font=section_font, fill=COLOR_TEXT, anchor="lm")
    y += 16
    _draw_table_header(draw, x0, y, STANDINGS_COLUMNS, header_font)
    y += HEADER_ROW_HEIGHT

    if not standings:
        draw.rectangle([x0, y, x0 + table_width, y + ROW_HEIGHT], fill=COLOR_ROW_EVEN)
        draw.text((x0 + table_width / 2, y + ROW_HEIGHT / 2), "No games logged yet", font=cell_font, fill=(150, 150, 155), anchor="mm")
        y += ROW_HEIGHT
    else:
        for i, s in enumerate(standings):
            row_bg = COLOR_ROW_EVEN if i % 2 == 0 else COLOR_ROW_ODD
            draw.rectangle([x0, y, x0 + table_width, y + ROW_HEIGHT], fill=row_bg)
            cy = y + ROW_HEIGHT / 2
            cx = x0

            col_w = STANDINGS_COLUMNS[0][1]
            draw.text((cx + col_w / 2, cy), str(i + 1), font=cell_font, fill=COLOR_TEXT, anchor="mm")
            cx += col_w

            col_w = STANDINGS_COLUMNS[1][1]
            icon_size = 20
            cs.draw_team_icon(content, draw, s["team"], cx + 6, cy - icon_size / 2, icon_size)
            draw.text((cx + 6 + icon_size + 8, cy), s["team"], font=name_font, fill=COLOR_TEXT, anchor="lm")
            cx += col_w

            wl = f"{s['w']}-{s['l']}" + (f"-{s['t']}" if s["t"] else "")
            col_w = STANDINGS_COLUMNS[2][1]
            draw.text((cx + col_w / 2, cy), wl, font=cell_font, fill=COLOR_TEXT, anchor="mm")
            cx += col_w

            col_w = STANDINGS_COLUMNS[3][1]
            draw.text((cx + col_w - 10, cy), _fmt0(s["pf"]), font=cell_font, fill=COLOR_TEXT, anchor="rm")
            cx += col_w

            col_w = STANDINGS_COLUMNS[4][1]
            draw.text((cx + col_w - 10, cy), _fmt0(s["pa"]), font=cell_font, fill=COLOR_TEXT, anchor="rm")
            cx += col_w

            col_w = STANDINGS_COLUMNS[5][1]
            diff_color = COLOR_POSITIVE if s["diff"] > 0 else (COLOR_NEGATIVE if s["diff"] < 0 else COLOR_TEXT)
            diff_text = f"+{_fmt0(s['diff'])}" if s["diff"] > 0 else _fmt0(s["diff"])
            draw.text((cx + col_w - 10, cy), diff_text, font=cell_font, fill=diff_color, anchor="rm")
            cx += col_w

            col_w = STANDINGS_COLUMNS[6][1]
            draw.text((cx + col_w - 10, cy), _fmt1(s["ppg"]), font=cell_font, fill=COLOR_TEXT, anchor="rm")
            cx += col_w

            col_w = STANDINGS_COLUMNS[7][1]
            draw.text((cx + col_w - 10, cy), _fmt1(s["papg"]), font=cell_font, fill=COLOR_TEXT, anchor="rm")
            cx += col_w

            col_w = STANDINGS_COLUMNS[8][1]
            draw.text((cx + col_w - 10, cy), _fmt0(s["yards_for_pg"]), font=cell_font, fill=COLOR_TEXT, anchor="rm")
            cx += col_w

            col_w = STANDINGS_COLUMNS[9][1]
            draw.text((cx + col_w - 10, cy), _fmt0(s["yards_against_pg"]), font=cell_font, fill=COLOR_TEXT, anchor="rm")

            y += ROW_HEIGHT

    draw.rectangle([x0, BANNER_HEIGHT + PADDING + 16, x0 + table_width, y], outline=COLOR_DIVIDER, width=1)

    y += SECTION_GAP
    draw.text((x0, y - 6), "POWER RANKINGS", font=section_font, fill=COLOR_TEXT, anchor="lm")
    y += 16
    table_top = y
    _draw_table_header(draw, x0, y, POWER_COLUMNS, header_font)
    y += HEADER_ROW_HEIGHT

    if not power_rankings:
        draw.rectangle([x0, y, x0 + table_width, y + ROW_HEIGHT], fill=COLOR_ROW_EVEN)
        draw.text((x0 + table_width / 2, y + ROW_HEIGHT / 2), "No games logged yet", font=cell_font, fill=(150, 150, 155), anchor="mm")
        y += ROW_HEIGHT
    else:
        for i, s in enumerate(power_rankings):
            row_bg = COLOR_ROW_EVEN if i % 2 == 0 else COLOR_ROW_ODD
            draw.rectangle([x0, y, x0 + table_width, y + ROW_HEIGHT], fill=row_bg)
            cy = y + ROW_HEIGHT / 2
            cx = x0

            col_w = POWER_COLUMNS[0][1]
            badge_color = _tier_color(i + 1)
            bx1, by1 = cx + (col_w - 22) / 2, cy - 11
            draw.rounded_rectangle([bx1, by1, bx1 + 22, by1 + 22], radius=6, fill=badge_color)
            draw.text((bx1 + 11, cy), str(i + 1), font=badge_font, fill=cs.badge_text_color(badge_color), anchor="mm")
            cx += col_w

            col_w = POWER_COLUMNS[1][1]
            icon_size = 20
            cs.draw_team_icon(content, draw, s["team"], cx + 6, cy - icon_size / 2, icon_size)
            draw.text((cx + 6 + icon_size + 8, cy), s["team"], font=name_font, fill=COLOR_TEXT, anchor="lm")
            cx += col_w

            wl = f"{s['w']}-{s['l']}" + (f"-{s['t']}" if s["t"] else "")
            col_w = POWER_COLUMNS[2][1]
            draw.text((cx + col_w / 2, cy), wl, font=cell_font, fill=COLOR_TEXT, anchor="mm")
            cx += col_w

            col_w = POWER_COLUMNS[3][1]
            diff_color = COLOR_POSITIVE if s["diff"] > 0 else (COLOR_NEGATIVE if s["diff"] < 0 else COLOR_TEXT)
            diff_text = f"+{_fmt0(s['diff'])}" if s["diff"] > 0 else _fmt0(s["diff"])
            draw.text((cx + col_w - 10, cy), diff_text, font=cell_font, fill=diff_color, anchor="rm")
            cx += col_w

            col_w = POWER_COLUMNS[4][1]
            draw.text((cx + col_w - 10, cy), _fmt1(s["power"]), font=_load_font(15, bold=True), fill=COLOR_TEXT, anchor="rm")

            y += ROW_HEIGHT

    draw.rectangle([x0, table_top, x0 + table_width, y], outline=COLOR_DIVIDER, width=1)

    final = _add_shadow_and_round(content, CORNER_RADIUS, MARGIN)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf
