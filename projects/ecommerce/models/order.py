"""Order and cart models."""
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import Optional
from .product import Product
from .user import User, Address

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_SHIPPED = "shipped"
STATUS_DELIVERED = "delivered"
STATUS_CANCELLED = "cancelled"
STATUS_REFUNDED = "refunded"

PAYMENT_STRIPE = "stripe"
PAYMENT_PAYPAL = "paypal"
PAYMENT_COD = "cod"

FREE_SHIPPING_THRESHOLD = Decimal("50.00")
SHIPPING_COST_STANDARD = Decimal("4.99")
SHIPPING_COST_EXPRESS = Decimal("12.99")


@dataclass
class OrderItem:
    """A single line in an order."""
    product: Product
    quantity: int
    unit_price: Decimal
    tax_rate: Decimal

    def subtotal(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(Decimal("0.01"))

    def tax_amount(self) -> Decimal:
        return (self.subtotal() * self.tax_rate).quantize(Decimal("0.01"))

    def total(self) -> Decimal:
        return (self.subtotal() + self.tax_amount()).quantize(Decimal("0.01"))


class Cart:
    """Shopping cart (pre-order)."""

    def __init__(self, user: Optional[User] = None):
        self.user = user
        self.items: list[OrderItem] = []
        self._coupon_code: Optional[str] = None
        self._discount_pct: Decimal = Decimal("0")

    def add_item(self, product: Product, quantity: int = 1) -> None:
        """Add product to cart or increment quantity if already present."""
        for item in self.items:
            if item.product.product_id == product.product_id:
                item.quantity += quantity
                return
        self.items.append(OrderItem(
            product=product,
            quantity=quantity,
            unit_price=product.price,
            tax_rate=product.get_tax_rate(),
        ))

    def remove_item(self, product_id: int) -> bool:
        original = len(self.items)
        self.items = [i for i in self.items if i.product.product_id != product_id]
        return len(self.items) < original

    def apply_coupon(self, code: str, discount_pct: Decimal) -> None:
        self._coupon_code = code
        self._discount_pct = discount_pct

    def subtotal(self) -> Decimal:
        return sum(i.subtotal() for i in self.items)

    def tax_total(self) -> Decimal:
        return sum(i.tax_amount() for i in self.items)

    def discount_amount(self) -> Decimal:
        return (self.subtotal() * self._discount_pct / 100).quantize(Decimal("0.01"))

    def shipping_cost(self, express: bool = False) -> Decimal:
        if self.subtotal() >= FREE_SHIPPING_THRESHOLD:
            return Decimal("0.00")
        return SHIPPING_COST_EXPRESS if express else SHIPPING_COST_STANDARD

    def grand_total(self, express_shipping: bool = False) -> Decimal:
        return (
            self.subtotal()
            + self.tax_total()
            - self.discount_amount()
            + self.shipping_cost(express_shipping)
        ).quantize(Decimal("0.01"))

    def item_count(self) -> int:
        return sum(i.quantity for i in self.items)

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def clear(self) -> None:
        self.items = []
        self._coupon_code = None
        self._discount_pct = Decimal("0")


class Order:
    """A confirmed purchase order."""

    def __init__(self, order_id: int, user: User, items: list[OrderItem],
                 shipping_address: Address, payment_method: str):
        self.order_id = order_id
        self.user = user
        self.items = items
        self.shipping_address = shipping_address
        self.payment_method = payment_method
        self.status = STATUS_PENDING
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self._tracking_number: Optional[str] = None
        self._refund_reason: Optional[str] = None

    def total_amount(self) -> Decimal:
        return sum(i.total() for i in self.items).quantize(Decimal("0.01"))

    def tax_total(self) -> Decimal:
        return sum(i.tax_amount() for i in self.items).quantize(Decimal("0.01"))

    def confirm(self) -> None:
        if self.status != STATUS_PENDING:
            raise ValueError(f"Cannot confirm order in status {self.status!r}")
        self.status = STATUS_CONFIRMED
        self.updated_at = datetime.utcnow()

    def ship(self, tracking_number: str) -> None:
        if self.status != STATUS_CONFIRMED:
            raise ValueError(f"Cannot ship order in status {self.status!r}")
        self.status = STATUS_SHIPPED
        self._tracking_number = tracking_number
        self.updated_at = datetime.utcnow()

    def deliver(self) -> None:
        if self.status != STATUS_SHIPPED:
            raise ValueError(f"Cannot deliver order in status {self.status!r}")
        self.status = STATUS_DELIVERED
        self.updated_at = datetime.utcnow()

    def cancel(self) -> None:
        if self.status in (STATUS_DELIVERED, STATUS_REFUNDED):
            raise ValueError(f"Cannot cancel order in status {self.status!r}")
        self.status = STATUS_CANCELLED
        self.updated_at = datetime.utcnow()

    def refund(self, reason: str) -> None:
        if self.status not in (STATUS_DELIVERED, STATUS_CONFIRMED):
            raise ValueError(f"Cannot refund order in status {self.status!r}")
        self.status = STATUS_REFUNDED
        self._refund_reason = reason
        self.updated_at = datetime.utcnow()

    def is_cancellable(self) -> bool:
        return self.status in (STATUS_PENDING, STATUS_CONFIRMED)

    def tracking_number(self) -> Optional[str]:
        return self._tracking_number

    def __repr__(self) -> str:
        return f"Order(id={self.order_id}, status={self.status!r}, total={self.total_amount()})"
