"""Authentication and session management."""
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from models.user import User, AnonymousUser, ROLE_ADMIN

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 3600 * 24 * 7   # 7 days
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900         # 15 minutes
TOKEN_BYTES = 32


class AuthError(Exception):
    pass


class AccountLockedError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class AuthService:
    """Handles login, logout, token issuance and session validation."""

    def __init__(self, user_repository, session_store):
        self.user_repo = user_repository
        self.session_store = session_store
        self._lockout_registry: dict[str, float] = {}

    def login(self, email: str, password: str) -> tuple[User, str]:
        """Authenticate user and return (user, session_token)."""
        self._check_lockout(email)
        user = self.user_repo.find_by_email(email)
        if not user or not user.check_password(password):
            self._record_failed_attempt(email, user)
            raise InvalidCredentialsError("Invalid email or password")
        if not user.is_active:
            raise AuthError("Account is deactivated")
        user.reset_login_attempts()
        token = self._issue_token(user)
        logger.info("User %s logged in", user.user_id)
        return user, token

    def logout(self, token: str) -> None:
        """Invalidate a session token."""
        self.session_store.delete(token)

    def validate_token(self, token: str) -> Optional[User]:
        """Return the user for a valid token, or None."""
        session = self.session_store.get(token)
        if not session:
            return None
        if session["expires_at"] < time.time():
            self.session_store.delete(token)
            return None
        return self.user_repo.find_by_id(session["user_id"])

    def refresh_token(self, old_token: str) -> Optional[str]:
        """Rotate a session token, extending its TTL."""
        user = self.validate_token(old_token)
        if not user:
            return None
        self.session_store.delete(old_token)
        return self._issue_token(user)

    def _issue_token(self, user: User) -> str:
        token = secrets.token_hex(TOKEN_BYTES)
        self.session_store.set(token, {
            "user_id": user.user_id,
            "role": user.role,
            "expires_at": time.time() + SESSION_TTL_SECONDS,
        })
        return token

    def _check_lockout(self, email: str) -> None:
        locked_until = self._lockout_registry.get(email)
        if locked_until and time.time() < locked_until:
            remaining = int(locked_until - time.time())
            raise AccountLockedError(f"Account locked. Try again in {remaining}s")

    def _record_failed_attempt(self, email: str, user: Optional[User]) -> None:
        if user:
            attempts = user.increment_login_attempts()
            if attempts >= MAX_LOGIN_ATTEMPTS:
                self._lockout_registry[email] = time.time() + LOCKOUT_DURATION_SECONDS
                logger.warning("Account %s locked after %d failed attempts", email, attempts)

    def require_admin(self, user: User) -> None:
        """Raise AuthError if user is not an admin."""
        if not user.is_admin():
            raise AuthError("Admin privileges required")

    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not user.check_password(old_password):
            raise InvalidCredentialsError("Current password is incorrect")
        if len(new_password) < 8:
            raise ValueError("New password must be at least 8 characters")
        user.set_password(new_password)
        self.user_repo.save(user)
        logger.info("Password changed for user %s", user.user_id)
