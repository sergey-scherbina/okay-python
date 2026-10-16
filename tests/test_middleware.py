import unittest
from typing import Any

from examples.shop.shop import Charge, Email, Receipt, Reserve, remote
from okay_effects import Answerer, Entry, Op, Routes, drive, only, record, replay, start, with_


def services(stock: dict[str, int], sent: list[str]) -> Routes:
    rs = Routes()

    def reserve(op: Reserve) -> bool:
        if stock.get(op.item, 0) == 0:
            return False
        stock[op.item] -= 1
        return True

    rs.on(Reserve, reserve)
    rs.on(Charge, lambda op: Receipt(True, f"ch_{op.user}"))
    rs.on(Email, lambda op: sent.append(f"{op.to}: {op.text}"))
    return rs


def checkout(user: str, cents: int):  # type: ignore[no-untyped-def]
    return start(lambda h: remote(h).checkout(user, "book", cents))


class TestMiddleware(unittest.TestCase):
    def test_every_operation_through_the_same_middleware(self) -> None:
        sent: list[str] = []
        audit: list[str] = []
        counts: dict[str, int] = {}
        log: list[Entry] = []

        # all of them alike: an audit trail, a metric, a recording
        def auditing(op: Op[Any], nxt: Answerer) -> Any:
            v = nxt(op)
            audit.append(f"{op!r} -> {v!r}")
            return v

        def metrics(op: Op[Any], nxt: Answerer) -> Any:
            counts[type(op).__name__] = counts.get(type(op).__name__, 0) + 1
            return nxt(op)

        # one of them its own way: only these users may be charged, above 5000 nobody
        allowed = {"bob"}

        def security(op: Charge, nxt: Answerer) -> Any:
            if op.user not in allowed or op.cents > 5000:
                raise PermissionError(f"forbidden: charge {op.user}")
            return nxt(op)

        answer = with_(services({"book": 5}, sent), auditing, metrics, record(log), only(Charge, security))

        self.assertEqual(drive(checkout("bob", 2000), answer), Receipt(True, "ch_bob"))
        self.assertEqual(audit[1], "Charge(user='bob', cents=2000) -> Receipt(paid=True, detail='ch_bob')")
        # refused by security: raised where Charge was performed, so no mail goes out
        with self.assertRaisesRegex(PermissionError, "forbidden: charge eve"):
            drive(checkout("eve", 100), answer)
        self.assertEqual((len(sent), counts["Charge"], counts["Email"]), (1, 2, 1))

        # replay: bob's run again from the recording — the same receipt, no service reached
        bob = log[:3]
        self.assertEqual(drive(checkout("bob", 2000), replay(bob)), Receipt(True, "ch_bob"))
        # a run that does something else is caught at the first difference
        with self.assertRaisesRegex(LookupError, "diverged at 1"):
            drive(checkout("bob", 3000), replay(bob))


if __name__ == "__main__":
    unittest.main()
