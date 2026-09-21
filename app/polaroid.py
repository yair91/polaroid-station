"""Procesamiento de imagenes con Pillow.

Dos salidas por cada foto que sube un invitado:
  1. `thumbnail()`  -> version reducida 128x128 que se guarda en pictures/
  2. `compose()`    -> polaroid (marco blanco + mensaje abajo) para polaroids/
"""
import io
import logging
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import config

log = logging.getLogger(__name__)

# Proporciones del marco, relativas al lado de la foto.
SIDE_MARGIN_RATIO = 0.08     # margen izquierdo/derecho/superior
BOTTOM_MARGIN_RATIO = 0.32   # franja inferior donde va el mensaje
FRAME_COLOR = (253, 252, 248)
TEXT_COLOR = (46, 42, 38)
SHADOW_COLOR = (214, 210, 202)

FONT_CANDIDATES = (
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/gnu-free/FreeSans.ttf",
    "/Library/Fonts/Arial.ttf",
)


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    # Pillow >= 10.1 permite escalar la fuente incluida.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - Pillow viejo
        return ImageFont.load_default()


def open_image(raw: bytes) -> Image.Image:
    """Abre la imagen subida, corrige la orientacion EXIF y la pasa a RGB."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise ValueError("El archivo no es una imagen valida.") from exc
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _square(img: Image.Image, size: int) -> Image.Image:
    """Recorte centrado a cuadrado del tamano pedido."""
    return ImageOps.fit(img, (size, size), method=Image.LANCZOS, centering=(0.5, 0.5))


def thumbnail(img: Image.Image, size: Optional[int] = None) -> bytes:
    """Version reducida (por defecto 128x128) en JPEG."""
    size = size or config.THUMB_SIZE
    buf = io.BytesIO()
    _square(img, size).save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    """Corta el texto en lineas que quepan en `max_width` pixeles."""
    lines: List[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _fit_text(draw, text: str, max_width: int, max_height: int,
              start_size: int) -> Tuple[List[str], ImageFont.ImageFont, int]:
    """Baja el tamano de fuente hasta que el mensaje quepa en la franja."""
    size = start_size
    while size >= 14:
        font = _load_font(size)
        lines = _wrap(draw, text, font, max_width)
        line_height = int(size * 1.35)
        if len(lines) * line_height <= max_height:
            return lines, font, line_height
        size -= 2
    font = _load_font(14)
    lines = _wrap(draw, text, font, max_width)[:4]
    return lines, font, int(14 * 1.35)


def compose(img: Image.Image, message: str, photo_size: Optional[int] = None) -> bytes:
    """Arma la polaroid: marco blanco y el mensaje escrito abajo. PNG listo
    para imprimir."""
    photo_size = photo_size or config.POLAROID_PHOTO_SIZE
    margin = int(photo_size * SIDE_MARGIN_RATIO)
    bottom = int(photo_size * BOTTOM_MARGIN_RATIO)

    width = photo_size + margin * 2
    height = margin + photo_size + bottom

    canvas = Image.new("RGB", (width, height), FRAME_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Borde exterior sutil, para que el marco se distinga sobre fondo blanco.
    draw.rectangle([0, 0, width - 1, height - 1], outline=SHADOW_COLOR, width=2)

    photo = _square(img, photo_size)
    canvas.paste(photo, (margin, margin))
    # Linea fina alrededor de la foto.
    draw.rectangle(
        [margin - 1, margin - 1, margin + photo_size, margin + photo_size],
        outline=SHADOW_COLOR, width=1,
    )

    message = (message or "").strip()
    if message:
        text_top = margin + photo_size
        area_height = bottom
        max_text_height = int(area_height * 0.66)
        lines, font, line_height = _fit_text(
            draw, message, photo_size, max_text_height, start_size=int(photo_size * 0.058)
        )
        block_height = len(lines) * line_height
        y = text_top + (area_height - block_height) / 2
        for line in lines:
            line_width = draw.textlength(line, font=font)
            draw.text(((width - line_width) / 2, y), line, font=font, fill=TEXT_COLOR)
            y += line_height

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
