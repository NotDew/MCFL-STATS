import io
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFilter

import card_style as cs

CARD_WIDTH = 700
CORNER_RADIUS = 22
MARGIN = 30

HEADER_HEIGHT = 100
ROW_HEIGHT = 64
ICON_SIZE = 40
PADDING = 24


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


def render_stat_leaderboard_card(stat_label: str, ranked: List[Tuple[str, str, float]], subtitle: str = None) -> io.BytesIO:
    num_rows = max(len(ranked), 1)
    height = HEADER_HEIGHT + num_rows * ROW_HEIGHT

    content = Image.new("RGB", (CARD_WIDTH, height), cs.CARD_BG)
    draw = ImageDraw.Draw(content)

    cs.draw_header(content, draw, CARD_WIDTH, HEADER_HEIGHT, stat_label.upper(),
                    subtitle or f"{stat_label} Leaders")

    name_font = cs.load_font(20, bold=True)
    team_font = cs.load_font(13, bold=False)
    value_font = cs.load_font(24, bold=True)
    badge_font = cs.load_font(17, bold=True)

    y = HEADER_HEIGHT

    if not ranked:
        draw.rectangle([0, y, CARD_WIDTH, y + ROW_HEIGHT], fill=cs.ROW_EVEN)
        draw.text((CARD_WIDTH / 2, y + ROW_HEIGHT / 2), "No stats recorded yet",
                   font=cs.load_font(15), fill=(150, 150, 155), anchor="mm")
        y += ROW_HEIGHT

    for i, (player, team, total) in enumerate(ranked):
        row_bg = cs.ROW_EVEN if i % 2 == 0 else cs.ROW_ODD
        draw.rectangle([0, y, CARD_WIDTH, y + ROW_HEIGHT], fill=row_bg)

        badge_color = cs.tier_color(i + 1, team)
        bx1, by1 = PADDING, y + (ROW_HEIGHT - 36) / 2
        bx2, by2 = bx1 + 36, by1 + 36
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=9, fill=badge_color)
        draw.text(((bx1 + bx2) / 2, (by1 + by2) / 2), str(i + 1), font=badge_font, fill=cs.badge_text_color(badge_color), anchor="mm")

        icon_x = bx2 + 14
        icon_y = y + (ROW_HEIGHT - ICON_SIZE) / 2
        cs.draw_team_icon(content, draw, team, icon_x, icon_y, ICON_SIZE)

        text_x = icon_x + ICON_SIZE + 16
        draw.text((text_x, y + ROW_HEIGHT / 2 - 12), player, font=name_font, fill=(20, 20, 25), anchor="lm")
        if team:
            draw.text((text_x, y + ROW_HEIGHT / 2 + 13), team, font=team_font, fill=(120, 123, 132), anchor="lm")

        value_color = (20, 50, 110) if i == 0 else (20, 20, 25)
        draw.text((CARD_WIDTH - PADDING, y + ROW_HEIGHT / 2), _format_total(total),
                   font=value_font, fill=value_color, anchor="rm")

        y += ROW_HEIGHT

    draw.line([(0, y), (CARD_WIDTH, y)], fill=cs.DIVIDER, width=1)

    final = _add_shadow_and_round(content, CORNER_RADIUS, MARGIN)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf
