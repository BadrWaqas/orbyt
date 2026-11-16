import io

import numpy as np
from PIL import Image

from orbyt.sources import black_marble as bm


def test_recolour_maps_dark_to_land_and_bright_to_paper_white():
    grey = np.array([[0, 255], [128, 40]], dtype="uint8")
    rgb = bm.recolour(grey)
    assert rgb.shape == (2, 2, 3) and rgb.dtype == np.uint8
    assert tuple(rgb[0, 0]) == (0x0C, 0x12, 0x19)  # no light: the land colour
    assert tuple(rgb[0, 1]) == (0xF2, 0xEE, 0xE3)  # full light: paper white
    # Lightness rises with the light, and the lights stay neutral, never amber.
    luma = rgb.astype(float) @ np.array([0.2126, 0.7152, 0.0722])
    assert luma[0, 0] < luma[1, 1] < luma[1, 0] < luma[0, 1]
    assert abs(int(rgb[1, 0, 0]) - int(rgb[1, 0, 2])) < 24


def test_convert_reads_transparent_rgba_and_writes_opaque_rgb_png():
    src = np.zeros((8, 8, 4), dtype="uint8")
    src[2, 3] = (255, 255, 255, 255)  # one lit pixel
    buf = io.BytesIO()
    Image.fromarray(src, "RGBA").save(buf, "PNG")
    out = bm.convert(buf.getvalue())
    with Image.open(io.BytesIO(out)) as im:
        assert im.mode == "RGB" and im.size == (8, 8)
        arr = np.asarray(im)
    assert tuple(arr[2, 3]) == (0xF2, 0xEE, 0xE3)
    assert tuple(arr[0, 0]) == (0x0C, 0x12, 0x19)


def test_tile_list_and_url_order():
    assert len(bm.tiles(2)) == 1 + 4 + 16
    assert bm.URL.format(z=3, x=4, y=2).endswith("/3/2/4.png")  # GIBS wants row before column
