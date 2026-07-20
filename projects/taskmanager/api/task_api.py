"""REST API handlers for task management."""
import json
import logging
from typing import Optional

from core.task import Task, Project, PRIORITY_MEDIUM, STATUS_TODO

logger = logging.getLogger(__name__)

VALID_STATUSES = {"todo", "in_progress", "blocked", "done", "cancelled"}
VALID_PRIORITIES = {1, 2, 3, 4}


def json_ok(data: dict, status: int = 200) -> dict:
    return {"status": status, "body": json.dumps(data)}


def json_error(msg: str, status: int = 400) -> dict:
    return {"status": status, "body": json.dumps({"error": msg})}


def parse_body(request: dict) -> dict:
    try:
        return json.loads(request.get("body") or "{}")
    except json.JSONDecodeError:
        return {}


class TaskAPI:
    """CRUD + lifecycle endpoints for tasks."""

    def __init__(self, task_repo, project_repo, auth_middleware):
        self.task_repo = task_repo
        self.project_repo = project_repo
        self.auth = auth_middleware
        self._temp_ids: list[str] = []

    def get_task(self, request: dict, task_id: str) -> dict:
        """GET /tasks/{id}"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        task = self.task_repo.find(task_id)
        if not task:
            return json_error("Task not found", 404)
        if not self._can_view(user, task):
            return json_error("Forbidden", 403)
        return json_ok(self._serialise_task(task))

    def create_task(self, request: dict) -> dict:
        """POST /tasks"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        body = parse_body(request)
        title = body.get("title", "").strip()
        if not title:
            return json_error("title is required")
        project_id = body.get("project_id", "")
        project = self.project_repo.find(project_id)
        if not project:
            return json_error("Project not found", 404)
        if not self._is_project_member(user, project):
            return json_error("Forbidden", 403)
        task = Task(
            title=title,
            project_id=project_id,
            assignee_id=body.get("assignee_id"),
            priority=body.get("priority", PRIORITY_MEDIUM),
        )
        task.description = body.get("description", "")
        if body.get("due_date"):
            from datetime import datetime
            task.due_date = datetime.fromisoformat(body["due_date"])
        self.task_repo.save(task)
        self._temp_ids.append(task.task_id)
        logger.info("Task %s created in project %s", task.task_id, project_id)
        return json_ok({"task_id": task.task_id}, 201)

    def update_task(self, request: dict, task_id: str) -> dict:
        """PATCH /tasks/{id}"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        task = self.task_repo.find(task_id)
        if not task:
            return json_error("Task not found", 404)
        if not self._can_edit(user, task):
            return json_error("Forbidden", 403)
        body = parse_body(request)
        if "title" in body:
            task.title = body["title"].strip()
        if "description" in body:
            task.description = body["description"]
        if "priority" in body:
            if body["priority"] not in VALID_PRIORITIES:
                return json_error(f"priority must be one of {VALID_PRIORITIES}")
            task.priority = body["priority"]
        if "assignee_id" in body:
            task.reassign(body["assignee_id"])
        self.task_repo.save(task)
        return json_ok({"task_id": task_id})

    def transition_status(self, request: dict, task_id: str) -> dict:
        """POST /tasks/{id}/status"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        task = self.task_repo.find(task_id)
        if not task:
            return json_error("Task not found", 404)
        body = parse_body(request)
        new_status = body.get("status", "")
        if new_status not in VALID_STATUSES:
            return json_error(f"Invalid status: {new_status!r}")
        try:
            self._apply_transition(task, new_status, body)
        except ValueError as exc:
            return json_error(str(exc))
        self.task_repo.save(task)
        return json_ok({"task_id": task_id, "status": task.status})

    def delete_task(self, request: dict, task_id: str) -> dict:
        """DELETE /tasks/{id}"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        task = self.task_repo.find(task_id)
        if not task:
            return json_error("Task not found", 404)
        if not self._can_edit(user, task):
            return json_error("Forbidden", 403)
        self.task_repo.delete(task_id)
        return json_ok({"deleted": task_id})

    def list_project_tasks(self, request: dict, project_id: str) -> dict:
        """GET /projects/{id}/tasks"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        project = self.project_repo.find(project_id)
        if not project:
            return json_error("Project not found", 404)
        params = request.get("query", {})
        tasks = self.task_repo.find_by_project(project_id)
        tasks = self._apply_filters(tasks, params)
        return json_ok({"tasks": [self._serialise_task(t) for t in tasks]})

    def _apply_filters(self, tasks: list[Task], params: dict) -> list[Task]:
        if status := params.get("status"):
            tasks = [t for t in tasks if t.status == status]
        if assignee := params.get("assignee_id"):
            tasks = [t for t in tasks if t.assignee_id == assignee]
        if priority := params.get("priority"):
            tasks = [t for t in tasks if str(t.priority) == str(priority)]
        return tasks

    def _serialise_task(self, task: Task) -> dict:
        return {
            "task_id": task.task_id,
            "title": task.title,
            "status": task.status,
            "priority": task.priority,
            "assignee_id": task.assignee_id,
            "project_id": task.project_id,
            "is_overdue": task.is_overdue(),
            "completion_pct": task.completion_pct(),
        }

    def _can_view(self, user, task: Task) -> bool:
        return user.get("is_admin") or task.assignee_id == user.get("id")

    def _can_edit(self, user, task: Task) -> bool:
        return user.get("is_admin") or task.assignee_id == user.get("id")

    def _is_project_member(self, user, project: Project) -> bool:
        return user.get("is_admin") or user.get("id") in project.members

    def _apply_transition(self, task: Task, new_status: str, body: dict) -> None:
        if new_status == "in_progress":
            task.start()
        elif new_status == "done":
            task.complete(notes=body.get("notes", ""))
        elif new_status == "blocked":
            task.block(reason=body.get("reason", "Unspecified"))
        elif new_status == "cancelled":
            task.cancel()
        elif new_status == "todo":
            task.unblock()


class ProjectAPI:
    """CRUD endpoints for projects."""

    def __init__(self, project_repo, auth_middleware):
        self.project_repo = project_repo
        self.auth = auth_middleware

    def create_project(self, request: dict) -> dict:
        """POST /projects"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        body = parse_body(request)
        name = body.get("name", "").strip()
        if not name:
            return json_error("name is required")
        project = Project(
            name=name,
            owner_id=user["id"],
            description=body.get("description", ""),
        )
        self.project_repo.save(project)
        return json_ok({"project_id": project.project_id}, 201)

    def get_project(self, request: dict, project_id: str) -> dict:
        """GET /projects/{id}"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        project = self.project_repo.find(project_id)
        if not project:
            return json_error("Project not found", 404)
        return json_ok({
            "project_id": project.project_id,
            "name": project.name,
            "owner_id": project.owner_id,
            "member_count": len(project.members),
            "task_count": len(project.tasks),
            "completion_pct": project.completion_pct(),
        })

    def add_member(self, request: dict, project_id: str) -> dict:
        """POST /projects/{id}/members"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        project = self.project_repo.find(project_id)
        if not project:
            return json_error("Project not found", 404)
        if user["id"] != project.owner_id and not user.get("is_admin"):
            return json_error("Forbidden", 403)
        body = parse_body(request)
        new_user_id = body.get("user_id", "")
        if not new_user_id:
            return json_error("user_id is required")
        project.add_member(new_user_id)
        self.project_repo.save(project)
        return json_ok({"added": new_user_id})

    def archive_project(self, request: dict, project_id: str) -> dict:
        """POST /projects/{id}/archive"""
        user = self.auth.get_user(request)
        if not user:
            return json_error("Unauthorised", 401)
        project = self.project_repo.find(project_id)
        if not project:
            return json_error("Project not found", 404)
        if user["id"] != project.owner_id and not user.get("is_admin"):
            return json_error("Forbidden", 403)
        project.archive()
        self.project_repo.save(project)
        return json_ok({"archived": project_id})
