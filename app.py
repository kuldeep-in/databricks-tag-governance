from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from server.routes import tables, apply, config


@asynccontextmanager
async def lifespan(app_instance):
    from server.config_store import reload_config
    try:
        reload_config()
        print("Config loaded from table.")
    except Exception as e:
        print(f"Startup: could not load config: {e}")
    yield

app = FastAPI(title="UC Tag Governance", lifespan=lifespan)

app.include_router(tables.router, prefix="/api")
app.include_router(apply.router,  prefix="/api")
app.include_router(config.router, prefix="/api")

# Serve React frontend (built into frontend/dist)
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dir):
    assets_dir = os.path.join(frontend_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(os.path.join(frontend_dir, "index.html"))
