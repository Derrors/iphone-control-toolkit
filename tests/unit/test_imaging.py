import io

import pytest
from PIL import Image

from iphone_mcp import imaging

SCREEN = (430, 932)


def png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 60, 90)).save(buf, "PNG")
    return buf.getvalue()


def size(jpeg):
    return Image.open(io.BytesIO(jpeg)).size


PORTRAIT = png(1290, 2796)


def test_full_screen_is_scaled_to_points():
    jpeg, wh = imaging.full_screen_jpeg(PORTRAIT, SCREEN)
    assert wh == (430, 932) and size(jpeg) == (430, 932)


def test_landscape_screenshot_swaps_dimensions():
    jpeg, wh = imaging.full_screen_jpeg(png(2796, 1290), SCREEN)
    assert wh == (932, 430) and size(jpeg) == (932, 430)


def test_wide_region_is_capped_at_1200():
    jpeg, region, zoom = imaging.region_jpeg(PORTRAIT, SCREEN, 0, 55, 430, 40)
    assert region == (0, 55, 430, 40)
    assert size(jpeg)[0] == 1200
    assert zoom == pytest.approx(1200 / 430)


def test_small_region_is_upscaled_to_600():
    jpeg, _, zoom = imaging.region_jpeg(PORTRAIT, SCREEN, 115, 108, 50, 20)
    assert size(jpeg)[0] == 600
    assert zoom == pytest.approx(12)


def test_region_is_clamped_to_screen():
    _, region, _ = imaging.region_jpeg(PORTRAIT, SCREEN, -10, 900, 100, 100)
    assert region == (0, 900, 90, 32)


def test_region_outside_screen_raises():
    with pytest.raises(ValueError):
        imaging.region_jpeg(PORTRAIT, SCREEN, 500, 10, 50, 50)


@pytest.mark.parametrize("pt,expected", [
    ((0, 0), (0, 0)),
    ((430, 932), (65535, 65535)),
    ((215, 466), (32768, 32768)),
    ((-5, 2000), (0, 65535)),
])
def test_hid_norm(pt, expected):
    assert imaging.hid_norm(*pt, SCREEN) == expected
