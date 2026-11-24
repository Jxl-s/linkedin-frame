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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

from lib.process import process_avatar

MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
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
    animated input. Limits: 3 MiB input, 10 MiB output, 30 frames,
    and 20 million total input pixels.
    """
    try:
        data = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ToolError("image_base64 must contain valid raw base64.") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise ToolError("Image must be at most 3 MiB.")

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

    if len(output) > MAX_OUTPUT_BYTES:
        raise ToolError("Result exceeds 10 MiB; use a smaller image or fewer GIF frames.")
    return Image(data=output, format=extension)


async def stream_response(request, call_next):
    # Keep JSON for clients with small SSE-event limits; stream past Vercel's buffered response limit.
    response = await call_next(request)
    if "content-length" in response.headers:
        del response.headers["content-length"]

    async def chunks():
        async for body in response.body_iterator:
            for start in range(0, len(body), 64 * 1024):
                yield body[start:start + 64 * 1024]

    return StreamingResponse(chunks(), status_code=response.status_code, headers=response.headers)


hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
hosts += [os.environ[key] for key in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL", "MCP_HOST") if os.environ.get(key)]

app = mcp.streamable_http_app(
    streamable_http_path="/api/mcp",
    stateless_http=True,
    json_response=True,
    max_request_body_size=4 * ((MAX_IMAGE_BYTES + 2) // 3) + 16 * 1024,
    transport_security=TransportSecuritySettings(
        allowed_hosts=hosts,
        allowed_origins=[f"https://{host}" for host in hosts] + ["http://localhost:*", "http://127.0.0.1:*"],
    ),
)
app.add_middleware(BaseHTTPMiddleware, dispatch=stream_response)
