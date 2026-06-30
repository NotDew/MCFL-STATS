from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from team_logos import get_team_logo

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


def team_color(team_name: str) -> Tuple[int, int, int]:
    return _TEAM_COLORS_LOWER.get((team_name or "").strip().lower(), DEFAULT_TEAM_COLOR)


GOLD = (212, 175, 55)
SILVER = (158, 164, 174)
BRONZE = (173, 110, 65)
BADGE_TEXT = (255, 255, 255)

HEADER_TOP = (15, 30, 64)
HEADER_BOTTOM = (10, 20, 46)
HEADER_DIVIDER = (70, 95, 145)
HEADER_TITLE_COLOR = (255, 255, 255)
HEADER_SUBTITLE_COLOR = (160, 178, 215)
YARD_LINE_COLOR = (45, 65, 110)
YARD_NUMBER_COLOR = (55, 78, 130)

CARD_BG = (255, 255, 255)
ROW_EVEN = (255, 255, 255)
ROW_ODD = (245, 246, 250)
DIVIDER = (228, 228, 233)

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
FONT_CANDIDATES_ITALIC_BOLD = [
    "arialbi.ttf",
    "C:/Windows/Fonts/arialbi.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
]


def load_font(size: int, bold: bool = False, italic_bold: bool = False) -> ImageFont.FreeTypeFont:
    if italic_bold:
        candidates = FONT_CANDIDATES_ITALIC_BOLD
    elif bold:
        candidates = FONT_CANDIDATES_BOLD
    else:
        candidates = FONT_CANDIDATES_REGULAR
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def badge_text_color(bg: Tuple[int, int, int]) -> Tuple[int, int, int]:
    luminance = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]
    return (30, 30, 35) if luminance > 150 else (255, 255, 255)


def tier_color(rank: int, team_name: str = "") -> Tuple[int, int, int]:
    if rank == 1:
        return GOLD
    if rank == 2:
        return SILVER
    if rank == 3:
        return BRONZE
    if team_name:
        return team_color(team_name)
    return (90, 110, 160)


def _vertical_gradient(width: int, height: int, top_color, bottom_color) -> Image.Image:
    base = Image.new("RGB", (1, height), top_color)
    top = Image.new("RGB", (1, height), top_color)
    bottom = Image.new("RGB", (1, height), bottom_color)
    grad = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        grad.putpixel((0, y), (r, g, b))
    return grad.resize((width, height))


def draw_football_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, w: int, h: int):
    bbox = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
    draw.ellipse(bbox, outline=(235, 238, 245), width=3)
    draw.line([(cx - w * 0.32, cy), (cx + w * 0.32, cy)], fill=(235, 238, 245), width=2)
    lace_spacing = h * 0.16
    for i in range(-2, 3):
        lx = cx + i * (w * 0.11)
        draw.line([(lx, cy - lace_spacing / 2), (lx, cy + lace_spacing / 2)], fill=(235, 238, 245), width=2)


def draw_header(img: Image.Image, draw: ImageDraw.ImageDraw, width: int, height: int,
                 title: str, subtitle: str, title_font_size: int = 30, subtitle_font_size: int = 13):
    gradient = _vertical_gradient(width, height, HEADER_TOP, HEADER_BOTTOM)
    img.paste(gradient, (0, 0))

    title_font = load_font(title_font_size, bold=True, italic_bold=True)
    subtitle_font = load_font(subtitle_font_size, bold=True)
    text_x = 100
    title_width = draw.textlength(title, font=title_font)
    yard_zone_start = max(text_x + title_width + 30, width * 0.55)

    yard_font = load_font(22, bold=True)
    yard_positions = [x for x in (width - 270, width - 210, width - 150) if x > yard_zone_start]
    for x, label in zip(yard_positions, ("40", "50", "40")):
        draw.text((x, height * 0.30), label, font=yard_font, fill=YARD_NUMBER_COLOR, anchor="mm")
    line_start = max(int(width * 0.46), int(yard_zone_start))
    for lx in range(line_start, width - 20, 14):
        draw.line([(lx, height * 0.62), (lx, height * 0.86)], fill=YARD_LINE_COLOR, width=2)

    icon_cx, icon_cy = 56, height // 2
    draw_football_icon(draw, icon_cx, icon_cy, 64, 38)

    draw.text((text_x, height * 0.32), title, font=title_font, fill=HEADER_TITLE_COLOR, anchor="lm")
    draw.text((text_x, height * 0.68), subtitle.upper(), font=subtitle_font, fill=HEADER_SUBTITLE_COLOR, anchor="lm")

    draw.rectangle([0, height - 3, width, height], fill=HEADER_DIVIDER)


def draw_team_icon(content: Image.Image, draw: ImageDraw.ImageDraw, team_name: str, x: int, y: int, size: int):
    logo = get_team_logo(team_name, size)
    if logo is not None:
        content.paste(logo, (int(x), int(y)), logo)
        return

    color = team_color(team_name)
    draw.rounded_rectangle([x, y, x + size, y + size], radius=size * 0.22, fill=color, outline=(255, 255, 255), width=2)
    initial = (team_name or "?").strip()[:1].upper()
    font = load_font(int(size * 0.55), bold=True)
    luminance = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
    text_color = (30, 30, 35) if luminance > 150 else (255, 255, 255)
    draw.text((x + size / 2, y + size / 2), initial, font=font, fill=text_color, anchor="mm")
