import asyncio
import copy
import io
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image
from starlette.testclient import TestClient

from api.discord import app, avatar_url, complete_interaction, interactions, render_avatar
from lib.commands import LINKEDIN_GREEN, parse_color

PAYLOAD = {
    "type": 2,
    "application_id": "1507578558040768522",
    "token": "test-token",
    "guild_id": "123",
    "data": {
        "name": "frame-opentowork",
        "options": [{"name": "user", "value": "456"}],
        "resolved": {"users": {"456": {"id": "456", "avatar": "avatar-hash", "discriminator": "0"}}},
    },
}


class DiscordEndpointTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.environment = patch.dict(os.environ, {"DISCORD_PUBLIC_KEY": self.key.public_key().public_bytes_raw().hex()})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = TestClient(app)

    def signed(self, payload, timestamp=None):
        body = json.dumps(payload).encode()
        timestamp = str(int(time.time())) if timestamp is None else timestamp
        return body, {
            "X-Signature-Timestamp": timestamp,
            "X-Signature-Ed25519": self.key.sign(timestamp.encode() + body).hex(),
            "Content-Type": "application/json",
        }

    def post(self, payload):
        body, headers = self.signed(payload)
        return self.client.post("/api/discord", content=body, headers=headers)

    def test_signed_ping(self):
        response = self.post({"type": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"type": 1})

    def test_bad_signatures_and_replays_are_rejected(self):
        body, headers = self.signed({"type": 1})
        old_body, old_headers = self.signed({"type": 1}, str(int(time.time()) - 301))
        for content, request_headers in (
            (body, {}),
            (body + b" ", headers),
            (old_body, old_headers),
            (body, {**headers, "X-Signature-Ed25519": "not-hex"}),
            (body, {**headers, "X-Signature-Timestamp": "invalid"}),
        ):
            self.assertEqual(self.client.post("/api/discord", content=content, headers=request_headers).status_code, 401)

    def test_missing_public_key_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.post({"type": 1}).status_code, 503)

    def test_both_commands_dispatch(self):
        for custom in (False, True):
            payload = copy.deepcopy(PAYLOAD)
            if custom:
                payload["data"]["name"] = "frame-custom"
                payload["data"]["options"] += [{"name": "color", "value": "#5865F2"}, {"name": "text", "value": "Hello"}]
            with patch("api.discord.complete_interaction", new_callable=AsyncMock) as complete:
                response = self.post(payload)
                self.assertEqual(response.json(), {"type": 5})
                complete.assert_awaited_once_with(
                    payload, "https://cdn.discordapp.com/avatars/456/avatar-hash.png?size=1024",
                    (88, 101, 242) if custom else LINKEDIN_GREEN,
                    "Hello" if custom else "#OPENTOWORK", "frame" if custom else "opentowork",
                )

    def test_invalid_arguments_do_not_start_work(self):
        payloads = []
        for color, text in (("red", "Hello"), ("#457032", "x" * 81)):
            payload = copy.deepcopy(PAYLOAD)
            payload["data"]["name"] = "frame-custom"
            payload["data"]["options"] += [{"name": "color", "value": color}, {"name": "text", "value": text}]
            payloads.append(payload)
        missing = copy.deepcopy(PAYLOAD)
        missing["data"]["resolved"] = {}
        payloads.append(missing)
        with patch("api.discord.complete_interaction", new_callable=AsyncMock) as complete:
            for payload in payloads:
                result = self.post(payload).json()
                self.assertEqual(result["type"], 4)
                self.assertEqual(result["data"]["flags"], 64)
            complete.assert_not_awaited()

    def test_acknowledgment_is_sent_before_processing(self):
        from starlette.requests import Request

        async def check():
            body, headers = self.signed(PAYLOAD)
            sent = []
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}
            async def send(message):
                sent.append(message)
            async def complete(*args):
                self.assertEqual(sent[-1]["type"], "http.response.body")
                self.assertEqual(json.loads(sent[-1]["body"]), {"type": 5})
            scope = {"type": "http", "method": "POST", "path": "/api/discord", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
            with patch("api.discord.complete_interaction", side_effect=complete):
                response = await interactions(Request(scope, receive))
                await response(scope, receive, send)
        asyncio.run(check())

    def test_avatar_variants_and_colors(self):
        user = {"id": "456", "avatar": "a_global", "discriminator": "0"}
        self.assertIn("/avatars/456/a_global.gif?", avatar_url(user, {}, None))
        self.assertIn("/guilds/123/users/456/avatars/a_guild.gif?", avatar_url(user, {"avatar": "a_guild"}, "123"))
        self.assertEqual(avatar_url({"id": str(5 << 22), "discriminator": "0"}, {}, None), "https://cdn.discordapp.com/embed/avatars/5.png")
        self.assertEqual(avatar_url({"id": "456", "discriminator": "1234"}, {}, None), "https://cdn.discordapp.com/embed/avatars/4.png")
        self.assertEqual(parse_color("#5865F2"), (88, 101, 242))


class AvatarResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def iter_chunked(self, size):
        yield self.data


class DiscordCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_png_and_gif_are_uploaded_to_original_response(self):
        for animated in (False, True):
            frames = [Image.new("RGB", (16, 16), color) for color in ("red", "blue")]
            buffer = io.BytesIO()
            if animated:
                frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=100)
            else:
                frames[0].save(buffer, format="PNG")
            session = MagicMock()
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock()
            session.get.return_value = AvatarResponse(buffer.getvalue())
            webhook = MagicMock(edit_message=AsyncMock())
            with patch("api.discord.aiohttp.ClientSession", return_value=session), patch("discord.Webhook.partial", return_value=webhook):
                await complete_interaction(PAYLOAD, "https://cdn.discordapp.com/test.png", LINKEDIN_GREEN, "Hello", "frame")
            webhook.edit_message.assert_awaited_once()
            args, kwargs = webhook.edit_message.call_args
            self.assertEqual(args, ("@original",))
            file = kwargs["attachments"][0]
            self.assertEqual(file.filename, "frame.gif" if animated else "frame.png")
            with Image.open(file.fp) as output:
                self.assertEqual(output.size, (800, 800))
                self.assertEqual(getattr(output, "n_frames", 1), 2 if animated else 1)
            self.assertFalse(kwargs["allowed_mentions"].everyone)
            file.close()

    async def test_fetch_failure_replies_with_error(self):
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock()
        session.get.return_value = AvatarResponse(b"", 404)
        webhook = MagicMock(edit_message=AsyncMock())
        with patch("api.discord.aiohttp.ClientSession", return_value=session), patch("discord.Webhook.partial", return_value=webhook):
            await complete_interaction(PAYLOAD, "https://cdn.discordapp.com/test.png", LINKEDIN_GREEN, "Hello", "frame")
        self.assertIn("Could not fetch", webhook.edit_message.call_args.kwargs["content"])
        self.assertNotIn("attachments", webhook.edit_message.call_args.kwargs)

    def test_large_gif_is_rejected_before_rendering(self):
        source = MagicMock(n_frames=121)
        source.__enter__.return_value = source
        with patch("PIL.Image.open", return_value=source):
            with self.assertRaisesRegex(ValueError, "too large"):
                render_avatar(b"image", LINKEDIN_GREEN, "Hello")


if __name__ == "__main__":
    unittest.main()
