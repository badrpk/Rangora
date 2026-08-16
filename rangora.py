from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Item:
    sku: str
    name: str
    unit_price: int
    stock: int
    taxable: bool = True


@dataclass(frozen=True)
class Coupon:
    code: str
    percent_off: int = 0
    fixed_off: int = 0
    min_subtotal: int = 0


@dataclass(frozen=True)
class CheckoutReceipt:
    checkout_id: str
    subtotal: int
    discount: int
    tax: int
    service_fee: int
    total: int
    lines: Tuple[Tuple[str, int, int], ...]
    receipt_hash: str


class CommerceCore:
    """Deterministic dependency-free commerce rules kernel."""

    def __init__(self, *, tax_bps: int = 0, service_fee: int = 0) -> None:
        if tax_bps < 0 or service_fee < 0:
            raise ValueError("tax_bps and service_fee must be non-negative")
        self.tax_bps = tax_bps
        self.service_fee = service_fee
        self.items: Dict[str, Item] = {}
        self.coupons: Dict[str, Coupon] = {}
        self._checkouts: Dict[str, CheckoutReceipt] = {}

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(value.strip().split())

    def add_item(self, sku: str, name: str, unit_price: int, stock: int, *, taxable: bool = True) -> Item:
        sku = self._clean(sku)
        if not sku or not self._clean(name):
            raise ValueError("sku and name are required")
        if unit_price < 0 or stock < 0:
            raise ValueError("unit_price and stock must be non-negative")
        item = Item(sku, self._clean(name), unit_price, stock, taxable)
        existing = self.items.get(sku)
        if existing and existing != item:
            raise ValueError(f"sku already exists with different metadata: {sku}")
        self.items[sku] = item
        return item

    def add_coupon(
        self,
        code: str,
        *,
        percent_off: int = 0,
        fixed_off: int = 0,
        min_subtotal: int = 0,
    ) -> Coupon:
        code = self._clean(code).upper()
        if not code:
            raise ValueError("coupon code is required")
        if not 0 <= percent_off <= 100:
            raise ValueError("percent_off must be 0..100")
        if fixed_off < 0 or min_subtotal < 0:
            raise ValueError("fixed_off and min_subtotal must be non-negative")
        if percent_off and fixed_off:
            raise ValueError("coupon cannot combine percentage and fixed discounts")
        coupon = Coupon(code, percent_off, fixed_off, min_subtotal)
        self.coupons[code] = coupon
        return coupon

    def quote(self, cart: Dict[str, int], *, coupon_code: Optional[str] = None) -> dict:
        if not cart:
            raise ValueError("cart is empty")
        lines: List[Tuple[str, int, int]] = []
        subtotal = 0
        taxable_subtotal = 0
        for sku in sorted(cart):
            qty = cart[sku]
            if qty <= 0:
                raise ValueError("quantities must be positive")
            item = self.items.get(sku)
            if item is None:
                raise KeyError(f"unknown sku: {sku}")
            if qty > item.stock:
                raise ValueError(f"insufficient stock: {sku}")
            line_total = item.unit_price * qty
            subtotal += line_total
            if item.taxable:
                taxable_subtotal += line_total
            lines.append((sku, qty, line_total))

        discount = 0
        if coupon_code:
            coupon = self.coupons.get(self._clean(coupon_code).upper())
            if coupon is None:
                raise KeyError("unknown coupon")
            if subtotal < coupon.min_subtotal:
                raise ValueError("coupon minimum subtotal not met")
            discount = (subtotal * coupon.percent_off) // 100 if coupon.percent_off else coupon.fixed_off
            discount = min(discount, subtotal)

        discounted_taxable = max(0, taxable_subtotal - min(discount, taxable_subtotal))
        tax = (discounted_taxable * self.tax_bps) // 10000
        total = subtotal - discount + tax + self.service_fee
        return {
            "lines": tuple(lines),
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "service_fee": self.service_fee,
            "total": total,
        }

    def checkout(self, checkout_id: str, cart: Dict[str, int], *, coupon_code: Optional[str] = None) -> CheckoutReceipt:
        checkout_id = self._clean(checkout_id)
        if not checkout_id:
            raise ValueError("checkout_id is required")
        existing = self._checkouts.get(checkout_id)
        if existing is not None:
            return existing
        quote = self.quote(cart, coupon_code=coupon_code)
        for sku, qty, _ in quote["lines"]:
            item = self.items[sku]
            self.items[sku] = Item(item.sku, item.name, item.unit_price, item.stock - qty, item.taxable)
        payload = {
            "checkout_id": checkout_id,
            "subtotal": quote["subtotal"],
            "discount": quote["discount"],
            "tax": quote["tax"],
            "service_fee": quote["service_fee"],
            "total": quote["total"],
            "lines": quote["lines"],
        }
        digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        receipt = CheckoutReceipt(receipt_hash=digest, **payload)
        self._checkouts[checkout_id] = receipt
        return receipt

    def inventory_manifest(self) -> dict:
        payload = {"items": [asdict(self.items[k]) for k in sorted(self.items)]}
        payload["manifest_hash"] = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return payload
