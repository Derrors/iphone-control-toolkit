"""截图缩放、局部放大和 HID 坐标换算。纯函数,不访问设备。"""
import io

from PIL import Image

HID_MAX = 65535


def oriented(image_size, screen):
    """截图是横的而屏幕尺寸是竖的(横屏 App),就把宽高互换。"""
    w, h = screen
    if image_size[0] > image_size[1] and w < h:
        return h, w
    return w, h


def full_screen_jpeg(png, screen, quality=80):
    """整屏截图缩放到点尺寸,图像像素即点坐标。返回 (jpeg, (宽, 高))。"""
    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = oriented(im.size, screen)
    buf = io.BytesIO()
    im.resize((w, h), Image.LANCZOS).save(buf, "JPEG", quality=quality)
    return buf.getvalue(), (w, h)


def region_jpeg(png, screen, x, y, width, height, quality=90):
    """从原始截图裁出 (x, y, width, height) 这块区域(点),长边不足 600 放大到 600、超过 1200 缩到 1200。

    返回 (jpeg, (x1, y1, 区域宽, 区域高), 放大倍数)。图中像素 (u, v) 对应屏幕点 (x1 + u/倍数, y1 + v/倍数)。
    区域不在屏幕内抛 ValueError。
    """
    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = oriented(im.size, screen)
    x1, y1 = max(0.0, x), max(0.0, y)
    x2, y2 = min(float(w), x + width), min(float(h), y + height)
    if x2 - x1 < 1 or y2 - y1 < 1:
        raise ValueError(f"放大区域不在屏幕内(屏幕 {w}x{h} 点)")
    px = im.width / w  # 每点对应的原图像素,一般是 3
    crop = im.crop((round(x1 * px), round(y1 * px), round(x2 * px), round(y2 * px)))
    long_side = max(crop.size)
    k = 600 / long_side if long_side < 600 else min(1.0, 1200 / long_side)
    if k != 1:
        crop = crop.resize((round(crop.width * k), round(crop.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    crop.save(buf, "JPEG", quality=quality)
    return buf.getvalue(), (x1, y1, x2 - x1, y2 - y1), crop.width / (x2 - x1)


def hid_norm(x, y, screen):
    """点坐标换成 HID 的 0..65535 归一化坐标。"""
    w, h = screen

    def clamp(v):
        return max(0, min(HID_MAX, round(v)))

    return clamp(x / w * HID_MAX), clamp(y / h * HID_MAX)
