import io
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD_WIDTH = 800
CORNER_RADIUS = 22
MARGIN = 30

TOP_N = 5
BLOCKS_PER_ROW = 3
BLOCK_WIDTH = 248
BLOCK_GAP = 14
BANNER_HEIGHT = 52
BLOCK_TITLE_HEIGHT = 30
ROW_HEIGHT = 36
PADDING = 24
TOP_MARGIN = 16
BOTTOM_MARGIN = 16

COLOR_BG = (255, 255, 255)
COLOR_BANNER_BG = (18, 22, 54)
COLOR_BANNER_TEXT = (255, 255, 255)
COLOR_BLOCK_TITLE_BG = (37, 56, 102)
COLOR_BLOCK_TITLE_TEXT = (255, 255, 255)
COLOR_ROW_EVEN = (255, 255, 255)
COLOR_ROW_ODD = (245, 246, 250)
COLOR_TEXT = (30, 30, 35)
COLOR_TEAM_TEXT = (130, 133, 140)
COLOR_VALUE_TEXT = (15, 15, 20)
COLOR_BORDER = (228, 228, 233)
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


def render_global_leaderboard_card(player_leaderboard: Dict[str, List[Tuple[str, str, float]]]) -> io.BytesIO:
    labels = list(player_leaderboard.keys())
    num_blocks = len(labels)
    num_rows = (num_blocks + BLOCKS_PER_ROW - 1) // BLOCKS_PER_ROW if num_blocks else 1
    block_height = BLOCK_TITLE_HEIGHT + TOP_N * ROW_HEIGHT

    grid_width = BLOCKS_PER_ROW * BLOCK_WIDTH + (BLOCKS_PER_ROW - 1) * BLOCK_GAP
    card_width = grid_width + PADDING * 2
    grid_height = num_rows * block_height + (num_rows - 1) * BLOCK_GAP if num_blocks else block_height
    height = BANNER_HEIGHT + TOP_MARGIN + grid_height + BOTTOM_MARGIN

    content = Image.new("RGB", (card_width, height), COLOR_BG)
    draw = ImageDraw.Draw(content)

    draw.rectangle([0, 0, card_width, BANNER_HEIGHT], fill=COLOR_BANNER_BG)
    banner_font = _load_font(20, bold=True)
    draw.text((card_width / 2, BANNER_HEIGHT / 2), "GLOBAL LEADERBOARD",
               font=banner_font, fill=COLOR_BANNER_TEXT, anchor="mm")

    title_font = _load_font(13, bold=True)
    name_font = _load_font(13, bold=True)
    value_font = _load_font(13, bold=False)
    badge_font = _load_font(11, bold=True)

    if not labels:
        empty_font = _load_font(14)
        draw.text((card_width / 2, BANNER_HEIGHT + TOP_MARGIN + block_height / 2),
                   "No stats recorded yet", font=empty_font, fill=(150, 150, 155), anchor="mm")

    for k, label in enumerate(labels):
        row_group, col_group = divmod(k, BLOCKS_PER_ROW)
        x0 = PADDING + col_group * (BLOCK_WIDTH + BLOCK_GAP)
        y0 = BANNER_HEIGHT + TOP_MARGIN + row_group * (block_height + BLOCK_GAP)

        draw.rectangle([x0, y0, x0 + BLOCK_WIDTH, y0 + BLOCK_TITLE_HEIGHT], fill=COLOR_BLOCK_TITLE_BG)
        draw.text((x0 + BLOCK_WIDTH / 2, y0 + BLOCK_TITLE_HEIGHT / 2), _display_label(label),
                   font=title_font, fill=COLOR_BLOCK_TITLE_TEXT, anchor="mm")

        ranked = player_leaderboard[label]
        for i in range(TOP_N):
            ry = y0 + BLOCK_TITLE_HEIGHT + i * ROW_HEIGHT
            row_bg = COLOR_ROW_EVEN if i % 2 == 0 else COLOR_ROW_ODD
            draw.rectangle([x0, ry, x0 + BLOCK_WIDTH, ry + ROW_HEIGHT], fill=row_bg)

            if i >= len(ranked):
                continue
            player, team, total = ranked[i]
            text_y = ry + ROW_HEIGHT / 2

            badge_color = _tier_color(i + 1)
            bx1, by1 = x0 + 6, ry + (ROW_HEIGHT - 20) / 2
            bx2, by2 = bx1 + 20, by1 + 20
            draw.rounded_rectangle([bx1, by1, bx2, by2], radius=5, fill=badge_color)
            draw.text(((bx1 + bx2) / 2, (by1 + by2) / 2), str(i + 1), font=badge_font, fill=BADGE_TEXT, anchor="mm")

            sx1 = bx2 + 7
            sw = 12
            sy1 = ry + (ROW_HEIGHT - sw) / 2
            if team:
                draw.rounded_rectangle([sx1, sy1, sx1 + sw, sy1 + sw], radius=3,
                                        fill=_team_color(team), outline=COLOR_SWATCH_BORDER, width=1)
                name_x = sx1 + sw + 7
            else:
                name_x = sx1

            value_text = _format_total(total)
            value_width = draw.textlength(value_text, font=value_font)
            max_name_width = x0 + BLOCK_WIDTH - 8 - name_x - value_width - 8

            display_name = player
            while draw.textlength(display_name, font=name_font) > max_name_width and len(display_name) > 3:
                display_name = display_name[:-2] + "…"
            draw.text((name_x, text_y), display_name, font=name_font, fill=COLOR_TEXT, anchor="lm")

            draw.text((x0 + BLOCK_WIDTH - 8, text_y), value_text, font=value_font, fill=COLOR_VALUE_TEXT, anchor="rm")

        draw.rectangle([x0, y0, x0 + BLOCK_WIDTH, y0 + BLOCK_TITLE_HEIGHT + TOP_N * ROW_HEIGHT],
                        outline=COLOR_BORDER, width=1)

    final = _add_shadow_and_round(content, CORNER_RADIUS, MARGIN)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf
