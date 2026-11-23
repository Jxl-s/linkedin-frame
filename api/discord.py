import asyncio
import io
import json
import logging
import os
import time

import aiohttp
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from lib.commands import LINKEDIN_GREEN, WEBSITE_URL, parse_color

logger = logging.getLogger(__name__)
MAX_AVATAR_BYTES = 8 * 1024 * 1024
MAX_FRAMES = 120
MAX_PIXELS = 100_000_000


def avatar_url(user, member, guild_id):
    avatar = member.get("avatar") or user.get("avatar")
    if avatar:
        extension = "gif" if avatar.startswith("a_") else "png"
        path = f"avatars/{user['id']}/{avatar}"
        if member.get("avatar") and guild_id:
            path = f"guilds/{guild_id}/users/{user['id']}/avatars/{avatar}"
        return f"https://cdn.discordapp.com/{path}.{extension}?size=1024"
    discriminator = int(user.get("discriminator", 0))
    index = discriminator % 5 if discriminator else (int(user["id"]) >> 22) % 6
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


def render_avatar(data, color, text):
    # Import image libraries after sending the acknowledgment to keep cold starts short.
    from PIL import Image
    from lib.process import process_avatar

    with Image.open(io.BytesIO(data)) as source:
        frames = getattr(source, "n_frames", 1)
        if frames > MAX_FRAMES or source.width * source.height * frames > MAX_PIXELS:
            raise ValueError("Avatar is too large to process; try a shorter or smaller GIF.")
    return process_avatar(data, color, text)


async def complete_interaction(payload, url, color, text, filename):
    import discord

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": f"DiscordBot ({WEBSITE_URL}, 1.0)"}) as session:
        webhook = discord.Webhook.partial(int(payload["application_id"]), payload["token"], session=session)
        mentions = discord.AllowedMentions.none()
        try:
            async with asyncio.timeout(45):
                async with session.get(url) as response:
                    if response.status != 200:
                        raise ValueError("Could not fetch this user's avatar. Please try again.")
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        data.extend(chunk)
                        if len(data) > MAX_AVATAR_BYTES:
                            raise ValueError("Avatar exceeds the 8 MiB input limit.")
                output, extension = await asyncio.to_thread(render_avatar, bytes(data), color, text)
                if len(output) > payload.get("attachment_size_limit", 10 * 1024 * 1024):
                    raise ValueError("The framed image exceeds Discord's upload limit; try a shorter GIF.")
                await webhook.edit_message(
                    "@original",
                    content=f"-# Also available as a web app: {WEBSITE_URL}",
                    attachments=[discord.File(io.BytesIO(output), filename=f"{filename}.{extension}")],
                    allowed_mentions=mentions,
                )
                return
        except ValueError as exc:
            message = str(exc)
        except TimeoutError:
            message = "Avatar processing timed out. Please try a smaller image or shorter GIF."
        except Exception as exc:
            # Do not log exception messages: HTTP exceptions can contain the interaction token.
            logger.error("Discord image processing failed: %s", type(exc).__name__)
            message = "Failed to apply frame. The image may be unsupported or corrupted."
        try:
            async with asyncio.timeout(10):
                await webhook.edit_message("@original", content=message, allowed_mentions=mentions)
        except (discord.HTTPException, aiohttp.ClientError, TimeoutError):
            logger.error("Could not deliver the Discord error reply")


def command_error(message):
    return JSONResponse({"type": 4, "data": {"content": message, "flags": 64, "allowed_mentions": {"parse": []}}})


async def interactions(request: Request):
    public_key = os.environ.get("DISCORD_PUBLIC_KEY")
    if not public_key:
        return Response(status_code=503)
    body = await request.body()
    if len(body) > 65536:
        return Response(status_code=413)
    try:
        timestamp = request.headers["X-Signature-Timestamp"]
        if abs(time.time() - int(timestamp)) > 300:
            return Response(status_code=401)
        signature = bytes.fromhex(request.headers["X-Signature-Ed25519"])
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(signature, timestamp.encode() + body)
    except (KeyError, ValueError, InvalidSignature):
        return Response(status_code=401)
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return Response(status_code=400)
    if not isinstance(payload, dict):
        return Response(status_code=400)
    if payload.get("type") == 1:
        return JSONResponse({"type": 1})
    if payload.get("type") != 2:
        return Response(status_code=400)
    try:
        command = payload["data"]
        name = command["name"]
        if name not in ("frame-custom", "frame-opentowork"):
            return command_error("Unknown command.")
        options = {option["name"]: option["value"] for option in command.get("options", [])}
        user_id = options["user"]
        resolved = command["resolved"]
        user = resolved["users"][user_id]
        member = resolved.get("members", {}).get(user_id, {})
        url = avatar_url(user, member, payload.get("guild_id"))
        color = LINKEDIN_GREEN
        text = "#OPENTOWORK"
        if name == "frame-custom":
            try:
                color = parse_color(options["color"])
            except ValueError:
                return command_error("Invalid color. Use a hex code like `#5865F2`.")
            text = options["text"]
            if not isinstance(text, str) or len(text) > 80:
                return command_error("Arc text must be at most 80 characters.")
        if not payload.get("token") or not payload.get("application_id"):
            return Response(status_code=400)
    except (KeyError, TypeError, ValueError, AttributeError):
        return command_error("Invalid command arguments. Please select a user and try again.")
    filename = "frame" if name == "frame-custom" else "opentowork"
    # ASGI awaits BackgroundTask after sending the deferred response, keeping Vercel's invocation alive.
    return JSONResponse({"type": 5}, background=BackgroundTask(complete_interaction, payload, url, color, text, filename))


app = Starlette(routes=[Route("/api/discord", interactions, methods=["POST"])])
