"""Async and parallel branches on asyncio: the business code stays a plain generator;
only the runner at the top is async. No coloured functions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast

from okay_effects.core import Cap, Eff, Op, Unhandled

T = TypeVar("T")
A = TypeVar("A")


@dataclass(frozen=True, eq=False, slots=True)
class Await(Op[T], Generic[T]):
    """Wait for an awaitable: the async runner awaits it, the program resumes with its value."""

    awaitable: Awaitable[T]


Async = Cap[Await[Any]]


def wait(cap: Async, aw: Awaitable[T]) -> Eff[T]:
    """``x = yield from wait(io, fetch())``"""
    return (yield from cap.perform(Await(aw)))


def sleep(cap: Async, seconds: float) -> Eff[None]:
    yield from cap.perform(Await(asyncio.sleep(seconds)))


async def run_async(body: Callable[[Async], Eff[A]]) -> A:
    """Run body on the event loop, its Awaits awaited; cancelled, its ``finally`` blocks run.
    Every other operation must be handled inside body."""
    cap: Async = Cap(Await)
    gen = body(cap)
    send: Any = None
    throw: BaseException | None = None
    try:
        while True:
            try:
                t = gen.send(send) if throw is None else gen.throw(throw)
            except StopIteration as done:
                return cast(A, done.value)
            send, throw = None, None
            if t.cap is not cap:
                raise Unhandled(f"{type(t.op).__name__}: a branch answers only its own handlers and Await")
            try:
                send = await cast(Await[Any], t.op).awaitable
            except asyncio.CancelledError:
                raise
            except Exception as e:
                throw = e
    finally:
        cap.live = False
        gen.close()


def all_of(cap: Async, *branches: Callable[[Async], Eff[A]]) -> Eff[list[A]]:
    """Branches at once; a failure in one cancels the others and is raised here."""

    async def together() -> list[A]:
        try:
            async with asyncio.TaskGroup() as g:
                tasks = [g.create_task(run_async(b)) for b in branches]
        except ExceptionGroup as eg:
            raise eg.exceptions[0] from None  # the branch's own failure, as if it were a call
        return [t.result() for t in tasks]

    return (yield from wait(cap, together()))


def race(cap: Async, *branches: Callable[[Async], Eff[A]]) -> Eff[A]:
    """The first answer wins; the others are cancelled, their ``finally`` blocks run."""

    async def first() -> A:
        tasks = [asyncio.create_task(run_async(b)) for b in branches]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return next(iter(done)).result()

    return (yield from wait(cap, first()))
