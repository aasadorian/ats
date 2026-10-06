import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class EventContext:
    request_id: str
    source: str
    ip_address: str | None = None


_current: ContextVar[EventContext | None] = ContextVar("event_context", default=None)


def current_context() -> EventContext:
    return _current.get() or EventContext(request_id=new_request_id(), source="shell")


def new_request_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def event_context(source: str, ip_address: str | None = None) -> Iterator[None]:
    token = _current.set(
        EventContext(request_id=new_request_id(), source=source, ip_address=ip_address)
    )
    try:
        yield
    finally:
        _current.reset(token)
