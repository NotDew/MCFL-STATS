import io
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD_WIDTH = 560
CORNER_RADIUS = 22
MARGIN = 30

TOP_N = 10
BANNER_HEIGHT = 56
ROW_HEIGHT = 46
PADDING = 24
TOP_MARGIN = 10
BOTTOM_MARGIN = 10

COLOR_BG = (255, 255, 255)
COLOR_BANNER_BG = (18, 22, 54)
COLOR_BANNER_TEXT = (255, 255, 255)
COLOR_ROW_EVEN = (255, 255, 255)
COLOR_ROW_ODD = (245, 246, 250)
COLOR_TEXT = (30, 30, 35)
COLOR_TEAM_TEXT = (110, 113, 122)
COLOR_VALUE_TEXT = (15, 15, 20)
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


AVERAGE_STAT_LABELS = {"QBR"}


def _display_label(label: str) -> str:
    return f"{label} (AVG)" if label in AVERAGE_STAT_LABELS else label


def _format_total(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


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


def render_stat_leaderboard_card(stat_label: str, ranked: List[Tuple[str, str, float]]) -> io.BytesIO:
    num_rows = max(len(ranked), 1)
    height = BANNER_HEIGHT + TOP_MARGIN + num_rows * ROW_HEIGHT + BOTTOM_MARGIN

    content = Image.new("RGB", (CARD_WIDTH, height), COLOR_BG)
    draw = ImageDraw.Draw(content)


    draw.rectangle([0, 0, CARD_WIDTH, BANNER_HEIGHT], fill=COLOR_BANNER_BG)
    banner_font = _load_font(22, bold=True)
    draw.text((CARD_WIDTH / 2, BANNER_HEIGHT / 2), _display_label(stat_label).upper(),
               font=banner_font, fill=COLOR_BANNER_TEXT, anchor="mm")

    name_font = _load_font(17, bold=True)
    team_font = _load_font(12, bold=False)
    value_font = _load_font(18, bold=True)
    badge_font = _load_font(14, bold=True)

    y = BANNER_HEIGHT + TOP_MARGIN

    if not ranked:
        draw.rectangle([0, y, CARD_WIDTH, y + ROW_HEIGHT], fill=COLOR_ROW_EVEN)
        draw.text((CARD_WIDTH / 2, y + ROW_HEIGHT / 2), "No stats recorded yet",
                   font=_load_font(14), fill=(150, 150, 155), anchor="mm")

    for i, (player, team, total) in enumerate(ranked):
        row_bg = COLOR_ROW_EVEN if i % 2 == 0 else COLOR_ROW_ODD
        draw.rectangle([0, y, CARD_WIDTH, y + ROW_HEIGHT], fill=row_bg)


        badge_color = _tier_color(i + 1)
        bx1, by1 = PADDING, y + (ROW_HEIGHT - 30) / 2
        bx2, by2 = bx1 + 30, by1 + 30
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=8, fill=badge_color)
        draw.text(((bx1 + bx2) / 2, (by1 + by2) / 2), str(i + 1), font=badge_font, fill=BADGE_TEXT, anchor="mm")


        sx1 = bx2 + 12
        sw = 16
        sy1 = y + (ROW_HEIGHT - sw) / 2
        if team:
            draw.rounded_rectangle([sx1, sy1, sx1 + sw, sy1 + sw], radius=4,
                                    fill=_team_color(team), outline=COLOR_SWATCH_BORDER, width=1)
            name_x = sx1 + sw + 10
        else:
            name_x = sx1


        if team:
            draw.text((name_x, y + ROW_HEIGHT / 2 - 10), player, font=name_font, fill=COLOR_TEXT, anchor="lm")
            draw.text((name_x, y + ROW_HEIGHT / 2 + 11), team, font=team_font, fill=COLOR_TEAM_TEXT, anchor="lm")
        else:
            draw.text((name_x, y + ROW_HEIGHT / 2), player, font=name_font, fill=COLOR_TEXT, anchor="lm")


        draw.text((CARD_WIDTH - PADDING, y + ROW_HEIGHT / 2), _format_total(total),
                   font=value_font, fill=COLOR_VALUE_TEXT, anchor="rm")

        y += ROW_HEIGHT

    draw.line([(0, y), (CARD_WIDTH, y)], fill=COLOR_DIVIDER, width=1)

    final = _add_shadow_and_round(content, CORNER_RADIUS, MARGIN)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf
