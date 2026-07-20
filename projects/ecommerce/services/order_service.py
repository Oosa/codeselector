"""Order business logic and orchestration."""
import logging
import uuid
from decimal import Decimal
from typing import Optional

from models.order import Cart, Order, OrderItem, STATUS_PENDING
from models.product import Product
from models.user import User, Address

logger = logging.getLogger(__name__)

MAX_ITEMS_PER_ORDER = 50
MIN_ORDER_AMOUNT = Decimal("1.00")


class InsufficientStockError(Exception):
    """Raised when a product has insufficient stock for an order."""
    pass


class OrderValidationError(Exception):
    """Raised when order data fails validation."""
    pass


class OrderService:
    """Handles the full order lifecycle."""

    def __init__(self, db, payment_gateway, notification_service):
        self.db = db
        self.payment_gateway = payment_gateway
        self.notification_service = notification_service
        self._order_cache: dict[int, Order] = {}

    def create_order_from_cart(self, cart: Cart, shipping_address: Address,
                                payment_method: str) -> Order:
        """Convert a cart into a confirmed order."""
        self._validate_cart(cart)
        self._check_stock_availability(cart)

        order_id = self._generate_order_id()
        items = list(cart.items)

        order = Order(
            order_id=order_id,
            user=cart.user,
            items=items,
            shipping_address=shipping_address,
            payment_method=payment_method,
        )
        self._reserve_stock(cart)
        self.db.save(order)
        self._order_cache[order_id] = order
        logger.info("Order %s created for user %s", order_id, cart.user.user_id)
        return order

    def _validate_cart(self, cart: Cart) -> None:
        if cart.is_empty():
            raise OrderValidationError("Cart is empty")
        if cart.item_count() > MAX_ITEMS_PER_ORDER:
            raise OrderValidationError(f"Too many items: {cart.item_count()}")
        if cart.subtotal() < MIN_ORDER_AMOUNT:
            raise OrderValidationError(f"Order total too low: {cart.subtotal()}")

    def _check_stock_availability(self, cart: Cart) -> None:
        for item in cart.items:
            if item.product.stock_quantity < item.quantity:
                raise InsufficientStockError(
                    f"Insufficient stock for {item.product.name}: "
                    f"requested {item.quantity}, available {item.product.stock_quantity}"
                )

    def _reserve_stock(self, cart: Cart) -> None:
        for item in cart.items:
            success = item.product.reserve_stock(item.quantity)
            if not success:
                raise InsufficientStockError(f"Failed to reserve stock for {item.product.name}")

    def _generate_order_id(self) -> int:
        return abs(hash(uuid.uuid4())) % (10 ** 9)

    def get_order(self, order_id: int) -> Optional[Order]:
        """Retrieve an order by ID, checking cache first."""
        if order_id in self._order_cache:
            return self._order_cache[order_id]
        order = self.db.find_by_id("orders", order_id)
        if order:
            self._order_cache[order_id] = order
        return order

    def get_user_orders(self, user: User) -> list[Order]:
        """Return all orders for a user, sorted newest first."""
        orders = self.db.find_all("orders", filters={"user_id": user.user_id})
        return sorted(orders, key=lambda o: o.created_at, reverse=True)

    async def process_payment(self, order: Order) -> bool:
        """Charge the customer and confirm the order on success."""
        try:
            charge_id = await self.payment_gateway.charge(
                amount=order.total_amount(),
                currency="USD",
                payment_method=order.payment_method,
                metadata={"order_id": order.order_id},
            )
            order.confirm()
            self.db.update(order)
            await self.notification_service.send_order_confirmation(order)
            logger.info("Payment %s succeeded for order %s", charge_id, order.order_id)
            return True
        except Exception as exc:
            logger.error("Payment failed for order %s: %s", order.order_id, exc)
            order.cancel()
            self.db.update(order)
            return False

    async def ship_order(self, order_id: int, tracking_number: str) -> Order:
        """Mark order as shipped and notify user."""
        order = self.get_order(order_id)
        if not order:
            raise OrderValidationError(f"Order {order_id} not found")
        order.ship(tracking_number)
        self.db.update(order)
        await self.notification_service.send_shipping_notification(order)
        logger.info("Order %s shipped with tracking %s", order_id, tracking_number)
        return order

    def cancel_order(self, order_id: int, user: User) -> Order:
        """Cancel an order if the user owns it and it is cancellable."""
        order = self.get_order(order_id)
        if not order:
            raise OrderValidationError(f"Order {order_id} not found")
        if order.user.user_id != user.user_id and not user.is_admin():
            raise PermissionError("Not authorised to cancel this order")
        if not order.is_cancellable():
            raise OrderValidationError(f"Order {order_id} cannot be cancelled")
        order.cancel()
        self.db.update(order)
        return order

    def calculate_order_total(self, items: list[OrderItem],
                               discount_pct: Decimal = Decimal("0")) -> dict:
        """Return a breakdown of order totals."""
        subtotal = sum(i.subtotal() for i in items)
        tax = sum(i.tax_amount() for i in items)
        discount = (subtotal * discount_pct / 100).quantize(Decimal("0.01"))
        total = subtotal + tax - discount
        return {
            "subtotal": subtotal,
            "tax": tax,
            "discount": discount,
            "total": total,
        }
