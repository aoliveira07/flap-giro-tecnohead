from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.runtime import Runtime
from app.settings import app_version, data_dir, load_options


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = Runtime(data_dir(), app_version(), initial_config=load_options())
    app.state.runtime = runtime
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()


app = FastAPI(
    title="Flap de Giro Tecnohead",
    version=app_version(),
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health")
async def health():
    runtime: Runtime = app.state.runtime
    return {"ok": True, "version": runtime.version, "operation_active": runtime.status()["operation_active"]}


web_dir = Path(__file__).resolve().parents[1] / "web"
app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(web_dir / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8100)

