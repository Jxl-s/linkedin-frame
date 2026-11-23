LINKEDIN_GREEN = (69, 112, 50)  # #457032
WEBSITE_URL = "https://linkedin-frame.vercel.app/"


def parse_color(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Expected 6 hex digits, got {len(hex_color)}")
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
