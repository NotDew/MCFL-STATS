import io
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD_WIDTH = 700
CORNER_RADIUS = 22
MARGIN = 30

AVATAR_SIZE = 84
HEADER_HEIGHT = 130
HERO_HEIGHT = 92
SECTION_HEADER_HEIGHT = 32
SUBHEADER_ROW_HEIGHT = 26
COL_ROW_HEIGHT = 42
PADDING = 26
COL_PADDING = 16
FOOTER_HEIGHT = 16
COL_WIDTH = CARD_WIDTH // 2


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
DEFAULT_TEAM_COLOR = (24, 30, 70)
_TEAM_COLORS_LOWER = {name.lower(): rgb for name, rgb in TEAM_COLORS.items()}


def _team_color(team_name: str):
    return _TEAM_COLORS_LOWER.get((team_name or "").strip().lower(), DEFAULT_TEAM_COLOR)


def _relative_luminance(rgb) -> float:
    r, g, b = (c / 255.0 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _header_text_colors(bg_rgb):
    if _relative_luminance(bg_rgb) > 0.6:
        return (25, 25, 30), (70, 70, 78)
    return (255, 255, 255), (210, 215, 230)


COLOR_HEADER_BG = (24, 30, 70)
COLOR_HEADER_TEXT = (255, 255, 255)
COLOR_HEADER_SUBTEXT = (175, 188, 226)
COLOR_CARD_BG = (255, 255, 255)
COLOR_ROW_EVEN = (255, 255, 255)
COLOR_ROW_ODD = (245, 246, 250)
COLOR_LABEL_TEXT = (45, 45, 50)
COLOR_VALUE_TEXT = (20, 20, 20)
COLOR_FOOTER_TEXT = (140, 140, 145)
COLOR_DIVIDER = (225, 225, 230)
COLOR_AVATAR_BORDER = (255, 255, 255)
COLOR_EMPTY_TEXT = (170, 170, 175)
COLOR_SUBHEADER_BG = (231, 233, 239)
COLOR_SUBHEADER_TEXT = (60, 65, 80)

COLOR_OFFENSE_HEADER = (37, 56, 102)
COLOR_DEFENSE_HEADER = (107, 45, 45)
COLOR_SECTION_TEXT = (255, 255, 255)

GOLD = (212, 175, 55)
SILVER = (158, 164, 174)
BRONZE = (173, 110, 65)
BLUE = (74, 99, 168)
BADGE_TEXT = (255, 255, 255)
HERO_TEXT_ON_DARK = (255, 255, 255)

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
    return BLUE


def _format_total(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


MAX_EXTRA_STATS = 3
HIGH_RANK_THRESHOLD = 3
SECONDARY_OFFENSE_THRESHOLD = 50


QB_STATS = ["QBR", "Pass Comp", "Pass Att", "Pass Pct", "Passing YD", "Passing TD", "INT (O)", "Rush", "Rushing YD", "Rushing TD"]
SKILL_STATS = ["Rec", "Rec YD", "Rec TD", "Rush", "Rushing YD", "Rushing TD"]
DEFENSE_STATS = ["Tackles", "Sacks", "INT (D)", "Swats", "Def TD"]


ALL_CARD_STATS = list(dict.fromkeys(["FP"] + QB_STATS + SKILL_STATS + DEFENSE_STATS))

POSITION_LABELS = {id(QB_STATS): "QB", id(SKILL_STATS): "WR"}


def _total_for(by_label: dict, label: str) -> float:
    entry = by_label.get(label)
    return entry["total"] if entry else 0.0


def _build_stat_layout(stats: List[dict]) -> Tuple[Optional[dict], List[tuple], List[dict], Optional[str]]:
    by_label = {s["label"]: s for s in stats}
    hero = by_label.get("FP")

    passing_yd = _total_for(by_label, "Passing YD")
    rec_yd = _total_for(by_label, "Rec YD")
    rush_yd = _total_for(by_label, "Rushing YD")

    offense_group, secondary_group = None, None
    if passing_yd > 0 and passing_yd >= rec_yd and passing_yd >= rush_yd:
        offense_group = QB_STATS
        if rec_yd >= SECONDARY_OFFENSE_THRESHOLD:
            secondary_group = SKILL_STATS
    elif rec_yd > 0 or rush_yd > 0:
        offense_group = SKILL_STATS
        if passing_yd >= SECONDARY_OFFENSE_THRESHOLD:
            secondary_group = QB_STATS

    seen = set()
    if hero:
        seen.add("FP")

    offense_specs: List[tuple] = []
    for group, is_primary in ((offense_group, True), (secondary_group, False)):
        if not group:
            continue
        group_rows = [by_label[label] for label in group if label not in seen and label in by_label]
        if not group_rows:
            continue
        if group is QB_STATS:
            title = "QUARTERBACK"
        else:


            title = "RUSHING / RECEIVING" if is_primary else "RECEIVING"
        offense_specs.append(("header", title))
        for s in group_rows:
            offense_specs.append(("stat", s))
            seen.add(s["label"])

    defense_list: List[dict] = []
    for label in DEFENSE_STATS:
        if label in seen or label not in by_label:
            continue
        defense_list.append(by_label[label])
        seen.add(label)

    leftover = [s for s in stats if s["label"] not in seen and s["rank"] <= HIGH_RANK_THRESHOLD]
    leftover.sort(key=lambda s: (s["rank"], -s["out_of"]))
    extra_offense = [s for s in leftover[:MAX_EXTRA_STATS] if s["label"] in QB_STATS or s["label"] in SKILL_STATS]
    extra_defense = [s for s in leftover[:MAX_EXTRA_STATS] if s["label"] in DEFENSE_STATS]
    if extra_offense:
        offense_specs.append(("header", "OTHER"))
        for s in extra_offense:
            offense_specs.append(("stat", s))
    defense_list.extend(extra_defense)

    if offense_group is not None:
        position_label = POSITION_LABELS[id(offense_group)]
    elif defense_list:
        position_label = "Lineman"
    else:
        position_label = None

    return hero, offense_specs, defense_list, position_label


def _rounded_avatar(avatar_bytes: bytes, size: int) -> Image.Image:
    img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size), Image.NEAREST)
    return img


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


def _spec_height(spec) -> int:
    return SUBHEADER_ROW_HEIGHT if spec[0] == "header" else COL_ROW_HEIGHT


def _specs_height(specs: List[tuple]) -> int:
    return sum(_spec_height(s) for s in specs) if specs else COL_ROW_HEIGHT


def _draw_column(draw, x0: int, y0: int, body_height: int, title: str, header_color, specs: List[tuple]):
    draw.rectangle([x0, y0, x0 + COL_WIDTH, y0 + SECTION_HEADER_HEIGHT], fill=header_color)
    header_font = _load_font(14, bold=True)
    draw.text((x0 + COL_WIDTH / 2, y0 + SECTION_HEADER_HEIGHT / 2), title,
               font=header_font, fill=COLOR_SECTION_TEXT, anchor="mm")

    body_top = y0 + SECTION_HEADER_HEIGHT
    label_font = _load_font(15, bold=True)
    value_font = _load_font(15, bold=False)
    badge_font = _load_font(12, bold=True)
    subheader_font = _load_font(12, bold=True)

    y = body_top
    row_i = 0

    if not specs:
        draw.rectangle([x0, y, x0 + COL_WIDTH, y + COL_ROW_HEIGHT], fill=COLOR_ROW_EVEN)
        draw.text((x0 + COL_WIDTH / 2, y + COL_ROW_HEIGHT / 2), "No stats recorded",
                   font=_load_font(13), fill=COLOR_EMPTY_TEXT, anchor="mm")
        y += COL_ROW_HEIGHT

    for kind, payload in specs:
        if kind == "header":
            draw.rectangle([x0, y, x0 + COL_WIDTH, y + SUBHEADER_ROW_HEIGHT], fill=COLOR_SUBHEADER_BG)
            draw.text((x0 + COL_PADDING, y + SUBHEADER_ROW_HEIGHT / 2), payload,
                       font=subheader_font, fill=COLOR_SUBHEADER_TEXT, anchor="lm")
            y += SUBHEADER_ROW_HEIGHT
            continue

        s = payload
        row_bg = COLOR_ROW_EVEN if row_i % 2 == 0 else COLOR_ROW_ODD
        draw.rectangle([x0, y, x0 + COL_WIDTH, y + COL_ROW_HEIGHT], fill=row_bg)
        text_y = y + COL_ROW_HEIGHT // 2

        draw.text((x0 + COL_PADDING, text_y), s["label"], font=label_font, fill=COLOR_LABEL_TEXT, anchor="lm")

        badge_color = _tier_color(s["rank"])
        badge_text = f"#{s['rank']}/{s['out_of']}"
        bw, bh = 64, 22
        bx2 = x0 + COL_WIDTH - COL_PADDING
        bx1 = bx2 - bw
        by1 = y + (COL_ROW_HEIGHT - bh) // 2
        by2 = by1 + bh
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=7, fill=badge_color)
        draw.text(((bx1 + bx2) / 2, (by1 + by2) / 2), badge_text, font=badge_font, fill=BADGE_TEXT, anchor="mm")

        value_x = bx1 - 10
        draw.text((value_x, text_y), _format_total(s["total"]), font=value_font, fill=COLOR_VALUE_TEXT, anchor="rm")

        y += COL_ROW_HEIGHT
        row_i += 1

    if y < body_top + body_height:
        draw.rectangle([x0, y, x0 + COL_WIDTH, body_top + body_height], fill=COLOR_ROW_EVEN)


def render_player_card(card_data: dict, avatar_bytes: Optional[bytes] = None) -> io.BytesIO:
    hero, offense_specs, defense_list, position_label = _build_stat_layout(card_data["stats"])
    defense_specs = [("stat", s) for s in defense_list]
    body_height = max(_specs_height(offense_specs), _specs_height(defense_specs))

    team = card_data.get("team") or ""
    header_color = _team_color(team)
    header_text_color, header_subtext_color = _header_text_colors(header_color)

    total_body = (HERO_HEIGHT if hero else COL_ROW_HEIGHT) + SECTION_HEADER_HEIGHT + body_height
    height = HEADER_HEIGHT + total_body + FOOTER_HEIGHT

    content = Image.new("RGB", (CARD_WIDTH, height), COLOR_CARD_BG)
    draw = ImageDraw.Draw(content)


    draw.rectangle([0, 0, CARD_WIDTH, HEADER_HEIGHT], fill=header_color)

    if position_label:
        pos_font = _load_font(16, bold=True)
        text_w = draw.textlength(position_label, font=pos_font)
        pad_x, pad_y = 14, 9
        bw, bh = text_w + pad_x * 2, 16 + pad_y * 2
        bx2, by1 = CARD_WIDTH - PADDING, 22
        bx1, by2 = bx2 - bw, by1 + bh
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=bh / 2, fill=(255, 255, 255))
        draw.text(((bx1 + bx2) / 2, (by1 + by2) / 2), position_label, font=pos_font, fill=(24, 30, 70), anchor="mm")

    text_x = PADDING
    if avatar_bytes:
        try:
            avatar = _rounded_avatar(avatar_bytes, AVATAR_SIZE)
            ax, ay = PADDING, (HEADER_HEIGHT - AVATAR_SIZE) // 2
            border = AVATAR_SIZE + 6
            draw.rectangle([ax - 3, ay - 3, ax - 3 + border, ay - 3 + border], fill=header_text_color)
            content.paste(avatar, (ax, ay), avatar)
            text_x = ax + AVATAR_SIZE + 22
        except Exception:
            pass

    name_font = _load_font(30, bold=True)
    sub_font = _load_font(15, bold=False)
    draw.text((text_x, 38), card_data["name"], font=name_font, fill=header_text_color)
    n = card_data["games_played"]
    games_line = f"{n} game{'s' if n != 1 else ''} played"
    subtitle = f"{team}   •   {games_line}" if team else games_line
    draw.text((text_x, 78), subtitle, font=sub_font, fill=header_subtext_color)

    y = HEADER_HEIGHT


    label_font = _load_font(20, bold=True)
    value_font_big = _load_font(34, bold=True)
    badge_font = _load_font(15, bold=True)
    small_font = _load_font(13, bold=False)

    if hero:
        hero_color = _tier_color(hero["rank"])
        draw.rectangle([0, y, CARD_WIDTH, y + HERO_HEIGHT], fill=hero_color)
        draw.text((PADDING, y + 16), hero["label"].upper(), font=label_font, fill=HERO_TEXT_ON_DARK)
        draw.text((PADDING, y + 42), _format_total(hero["total"]), font=value_font_big, fill=HERO_TEXT_ON_DARK)

        rank_text = f"RANK #{hero['rank']}"
        out_of_text = f"of {hero['out_of']}"
        draw.text((CARD_WIDTH - PADDING, y + 30), rank_text, font=badge_font, fill=HERO_TEXT_ON_DARK, anchor="ra")
        draw.text((CARD_WIDTH - PADDING, y + 52), out_of_text, font=small_font, fill=HERO_TEXT_ON_DARK, anchor="ra")
        y += HERO_HEIGHT
    else:
        draw.rectangle([0, y, CARD_WIDTH, y + COL_ROW_HEIGHT], fill=COLOR_ROW_EVEN)
        draw.text((PADDING, y + COL_ROW_HEIGHT // 2), "No tracked stats recorded yet",
                   font=_load_font(16), fill=COLOR_FOOTER_TEXT, anchor="lm")
        y += COL_ROW_HEIGHT


    _draw_column(draw, 0, y, body_height, "OFFENSE", COLOR_OFFENSE_HEADER, offense_specs)
    _draw_column(draw, COL_WIDTH, y, body_height, "DEFENSE", COLOR_DEFENSE_HEADER, defense_specs)
    draw.line([(COL_WIDTH, y), (COL_WIDTH, y + SECTION_HEADER_HEIGHT + body_height)],
               fill=COLOR_DIVIDER, width=1)
    y += SECTION_HEADER_HEIGHT + body_height

    final = _add_shadow_and_round(content, CORNER_RADIUS, MARGIN)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf
