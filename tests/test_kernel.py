import unittest

from examples.shop.shop import Charge, Email, Receipt, Reserve, remote
from okay_effects import Eff, Host, start




class TestKernel(unittest.TestCase):
    def test_a_checkout_waits_for_a_manager(self) -> None:
        run = start(lambda h: remote(h).checkout("bob", "book", 2000))
        s = run.step()
        self.assertEqual(s.op, Reserve("book"))
        s = run.resume(True)
        self.assertEqual(s.op, Charge("bob", 2000))
        pending = run  # kept as a value: its caller is not stuck inside a call
        s = pending.resume(Receipt(True, "approved by ann"))
        self.assertEqual(s.op, Email("bob", "paid, receipt approved by ann"))
        s = pending.resume(None)
        self.assertEqual((s.kind, s.value), ("done", Receipt(True, "approved by ann")))

    def test_fail_is_raised_at_the_operation(self) -> None:
        def body(h: Host) -> Eff[str]:
            try:
                yield from h.outside(Reserve).perform(Reserve("x"))
                return "unreached"
            except LookupError as e:
                return f"recovered: {e}"

        run = start(body)
        run.step()
        s = run.fail(LookupError("no such sku"))
        self.assertEqual(s.value, "recovered: no such sku")

    def test_cancel_runs_finally(self) -> None:
        cleaned: list[bool] = []

        def body(h: Host) -> Eff[bool]:
            try:
                return (yield from h.outside(Reserve).perform(Reserve("x")))
            finally:
                cleaned.append(True)

        run = start(body)
        run.step()
        self.assertEqual(run.cancel().kind, "cancelled")
        self.assertEqual(cleaned, [True])

    def test_a_failure_in_the_program(self) -> None:
        def body(h: Host) -> Eff[int]:
            raise RuntimeError("boom")
            yield  # noqa: unreachable

        s = start(body).step()
        self.assertEqual((s.kind, str(s.failure)), ("failed", "boom"))


if __name__ == "__main__":
    unittest.main()
