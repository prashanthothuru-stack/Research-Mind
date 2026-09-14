from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.config import Settings, get_settings
from app.db.store import Store
from app.llm.factory import create_llm
from app.security import decode_token


@lru_cache
def _store() -> Store:
    return Store(get_settings())


def get_store() -> Store:
    return _store()


def get_llm():
    return create_llm(get_settings())


def get_current_user(
    store: Annotated[Store, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token")
    payload = decode_token(authorization.split(" ", 1)[1], settings)
    if not payload:
        raise HTTPException(401, "Invalid token")
    user = store.get_user(payload["sub"])
    if not user:
        raise HTTPException(401, "User not found")
    return user
