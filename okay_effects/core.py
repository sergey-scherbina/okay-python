"""Operations, capabilities, handlers: the core, on generators."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast

R = TypeVar("R")
A = TypeVar("A")
B = TypeVar("B")
O = TypeVar("O", bound="Op[Any]")
O_contra = TypeVar("O_contra", bound="Op[Any]", contravariant=True)


class Op(Generic[R]):
    """An operation answering R: subclass it, usually as a frozen dataclass.

    ``class Reserve(Op[bool])`` answers a bool."""

    __slots__ = ()


@dataclass(frozen=True, eq=False, slots=True)
class Tagged:
    """An operation on its way to the handler that owns its capability."""

    cap: Cap[Any]
    op: Op[Any]


Eff = Generator[Tagged, Any, A]
"""A program answering A: a generator performing operations with ``yield from``."""


class Escaped(Exception):
    """A capability used after its handler returned."""


class Unhandled(Exception):
    """An operation no live handler owns."""


class Cap(Generic[O_contra]):
    """A capability: made by a handler, handed to its body; the body performs through it.
    Contravariant: a capability taking any operation serves where a Cap[Reserve] is wanted."""

    __slots__ = ("_kind", "live")

    def __init__(self, kind: type[O_contra]) -> None:
        self._kind: type[Any] = kind
        self.live = True

    def perform(self, op: Op[R]) -> Eff[R]:
        """``x = yield from cap.perform(op)``: suspends until the owner answers."""
        if not isinstance(op, self._kind):
            raise TypeError(f"{type(op).__name__} through a capability for {self._kind.__name__}")
        if not self.live:
            raise Escaped(f"{self}: used outside its handler, the capability escaped its scope")
        return cast(R, (yield Tagged(self, op)))

    def __repr__(self) -> str:
        return f"Cap({self._kind.__name__})@{id(self):x}"


@dataclass(frozen=True, slots=True)
class Abort:
    """As an answer: the body stops where it performed (its ``finally`` blocks run)
    and the handler's value is ``value`` — never resumed (the kernel's Aborting)."""

    value: Any


@dataclass(frozen=True, slots=True)
class Raise:
    """As an answer: ``error`` is raised in the body where the operation was performed."""

    error: BaseException


def pure(a: A) -> Eff[A]:
    """A program answering a, performing nothing."""
    return a
    yield  # a generator  # noqa: unreachable


def handle(kind: type[O], answer: Callable[[O], Eff[Any]], body: Callable[[Cap[O]], Eff[A]]) -> Eff[A]:
    """Make a capability for ``kind``, run ``body`` with it, answer each of its operations
    with ``answer`` — itself a program, so it may perform through capabilities from
    outside (a component built on another), and may answer ``Abort(v)`` or ``Raise(e)``.
    Operations of other capabilities pass outward, unchanged."""
    cap = Cap(kind)
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
            if t.cap is cap:
                a = yield from answer(cast(O, t.op))
                if isinstance(a, Abort):
                    return cast(A, a.value)  # finally: the body is closed, its finally blocks run
                if isinstance(a, Raise):
                    throw = a.error
                else:
                    send = a
            elif not t.cap.live:
                raise Escaped(f"{t.cap}: used outside its handler, the capability escaped its scope")
            else:  # not mine: outward, and its answer — or failure — back in
                try:
                    send = yield t
                except Exception as e:
                    throw = e
    finally:
        cap.live = False
        gen.close()


def answering(kind: type[O], f: Callable[[O], Any], body: Callable[[Cap[O]], Eff[A]]) -> Eff[A]:
    """``handle`` for a plain answer: f answers each operation (Answering)."""

    def answer(op: O) -> Eff[Any]:
        return f(op)
        yield  # noqa: unreachable

    return (yield from handle(kind, answer, body))


def returning(kind: type[O], answer: Callable[[O], Eff[Any]], ret: Callable[[A], B],
              body: Callable[[Cap[O]], Eff[A]]) -> Eff[B]:
    """The handler's value made from its body's (Returning)."""
    return ret((yield from handle(kind, answer, body)))


def run(program: Eff[A]) -> A:
    """Run a program whose every operation is handled inside it."""
    try:
        t = next(program)
    except StopIteration as done:
        return cast(A, done.value)
    program.close()
    if not t.cap.live:
        raise Escaped(f"{t.cap}: used outside its handler, the capability escaped its scope")
    raise Unhandled(f"{type(t.op).__name__}: no live handler owns {t.cap}")
