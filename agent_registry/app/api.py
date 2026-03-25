"""REST API реестра A2A-агентов."""
from fastapi import APIRouter, HTTPException
from fastapi.params import Query

from .models import RegisterRequest
from .registry import registry

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents():
    agents = await registry.list_all()
    return {"agents": [a.model_dump() for a in agents], "total": len(agents)}


@router.get("/search")
async def search_agents(
    skill: str | None = Query(None, description="Фильтр по имени/описанию навыка"),
    tag: str | None = Query(None, description="Фильтр по тегу навыка"),
):
    results = await registry.search(skill=skill, tag=tag)
    return {"agents": [a.model_dump() for a in results], "total": len(results)}


@router.post("", status_code=201)
async def register_agent(req: RegisterRequest):
    await registry.add(req.agent_card)
    return {"ok": True, "name": req.agent_card.name}


@router.get("/{name}")
async def get_agent(name: str):
    agent = await registry.get(name)
    if not agent:
        raise HTTPException(404, f"Agent '{name}' not found")
    return agent.model_dump()


@router.delete("/{name}")
async def delete_agent(name: str):
    removed = await registry.remove(name)
    if not removed:
        raise HTTPException(404, f"Agent '{name}' not found")
    return {"ok": True, "name": name}
