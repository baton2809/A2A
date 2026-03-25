"""Purple Agent — A2A compatible agent server."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .agent_card import AGENT_CARD
from .handler import task_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Purple Agent", version="1.0.0")


@app.on_event("startup")
async def startup():
    await task_handler.connect()


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "purple-agent"}


@app.get("/.well-known/agent-card.json")
async def agent_card():
    """A2A Agent Card endpoint."""
    return JSONResponse(AGENT_CARD)


@app.post("/tasks/send")
async def tasks_send(request: Request):
    """A2A tasks/send — synchronous task execution."""
    body = await request.json()
    result = await task_handler.handle_send(body)
    return JSONResponse(result)


@app.post("/tasks/stream")
async def tasks_stream(request: Request):
    """A2A tasks/stream — streaming task execution."""
    body = await request.json()
    return StreamingResponse(
        task_handler.handle_stream(body),
        media_type="text/event-stream",
    )


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status and result."""
    task = await task_handler.get_task(task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return JSONResponse(task)
