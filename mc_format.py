"""Convert Marvel Champions card scans (TIFF/PNG/JPG, no bleed) into MPC-ready JPGs with a bleed border.

The Drive scans are 600 DPI, roughly 1440-1457 x 2072-2082 px: the card face (63 x 88 mm) with the outer
edge trimmed by a hair and slight size variation between scans.  MPC's print target is 2.72 x 3.70 in
(card + ~3 mm bleed on each side); at the scans' native 600 DPI that is 1632 x 2220 px with a 1488 x 2076
card area.  (MPC accepts up to 800 DPI, but the scans carry no more detail than 600, so 800 would only be
interpolation.  Change DPI below if you want it anyway.)

Steps: scale the scan to fit inside the card area without cropping, centre it, extend its edge colour
outward to fill the rest of the card area and the bleed ring, then paint the rounded-corner gaps.
"""
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageOps

DPI = 600
OUT_W, OUT_H = round(2.72 * DPI), round(3.70 * DPI)      # 1632 x 2220
CARD_W, CARD_H = round(2.48 * DPI), round(3.46 * DPI)    # 1488 x 2076
BLEED = (OUT_W - CARD_W) // 2                             # 72
CORNER = round(0.12 * DPI)                                # ~3 mm printed corner radius
INSET = max(2, DPI // 150)                                # skip the outermost scanner-edge pixels when sampling


def _extend(canvas, box):
    """Fill everything outside `box` by replicating the pixels just inside its edges (Proxy Nexus style)."""
    x0, y0, x1, y1 = box
    W, H = canvas.size
    i = INSET
    top = canvas.crop((x0, y0 + i, x1, y0 + i + 1)).resize((x1 - x0, y0), Image.NEAREST)
    bot = canvas.crop((x0, y1 - i - 1, x1, y1 - i)).resize((x1 - x0, H - y1), Image.NEAREST)
    canvas.paste(top, (x0, 0))
    canvas.paste(bot, (x0, y1))
    left = canvas.crop((x0 + i, 0, x0 + i + 1, H)).resize((x0, H), Image.NEAREST)
    right = canvas.crop((x1 - i - 1, 0, x1 - i, H)).resize((W - x1, H), Image.NEAREST)
    canvas.paste(left, (0, 0))
    canvas.paste(right, (x1, 0))
    return canvas


def _edge_color(card):
    w, h = card.size
    s = max(4, w // 60)
    strips = [card.crop((CORNER, INSET, w - CORNER, INSET + s)), card.crop((CORNER, h - INSET - s, w - CORNER, h - INSET)),
              card.crop((INSET, CORNER, INSET + s, h - CORNER)), card.crop((w - INSET - s, CORNER, w - INSET, h - CORNER))]
    px = []
    for st in strips:
        px += list(st.getdata())
    px.sort(key=lambda p: sum(p))
    return px[len(px) // 2]


def format_card(src_path, dst_path, quality=92):
    im = Image.open(src_path)
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = bg
    im = im.convert("RGB")
    if im.width > im.height:
        im = im.rotate(90, expand=True)

    # scale to fit the card area (no cropping), centre it
    scale = min(CARD_W / im.width, CARD_H / im.height)
    w, h = round(im.width * scale), round(im.height * scale)
    card = im.resize((w, h), Image.LANCZOS) if (w, h) != im.size else im
    x0, y0 = (OUT_W - w) // 2, (OUT_H - h) // 2
    canvas = Image.new("RGB", (OUT_W, OUT_H))
    canvas.paste(card, (x0, y0))
    _extend(canvas, (x0, y0, x0 + w, y0 + h))

    # soften the replicated ring so it does not read as hard streaks, keeping the card itself untouched
    blurred = canvas.filter(ImageFilter.GaussianBlur(3))
    ring = Image.new("L", (OUT_W, OUT_H), 255)
    ImageDraw.Draw(ring).rectangle((x0 + INSET, y0 + INSET, x0 + w - INSET, y0 + h - INSET), fill=0)
    canvas = Image.composite(blurred, canvas, ring)

    # paint the rounded-corner gaps (white/black scanner background) with the border colour
    col = _edge_color(card)
    fill = Image.new("RGB", (OUT_W, OUT_H), col)
    mask = Image.new("L", (OUT_W, OUT_H), 0)
    d = ImageDraw.Draw(mask)
    r = CORNER + 6
    for (cx, cy) in [(x0, y0), (x0 + w, y0), (x0, y0 + h), (x0 + w, y0 + h)]:
        d.rectangle((cx - r, cy - r, cx + r, cy + r), fill=255)
    inner = Image.new("L", (OUT_W, OUT_H), 0)
    ImageDraw.Draw(inner).rounded_rectangle((x0, y0, x0 + w - 1, y0 + h - 1), radius=CORNER, fill=255)
    mask.paste(0, mask=inner)
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    canvas = Image.composite(fill, canvas, mask)
    canvas.save(dst_path, "JPEG", quality=quality, optimize=True, dpi=(DPI, DPI))
    return canvas.size


if __name__ == "__main__":
    print(format_card(sys.argv[1], sys.argv[2]))
