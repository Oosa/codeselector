"""User domain models."""
import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


ROLE_ADMIN = "admin"
ROLE_CUSTOMER = "customer"
ROLE_GUEST = "guest"
PASSWORD_HASH_ITERATIONS = 100_000


@dataclass
class Address:
    """Postal address."""
    street: str
    city: str
    country: str
    zip_code: str
    is_default: bool = False


@dataclass
class UserProfile:
    """Extended user profile information."""
    bio: str = ""
    avatar_url: str = ""
    phone: str = ""
    birth_date: Optional[datetime] = None


class User:
    """Core user entity."""

    def __init__(self, user_id: int, email: str, role: str = ROLE_CUSTOMER):
        self.user_id = user_id
        self.email = email
        self.role = role
        self._password_hash: str = ""
        self.profile = UserProfile()
        self.addresses: list[Address] = []
        self.created_at = datetime.utcnow()
        self.is_active = True
        self._login_attempts = 0

    def set_password(self, raw_password: str) -> None:
        """Hash and store the user's password."""
        salt = os.urandom(16).hex()
        hashed = hashlib.pbkdf2_hmac(
            "sha256",
            raw_password.encode(),
            salt.encode(),
            PASSWORD_HASH_ITERATIONS,
        )
        self._password_hash = f"{salt}:{hashed.hex()}"

    def check_password(self, raw_password: str) -> bool:
        """Verify a raw password against the stored hash."""
        if not self._password_hash:
            return False
        salt, stored = self._password_hash.split(":", 1)
        hashed = hashlib.pbkdf2_hmac(
            "sha256",
            raw_password.encode(),
            salt.encode(),
            PASSWORD_HASH_ITERATIONS,
        )
        return hashed.hex() == stored

    def add_address(self, address: Address) -> None:
        """Add a shipping address. First address becomes default."""
        if not self.addresses:
            address.is_default = True
        self.addresses.append(address)

    def get_default_address(self) -> Optional[Address]:
        """Return the default shipping address."""
        for addr in self.addresses:
            if addr.is_default:
                return addr
        return None

    def increment_login_attempts(self) -> int:
        self._login_attempts += 1
        return self._login_attempts

    def reset_login_attempts(self) -> None:
        self._login_attempts = 0

    def deactivate(self) -> None:
        self.is_active = False

    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def __repr__(self) -> str:
        return f"User(id={self.user_id}, email={self.email!r}, role={self.role!r})"


class AnonymousUser:
    """Sentinel for unauthenticated requests."""
    role = ROLE_GUEST
    is_active = False
    user_id = None

    def is_admin(self) -> bool:
        return False

    def check_password(self, _: str) -> bool:
        return False
