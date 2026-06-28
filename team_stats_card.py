import io
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD_WIDTH = 760
CORNER_RADIUS = 22
MARGIN = 30

TOP_N = 3
BLOCKS_PER_ROW = 3
BLOCK_WIDTH = 232
BLOCK_GAP = 14
BANNER_HEIGHT = 52
BLOCK_TITLE_HEIGHT = 30
ROW_HEIGHT = 38
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
COLOR_VALUE_TEXT = (15, 15, 20)
COLOR_BORDER = (228, 228, 233)
COLOR_SWATCH_BORDER = (255, 255, 255)

GOLD = (212, 175, 55)
SILVER = (158, 164, 174)
BRONZE = (173, 110, 65)
BADGE_TEXT = (255, 255, 255)


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
    return (90, 110, 160)


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


def _relative_luminance(rgb) -> float:
    r, g, b = (c / 255.0 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _header_text_colors(bg_rgb):
    if _relative_luminance(bg_rgb) > 0.6:
        return (25, 25, 30), (70, 70, 78)
    return (255, 255, 255), (210, 215, 230)


SINGLE_BLOCK_WIDTH = 232
SINGLE_BLOCK_HEIGHT = 80
SINGLE_BLOCK_GAP = 14


def render_single_team_card(team_name: str, stats: List[dict]) -> io.BytesIO:
    header_color = _team_color(team_name)
    header_text_color, header_subtext_color = _header_text_colors(header_color)

    num_blocks = len(stats)
    num_rows = (num_blocks + BLOCKS_PER_ROW - 1) // BLOCKS_PER_ROW if num_blocks else 1
    grid_width = BLOCKS_PER_ROW * SINGLE_BLOCK_WIDTH + (BLOCKS_PER_ROW - 1) * SINGLE_BLOCK_GAP
    card_width = grid_width + PADDING * 2
    grid_height = num_rows * SINGLE_BLOCK_HEIGHT + (num_rows - 1) * SINGLE_BLOCK_GAP if num_blocks else SINGLE_BLOCK_HEIGHT
    header_height = 64
    height = header_height + TOP_MARGIN + grid_height + BOTTOM_MARGIN

    content = Image.new("RGB", (card_width, height), COLOR_BG)
    draw = ImageDraw.Draw(content)

    draw.rectangle([0, 0, card_width, header_height], fill=header_color)
    name_font = _load_font(24, bold=True)
    sub_font = _load_font(13, bold=False)
    draw.text((PADDING, header_height / 2 - 11), team_name, font=name_font, fill=header_text_color, anchor="lm")
    n = len(stats)
    draw.text((PADDING, header_height / 2 + 14), f"{n} tracked stat{'s' if n != 1 else ''} recorded",
               font=sub_font, fill=header_subtext_color, anchor="lm")

    label_font = _load_font(12, bold=True)
    value_font = _load_font(22, bold=True)
    badge_font = _load_font(11, bold=True)

    if not stats:
        empty_font = _load_font(14)
        draw.text((card_width / 2, header_height + TOP_MARGIN + SINGLE_BLOCK_HEIGHT / 2),
                   "No stats recorded yet", font=empty_font, fill=(150, 150, 155), anchor="mm")

    for k, s in enumerate(stats):
        row_group, col_group = divmod(k, BLOCKS_PER_ROW)
        x0 = PADDING + col_group * (SINGLE_BLOCK_WIDTH + SINGLE_BLOCK_GAP)
        y0 = header_height + TOP_MARGIN + row_group * (SINGLE_BLOCK_HEIGHT + SINGLE_BLOCK_GAP)

        draw.rounded_rectangle([x0, y0, x0 + SINGLE_BLOCK_WIDTH, y0 + SINGLE_BLOCK_HEIGHT],
                                radius=10, fill=COLOR_ROW_ODD, outline=COLOR_BORDER, width=1)

        draw.text((x0 + 14, y0 + 14), s["label"].upper(), font=label_font, fill=(110, 113, 122), anchor="lm")
        draw.text((x0 + 14, y0 + 44), _format_total(s["total"]), font=value_font, fill=COLOR_VALUE_TEXT, anchor="lm")

        badge_color = _tier_color(s["rank"])
        badge_text = f"#{s['rank']} / {s['out_of']}"
        bw, bh = 80, 24
        bx2, by2 = x0 + SINGLE_BLOCK_WIDTH - 12, y0 + SINGLE_BLOCK_HEIGHT - 12
        bx1, by1 = bx2 - bw, by2 - bh
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=7, fill=badge_color)
        draw.text(((bx1 + bx2) / 2, (by1 + by2) / 2), badge_text, font=badge_font, fill=BADGE_TEXT, anchor="mm")

    final = _add_shadow_and_round(content, CORNER_RADIUS, MARGIN)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf

def render_team_stats_card(team_leaderboard: Dict[str, List[Tuple[str, float]]]) -> io.BytesIO:
    labels = list(team_leaderboard.keys())
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
    draw.text((card_width / 2, BANNER_HEIGHT / 2), "TOP TEAMS BY STAT",
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
        draw.text((x0 + BLOCK_WIDTH / 2, y0 + BLOCK_TITLE_HEIGHT / 2), label,
                   font=title_font, fill=COLOR_BLOCK_TITLE_TEXT, anchor="mm")

        ranked = team_leaderboard[label]
        for i in range(TOP_N):
            ry = y0 + BLOCK_TITLE_HEIGHT + i * ROW_HEIGHT
            row_bg = COLOR_ROW_EVEN if i % 2 == 0 else COLOR_ROW_ODD
            draw.rectangle([x0, ry, x0 + BLOCK_WIDTH, ry + ROW_HEIGHT], fill=row_bg)

            if i >= len(ranked):
                continue
            team_name, total = ranked[i]
            text_y = ry + ROW_HEIGHT / 2


            badge_color = _tier_color(i + 1)
            bx1, by1 = x0 + 6, ry + (ROW_HEIGHT - 22) / 2
            bx2, by2 = bx1 + 22, by1 + 22
            draw.rounded_rectangle([bx1, by1, bx2, by2], radius=6, fill=badge_color)
            draw.text(((bx1 + bx2) / 2, (by1 + by2) / 2), str(i + 1), font=badge_font, fill=BADGE_TEXT, anchor="mm")


            sx1 = bx2 + 8
            sw = 14
            sy1 = ry + (ROW_HEIGHT - sw) / 2
            draw.rounded_rectangle([sx1, sy1, sx1 + sw, sy1 + sw], radius=3,
                                    fill=_team_color(team_name), outline=COLOR_SWATCH_BORDER, width=1)


            name_x = sx1 + sw + 8
            max_name_width = x0 + BLOCK_WIDTH - 8 - name_x - 46
            display_name = team_name
            while draw.textlength(display_name, font=name_font) > max_name_width and len(display_name) > 3:
                display_name = display_name[:-2] + "…"
            draw.text((name_x, text_y), display_name, font=name_font, fill=COLOR_TEXT, anchor="lm")


            draw.text((x0 + BLOCK_WIDTH - 8, text_y), _format_total(total),
                       font=value_font, fill=COLOR_VALUE_TEXT, anchor="rm")

        draw.rectangle([x0, y0, x0 + BLOCK_WIDTH, y0 + BLOCK_TITLE_HEIGHT + TOP_N * ROW_HEIGHT],
                        outline=COLOR_BORDER, width=1)

    final = _add_shadow_and_round(content, CORNER_RADIUS, MARGIN)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf
