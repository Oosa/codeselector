"""Task and project core models."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

PRIORITY_LOW = 1
PRIORITY_MEDIUM = 2
PRIORITY_HIGH = 3
PRIORITY_CRITICAL = 4

STATUS_TODO = "todo"
STATUS_IN_PROGRESS = "in_progress"
STATUS_BLOCKED = "blocked"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"

DEFAULT_ESTIMATE_HOURS = 1


class TaskPriority(Enum):
    LOW = PRIORITY_LOW
    MEDIUM = PRIORITY_MEDIUM
    HIGH = PRIORITY_HIGH
    CRITICAL = PRIORITY_CRITICAL


@dataclass
class Label:
    label_id: str
    name: str
    color: str = "#cccccc"


@dataclass
class TimeEntry:
    """A time tracking entry for a task."""
    entry_id: str
    task_id: str
    user_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    description: str = ""

    def duration_minutes(self) -> int:
        if not self.ended_at:
            return int((datetime.utcnow() - self.started_at).total_seconds() / 60)
        return int((self.ended_at - self.started_at).total_seconds() / 60)

    def is_running(self) -> bool:
        return self.ended_at is None

    def stop(self) -> None:
        if self.ended_at is not None:
            raise ValueError("Time entry already stopped")
        self.ended_at = datetime.utcnow()


class Task:
    """A unit of work in a project."""

    def __init__(self, title: str, project_id: str,
                 assignee_id: Optional[str] = None,
                 priority: int = PRIORITY_MEDIUM):
        self.task_id = str(uuid.uuid4())
        self.title = title
        self.project_id = project_id
        self.assignee_id = assignee_id
        self.priority = priority
        self.status = STATUS_TODO
        self.description: str = ""
        self.labels: list[Label] = []
        self.subtasks: list["Task"] = []
        self.parent_task_id: Optional[str] = None
        self.estimate_hours: float = DEFAULT_ESTIMATE_HOURS
        self.time_entries: list[TimeEntry] = []
        self.due_date: Optional[datetime] = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self._block_reason: Optional[str] = None
        self._completion_notes: str = ""

    def start(self) -> None:
        """Transition task to in-progress."""
        if self.status == STATUS_DONE:
            raise ValueError("Cannot start a completed task")
        if self.status == STATUS_CANCELLED:
            raise ValueError("Cannot start a cancelled task")
        self.status = STATUS_IN_PROGRESS
        self.updated_at = datetime.utcnow()

    def complete(self, notes: str = "") -> None:
        """Mark task as done."""
        if self.status == STATUS_CANCELLED:
            raise ValueError("Cannot complete a cancelled task")
        for subtask in self.subtasks:
            if subtask.status not in (STATUS_DONE, STATUS_CANCELLED):
                raise ValueError(f"Subtask '{subtask.title}' is not done")
        self.status = STATUS_DONE
        self._completion_notes = notes
        self.updated_at = datetime.utcnow()

    def block(self, reason: str) -> None:
        """Mark task as blocked with a reason."""
        if self.status == STATUS_DONE:
            raise ValueError("Cannot block a completed task")
        self.status = STATUS_BLOCKED
        self._block_reason = reason
        self.updated_at = datetime.utcnow()

    def unblock(self) -> None:
        if self.status != STATUS_BLOCKED:
            raise ValueError("Task is not blocked")
        self.status = STATUS_IN_PROGRESS
        self._block_reason = None
        self.updated_at = datetime.utcnow()

    def cancel(self) -> None:
        if self.status == STATUS_DONE:
            raise ValueError("Cannot cancel a completed task")
        self.status = STATUS_CANCELLED
        self.updated_at = datetime.utcnow()

    def reassign(self, new_assignee_id: str) -> None:
        self.assignee_id = new_assignee_id
        self.updated_at = datetime.utcnow()

    def add_label(self, label: Label) -> None:
        if not any(lb.label_id == label.label_id for lb in self.labels):
            self.labels.append(label)

    def remove_label(self, label_id: str) -> bool:
        original = len(self.labels)
        self.labels = [lb for lb in self.labels if lb.label_id != label_id]
        return len(self.labels) < original

    def add_subtask(self, subtask: "Task") -> None:
        subtask.parent_task_id = self.task_id
        self.subtasks.append(subtask)

    def start_timer(self, user_id: str) -> TimeEntry:
        entry = TimeEntry(
            entry_id=str(uuid.uuid4()),
            task_id=self.task_id,
            user_id=user_id,
            started_at=datetime.utcnow(),
        )
        self.time_entries.append(entry)
        return entry

    def stop_timer(self, entry_id: str) -> TimeEntry:
        for entry in self.time_entries:
            if entry.entry_id == entry_id and entry.is_running():
                entry.stop()
                return entry
        raise ValueError(f"No running time entry with id {entry_id}")

    def total_logged_hours(self) -> float:
        return sum(e.duration_minutes() for e in self.time_entries) / 60

    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        return self.due_date < datetime.utcnow() and self.status != STATUS_DONE

    def completion_pct(self) -> int:
        if not self.subtasks:
            return 100 if self.status == STATUS_DONE else 0
        done = sum(1 for s in self.subtasks if s.status == STATUS_DONE)
        return int(done / len(self.subtasks) * 100)

    def is_unassigned(self) -> bool:
        return self.assignee_id is None

    def __repr__(self) -> str:
        return f"Task(id={self.task_id[:8]}, title={self.title!r}, status={self.status!r})"


class Project:
    """A collection of tasks."""

    def __init__(self, name: str, owner_id: str, description: str = ""):
        self.project_id = str(uuid.uuid4())
        self.name = name
        self.owner_id = owner_id
        self.description = description
        self.tasks: list[Task] = []
        self.members: list[str] = [owner_id]
        self.created_at = datetime.utcnow()
        self.is_archived = False

    def add_task(self, task: Task) -> None:
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> bool:
        original = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.task_id != task_id]
        return len(self.tasks) < original

    def add_member(self, user_id: str) -> None:
        if user_id not in self.members:
            self.members.append(user_id)

    def remove_member(self, user_id: str) -> bool:
        if user_id == self.owner_id:
            raise ValueError("Cannot remove project owner")
        original = len(self.members)
        self.members = [m for m in self.members if m != user_id]
        return len(self.members) < original

    def open_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.status not in (STATUS_DONE, STATUS_CANCELLED)]

    def overdue_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.is_overdue()]

    def tasks_by_priority(self) -> list[Task]:
        return sorted(self.tasks, key=lambda t: t.priority, reverse=True)

    def archive(self) -> None:
        self.is_archived = True

    def completion_pct(self) -> int:
        if not self.tasks:
            return 0
        done = sum(1 for t in self.tasks if t.status == STATUS_DONE)
        return int(done / len(self.tasks) * 100)
