# discord-linkedin-frame

A Discord bot that applies LinkedIn-style circular frames with arc text to user profile pictures. Supports both static images and animated GIFs.

## Commands

### `/frame-custom`
Apply a custom-colored frame with custom arc text to a user's profile picture.

| Parameter | Description |
|-----------|-------------|
| `user` | The Discord member whose profile picture to use |
| `color` | Frame color as a hex code (e.g. `#5865F2`) |
| `text` | Text to display on the arc |

### `/frame-opentowork`
Apply the LinkedIn `#OPENTOWORK` frame (green, `#457032`) to a user's profile picture.

| Parameter | Description |
|-----------|-------------|
| `user` | The Discord member whose profile picture to use |

## Setup

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
main.py           # Bot entry point and slash commands
lib/
  frame.py        # Applies colored ring frame using assets/alpha.png
  text.py         # Renders text along a circular arc
  process.py      # Combines frame + text, handles static and animated avatars
assets/
  alpha.png       # Frame alpha mask (red channel = opacity)
  Carlito-Bold.ttf
```
