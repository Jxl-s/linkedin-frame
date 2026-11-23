import base64
import binascii
import io
import os
from typing import Annotated

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from PIL import Image as PILImage
from pydantic import Field

from lib.process import process_avatar

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 3 * 1024 * 1024
MAX_FRAMES = 30
MAX_PIXELS = 20_000_000

mcp = MCPServer("LinkedIn Frame")


@mcp.tool()
def frame_avatar(
    image_base64: Annotated[str, Field(max_length=4 * ((MAX_IMAGE_BYTES + 2) // 3))],
    color: Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")] = "#457032",
    text: Annotated[str, Field(max_length=80)] = "#OPENTOWORK",
) -> Image:
    """Add a colored circular frame and arc text to a base64-encoded image.

    Supply raw base64, without a data URL prefix. Returns a PNG, or a GIF for
    animated input. Limit: 2 MiB input, 30 frames, 20 million total input pixels.
    """
    try:
        data = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ToolError("image_base64 must contain valid raw base64.") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise ToolError("Image must be at most 2 MiB.")

    try:
        with PILImage.open(io.BytesIO(data)) as source:
            frames = getattr(source, "n_frames", 1)
            if frames > MAX_FRAMES:
                raise ToolError("Image must have at most 30 frames.")
            if source.width * source.height * frames > MAX_PIXELS:
                raise ToolError("Image exceeds 20 million total pixels.")
        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        output, extension = process_avatar(data, rgb, text)
    except (OSError, ValueError, EOFError, PILImage.DecompressionBombError) as exc:
        raise ToolError("Image is unsupported, corrupted, or too large.") from exc

    # shortcut: inline MCP images must fit Vercel's response limit; use storage for larger results.
    if len(output) > MAX_OUTPUT_BYTES:
        raise ToolError("Result exceeds 3 MiB; use a smaller image or fewer GIF frames.")
    return Image(data=output, format=extension)


hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
hosts += [os.environ[key] for key in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL", "MCP_HOST") if os.environ.get(key)]

app = mcp.streamable_http_app(
    streamable_http_path="/api/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=hosts,
        allowed_origins=[f"https://{host}" for host in hosts] + ["http://localhost:*", "http://127.0.0.1:*"],
    ),
)
