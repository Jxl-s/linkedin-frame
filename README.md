# linkedin-frame

Apply LinkedIn-style circular frames with custom arc text to profile pictures — as a **Discord bot**, a **browser-based web app**, and a **serverless MCP tool** hosted on Vercel.

Supports both static images and animated GIFs.

<img src=".github/images/example.webp" width="300"/> <img src=".github/images/example2.webp" width="300"/>

## Web app

**https://discord-linkedin-frame.vercel.app/**

Upload any image or GIF, pick a color and arc text, and download the result.

## MCP server

Connect an MCP client using Streamable HTTP at **https://discord-linkedin-frame.vercel.app/api/mcp**.

The `frame_avatar` tool calls the existing `lib.process.process_avatar` function:

| Argument | Description |
|-----------|-------------|
| `image_base64` | Required raw base64 image bytes, without a `data:` URL prefix |
| `color` | Six-digit hex color, default `#457032` |
| `text` | Arc text (up to 80 characters), default `#OPENTOWORK` |

The result is MCP image content: PNG for static images, GIF for animated images.
Inputs are limited to 2 MiB, 30 frames, and 20 million total pixels; output is
limited to 3 MiB before base64 encoding. Images are processed in memory without
being stored. The endpoint is public and does not require authentication.

### Deploy to Vercel

Import this repository with the **Other** framework preset, or run:

```bash
vercel --prod
```

`vercel.json` copies only the web app's HTML, JavaScript, and assets into the
static output directory and deploys `api/mcp.py` as a Python 3.12 function.
No environment variables are required for the website or MCP server. The Discord
bot continues to run separately; do not add its `DISCORD_TOKEN` to Vercel.

For local MCP development and tests, after installing the dependencies below:

```bash
.venv/bin/python -m uvicorn api.mcp:app --reload
.venv/bin/python -m unittest discover -s tests -v
```

The local endpoint is `http://localhost:8000/api/mcp`.

## Discord bot

### Commands

#### `/frame-custom`
Apply a custom-colored frame with custom arc text to a user's profile picture.

| Parameter | Description |
|-----------|-------------|
| `user` | The Discord member whose profile picture to use |
| `color` | Frame color as a hex code (e.g. `#5865F2`) |
| `text` | Text to display on the arc |

#### `/frame-opentowork`
Apply the LinkedIn `#OPENTOWORK` frame (green, `#457032`) to a user's profile picture.

| Parameter | Description |
|-----------|-------------|
| `user` | The Discord member whose profile picture to use |

### Setup

#### Docker (recommended)

**1. Create a `.env` file:**
```
DISCORD_TOKEN=your_bot_token_here
```

**2. Run with Docker Compose:**
```bash
docker compose up -d
```

This starts both the Discord bot and an nginx web server for the web app on port `8080`.

#### Manual

**1. Install dependencies**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**2. Configure environment**

Create a `.env` file at the project root:
```
DISCORD_TOKEN=your_bot_token_here
```

**3. Run**
```bash
.venv/bin/python3 main.py
```

Slash commands are synced globally on startup.

## Project structure

```
main.py           # Discord bot entry point and slash commands
lib/
  frame.py        # Applies colored ring frame using assets/alpha.png
  text.py         # Renders text along a circular arc
  process.py      # Combines frame + text, handles static and animated GIFs
assets/
  alpha.png       # Frame alpha mask (grayscale: white = frame, black = avatar)
  Carlito-Bold.ttf
index.html        # Web app
js/
  app.js          # Web app logic (mirrors lib/ in the browser)
  vendor/         # gif.js, gif.worker.js, omggif.js
api/mcp.py        # Stateless Streamable HTTP MCP server, reuses lib/process.py
vercel.json       # Static web output and Python function configuration
tests/test_mcp.py # MCP transport, image output, and validation tests
```
