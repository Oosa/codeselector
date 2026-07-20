"""Product and inventory models."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
from datetime import datetime

TAX_RATE_STANDARD = Decimal("0.20")
TAX_RATE_REDUCED = Decimal("0.05")
TAX_RATE_ZERO = Decimal("0.00")

CATEGORY_ELECTRONICS = "electronics"
CATEGORY_CLOTHING = "clothing"
CATEGORY_FOOD = "food"

LOW_STOCK_THRESHOLD = 10


@dataclass
class Category:
    category_id: int
    name: str
    slug: str
    parent_id: Optional[int] = None
    description: str = ""


@dataclass
class ProductImage:
    url: str
    alt_text: str = ""
    is_primary: bool = False
    sort_order: int = 0


class Product:
    """A product listed in the store."""

    def __init__(
        self,
        product_id: int,
        name: str,
        sku: str,
        price: Decimal,
        category: Category,
        tax_category: str = "standard",
    ):
        self.product_id = product_id
        self.name = name
        self.sku = sku
        self.price = price
        self.category = category
        self.tax_category = tax_category
        self.images: list[ProductImage] = []
        self.stock_quantity: int = 0
        self.is_active: bool = True
        self.created_at = datetime.utcnow()
        self._discount_pct: Decimal = Decimal("0")

    def get_tax_rate(self) -> Decimal:
        """Return applicable tax rate based on tax_category."""
        if self.tax_category == "reduced":
            return TAX_RATE_REDUCED
        if self.tax_category == "zero":
            return TAX_RATE_ZERO
        return TAX_RATE_STANDARD

    def get_price_with_tax(self) -> Decimal:
        """Compute final price including tax and any active discount."""
        discounted = self.price * (1 - self._discount_pct / 100)
        tax = discounted * self.get_tax_rate()
        return (discounted + tax).quantize(Decimal("0.01"))

    def apply_discount(self, pct: Decimal) -> None:
        """Set a percentage discount (0–100)."""
        if not (Decimal("0") <= pct <= Decimal("100")):
            raise ValueError(f"Discount must be 0–100, got {pct}")
        self._discount_pct = pct

    def remove_discount(self) -> None:
        self._discount_pct = Decimal("0")

    def add_stock(self, qty: int) -> int:
        if qty <= 0:
            raise ValueError("Stock quantity to add must be positive")
        self.stock_quantity += qty
        return self.stock_quantity

    def reserve_stock(self, qty: int) -> bool:
        """Reserve stock for an order. Returns False if insufficient."""
        if self.stock_quantity < qty:
            return False
        self.stock_quantity -= qty
        return True

    def is_low_stock(self) -> bool:
        return 0 < self.stock_quantity <= LOW_STOCK_THRESHOLD

    def is_out_of_stock(self) -> bool:
        return self.stock_quantity <= 0

    def primary_image(self) -> Optional[ProductImage]:
        for img in self.images:
            if img.is_primary:
                return img
        return self.images[0] if self.images else None

    def __repr__(self) -> str:
        return f"Product(id={self.product_id}, sku={self.sku!r}, price={self.price})"


class ProductVariant(Product):
    """A size/colour variant of a base product."""

    def __init__(self, base_product: Product, variant_id: int,
                 attributes: dict, price_modifier: Decimal = Decimal("0")):
        super().__init__(
            product_id=variant_id,
            name=base_product.name,
            sku=f"{base_product.sku}-V{variant_id}",
            price=base_product.price + price_modifier,
            category=base_product.category,
            tax_category=base_product.tax_category,
        )
        self.base_product = base_product
        self.attributes = attributes  # e.g. {"color": "red", "size": "M"}
        self.price_modifier = price_modifier


# --- property accessors added for CodeSelector decorator tests ---
class ProductCatalogue:
    """Read-only view over a list of products."""

    def __init__(self, products: list):
        self._products = products
        self._active_filter: bool = True

    @property
    def active_only(self) -> bool:
        return self._active_filter

    @active_only.setter
    def active_only(self, value: bool) -> None:
        self._active_filter = value

    @property
    def count(self) -> int:
        return len(self._products)

    @property
    def visible(self) -> list:
        if self._active_filter:
            return [p for p in self._products if p.is_active]
        return list(self._products)
