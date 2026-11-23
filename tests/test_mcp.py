import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image
from starlette.testclient import TestClient

from api.mcp import MAX_IMAGE_BYTES, MAX_OUTPUT_BYTES
from docker_app import app


def image_base64(animated=False, frames=2):
    images = [Image.new("RGB", (16, 16), (i, 100, 200)) for i in range(frames)]
    buffer = io.BytesIO()
    if animated:
        images[0].save(buffer, format="GIF", save_all=True, append_images=images[1:], duration=100, loop=0)
    else:
        images[0].save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


class MCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, base_url="http://localhost:8000")
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def rpc(self, method, params):
        response = self.client.post(
            "/api/mcp",
            headers={"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"},
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("mcp-session-id", response.headers)
        return response.json()["result"]

    def call(self, **arguments):
        return self.rpc("tools/call", {"name": "frame_avatar", "arguments": arguments})

    def test_website_and_assets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("LinkedIn Frame Generator", response.text)
        for path in ("/js/app.js", "/js/vendor/gif.worker.js", "/assets/alpha.png", "/assets/Carlito-Bold.ttf"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_source_and_secrets_are_not_served(self):
        for path in ("/.env", "/.git/config", "/main.py", "/api/discord.py", "/requirements.txt"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_discord_endpoint_is_available(self):
        with patch.dict("os.environ", {"DISCORD_PUBLIC_KEY": "0" * 64}):
            response = self.client.post("/api/discord", json={"type": 1})
        self.assertEqual(response.status_code, 401)

    def test_initialize_and_discover(self):
        result = self.rpc("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        })
        self.assertEqual(result["serverInfo"]["name"], "LinkedIn Frame")
        tools = self.rpc("tools/list", {})["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["frame_avatar"])

    def test_png_and_gif(self):
        expected_size = (16, 16)
        for animated, extension in ((False, "png"), (True, "gif")):
            with self.subTest(extension=extension):
                result = self.call(image_base64=image_base64(animated), color="#5865F2", text="Hello")
                self.assertFalse(result.get("isError"), result)
                content = result["content"][0]
                self.assertEqual(content["mimeType"], f"image/{extension}")
                with Image.open(io.BytesIO(base64.b64decode(content["data"]))) as output:
                    self.assertEqual(output.size, expected_size)
                    self.assertEqual(output.format.lower(), extension)
                    self.assertEqual(getattr(output, "n_frames", 1), 2 if animated else 1)

    def test_bad_input_is_tool_error(self):
        valid = image_base64()
        for arguments in (
            {"image_base64": "!!!"},
            {"image_base64": base64.b64encode(b"not an image").decode()},
            {"image_base64": valid, "color": "red"},
            {"image_base64": valid, "text": "x" * 81},
            {"image_base64": base64.b64encode(b"x" * (MAX_IMAGE_BYTES + 1)).decode()},
            {"image_base64": image_base64(True, 31)},
        ):
            with self.subTest(fields=list(arguments)):
                self.assertTrue(self.call(**arguments)["isError"])

    def test_oversized_result_is_tool_error(self):
        with patch("api.mcp.process_avatar", return_value=(b"x" * (MAX_OUTPUT_BYTES + 1), "png")):
            self.assertTrue(self.call(image_base64=image_base64())["isError"])

    def test_rejects_foreign_host_and_origin(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}):
            response = self.client.post("/api/mcp", headers=headers, json={})
            self.assertIn(response.status_code, (403, 421))


if __name__ == "__main__":
    unittest.main()
