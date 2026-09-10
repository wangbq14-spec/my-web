from fastapi import APIRouter

from app.llm.registry import get_model_registry

router = APIRouter()


@router.get("")
def list_models() -> list[dict[str, str]]:
    return get_model_registry().tiers()
