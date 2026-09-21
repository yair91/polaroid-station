"""Genera 3 fotos de prueba por si no tienes imagenes a la mano.

    python3 scripts/make_sample_photos.py
"""
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), "sample_photos")
PALETTES = [
    ((244, 162, 97), (231, 111, 81), "1"),
    ((42, 157, 143), (38, 70, 83), "2"),
    ((233, 196, 106), (244, 162, 97), "3"),
]


def gradient(top, bottom, size=(1200, 900)):
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(size[1]):
        t = y / max(size[1] - 1, 1)
        draw.line(
            [(0, y), (size[0], y)],
            fill=tuple(int(top[c] + (bottom[c] - top[c]) * t) for c in range(3)),
        )
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    for top, bottom, label in PALETTES:
        img = gradient(top, bottom)
        draw = ImageDraw.Draw(img)
        draw.ellipse([450, 300, 750, 600], fill=(255, 255, 255))
        draw.text((590, 430), label, fill=(60, 60, 60))
        path = os.path.join(OUT, f"foto-{label}.jpg")
        img.save(path, quality=90)
        print("creada", path)


if __name__ == "__main__":
    main()
