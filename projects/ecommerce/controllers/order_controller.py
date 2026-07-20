"""HTTP handlers for order endpoints."""
import json
import logging
from decimal import Decimal
from typing import Optional

from services.order_service import OrderService, OrderValidationError, InsufficientStockError
from services.auth_service import AuthService, AuthError
from models.user import User

logger = logging.getLogger(__name__)

HTTP_200 = 200
HTTP_201 = 201
HTTP_400 = 400
HTTP_401 = 401
HTTP_403 = 403
HTTP_404 = 404
HTTP_500 = 500


def _json_response(data: dict, status: int = HTTP_200) -> dict:
    return {"status": status, "body": json.dumps(data)}


def _error_response(message: str, status: int) -> dict:
    return _json_response({"error": message}, status)


class OrderController:
    """REST controller: maps HTTP requests to OrderService calls."""

    def __init__(self, order_service: OrderService, auth_service: AuthService):
        self.order_service = order_service
        self.auth_service = auth_service

    def _authenticate(self, request: dict) -> Optional[User]:
        token = request.get("headers", {}).get("Authorization", "").replace("Bearer ", "")
        return self.auth_service.validate_token(token)

    async def create_order(self, request: dict) -> dict:
        """POST /orders — create a new order from the user's cart."""
        user = self._authenticate(request)
        if not user:
            return _error_response("Unauthorised", HTTP_401)
        try:
            body = json.loads(request.get("body", "{}"))
            cart = body.get("cart")
            address = body.get("shipping_address")
            payment_method = body.get("payment_method", "stripe")
            order = self.order_service.create_order_from_cart(cart, address, payment_method)
            paid = await self.order_service.process_payment(order)
            if not paid:
                return _error_response("Payment failed", HTTP_400)
            return _json_response({"order_id": order.order_id}, HTTP_201)
        except OrderValidationError as exc:
            return _error_response(str(exc), HTTP_400)
        except InsufficientStockError as exc:
            return _error_response(str(exc), HTTP_400)
        except Exception as exc:
            logger.error("Unexpected error in create_order: %s", exc)
            return _error_response("Internal error", HTTP_500)

    async def get_order(self, request: dict, order_id: int) -> dict:
        """GET /orders/{id} — retrieve order details."""
        user = self._authenticate(request)
        if not user:
            return _error_response("Unauthorised", HTTP_401)
        order = self.order_service.get_order(order_id)
        if not order:
            return _error_response("Order not found", HTTP_404)
        if order.user.user_id != user.user_id and not user.is_admin():
            return _error_response("Forbidden", HTTP_403)
        return _json_response({
            "order_id": order.order_id,
            "status": order.status,
            "total": str(order.total_amount()),
        })

    async def list_user_orders(self, request: dict) -> dict:
        """GET /orders — list current user's orders."""
        user = self._authenticate(request)
        if not user:
            return _error_response("Unauthorised", HTTP_401)
        orders = self.order_service.get_user_orders(user)
        return _json_response({"orders": [
            {"order_id": o.order_id, "status": o.status, "total": str(o.total_amount())}
            for o in orders
        ]})

    async def cancel_order(self, request: dict, order_id: int) -> dict:
        """DELETE /orders/{id} — cancel an order."""
        user = self._authenticate(request)
        if not user:
            return _error_response("Unauthorised", HTTP_401)
        try:
            order = self.order_service.cancel_order(order_id, user)
            return _json_response({"order_id": order.order_id, "status": order.status})
        except PermissionError as exc:
            return _error_response(str(exc), HTTP_403)
        except OrderValidationError as exc:
            return _error_response(str(exc), HTTP_400)

    async def ship_order(self, request: dict, order_id: int) -> dict:
        """POST /orders/{id}/ship — admin: mark order as shipped."""
        user = self._authenticate(request)
        if not user:
            return _error_response("Unauthorised", HTTP_401)
        try:
            self.auth_service.require_admin(user)
        except AuthError:
            return _error_response("Forbidden", HTTP_403)
        body = json.loads(request.get("body", "{}"))
        tracking = body.get("tracking_number", "")
        if not tracking:
            return _error_response("tracking_number required", HTTP_400)
        try:
            order = await self.order_service.ship_order(order_id, tracking)
            return _json_response({"order_id": order.order_id, "status": order.status})
        except OrderValidationError as exc:
            return _error_response(str(exc), HTTP_400)
