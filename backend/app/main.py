from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import routes_datasets, routes_demo, routes_devices, routes_health, routes_machines, websocket
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.database.session import init_db

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(f"{settings.app_name} starting up ({settings.environment})")
    yield
    logger.info(f"{settings.app_name} shutting down")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_machines.router)
app.include_router(routes_datasets.router)
app.include_router(routes_devices.router)
app.include_router(routes_demo.router)
app.include_router(websocket.router)


def mount_frontend(target: FastAPI, directory: Path) -> bool:
    """Serve the built dashboard at "/" on the same origin as the API. Mounted last, so /api and /ws keep priority."""
    if not (directory / "index.html").is_file():
        logger.warning(f"IDEALAB_SERVE_FRONTEND_DIR={directory} has no index.html; serving the API only")
        return False
    target.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
    logger.info(f"Serving the built dashboard from {directory}")
    return True


if settings.serve_frontend_dir is not None:
    mount_frontend(app, settings.serve_frontend_dir)
