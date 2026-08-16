import pytest

from rangora import CommerceCore


def make_core():
    c = CommerceCore(tax_bps=500, service_fee=25)
    c.add_item("A", "Alpha", 100, 10, taxable=True)
    c.add_item("B", "Beta", 50, 5, taxable=False)
    return c


def test_quote_totals():
    c = make_core()
    q = c.quote({"A": 2, "B": 1})
    assert q["subtotal"] == 250
    assert q["tax"] == 10
    assert q["service_fee"] == 25
    assert q["total"] == 285


def test_stock_limit_enforced():
    c = make_core()
    with pytest.raises(ValueError, match="insufficient stock"):
        c.quote({"B": 6})


def test_unknown_sku_rejected():
    c = make_core()
    with pytest.raises(KeyError):
        c.quote({"NOPE": 1})


def test_percentage_coupon():
    c = make_core()
    c.add_coupon("SAVE10", percent_off=10, min_subtotal=100)
    q = c.quote({"A": 2}, coupon_code="save10")
    assert q["discount"] == 20
    assert q["total"] == 214


def test_coupon_minimum_enforced():
    c = make_core()
    c.add_coupon("BIG", fixed_off=20, min_subtotal=500)
    with pytest.raises(ValueError, match="minimum subtotal"):
        c.quote({"A": 1}, coupon_code="BIG")


def test_checkout_decrements_inventory():
    c = make_core()
    c.checkout("order-1", {"A": 3})
    assert c.items["A"].stock == 7


def test_checkout_is_idempotent():
    c = make_core()
    first = c.checkout("order-1", {"A": 2})
    second = c.checkout("order-1", {"A": 9})
    assert first == second
    assert c.items["A"].stock == 8


def test_receipt_hash_reproducible():
    one = make_core()
    two = make_core()
    r1 = one.checkout("order-1", {"A": 2, "B": 1})
    r2 = two.checkout("order-1", {"A": 2, "B": 1})
    assert r1.receipt_hash == r2.receipt_hash


def test_inventory_manifest_reproducible():
    one = make_core()
    two = make_core()
    assert one.inventory_manifest()["manifest_hash"] == two.inventory_manifest()["manifest_hash"]


def test_rejects_invalid_coupon_shape():
    c = make_core()
    with pytest.raises(ValueError):
        c.add_coupon("BAD", percent_off=10, fixed_off=5)
