"""A handed-out program answered in one place: every operation, as data, through middleware."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from okay_effects.core import O, Op
from okay_effects.kernel import Computation

A = TypeVar("A")

Answerer = Callable[[Op[Any]], Any]
"""The host's answer to any operation; an exception is raised in the program where it was performed."""

Middleware = Callable[[Op[Any], Answerer], Any]
"""Around every operation — monitor, log, authorize, record; ``next`` answers it."""


def drive(c: Computation[A], answer: Answerer) -> A:
    """The program run to its value, every operation it performs for the host answered by answer."""
    s = c.step()
    while s.kind == "yielded":
        assert s.op is not None
        try:
            v = answer(s.op)
        except Exception as e:
            s = c.fail(e)
            continue
        s = c.resume(v)
    if s.kind == "failed":
        assert s.failure is not None
        raise s.failure
    return s.value  # type: ignore[return-value]  # done: the value is there


def with_(answer: Answerer, *ms: Middleware) -> Answerer:
    """answer wrapped in middleware, the first outermost."""
    for m in reversed(ms):
        answer = (lambda m, nxt: lambda op: m(op, nxt))(m, answer)
    return answer


def only(kind: type[O], m: Callable[[O, Answerer], Any]) -> Middleware:
    """m for the operations of type ``kind`` alone; the others pass by untouched."""

    def around(op: Op[Any], nxt: Answerer) -> Any:
        if isinstance(op, kind):
            return m(op, nxt)
        return nxt(op)

    return around


class Routes:
    """Answers by the operation's type."""

    def __init__(self) -> None:
        self._by: dict[type[Any], Callable[[Any], Any]] = {}

    def on(self, kind: type[O], f: Callable[[O], Any]) -> None:
        """f answers the operations of type ``kind``."""
        self._by[kind] = f

    def __call__(self, op: Op[Any]) -> Any:
        f = self._by.get(type(op))
        if f is None:
            raise LookupError(f"okay: no route for {type(op).__name__}")
        return f(op)


@dataclass(frozen=True, slots=True)
class Entry:
    """One operation and how it was answered."""

    op: Op[Any]
    answer: Any = None
    error: BaseException | None = None


def record(log: list[Entry]) -> Middleware:
    """Every operation and its answer appended to log."""

    def around(op: Op[Any], nxt: Answerer) -> Any:
        try:
            v = nxt(op)
        except Exception as e:
            log.append(Entry(op, error=e))
            raise
        log.append(Entry(op, v))
        return v

    return around


def replay(log: list[Entry]) -> Answerer:
    """A recorded run answered again from its log, nothing reached; an operation other
    than the one recorded is refused, the run having diverged."""
    it = iter(enumerate(log))

    def answer(op: Op[Any]) -> Any:
        i, e = next(it, (len(log), None))
        if e is None:
            raise LookupError(f"okay replay: {op!r} past the end of the log")
        if e.op != op:
            raise LookupError(f"okay replay: diverged at {i}: recorded {e.op!r}, now {op!r}")
        if e.error is not None:
            raise e.error
        return e.answer

    return answer
