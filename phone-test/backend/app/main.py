import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.services.device_manager import device_manager
from app.services.moonraker_client import close_shared_session
from app.vision.ocr_service import ocr_service
from app.api import devices, tasks, templates, calibration, emergency, ws, auth, vision_test, settings_api
from app.api import templates_icons

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await device_manager.init_devices()
    await device_manager.start_heartbeat()

    # Preload PaddleOCR model in a thread to avoid blocking the event loop
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ocr_service._ensure_loaded)
        logging.getLogger(__name__).info("PaddleOCR model preloaded")
    except Exception as e:
        logging.getLogger(__name__).warning("PaddleOCR preload skipped: %s", e)

    logging.getLogger(__name__).info("Server started")
    yield
    # Shutdown
    await device_manager.stop_heartbeat()
    await close_shared_session()
    await engine.dispose()


app = FastAPI(
    title="手机APP自动化测试系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers (templates_icons BEFORE templates to avoid prefix collision)
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(tasks.router)
app.include_router(templates_icons.router)
app.include_router(templates.router)
app.include_router(calibration.router)
app.include_router(emergency.router)
app.include_router(ws.router)
app.include_router(vision_test.router)
app.include_router(settings_api.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
