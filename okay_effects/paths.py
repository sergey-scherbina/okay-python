"""Every path: a continuation resumed with each answer in turn.

A generator cannot be copied, so the rest of the program is re-run from the
start with the answers so far replayed — for a program that is pure apart
from its effects (what it does to the world, it does through operations)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TypeVar, cast

from okay_effects.core import Cap, Eff, O, Unhandled

A = TypeVar("A")


def every_path(kind: type[O], answers: Callable[[O], Iterable[Any]], body: Callable[[Cap[O]], Eff[A]]) -> list[A]:
    """The body's value for every combination of answers, depth first."""
    out: list[A] = []

    def explore(prefix: list[Any]) -> None:
        cap = Cap(kind)
        gen = body(cap)
        send: Any = None
        try:
            for i in range(1 << 62):
                try:
                    t = gen.send(send)
                except StopIteration as done:
                    out.append(cast(A, done.value))
                    return
                if t.cap is not cap:
                    raise Unhandled(f"{type(t.op).__name__}: every_path answers only {kind.__name__}")
                if i < len(prefix):
                    send = prefix[i]
                    continue
                for a in answers(cast(O, t.op)):
                    explore([*prefix, a])
                return
        finally:
            cap.live = False
            gen.close()

    explore([])
    return out
