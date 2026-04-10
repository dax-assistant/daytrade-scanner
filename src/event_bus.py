from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, DefaultDict, List

LOGGER = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[Callable[..., Awaitable[None]]]] = defaultdict(list)

    def on(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        self._handlers[event].append(handler)

    async def emit(self, event: str, payload: Any) -> None:
        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        results = await asyncio.gather(*(h(payload) for h in handlers), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                LOGGER.exception("Event handler failed for event '%s': %s", event, result)
