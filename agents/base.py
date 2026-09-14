from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.db.store import Store
from app.llm.base import LLMProvider


EmitFn = Callable[[dict], Awaitable[None]]


class BaseAgent:
    name = "agent"
    title = "Agent"

    def __init__(self, llm: LLMProvider, store: Store, emit: EmitFn):
        self.llm = llm
        self.store = store
        self.emit = emit

    async def event(self, kind: str, **payload: Any) -> None:
        await self.emit({"agent": self.name, "title": self.title, "kind": kind, **payload})
