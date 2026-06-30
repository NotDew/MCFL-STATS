import io
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter

import card_style as cs

CARD_WIDTH = 820
CORNER_RADIUS = 22
MARGIN = 30
HEADER_HEIGHT = 90

TOP_N = 5
BLOCKS_PER_ROW = 3
BLOCK_WIDTH = 254
BLOCK_GAP = 14
BLOCK_TITLE_HEIGHT = 32
ROW_HEIGHT = 38
PADDING = 24
TOP_MARGIN = 16
BOTTOM_MARGIN = 16
ICON_SIZE = 22


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
    height = HEADER_HEIGHT + TOP_MARGIN + grid_height + BOTTOM_MARGIN

    content = Image.new("RGB", (card_width, height), cs.CARD_BG)
    draw = ImageDraw.Draw(content)
    cs.draw_header(content, draw, card_width, HEADER_HEIGHT, "GLOBAL LEADERBOARD", "Top 5 In Every Stat", title_font_size=26)

    title_font = cs.load_font(13, bold=True)
    name_font = cs.load_font(13, bold=True)
    value_font = cs.load_font(13, bold=False)
    badge_font = cs.load_font(11, bold=True)

    if not labels:
        draw.text((card_width / 2, HEADER_HEIGHT + TOP_MARGIN + block_height / 2),
                   "No stats recorded yet", font=cs.load_font(14), fill=(150, 150, 155), anchor="mm")

    for k, label in enumerate(labels):
        row_group, col_group = divmod(k, BLOCKS_PER_ROW)
        x0 = PADDING + col_group * (BLOCK_WIDTH + BLOCK_GAP)
        y0 = HEADER_HEIGHT + TOP_MARGIN + row_group * (block_height + BLOCK_GAP)

        draw.rectangle([x0, y0, x0 + BLOCK_WIDTH, y0 + BLOCK_TITLE_HEIGHT], fill=cs.HEADER_TOP)
        draw.text((x0 + BLOCK_WIDTH / 2, y0 + BLOCK_TITLE_HEIGHT / 2), label,
                   font=title_font, fill=(255, 255, 255), anchor="mm")

        ranked = player_leaderboard[label]
        for i in range(TOP_N):
            ry = y0 + BLOCK_TITLE_HEIGHT + i * ROW_HEIGHT
            row_bg = cs.ROW_EVEN if i % 2 == 0 else cs.ROW_ODD
            draw.rectangle([x0, ry, x0 + BLOCK_WIDTH, ry + ROW_HEIGHT], fill=row_bg)

            if i >= len(ranked):
                continue
            player, team, total = ranked[i]
            text_y = ry + ROW_HEIGHT / 2

            badge_color = cs.tier_color(i + 1, team)
            bx1, by1 = x0 + 5, ry + (ROW_HEIGHT - 20) / 2
            bx2, by2 = bx1 + 20, by1 + 20
            draw.rounded_rectangle([bx1, by1, bx2, by2], radius=5, fill=badge_color)
            draw.text(((bx1 + bx2) / 2, (by1 + by2) / 2), str(i + 1), font=badge_font, fill=cs.badge_text_color(badge_color), anchor="mm")

            icon_x = bx2 + 6
            icon_y = ry + (ROW_HEIGHT - ICON_SIZE) / 2
            cs.draw_team_icon(content, draw, team, icon_x, icon_y, ICON_SIZE)

            name_x = icon_x + ICON_SIZE + 7
            value_text = _format_total(total)
            value_width = draw.textlength(value_text, font=value_font)
            max_name_width = x0 + BLOCK_WIDTH - 8 - name_x - value_width - 8

            display_name = player
            while draw.textlength(display_name, font=name_font) > max_name_width and len(display_name) > 3:
                display_name = display_name[:-2] + "…"
            draw.text((name_x, text_y), display_name, font=name_font, fill=(20, 20, 25), anchor="lm")
            draw.text((x0 + BLOCK_WIDTH - 8, text_y), value_text, font=value_font, fill=(15, 15, 20), anchor="rm")

        draw.rectangle([x0, y0, x0 + BLOCK_WIDTH, y0 + BLOCK_TITLE_HEIGHT + TOP_N * ROW_HEIGHT],
                        outline=cs.DIVIDER, width=1)

    final = _add_shadow_and_round(content, CORNER_RADIUS, MARGIN)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    buf.seek(0)
    return buf
