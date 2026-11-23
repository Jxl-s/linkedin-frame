import io
from PIL import Image, ImageSequence

from .frame import apply_frame
from .text import apply_arc_text


def _process_frame(frame: Image.Image, color: tuple, text: str, size: int) -> Image.Image:
    result = apply_arc_text(apply_frame(frame, color), text)
    return result.resize((size, size), Image.Resampling.LANCZOS)


def process_avatar(avatar_bytes: bytes, color: tuple, text: str) -> tuple[bytes, str]:
    """
    Apply frame color and arc text to an avatar.
    Handles both static images (returns PNG) and animated GIFs (returns GIF).
    Output is a centered square with side min(original width, original height).
    Returns (output_bytes, file_extension).
    """
    src = Image.open(io.BytesIO(avatar_bytes))
    size = min(src.size)

    if getattr(src, "n_frames", 1) == 1:
        result = _process_frame(src, color, text, size)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue(), "png"

    frames = []
    durations = []
    for frame in ImageSequence.Iterator(src):
        durations.append(frame.info.get("duration", 100))
        processed = _process_frame(frame.copy(), color, text, size)
        # GIF doesn't support full alpha — composite onto black before quantizing
        bg = Image.new("RGBA", processed.size, (0, 0, 0, 255))
        rgb = Image.alpha_composite(bg, processed).convert("RGB")
        frames.append(rgb.quantize(colors=256))

    if not frames:
        raise ValueError("GIF contained no frames")

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )
    return buf.getvalue(), "gif"
