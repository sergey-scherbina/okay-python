import unittest
from typing import Any

from examples.shop.shop import Charge, Receipt, remote
from okay_effects import drive, start, wire


class Far:
    """the other side as a table of named functions answering plain values, as a foreign host does"""

    def __init__(self, fs: dict[str, Any]) -> None:
        self.fs = fs

    def call(self, name: str, args: list[Any]) -> Any:
        if name not in self.fs:
            raise LookupError(f"no {name}")
        return self.fs[name](*args)


def checkout(user: str, item: str, cents: int):  # type: ignore[no-untyped-def]
    return start(lambda h: remote(h).checkout(user, item, cents))


class TestWire(unittest.TestCase):
    def test_the_shop_steps_over_the_wire(self) -> None:
        log: list[str] = []
        far = Far({
            "reserve": lambda r: r["item"] == "book",
            "charge": lambda c: {"paid": True, "detail": "ch_" + c["user"]},  # a receipt as it comes off the wire
            "email": lambda e: log.append(f"{e['to']}: {e['text']}"),
        })
        self.assertEqual(drive(checkout("bob", "book", 2000), wire.remote(far.call)), Receipt(True, "ch_bob"))
        self.assertEqual(drive(checkout("eve", "pen", 100), wire.remote(far.call)), Receipt(False, "pen: out of stock"))
        self.assertEqual(log, ["bob: paid, receipt ch_bob", "eve: not paid: pen: out of stock"])

    def test_a_failure_over_the_wire(self) -> None:
        with self.assertRaisesRegex(LookupError, "no reserve"):
            drive(checkout("bob", "book", 2000), wire.remote(Far({}).call))

    def test_serve_a_python_handler(self) -> None:
        n, f = wire.serve(Charge, lambda op: Receipt(op.cents <= 5000, op.user))
        self.assertEqual((n, f({"user": "ann", "cents": 300})), ("charge", {"paid": True, "detail": "ann"}))
        far = Far({n: f, "reserve": lambda r: True, "email": lambda e: None})
        self.assertEqual(drive(checkout("ann", "book", 9000), wire.remote(far.call)), Receipt(False, "ann"))
