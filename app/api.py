from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from app.models import ConfigPatch, PositionRequest, PresetCreate, PresetUpdate
from app.runtime import Runtime

router = APIRouter(prefix="/api/v1")


def runtime_from(request: Request) -> Runtime:
    return request.app.state.runtime


def operation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/status")
async def status(request: Request):
    return runtime_from(request).status()


@router.get("/config")
async def config(request: Request):
    return runtime_from(request).config.model_dump()


@router.put("/config")
async def update_config(payload: ConfigPatch, request: Request):
    try:
        return await runtime_from(request).save_config(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/open")
async def open_flap(request: Request):
    return await runtime_from(request).open()


@router.post("/close")
async def close_flap(request: Request):
    try:
        return await runtime_from(request).close()
    except Exception as exc:
        raise operation_error(exc) from exc


@router.post("/stop")
async def stop_flap(request: Request):
    try:
        return await runtime_from(request).stop()
    except Exception as exc:
        raise operation_error(exc) from exc


@router.post("/rotate/left")
async def rotate_left(request: Request):
    runtime = runtime_from(request)
    try:
        return await runtime.position(0, source="UI")
    except Exception as exc:
        raise operation_error(exc) from exc


@router.post("/rotate/right")
async def rotate_right(request: Request):
    runtime = runtime_from(request)
    try:
        return await runtime.position(100, source="UI")
    except Exception as exc:
        raise operation_error(exc) from exc


@router.post("/position")
async def set_position(payload: PositionRequest, request: Request):
    try:
        return await runtime_from(request).position(payload.position)
    except Exception as exc:
        raise operation_error(exc) from exc


@router.post("/calibrate/home")
async def calibrate_home(request: Request):
    return await runtime_from(request).calibrate()


@router.post("/turn_on")
async def turn_on(request: Request):
    try:
        return await runtime_from(request).turn_on()
    except Exception as exc:
        raise operation_error(exc) from exc


@router.post("/turn_off")
async def turn_off(request: Request):
    try:
        return await runtime_from(request).turn_off()
    except Exception as exc:
        raise operation_error(exc) from exc


@router.get("/presets")
async def list_presets(request: Request):
    return await runtime_from(request).list_presets()


@router.post("/presets", status_code=201)
async def create_preset(payload: PresetCreate, request: Request):
    item = await runtime_from(request).database.create_preset(payload.name.strip(), payload.position)
    await runtime_from(request).mqtt.publish_current_state()
    return item


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: int, payload: PresetUpdate, request: Request):
    values = payload.model_dump(exclude_none=True)
    if "name" in values:
        values["name"] = values["name"].strip()
    item = await runtime_from(request).database.update_preset(preset_id, values)
    if not item:
        raise HTTPException(status_code=404, detail="Preset not found")
    await runtime_from(request).mqtt.publish_current_state()
    return item


@router.delete("/presets/{preset_id}", status_code=204)
async def delete_preset(preset_id: int, request: Request):
    if not await runtime_from(request).database.delete_preset(preset_id):
        raise HTTPException(status_code=404, detail="Preset not found")
    await runtime_from(request).mqtt.publish_current_state()
    return Response(status_code=204)


@router.post("/presets/{preset_id}/select")
async def select_preset(preset_id: int, request: Request):
    try:
        return await runtime_from(request).preset(preset_id)
    except Exception as exc:
        raise operation_error(exc) from exc


@router.get("/tv/entities")
async def tv_entities(request: Request):
    return await runtime_from(request).linked_tv_entities()


@router.post("/tv/reconcile")
async def tv_reconcile(request: Request):
    return await runtime_from(request).reconcile_tv()


@router.get("/diagnostics")
async def diagnostics(request: Request):
    runtime = runtime_from(request)
    return {
        "status": runtime.status(),
        "profile": runtime.profile,
        "persisted_state": runtime.state,
        "logs": await runtime.database.recent_logs(),
        "tv_entities": await runtime.linked_tv_entities(),
    }


@router.get("/diagnostics/export")
async def diagnostics_export(request: Request):
    runtime = runtime_from(request)
    data = await diagnostics(request)
    import json

    return PlainTextResponse(json.dumps(data, ensure_ascii=False, indent=2, default=str), media_type="application/json")


@router.post("/diagnostics/connection")
async def test_connection(request: Request):
    return await runtime_from(request).driver.test_connection()


@router.post("/diagnostics/ir/{action}")
async def test_ir(action: str, request: Request):
    if action not in {"open", "close", "stop", "left", "right"}:
        raise HTTPException(status_code=404, detail="Unknown IR action")
    try:
        result = await runtime_from(request)._send_ir(action, source="DIAGNOSTIC")
        return result
    except Exception as exc:
        raise operation_error(exc) from exc

