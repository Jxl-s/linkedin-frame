import io
import os
import discord
from dotenv import load_dotenv
from discord import app_commands

from lib.process import process_avatar

load_dotenv()
TOKEN = os.environ["DISCORD_TOKEN"]
LINKEDIN_GREEN = (69, 112, 50)  # #457032
WEBSITE_URL = "https://discord-linkedin-frame.vercel.app/"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def parse_color(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Expected 6 hex digits, got {len(hex_color)}")
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)


async def fetch_avatar(user: discord.User) -> bytes:
    animated = user.display_avatar.is_animated()
    fmt = "gif" if animated else "png"
    return await user.display_avatar.replace(size=1024, format=fmt).read()


@client.event
async def on_ready():
    try:
        await tree.sync()
    except Exception as e:
        print(f"Failed to sync command tree: {e}")
    print(f"Logged in as {client.user}")


@tree.command(name="frame-custom", description="Apply a custom frame to a user's profile picture")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    user="The user whose profile picture to use",
    color="Frame color as a hex code (e.g. #5865F2)",
    text="Text to display on the arc",
)
async def frame_command(interaction: discord.Interaction, user: discord.User, color: str, text: str):
    await interaction.response.defer()
    print(f"[frame-custom] {interaction.user} → target={user} color={color} text={text!r}")

    try:
        color_rgb = parse_color(color)
    except Exception:
        await interaction.followup.send("Invalid color. Use a hex code like `#5865F2`.")
        return

    try:
        avatar_bytes = await fetch_avatar(user)
    except discord.HTTPException as e:
        await interaction.followup.send(f"Could not fetch avatar for {user.mention}: {e}")
        return

    try:
        data, ext = process_avatar(avatar_bytes, color_rgb, text)
    except Exception as e:
        print(f"[frame-custom] processing error: {e}")
        await interaction.followup.send("Failed to apply frame. The image may be unsupported or corrupted.")
        return

    await interaction.followup.send(
        content=f"-# Also available as a web app: {WEBSITE_URL}",
        file=discord.File(io.BytesIO(data), filename=f"frame.{ext}"),
    )
    print(f"[frame-custom] done → {ext}")


@tree.command(name="frame-opentowork", description="Add the #OPENTOWORK LinkedIn frame to a user's profile picture")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(user="The user whose profile picture to use")
async def opentowork_command(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer()
    print(f"[frame-opentowork] {interaction.user} → target={user}")

    try:
        avatar_bytes = await fetch_avatar(user)
    except discord.HTTPException as e:
        await interaction.followup.send(f"Could not fetch avatar for {user.mention}: {e}")
        return

    try:
        data, ext = process_avatar(avatar_bytes, LINKEDIN_GREEN, "#OPENTOWORK")
    except Exception as e:
        print(f"[frame-opentowork] processing error: {e}")
        await interaction.followup.send("Failed to apply frame. The image may be unsupported or corrupted.")
        return

    await interaction.followup.send(
        content=f"-# Also available as a web app: {WEBSITE_URL}",
        file=discord.File(io.BytesIO(data), filename=f"opentowork.{ext}"),
    )
    print(f"[frame-opentowork] done → {ext}")


client.run(TOKEN)
