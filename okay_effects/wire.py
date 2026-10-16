"""Steps over a wire: each side sees only operations and answers.

An operation crosses as its name (its class's name in snake_case, or
``op_name``) and one record of its fields — the shape of a Scala case class:
``Charge(user, cents)`` is ``charge {user, cents}``. An answer comes back as
a plain value (numbers, strings, lists, dicts) and is decoded into what the
operation answers, ``R`` of ``Op[R]``. No transport here: a Caller is
whatever sends a request and waits — okay's Python worker's ``okay_call``."""

from __future__ import annotations

import dataclasses
import re
import typing
from collections.abc import Callable
from typing import Any, TypeVar

from okay_effects.core import Op
from okay_effects.middleware import Answerer

O = TypeVar("O", bound=Op[Any])
R = TypeVar("R")

Caller = Callable[[str, list[Any]], Any]
"""One request over the wire and its answer; a failure on the other side is raised."""


def name(op: type[Op[Any]] | Op[Any]) -> str:
    """An operation's name on the wire."""
    cls = op if isinstance(op, type) else type(op)
    given = getattr(cls, "op_name", None)
    return given if isinstance(given, str) else re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()


def encode(op: Op[Any]) -> tuple[str, list[Any]]:
    """An operation as its name and one record of its fields; none for an operation without fields."""
    rec = plain(op)
    return name(op), ([rec] if rec else [])


def answer_type(cls: type[Op[Any]]) -> Any:
    """R of a class declared ``class C(Op[R])``."""
    for base in getattr(cls, "__orig_bases__", ()):
        if typing.get_origin(base) is Op:
            return typing.get_args(base)[0]
    for parent in cls.__mro__[1:]:
        if parent is not Op and issubclass(parent, Op):
            return answer_type(parent)
    return Any


def decode(t: Any, v: Any) -> Any:
    """A plain value as t: a dict into a dataclass, field by field; lists of them; the rest as is."""
    if v is None or t is Any or t is None or isinstance(t, TypeVar):
        return v
    if dataclasses.is_dataclass(t) and isinstance(t, type) and isinstance(v, dict):
        hints = typing.get_type_hints(t)
        return t(**{f.name: decode(hints.get(f.name, Any), v[f.name]) for f in dataclasses.fields(t) if f.name in v})
    if typing.get_origin(t) in (list, tuple) and isinstance(v, (list, tuple)):
        (inner, *_) = typing.get_args(t) or (Any,)
        return [decode(inner, x) for x in v]
    if t is float and isinstance(v, int):
        return float(v)
    return v


def plain(v: Any) -> Any:
    """A Python value as wire values: a dataclass as a dict of its fields."""
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {f.name: plain(getattr(v, f.name)) for f in dataclasses.fields(v)}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    return v


def remote(call: Caller) -> Answerer:
    """Every operation answered over the wire. Middleware goes around it as around any Answerer."""

    def answer(op: Op[Any]) -> Any:
        n, args = encode(op)
        return decode(answer_type(type(op)), call(n, args))

    return answer


def serve(kind: type[O], answer: Callable[[O], Any]) -> tuple[str, Callable[..., Any]]:
    """The other way: a Python answer to ``kind``, callable from the wire by name with
    the operation's record as its argument, its answer a plain value."""

    def f(*args: Any) -> Any:
        rec = args[0] if args else {}
        return plain(answer(decode(kind, rec)))

    return name(kind), f
