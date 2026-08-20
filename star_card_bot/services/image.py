"""
Наносит на фото карты плашку с текущим курсом (⭐ N.NN), названием и редкостью.
Если по какой-то причине не получится обработать изображение (недоступен Pillow,
битый файл и т.п.) - бот просто отправит исходное фото с курсом в подписи (caption),
так что функциональность бота не пострадает.
"""

import io
from aiogram import Bot
from aiogram.types import BufferedInputFile
from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
]
FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

RARITY_COLORS = {
    None: (255, 205, 40),          # золотой - обычная карта
    "rare": (60, 140, 255),        # синий
    "epic": (170, 80, 240),        # фиолетовый
    "mythic": (255, 130, 40),      # оранжевый
    "legendary": (255, 210, 60),   # ярко-золотой
}
RARITY_LABEL = {
    None: "STAR CARD",
    "rare": "RARE",
    "epic": "EPIC",
    "mythic": "MYTHIC",
    "legendary": "LEGENDARY",
}


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


async def render_card_image(bot: Bot, file_id: str, name: str, rate: float,
                             rarity: str | None = None, day_change: float | None = None) -> BufferedInputFile | None:
    try:
        file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        buf.seek(0)

        img = Image.open(buf).convert("RGB")
        img = ImageOps.exif_transpose(img)

        # Приводим к аккуратному формату карточки 3:4 (обрезка по центру)
        target_ratio = 3 / 4
        w, h = img.size
        cur_ratio = w / h
        if cur_ratio > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))

        img = img.resize((900, 1200))
        w, h = img.size

        accent = RARITY_COLORS.get(rarity, RARITY_COLORS[None])
        label = RARITY_LABEL.get(rarity, RARITY_LABEL[None])

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # верхняя плашка редкости
        draw.rounded_rectangle([28, 28, 28 + 22 + len(label) * 15, 78], radius=18,
                                fill=(0, 0, 0, 160))
        font_label = _load_font(FONT_CANDIDATES_BOLD, 28)
        draw.text((44, 38), label, font=font_label, fill=accent)

        # нижний градиент + плашка курса
        grad_h = 260
        gradient = Image.new("L", (1, grad_h), color=0)
        for y in range(grad_h):
            gradient.putpixel((0, y), int(200 * (y / grad_h)))
        gradient = gradient.resize((w, grad_h))
        black_grad = Image.new("RGBA", (w, grad_h), (0, 0, 0, 255))
        black_grad.putalpha(gradient)
        overlay.paste(black_grad, (0, h - grad_h), black_grad)

        font_name = _load_font(FONT_CANDIDATES_BOLD, 46)
        font_rate = _load_font(FONT_CANDIDATES_BOLD, 40)
        font_small = _load_font(FONT_CANDIDATES_REGULAR, 24)

        draw.text((36, h - 200), name, font=font_name, fill=(255, 255, 255))
        draw.text((36, h - 140), "Текущий курс", font=font_small, fill=(210, 210, 210))
        draw.text((36, h - 108), f"⭐ {rate:,.2f}", font=font_rate, fill=accent)

        if day_change is not None:
            chg_color = (90, 220, 120) if day_change >= 0 else (230, 80, 80)
            chg_text = f"{'+' if day_change >= 0 else ''}{day_change:.1f}% за 24ч"
            chg_w = draw.textlength(f"⭐ {rate:,.2f}", font=font_rate)
            draw.text((36 + chg_w + 24, h - 100), chg_text, font=font_small, fill=chg_color)

        # тонкая рамка в цвет редкости
        draw.rounded_rectangle([4, 4, w - 4, h - 4], radius=28, outline=accent, width=6)

        final_img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        out = io.BytesIO()
        final_img.save(out, format="JPEG", quality=92)
        out.seek(0)
        return BufferedInputFile(out.read(), filename="card.jpg")
    except Exception:
        return None
