"""A2A task handler for Purple Agent with Redis-backed storage."""
import json
import logging
import os
import uuid

import redis.asyncio as redis

from .agent import process_message, process_message_stream

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_KEY_PREFIX = "purple:tasks"


class TaskHandler:
    """Handles A2A task lifecycle with Redis-backed storage."""

    def __init__(self):
        self._redis: redis.Redis | None = None
        self._local: dict[str, dict] = {}

    async def connect(self):
        """Connect to Redis, fallback to in-memory storage."""
        try:
            self._redis = redis.from_url(REDIS_URL, decode_responses=True)
            await self._redis.ping()
            logger.info("Task handler connected to Redis")
        except Exception:
            logger.warning("Redis unavailable, using in-memory task storage")
            self._redis = None

    async def _save_task(self, task_id: str, task: dict) -> None:
        """Save task to Redis (or local fallback)."""
        if self._redis:
            try:
                await self._redis.set(
                    f"{REDIS_KEY_PREFIX}:{task_id}",
                    json.dumps(task),
                    ex=3600,  # 1 hour TTL
                )
            except Exception:
                logger.warning("Redis write failed, saving locally")
        self._local[task_id] = task

    async def _get_task(self, task_id: str) -> dict | None:
        """Get task from Redis (or local fallback)."""
        if self._redis:
            try:
                data = await self._redis.get(f"{REDIS_KEY_PREFIX}:{task_id}")
                if data:
                    return json.loads(data)
            except Exception:
                pass
        return self._local.get(task_id)

    async def handle_send(self, request: dict) -> dict:
        """Handle tasks/send request."""
        task_id = request.get("id", str(uuid.uuid4()))
        message = self._extract_message(request)

        # Update task state
        working_task = {
            "id": task_id,
            "status": {"state": "working"},
            "history": [],
        }
        await self._save_task(task_id, working_task)

        # Process message
        response = await process_message(message)

        # Complete task
        artifact = {
            "parts": [{"type": "text", "text": response}],
        }

        completed_task = {
            "id": task_id,
            "status": {"state": "completed"},
            "artifacts": [artifact],
            "history": [
                {"role": "user", "parts": [{"type": "text", "text": message}]},
                {"role": "agent", "parts": [{"type": "text", "text": response}]},
            ],
        }
        await self._save_task(task_id, completed_task)

        return completed_task

    async def handle_stream(self, request: dict):
        """Handle tasks/stream request — yields SSE events."""
        task_id = request.get("id", str(uuid.uuid4()))
        message = self._extract_message(request)

        # Send working status
        yield self._sse_event({
            "id": task_id,
            "status": {"state": "working"},
        })

        # Stream response
        full_response = []
        async for chunk in process_message_stream(message):
            full_response.append(chunk)
            yield self._sse_event({
                "id": task_id,
                "artifact": {"parts": [{"type": "text", "text": chunk}], "append": True},
            })

        # Send completed status
        final_text = "".join(full_response)
        completed_task = {
            "id": task_id,
            "status": {"state": "completed"},
            "artifacts": [{"parts": [{"type": "text", "text": final_text}]}],
            "history": [
                {"role": "user", "parts": [{"type": "text", "text": message}]},
                {"role": "agent", "parts": [{"type": "text", "text": final_text}]},
            ],
        }
        await self._save_task(task_id, completed_task)

        yield self._sse_event({
            "id": task_id,
            "status": {"state": "completed"},
            "artifact": {"parts": [{"type": "text", "text": final_text}]},
        })

    async def get_task(self, task_id: str) -> dict | None:
        return await self._get_task(task_id)

    def _extract_message(self, request: dict) -> str:
        """Extract text message from A2A request."""
        message = request.get("message", {})
        parts = message.get("parts", [])
        for part in parts:
            if part.get("type") == "text":
                return part.get("text", "")
        return ""

    def _sse_event(self, data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"


task_handler = TaskHandler()
