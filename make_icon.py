# -*- coding: utf-8 -*-
"""Генерация иконки приложения mimi crack (снежинка на тёмной плитке).
Создаёт ui/app.ico (для exe и проводника) и ui/app_icon.png (превью).
Запуск:  py -3.12 make_icon.py   (нужен Pillow)
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

S = 1024
R = int(S * 0.24)          # радиус скругления плитки
CX = CY = S / 2
ARM = S * 0.34             # длина луча снежинки
W = max(2, int(S * 0.026)) # толщина линий


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def draw_snowflake(d, cx, cy, arm, w, color):
    for k in range(6):
        a = math.radians(60 * k)
        ca, sa = math.cos(a), math.sin(a)
        ex, ey = cx + arm * ca, cy + arm * sa
        d.line([cx, cy, ex, ey], fill=color, width=w)
        # округлые концы
        d.ellipse([ex - w / 2, ey - w / 2, ex + w / 2, ey + w / 2], fill=color)
        # боковые веточки
        for f in (0.52, 0.8):
            bx, by = cx + arm * f * ca, cy + arm * f * sa
            bl = arm * 0.22
            for da in (52, -52):
                a2 = a + math.radians(da)
                d.line([bx, by, bx + bl * math.cos(a2), by + bl * math.sin(a2)],
                       fill=color, width=w)
    # центральная точка
    d.ellipse([cx - w, cy - w, cx + w, cy + w], fill=color)


# фон-плитка (почти чёрная, с лёгким верхним бликом)
base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
tile = Image.new("RGBA", (S, S), (13, 13, 14, 255))
grad = Image.new("L", (1, S))
for y in range(S):
    grad.putpixel((0, y), int(46 * (1 - y / S)))     # блик сверху
sheen = Image.new("RGBA", (S, S), (255, 255, 255, 0))
sheen.putalpha(grad.resize((S, S)))
tile = Image.alpha_composite(tile, sheen)

mask = rounded_mask(S, R)
base.paste(tile, (0, 0), mask)

d = ImageDraw.Draw(base)
# тонкая светлая рамка
d.rounded_rectangle([3, 3, S - 4, S - 4], radius=R, outline=(255, 255, 255, 46), width=6)

# мягкая тень снежинки для объёма
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
dg = ImageDraw.Draw(glow)
draw_snowflake(dg, CX, CY + S * 0.012, ARM, W + 6, (0, 0, 0, 120))
glow = glow.filter(ImageFilter.GaussianBlur(10))
base = Image.alpha_composite(base, glow)

d = ImageDraw.Draw(base)
draw_snowflake(d, CX, CY, ARM, W, (255, 255, 255, 255))

# обрезаем по маске (на случай выхода линий)
out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
out.paste(base, (0, 0), mask)

here = os.path.dirname(os.path.abspath(__file__))
png = os.path.join(here, "ui", "app_icon.png")
ico = os.path.join(here, "ui", "app.ico")
out.save(png)
out.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("saved:", png)
print("saved:", ico)
