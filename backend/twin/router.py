"""Version 2 routes. Legacy HTTP contracts remain in backend.api.main."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Body, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from .laptop1 import Laptop1TelemetryClient
from .schemas import Controls, DemoReset, OperatorDecisionSubmission, ReplayControl, Telemetry, TelemetrySourceSelection, WhatIf
from .service import TwinService
from .storage import settings_from_env
from .telemetry_sources import TelemetrySources

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2", tags=["Digital Twin V2"])


@asynccontextmanager
async def lifespan(app):
    storage = settings_from_env()
    service = TwinService(
        storage.database,
        encryption_required=storage.encryption_required,
        database_key=storage.key,
    )
    app.state.twin = service
    app.state.twin_error = None
    laptop1_client = Laptop1TelemetryClient()
    app.state.laptop1_telemetry = laptop1_client
    sources = TelemetrySources(laptop1_client, os.getenv("SKYNEX_DATA_SOURCE", "LIVE_LAPTOP1"))
    app.state.telemetry_sources = sources
    sources.start()

    async def loop():
        while True:
            try:
                if sources.mode == "LIVE_LAPTOP1":
                    await asyncio.to_thread(service.tick)
                else:
                    await asyncio.to_thread(sources.replay.snapshot)
                app.state.twin_error = None
            except Exception:
                logger.exception("Digital twin tick failed")
                app.state.twin_error = "Simulation or persistence unavailable"
            await asyncio.sleep(0.1 if sources.mode == "OFFLINE_REPLAY" else 1)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await laptop1_client.stop()
        service.close()


@router.get("/health")
def health(request: Request):
    if request.app.state.twin_error:
        raise HTTPException(503, request.app.state.twin_error)
    return {"status": "ok", "version": "2.0.0", "engine_id": "VAYU-01"}


@router.get("/twin")
def twin(request: Request):
    return request.app.state.twin.snapshot()


@router.get("/laptop1")
def laptop1_telemetry(request: Request):
    return request.app.state.laptop1_telemetry.snapshot()


@router.get("/telemetry/source")
def current_source(request: Request):
    return request.app.state.telemetry_sources.snapshot()


@router.post("/telemetry/source")
async def select_source(body: TelemetrySourceSelection, request: Request):
    return await request.app.state.telemetry_sources.select(body.mode)


@router.get("/replay")
def offline_replay(request: Request):
    replay = request.app.state.telemetry_sources.replay
    return {**replay.snapshot(), "scenarios": replay.catalogue()}


@router.post("/replay/control")
async def replay_control(body: ReplayControl, request: Request):
    sources = request.app.state.telemetry_sources
    async with sources.switch_lock:
        if sources.mode != "OFFLINE_REPLAY":
            raise HTTPException(409, "Select OFFLINE_REPLAY before using replay controls.")
        try:
            return sources.replay.control(body.action, scenario=body.scenario, speed=body.speed)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error


@router.post("/recommendations/current")
def record_current_recommendation(request: Request):
    return {
        "recommendation": request.app.state.twin.record_current_recommendation(
            request.app.state.twin.snapshot()
        )
    }


@router.get("/recommendations/pending")
def pending_recommendations(
    request: Request, limit: int = Query(default=100, ge=1, le=500)
):
    return {
        "recommendations": request.app.state.twin.pending_recommendations(limit)
    }


@router.post("/recommendations/evaluate")
def evaluate_recommendations(request: Request):
    """Evaluate server-owned evidence and persist advisories; never send commands."""
    return request.app.state.twin.scenario_recommendations(
        request.app.state.telemetry_sources.snapshot()
    )


@router.post("/recommendations/intelligence")
def evaluate_intelligence_recommendations(
    request: Request,
    bundle: dict = Body(...),
):
    """Persist externally assessed Phase 2–5 evidence as advisory recommendations."""
    return request.app.state.twin.intelligence_recommendations(bundle)


@router.post("/recommendations/{recommendation_id}/decision")
def decide_recommendation(
    recommendation_id: str,
    body: OperatorDecisionSubmission,
    request: Request,
):
    try:
        return request.app.state.twin.decide_recommendation(
            recommendation_id, body.status, body.operator_comment
        )
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/decisions/history")
def decision_history(
    request: Request, limit: int = Query(default=200, ge=1, le=1000)
):
    return {"history": request.app.state.twin.decision_history(limit)}


@router.get("/history")
def history(request: Request, limit: int = Query(default=180, ge=1, le=3600)):
    return {"history": request.app.state.twin.history(limit)}


@router.get("/fleet")
def fleet(request: Request):
    return request.app.state.twin.fleet_snapshot()


@router.get("/missions")
def missions(request: Request, limit: int = Query(default=24, ge=1, le=200)):
    return {"missions": request.app.state.twin.missions(limit)}


@router.get("/fault-history")
def fault_history(request: Request, limit: int = Query(default=180, ge=1, le=3600)):
    return {"fault_history": request.app.state.twin.fault_history(limit)}


@router.get("/missions/{mission_id}/replay")
def mission_replay(mission_id: str, request: Request):
    # The time-indexed snapshot stream is directly consumable by existing replay controls.
    return {"mission_id": mission_id, "history": request.app.state.twin.history(3600)}


@router.post("/controls")
def controls(body: Controls, request: Request):
    return request.app.state.twin.configure(body)


@router.post("/demo/reset")
def demo_reset(body: DemoReset, request: Request):
    try:
        return request.app.state.twin.reset_demo(body.scenario)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/telemetry")
def telemetry(body: Telemetry, request: Request):
    try:
        return request.app.state.twin.ingest(body)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/what-if")
def what_if(body: WhatIf, request: Request):
    return request.app.state.twin.what_if(body)


@router.get("/report")
def report(request: Request):
    service = request.app.state.twin
    with service.lock:
        return {"report_type": "SIH26054 engine condition report", "snapshot": service.snapshot(),
                "history": service.history(180),
                "validation_status": "Synthetic prototype. No fleet-calibrated RUL or failure probabilities."}


@router.websocket("/stream")
async def stream(socket: WebSocket):
    # Browser WebSocket requests bypass HTTP CORS; enforce the origin here too.
    allowed = os.getenv("TWIN_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173").split(",")
    origin = socket.headers.get("origin")
    if origin and "*" not in allowed and origin not in allowed:
        await socket.close(code=1008)
        return
    await socket.accept()
    try:
        while True:
            await socket.send_json(socket.app.state.twin.snapshot())
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        pass
