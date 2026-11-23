from pathlib import Path
from PIL import Image, ImageOps
import numpy as np

ALPHA_PATH = Path(__file__).parent.parent / "assets" / "alpha.png"
if not ALPHA_PATH.exists():
    raise FileNotFoundError(f"Required asset not found: {ALPHA_PATH}")


def apply_frame(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """
    Composite a colored frame onto a square image using assets/alpha.png.

    alpha.png is a grayscale image used as the frame's alpha mask:
    255 = fully opaque frame color, 0 = fully transparent (shows original image).
    The image is center-cropped to a square, then resized to match alpha.png.
    Returns an RGBA image.
    """
    alpha_img = Image.open(ALPHA_PATH).convert("L")
    w, h = alpha_img.size

    base = ImageOps.fit(image.convert("RGBA"), (w, h), method=Image.Resampling.LANCZOS)

    red_channel = np.array(alpha_img)  # shape (h, w), values 0-255

    # Build the frame layer: solid color with alpha = red channel
    r, g, b = color
    frame_arr = np.zeros((h, w, 4), dtype=np.uint8)
    frame_arr[:, :, 0] = r
    frame_arr[:, :, 1] = g
    frame_arr[:, :, 2] = b
    frame_arr[:, :, 3] = red_channel

    frame_layer = Image.fromarray(frame_arr, mode="RGBA")

    result = Image.alpha_composite(base, frame_layer)
    return result
