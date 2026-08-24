"""
Наносит на фото карты плашку с текущим курсом (⭐ N.NN), названием и редкостью.
Если по какой-то причине не получится обработать изображение (недоступен Pillow,
битый файл и т.п.) - бот просто отправит исходное фото с курсом в подписи (caption),
так что функциональность бота не пострадает.

Дизайн рисуется в 2x разрешении и затем уменьшается (supersampling) - так все
скругления и линии получаются гладкими, без "лесенки" и пиксельных огрызков.
Звезда рисуется как векторный многоугольник, а не текстовым символом: у эмодзи
⭐ почти нет шансов найти шрифт с нужным глифом, и он рисуется квадратиком
поверх фото - вместо этого используем ту же самую фигуру, которую сам PIL
отрисовывает пиксель в пиксель, независимо от того, какие шрифты есть в системе.
"""

import io
import os
import math
from aiogram import Bot
from aiogram.types import BufferedInputFile
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")

# Шрифт, который лежит прямо в проекте (DejaVu Sans, поддерживает кириллицу) -
# всегда пробуем его первым, чтобы не зависеть от того, какие шрифты вообще
# установлены в системе (актуально для Windows, где путей /usr/share/fonts нет).
FONT_CANDIDATES_BOLD = [
    os.path.join(_ASSETS_DIR, "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\tahomabd.ttf",
]
FONT_CANDIDATES_REGULAR = [
    os.path.join(_ASSETS_DIR, "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
]

# Палитра по редкости: (акцентный цвет, второй цвет для мягкого градиента в плашке)
RARITY_COLORS = {
    None: (255, 200, 60),
    "rare": (66, 150, 255),
    "epic": (176, 88, 246),
    "mythic": (255, 128, 40),
    "legendary": (255, 178, 40),
}
RARITY_LABEL = {
    None: "STAR CARD",
    "rare": "RARE",
    "epic": "EPIC",
    "mythic": "MYTHIC",
    "legendary": "LEGENDARY",
}

# Всё рисуется в этом разрешении и затем уменьшается до целевого - сглаживает
# скругления углов, обводку и текст.
SS = 2
CARD_W, CARD_H = 900 * SS, 1200 * SS
RADIUS = 34 * SS


def _load_font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def _draw_star(draw, cx, cy, r, fill):
    """Рисует пятиконечную звезду как многоугольник - без зависимости от шрифтов."""
    points = []
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        points.append((cx + rad * math.cos(ang), cy - rad * math.sin(ang)))
    draw.polygon(points, fill=fill)


def _soft_shadow_layer(size, box, radius, alpha, blur):
    """Слой с мягкой тенью под плашкой - для лёгкого 'приподнятого' эффекта."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=(0, 0, 0, alpha))
    return layer.filter(ImageFilter.GaussianBlur(blur))


async def render_card_image(bot: Bot, file_id: str, name: str, rate: float,
                             rarity: str | None = None, day_change: float | None = None) -> BufferedInputFile | None:
    try:
        file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        buf.seek(0)

        photo = Image.open(buf).convert("RGB")
        photo = ImageOps.exif_transpose(photo)

        # Приводим к аккуратному формату карточки 3:4 (обрезка по центру)
        target_ratio = 3 / 4
        w, h = photo.size
        cur_ratio = w / h
        if cur_ratio > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            photo = photo.crop((left, 0, left + new_w, h))
        else:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            photo = photo.crop((0, top, w, top + new_h))

        photo = photo.resize((CARD_W, CARD_H), Image.LANCZOS)

        accent = RARITY_COLORS.get(rarity, RARITY_COLORS[None])
        label = RARITY_LABEL.get(rarity, RARITY_LABEL[None])

        # Холст карты: фон + чуть затемняем фото сверху и снизу для контраста текста,
        # затем маскируем всё скруглёнными углами ЦЕЛИКОМ (это и убирает те самые
        # "квадратики" по углам - раньше скруглялась только рамка, а само фото под
        # ней оставалось прямоугольным и торчало из-под скруглений).
        card = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 255))
        card.paste(photo, (0, 0))

        overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # --- верхняя лёгкая виньетка, чтобы плашка редкости была читаема на любом фото
        top_grad_h = 220 * SS
        top_grad = Image.new("L", (1, top_grad_h), 0)
        for y in range(top_grad_h):
            top_grad.putpixel((0, y), int(150 * (1 - y / top_grad_h)))
        top_grad = top_grad.resize((CARD_W, top_grad_h))
        top_black = Image.new("RGBA", (CARD_W, top_grad_h), (0, 0, 0, 255))
        top_black.putalpha(top_grad)
        overlay.alpha_composite(top_black, (0, 0))

        # --- нижний градиент под текст (двухслойный: мягкий дальний + плотный ближний)
        grad_h = 460 * SS
        bottom_grad = Image.new("L", (1, grad_h), 0)
        for y in range(grad_h):
            t = y / grad_h
            bottom_grad.putpixel((0, y), int(235 * (t ** 1.6)))
        bottom_grad = bottom_grad.resize((CARD_W, grad_h))
        bottom_black = Image.new("RGBA", (CARD_W, grad_h), (0, 0, 0, 255))
        bottom_black.putalpha(bottom_grad)
        overlay.alpha_composite(bottom_black, (0, CARD_H - grad_h))

        # --- плашка редкости (верхний левый угол): мягкая тень + скруглённый прямоугольник
        pad_x, pad_y = 28 * SS, 30 * SS
        star_r = 15 * SS
        font_label = _load_font(FONT_CANDIDATES_BOLD, 27 * SS)
        label_w = draw.textlength(label, font=font_label)
        badge_pad_l = 22 * SS
        badge_h = 58 * SS
        badge_w = int(badge_pad_l + star_r * 2 + 12 * SS + label_w + 22 * SS)
        badge_box = [pad_x, pad_y, pad_x + badge_w, pad_y + badge_h]

        shadow = _soft_shadow_layer((CARD_W, CARD_H), badge_box, badge_h // 2, 120, 10 * SS)
        overlay.alpha_composite(shadow)
        draw.rounded_rectangle(badge_box, radius=badge_h // 2, fill=(18, 16, 26, 210),
                                outline=(*accent, 130), width=max(1, SS))
        _draw_star(draw, pad_x + badge_pad_l + star_r, pad_y + badge_h / 2, star_r, accent)
        draw.text((pad_x + badge_pad_l + star_r * 2 + 12 * SS, pad_y + badge_h / 2), label,
                   font=font_label, fill=(255, 255, 255), anchor="lm")

        # --- нижний текстовый блок: имя, подпись, курс, изменение за 24ч
        margin = 40 * SS
        base_y = CARD_H - 86 * SS

        font_rate = _load_font(FONT_CANDIDATES_BOLD, 46 * SS)
        font_name = _load_font(FONT_CANDIDATES_BOLD, 42 * SS)
        font_caption = _load_font(FONT_CANDIDATES_REGULAR, 21 * SS)
        font_change = _load_font(FONT_CANDIDATES_BOLD, 21 * SS)

        # курс + иконка звезды - самый крупный, самый заметный элемент
        rate_text = f"{rate:,.2f}"
        star_cy = base_y - 14 * SS
        _draw_star(draw, margin + 15 * SS, star_cy, 16 * SS, accent)
        draw.text((margin + 38 * SS, base_y), rate_text, font=font_rate, fill=accent, anchor="ls")

        if day_change is not None:
            rate_w = draw.textlength(rate_text, font=font_rate)
            chip_x0 = margin + 38 * SS + rate_w + 18 * SS
            up = day_change >= 0
            chg_color = (94, 224, 130) if up else (240, 88, 88)
            chg_text = f"{'▲' if up else '▼'} {abs(day_change):.1f}%"
            chg_w = draw.textlength(chg_text, font=font_change)
            chip_pad = 14 * SS
            chip_box = [chip_x0, base_y - 34 * SS, chip_x0 + chg_w + chip_pad * 2, base_y + 4 * SS]
            draw.rounded_rectangle(chip_box, radius=(chip_box[3] - chip_box[1]) // 2,
                                    fill=(0, 0, 0, 150), outline=(*chg_color, 200), width=max(1, SS))
            draw.text(((chip_box[0] + chip_box[2]) / 2, (chip_box[1] + chip_box[3]) / 2 + 1 * SS),
                       chg_text, font=font_change, fill=chg_color, anchor="mm")

        # подпись "Текущий курс" над цифрами, чуть разрежённая по буквам - premium-деталь
        caption_y = base_y - 34 * SS - 22 * SS
        caption_txt = "ТЕКУЩИЙ КУРС"
        cx = margin
        for ch in caption_txt:
            draw.text((cx, caption_y), ch, font=font_caption, fill=(200, 200, 210, 235), anchor="ls")
            cx += draw.textlength(ch, font=font_caption) + 3 * SS

        # тонкая линия-разделитель в цвет акцента
        divider_y = caption_y - 22 * SS
        draw.line([(margin, divider_y), (margin + 64 * SS, divider_y)], fill=(*accent, 220), width=3 * SS)

        # название карты - крупным шрифтом над разделителем
        name_y = divider_y - 16 * SS
        max_name_w = CARD_W - margin * 2
        display_name = name
        while draw.textlength(display_name, font=font_name) > max_name_w and len(display_name) > 1:
            display_name = display_name[:-2] + "…"
        draw.text((margin, name_y), display_name, font=font_name, fill=(255, 255, 255), anchor="ls")

        # --- склеиваем фото + оверлей, затем маскируем скруглёнными углами ЦЕЛИКОМ
        composed = Image.alpha_composite(card, overlay)
        mask = _rounded_mask((CARD_W, CARD_H), RADIUS)
        rounded = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        rounded.paste(composed, (0, 0), mask)

        # мягкое сияние рамки в цвет редкости под чёткой тонкой линией сверху
        border_layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(border_layer)
        glow_box = [SS, SS, CARD_W - SS, CARD_H - SS]
        bd.rounded_rectangle(glow_box, radius=RADIUS, outline=(*accent, 255), width=4 * SS)
        glow = border_layer.filter(ImageFilter.GaussianBlur(6 * SS))
        rounded.alpha_composite(glow)
        bd2 = ImageDraw.Draw(rounded)
        bd2.rounded_rectangle(glow_box, radius=RADIUS, outline=(*accent, 255), width=max(2, 2 * SS))

        final_img = rounded.convert("RGB").resize((900, 1200), Image.LANCZOS)

        out = io.BytesIO()
        final_img.save(out, format="JPEG", quality=94)
        out.seek(0)
        return BufferedInputFile(out.read(), filename="card.jpg")
    except Exception:
        return None
