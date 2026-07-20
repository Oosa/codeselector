"""In-memory repository implementations for all domain objects."""
import threading
from typing import Generic, TypeVar, Optional, Callable
from datetime import datetime

T = TypeVar("T")

SORT_ASC = "asc"
SORT_DESC = "desc"


class NotFoundError(Exception):
    pass


class DuplicateKeyError(Exception):
    pass


class BaseRepository(Generic[T]):
    """Thread-safe in-memory store with basic CRUD."""

    def __init__(self, id_attr: str = "id"):
        self._store: dict[str, T] = {}
        self._id_attr = id_attr
        self._lock = threading.RLock()
        self._write_count = 0
        self._read_count = 0

    def save(self, entity: T) -> T:
        key = str(getattr(entity, self._id_attr))
        with self._lock:
            self._store[key] = entity
            self._write_count += 1
        return entity

    def find(self, entity_id: str) -> Optional[T]:
        with self._lock:
            self._read_count += 1
            return self._store.get(str(entity_id))

    def find_or_raise(self, entity_id: str) -> T:
        entity = self.find(entity_id)
        if entity is None:
            raise NotFoundError(f"Entity {entity_id!r} not found")
        return entity

    def delete(self, entity_id: str) -> bool:
        with self._lock:
            key = str(entity_id)
            if key in self._store:
                del self._store[key]
                self._write_count += 1
                return True
        return False

    def all(self) -> list[T]:
        with self._lock:
            self._read_count += 1
            return list(self._store.values())

    def count(self) -> int:
        with self._lock:
            return len(self._store)

    def exists(self, entity_id: str) -> bool:
        with self._lock:
            return str(entity_id) in self._store

    def find_where(self, predicate: Callable[[T], bool]) -> list[T]:
        with self._lock:
            self._read_count += 1
            return [e for e in self._store.values() if predicate(e)]

    def find_first(self, predicate: Callable[[T], bool]) -> Optional[T]:
        with self._lock:
            for entity in self._store.values():
                if predicate(entity):
                    return entity
        return None

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._write_count += 1

    def stats(self) -> dict:
        return {
            "count": self.count(),
            "reads": self._read_count,
            "writes": self._write_count,
        }


class TaskRepository(BaseRepository):
    """Repository for Task entities."""

    def __init__(self):
        super().__init__(id_attr="task_id")

    def find_by_project(self, project_id: str) -> list:
        return self.find_where(lambda t: t.project_id == project_id)

    def find_by_assignee(self, user_id: str) -> list:
        return self.find_where(lambda t: t.assignee_id == user_id)

    def find_due_before(self, cutoff: datetime) -> list:
        return self.find_where(
            lambda t: t.due_date is not None and t.due_date <= cutoff
        )

    def find_overdue(self) -> list:
        return self.find_where(lambda t: t.is_overdue())

    def find_unassigned(self) -> list:
        return self.find_where(lambda t: t.is_unassigned())

    def search_by_title(self, keyword: str) -> list:
        kw = keyword.lower()
        return self.find_where(lambda t: kw in t.title.lower())


class ProjectRepository(BaseRepository):
    """Repository for Project entities."""

    def __init__(self):
        super().__init__(id_attr="project_id")

    def find_by_owner(self, owner_id: str) -> list:
        return self.find_where(lambda p: p.owner_id == owner_id)

    def find_by_member(self, user_id: str) -> list:
        return self.find_where(lambda p: user_id in p.members)

    def find_active(self) -> list:
        return self.find_where(lambda p: not p.is_archived)

    def find_archived(self) -> list:
        return self.find_where(lambda p: p.is_archived)


class UserRepository(BaseRepository):
    """Simple user store for the task manager."""

    def __init__(self):
        super().__init__(id_attr="user_id")
        self._email_index: dict[str, str] = {}

    def save(self, entity) -> object:
        result = super().save(entity)
        if hasattr(entity, "email"):
            self._email_index[entity.email] = str(entity.user_id)
        return result

    def find_by_email(self, email: str) -> Optional[object]:
        user_id = self._email_index.get(email)
        if not user_id:
            return None
        return self.find(user_id)

    def find_by_id(self, user_id: str) -> Optional[object]:
        return self.find(user_id)
