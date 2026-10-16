import unittest
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from okay_effects import Abort, Cap, Eff, Escaped, Op, Raise, Unhandled, answering, handle, returning, run

T = TypeVar("T")
A = TypeVar("A")


@dataclass(frozen=True)
class Ask(Op[T], Generic[T]):
    pass


def reader(v: T, body: Callable[[Cap[Ask[T]]], Eff[A]]) -> Eff[A]:
    return (yield from answering(Ask, lambda _: v, body))


class TestCore(unittest.TestCase):
    def test_two_instances_of_one_effect(self) -> None:
        def prog(outer: Cap[Ask[int]]) -> Eff[int]:
            def inner_body(inner: Cap[Ask[int]]) -> Eff[int]:
                a = yield from outer.perform(Ask[int]())
                b = yield from inner.perform(Ask[int]())
                return a * 10 + b

            return (yield from reader(2, inner_body))

        self.assertEqual(run(reader(1, prog)), 12)

    def test_different_types_told_apart_by_capability(self) -> None:
        def prog(n: Cap[Ask[int]]) -> Eff[str]:
            def body(s: Cap[Ask[str]]) -> Eff[str]:
                return (yield from s.perform(Ask[str]())) * (yield from n.perform(Ask[int]()))

            return (yield from reader("ab", body))

        self.assertEqual(run(reader(3, prog)), "ababab")

    def test_escaped_capability_refused(self) -> None:
        kept: list[Cap[Ask[int]]] = []

        def keep(a: Cap[Ask[int]]) -> Eff[int]:
            kept.append(a)
            return 0
            yield  # noqa: unreachable

        run(reader(1, keep))
        with self.assertRaisesRegex(Escaped, "escaped its scope"):
            run(kept[0].perform(Ask[int]()))

        def inside(_: Cap[Ask[int]]) -> Eff[int]:
            return (yield from kept[0].perform(Ask[int]()))

        with self.assertRaisesRegex(Escaped, "escaped its scope"):
            run(reader(2, inside))

    def test_unhandled_refused(self) -> None:
        with self.assertRaises(Unhandled):
            run(Cap(Ask).perform(Ask[int]()))

    def test_abort_ends_the_body_and_runs_finally(self) -> None:
        cleaned: list[bool] = []

        def body(a: Cap[Ask[int]]) -> Eff[int]:
            try:
                yield from a.perform(Ask[int]())
                return 1
            finally:
                cleaned.append(True)

        def ret(n: int) -> str:
            return "aborted" if n < 0 else "done"

        def abort(_: Ask[int]) -> Eff[object]:
            return Abort(-1)
            yield  # noqa: unreachable

        self.assertEqual(run(returning(Ask, abort, ret, body)), "aborted")
        self.assertEqual(cleaned, [True])

    def test_raise_at_the_operation(self) -> None:
        def refuse(_: Ask[int]) -> Eff[object]:
            return Raise(ValueError("refused"))
            yield  # noqa: unreachable

        def body(a: Cap[Ask[int]]) -> Eff[str]:
            try:
                yield from a.perform(Ask[int]())
                return "unreached"
            except ValueError as e:
                return str(e)

        self.assertEqual(run(handle(Ask, refuse, body)), "refused")

    def test_a_million_operations(self) -> None:
        def body(a: Cap[Ask[int]]) -> Eff[int]:
            s = 0
            for _ in range(1_000_000):
                s += yield from a.perform(Ask[int]())
            return s

        self.assertEqual(run(reader(1, body)), 1_000_000)


if __name__ == "__main__":
    unittest.main()
