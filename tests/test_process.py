import io
import unittest

from PIL import Image, ImageDraw, ImageSequence

from lib.process import process_avatar


class ProcessTests(unittest.TestCase):
    def test_png_and_gif_center_crop_at_original_size(self):
        for width, height in ((320, 320), (640, 160), (160, 640), (321, 180)):
            size = min(width, height)
            left, top = (width - size) // 2, (height - size) // 2
            for animated in (False, True):
                with self.subTest(size=(width, height), animated=animated):
                    frames = []
                    colors = [(0, 200, 0), (0, 0, 200), (200, 200, 0)] if animated else [(0, 200, 0)]
                    for color in colors:
                        frame = Image.new("RGB", (width, height), "red")
                        ImageDraw.Draw(frame).rectangle((left, top, left + size - 1, top + size - 1), fill=color)
                        frames.append(frame)
                    source = io.BytesIO()
                    if animated:
                        frames[0].save(source, format="GIF", save_all=True, append_images=frames[1:], duration=[40, 80, 120], loop=0)
                    else:
                        frames[0].save(source, format="PNG")
                    data, extension = process_avatar(source.getvalue(), (69, 112, 50), "")
                    self.assertEqual(extension, "gif" if animated else "png")
                    with Image.open(io.BytesIO(data)) as output:
                        self.assertEqual(output.size, (size, size))
                        self.assertEqual(getattr(output, "n_frames", 1), len(frames))
                        if animated:
                            self.assertEqual(output.info["loop"], 0)
                        for index, frame in enumerate(ImageSequence.Iterator(output)):
                            if animated:
                                self.assertEqual(frame.info["duration"], [40, 80, 120][index])
                            pixel = frame.convert("RGB").getpixel((size // 5, size // 2))
                            for actual, expected in zip(pixel, colors[index]):
                                self.assertAlmostEqual(actual, expected, delta=3)


if __name__ == "__main__":
    unittest.main()
