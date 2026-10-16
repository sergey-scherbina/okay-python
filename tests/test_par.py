import asyncio
import time
import unittest

from okay_effects import Async, Eff, all_of, race, run_async, sleep, wait


class TestPar(unittest.TestCase):
    def test_all_runs_at_once(self) -> None:
        def branch(n: int):  # type: ignore[no-untyped-def]
            def go(io: Async) -> Eff[int]:
                yield from sleep(io, 0.05)
                return n

            return go

        def main(io: Async) -> Eff[int]:
            xs = yield from all_of(io, branch(1), branch(2), branch(40))
            return sum(xs)

        t = time.monotonic()
        self.assertEqual(asyncio.run(run_async(main)), 43)
        self.assertLess(time.monotonic() - t, 0.09)

    def test_race_cancels_the_loser(self) -> None:
        cleaned: list[bool] = []

        def slow(io: Async) -> Eff[str]:
            try:
                yield from sleep(io, 1)
                return "slow"
            finally:
                cleaned.append(True)

        def fast(io: Async) -> Eff[str]:
            yield from sleep(io, 0.01)
            return "fast"

        def main(io: Async) -> Eff[str]:
            return (yield from race(io, slow, fast))

        t = time.monotonic()
        self.assertEqual(asyncio.run(run_async(main)), "fast")
        self.assertLess(time.monotonic() - t, 0.5)
        self.assertEqual(cleaned, [True])

    def test_a_failure_cancels_the_others(self) -> None:
        cleaned: list[bool] = []

        def slow(io: Async) -> Eff[int]:
            try:
                yield from sleep(io, 1)
                return 1
            finally:
                cleaned.append(True)

        def boom(io: Async) -> Eff[int]:
            yield from sleep(io, 0.01)
            raise ValueError("boom")

        def main(io: Async) -> Eff[str]:
            try:
                yield from all_of(io, slow, boom)
                return "unreached"
            except ValueError:
                return "failed"

        self.assertEqual(asyncio.run(run_async(main)), "failed")
        self.assertEqual(cleaned, [True])

    def test_await_any_awaitable(self) -> None:
        async def fetch() -> str:
            await asyncio.sleep(0)
            return "data"

        def main(io: Async) -> Eff[str]:
            return (yield from wait(io, fetch())).upper()

        self.assertEqual(asyncio.run(run_async(main)), "DATA")


if __name__ == "__main__":
    unittest.main()
