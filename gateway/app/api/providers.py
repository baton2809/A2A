from fastapi import APIRouter, HTTPException

from ..providers.schema import LLMProvider, ProviderIn
from ..providers.store import store

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
async def list_providers():
    providers = await store.all()
    return {"items": [p.model_dump() for p in providers], "total": len(providers)}


@router.post("", status_code=201)
async def add_provider(body: ProviderIn):
    provider = LLMProvider(**body.model_dump())
    await store.add(provider)
    return {"ok": True, "name": provider.name}


@router.delete("/{name}")
async def remove_provider(name: str):
    ok = await store.remove(name)
    if not ok:
        raise HTTPException(404, f"Провайдер '{name}' не найден")
    return {"ok": True, "name": name}


@router.get("/{name}")
async def get_provider(name: str):
    providers = await store.all()
    for p in providers:
        if p.name == name:
            return p.model_dump()
    raise HTTPException(404, f"Провайдер '{name}' не найден")
