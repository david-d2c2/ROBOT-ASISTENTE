"""Convierte el render 3D con fondo verde cromático en un sprite PNG transparente.

Uso: .venv/Scripts/python.exe tools/process_sprite.py <entrada> <salida> [lado]
"""
import sys
from PIL import Image


def chroma_key(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    width, height = img.size
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    source = img.load()
    target = out.load()
    for y in range(height):
        for x in range(width):
            r, g, b = source[x, y]
            greenness = g - max(r, b)
            if greenness >= 90:
                continue
            alpha = 255
            if greenness > 20:
                alpha = max(0, min(255, 255 - int((greenness - 20) * 255 / 70)))
            if greenness > 0:
                g = max(r, b)  # despill del borde verde
            target[x, y] = (r, g, b, alpha)
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    side = int(sys.argv[3]) if len(sys.argv) > 3 else 512
    sprite = chroma_key(Image.open(src))
    bbox = sprite.getbbox()
    sprite = sprite.crop(bbox)
    print(f"crop bbox: {bbox}")
    canvas_side = int(max(sprite.size) * 1.04)
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    canvas.paste(sprite, ((canvas_side - sprite.width) // 2, (canvas_side - sprite.height) // 2), sprite)
    canvas = canvas.resize((side, side), Image.LANCZOS)
    canvas.save(dst)
    print(f"guardado: {dst} ({side}x{side}, escala original {canvas_side} -> {side})")


if __name__ == "__main__":
    main()
