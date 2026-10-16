package okay.foreign

import okay.codec.Schema
import okay.std.Reader

/** okay-python (Python effects on generators, its own capabilities and
 * handlers) over okay's worker wire: each side sees only operations and answers */
object TestOkayPythonWire:
  final case class Reserve(item: String) derives Schema
  final case class Charge(user: String, cents: Long) derives Schema
  final case class Email(to: String, text: String) derives Schema
  final case class Receipt(paid: Boolean, detail: String) derives Schema
  final case class Store(stock: Set[String], approve: Boolean)

  val sent = scala.collection.mutable.ArrayBuffer[String]()
  val reserve = Py.callback[Reserve, Boolean]("reserve")(r => Reader.ask[Store].map(_.stock(r.item)))
  val charge = Py.callback[Charge, Receipt]("charge")(c =>
    Reader.ask[Store].map(s => if s.approve then Receipt(true, s"scala-${c.user}-${c.cents}") else Receipt(false, "declined")))
  val email = Py.callback[Email, Boolean]("email")(e => Reader.ask[Store].map { _ => sent += s"${e.to}: ${e.text}"; true })

  val shop = Py.module("pyshop", """
    import sys
    sys.path.insert(0, "/Users/sergiy/work/my/okay-python")
    import okay
    from okay_effects import drive, start, wire
    from examples.shop.shop import Charge, Receipt, remote

    # the Python shop, unchanged, handed out: its capabilities answered by okay, step by step
    def checkout(user, item, cents):
        run = start(lambda h: remote(h).checkout(user, item, cents))
        r = drive(run, wire.remote(lambda name, args: okay.okay_call(name, *args)))
        return f"{r.paid} {r.detail}"

    # a Python handler, served to okay by its operation's name
    _, charge = wire.serve(Charge, lambda op: Receipt(op.cents <= 5000, f"py-{op.user}-{op.cents}"))
  """)

class TestOkayPythonWire extends munit.FunSuite {
  import TestOkayPythonWire.*

  override def munitTests(): Seq[Test] = super.munitTests().map(_.tag(new munit.Tag("Live")))
  override def munitIgnore: Boolean = TestPy.python.isEmpty

  private lazy val w = PySubprocess.start(TestPy.python.get, modules = Seq(shop))
  private given okay.Answers[PyEval] = w.handler
  override def afterAll(): Unit = if TestPy.python.nonEmpty then w.close()

  private val cbs = Py.callbacks(reserve, charge, email)

  test("the Python shop runs in Python; its inventory, payments and mail are Scala handlers, step by step") {
    sent.clear()
    val paid = shop.fn[String]("checkout").calling(cbs)("bob", "book", 2000L)
    assertEquals(Reader.run(Store(Set("book"), approve = true))(paid).runWith, Right("True scala-bob-2000"))
    val out = shop.fn[String]("checkout").calling(cbs)("eve", "pen", 100L)
    assertEquals(Reader.run(Store(Set("book"), approve = true))(out).runWith, Right("False pen: out of stock"))
    assertEquals(sent.toList, List("bob: paid, receipt scala-bob-2000", "eve: not paid: pen: out of stock"))
  }

  test("the other way: a Python handler answers okay's operation, a record in, a record out") {
    assertEquals(shop.fn[Receipt]("charge")(Charge("ann", 300L)).runWith, Right(Receipt(true, "py-ann-300")))
    assertEquals(shop.fn[Receipt]("charge")(Charge("ann", 9000L)).runWith, Right(Receipt(false, "py-ann-9000")))
  }
}
