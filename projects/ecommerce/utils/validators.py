"""Input validation utilities."""
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
PHONE_REGEX = re.compile(r"^\+?[1-9]\d{6,14}$")
SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKU_REGEX = re.compile(r"^[A-Z0-9\-]{3,20}$")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 5000


class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_email(email: Any) -> str:
    """Validate and normalise an email address."""
    if not isinstance(email, str):
        raise ValidationError("email", "Must be a string")
    email = email.strip().lower()
    if not EMAIL_REGEX.match(email):
        raise ValidationError("email", f"Invalid email format: {email!r}")
    return email


def validate_password(password: Any) -> str:
    """Validate password strength."""
    if not isinstance(password, str):
        raise ValidationError("password", "Must be a string")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError("password", f"Must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError("password", "Password too long")
    return password


def validate_phone(phone: Any) -> str:
    if not isinstance(phone, str):
        raise ValidationError("phone", "Must be a string")
    phone = phone.strip().replace(" ", "").replace("-", "")
    if not PHONE_REGEX.match(phone):
        raise ValidationError("phone", f"Invalid phone number: {phone!r}")
    return phone


def validate_price(value: Any) -> Decimal:
    """Ensure value is a valid non-negative price."""
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        raise ValidationError("price", f"Cannot parse as decimal: {value!r}")
    if price < Decimal("0"):
        raise ValidationError("price", "Price cannot be negative")
    if price > Decimal("99999.99"):
        raise ValidationError("price", "Price exceeds maximum allowed value")
    return price.quantize(Decimal("0.01"))


def validate_quantity(value: Any) -> int:
    """Ensure value is a positive integer quantity."""
    try:
        qty = int(value)
    except (TypeError, ValueError):
        raise ValidationError("quantity", f"Cannot parse as integer: {value!r}")
    if qty <= 0:
        raise ValidationError("quantity", "Quantity must be positive")
    if qty > 9999:
        raise ValidationError("quantity", "Quantity exceeds allowed maximum")
    return qty


def validate_slug(slug: Any) -> str:
    if not isinstance(slug, str):
        raise ValidationError("slug", "Must be a string")
    slug = slug.strip().lower()
    if not SLUG_REGEX.match(slug):
        raise ValidationError("slug", f"Invalid slug format: {slug!r}")
    return slug


def validate_sku(sku: Any) -> str:
    if not isinstance(sku, str):
        raise ValidationError("sku", "Must be a string")
    sku = sku.strip().upper()
    if not SKU_REGEX.match(sku):
        raise ValidationError("sku", f"Invalid SKU format: {sku!r}")
    return sku


def validate_name(name: Any, field: str = "name") -> str:
    if not isinstance(name, str):
        raise ValidationError(field, "Must be a string")
    name = name.strip()
    if not name:
        raise ValidationError(field, "Cannot be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(field, f"Too long (max {MAX_NAME_LENGTH} chars)")
    return name


def validate_description(text: Any) -> str:
    if not isinstance(text, str):
        raise ValidationError("description", "Must be a string")
    if len(text) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError("description", f"Too long (max {MAX_DESCRIPTION_LENGTH} chars)")
    return text.strip()


def validate_required_fields(data: dict, required: list[str]) -> None:
    """Raise ValidationError for any missing required field."""
    for field_name in required:
        if field_name not in data or data[field_name] is None:
            raise ValidationError(field_name, "This field is required")


def sanitise_string(value: str, max_length: Optional[int] = None) -> str:
    """Strip HTML tags and control characters from a string."""
    cleaned = re.sub(r"<[^>]+>", "", value)
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)
    cleaned = cleaned.strip()
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned
