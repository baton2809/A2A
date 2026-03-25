import time

from fastapi import APIRouter

from ..providers.store import store

router = APIRouter(tags=["infra"])
_started_at = time.time()


@router.get("/health")
async def health():
    providers = await store.all()
    healthy = [p for p in providers if p.healthy]
    return {
        "status": "ok",
        "uptime_s": round(time.time() - _started_at, 1),
        "providers": {
            "total": len(providers),
            "healthy": len(healthy),
        },
    }
