from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import FileResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from api.discord import app as discord_app
from api.mcp import app as mcp_app

ROOT = Path(__file__).parent


async def homepage(request):
    return FileResponse(ROOT / "index.html")


app = Starlette(
    routes=[
        Route("/", homepage),
        *discord_app.routes,
        Mount("/js", StaticFiles(directory=ROOT / "js")),
        Mount("/assets", StaticFiles(directory=ROOT / "assets")),
        Mount("/", mcp_app),
    ],
    lifespan=mcp_app.router.lifespan_context,
)
