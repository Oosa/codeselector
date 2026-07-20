"""Background workers for notifications and reminders."""
import asyncio
import logging
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Optional, Callable

from core.task import Task, Project, STATUS_DONE, STATUS_CANCELLED

logger = logging.getLogger(__name__)

REMINDER_LOOKAHEAD_HOURS = 24
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 2   # seconds
BATCH_SIZE = 50


@dataclass
class NotificationPayload:
    recipient_email: str
    subject: str
    body: str
    task_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    retries: int = 0


class EmailSender:
    """Low-level SMTP email sender."""

    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._connection: Optional[smtplib.SMTP] = None

    def connect(self) -> None:
        self._connection = smtplib.SMTP(self.host, self.port)
        self._connection.starttls()
        self._connection.login(self.username, self.password)

    def disconnect(self) -> None:
        if self._connection:
            self._connection.quit()
            self._connection = None

    def send(self, payload: NotificationPayload) -> bool:
        """Send a single email. Returns True on success."""
        if not self._connection:
            self.connect()
        msg = MIMEText(payload.body, "html")
        msg["Subject"] = payload.subject
        msg["From"] = self.username
        msg["To"] = payload.recipient_email
        try:
            self._connection.sendmail(self.username, payload.recipient_email, msg.as_string())
            payload.sent_at = datetime.utcnow()
            return True
        except smtplib.SMTPException as exc:
            logger.error("SMTP error sending to %s: %s", payload.recipient_email, exc)
            return False

    def send_batch(self, payloads: list[NotificationPayload]) -> tuple[int, int]:
        """Send a batch. Returns (sent_count, failed_count)."""
        sent = failed = 0
        for payload in payloads:
            if self.send(payload):
                sent += 1
            else:
                failed += 1
        return sent, failed


class NotificationWorker:
    """Async worker: polls for due reminders and sends emails."""

    def __init__(self, task_repo, user_repo, email_sender: EmailSender):
        self.task_repo = task_repo
        self.user_repo = user_repo
        self.email_sender = email_sender
        self._queue: list[NotificationPayload] = []
        self._running = False
        self._processed_count = 0
        self._failed_count = 0

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        logger.info("NotificationWorker started")
        await asyncio.gather(
            self._poll_due_tasks(),
            self._drain_queue(),
        )

    async def stop(self) -> None:
        self._running = False
        logger.info("NotificationWorker stopped. Processed=%d failed=%d",
                    self._processed_count, self._failed_count)

    async def _poll_due_tasks(self) -> None:
        """Periodically scan for tasks due within REMINDER_LOOKAHEAD_HOURS."""
        while self._running:
            try:
                cutoff = datetime.utcnow() + timedelta(hours=REMINDER_LOOKAHEAD_HOURS)
                due_tasks = self.task_repo.find_due_before(cutoff)
                for task in due_tasks:
                    await self._enqueue_reminder(task)
            except Exception as exc:
                logger.error("Error polling due tasks: %s", exc)
            await asyncio.sleep(300)  # poll every 5 minutes

    async def _enqueue_reminder(self, task: Task) -> None:
        if task.status in (STATUS_DONE, STATUS_CANCELLED):
            return
        if not task.assignee_id:
            return
        user = self.user_repo.find_by_id(task.assignee_id)
        if not user:
            return
        payload = NotificationPayload(
            recipient_email=user.email,
            subject=f"Reminder: '{task.title}' is due soon",
            body=self._render_reminder_email(task, user),
            task_id=task.task_id,
        )
        self._queue.append(payload)

    async def _drain_queue(self) -> None:
        """Send queued notifications in batches."""
        while self._running:
            if self._queue:
                batch = self._queue[:BATCH_SIZE]
                self._queue = self._queue[BATCH_SIZE:]
                await self._send_batch_with_retry(batch)
            await asyncio.sleep(10)

    async def _send_batch_with_retry(self, batch: list[NotificationPayload]) -> None:
        for payload in batch:
            success = False
            for attempt in range(MAX_RETRY_ATTEMPTS):
                try:
                    success = self.email_sender.send(payload)
                    if success:
                        self._processed_count += 1
                        break
                except Exception as exc:
                    logger.warning("Attempt %d failed for %s: %s",
                                   attempt + 1, payload.recipient_email, exc)
                    wait = RETRY_BACKOFF_BASE ** attempt
                    await asyncio.sleep(wait)
            if not success:
                self._failed_count += 1
                logger.error("All retries failed for %s task=%s",
                             payload.recipient_email, payload.task_id)

    def _render_reminder_email(self, task: Task, user) -> str:
        due_str = task.due_date.strftime("%Y-%m-%d %H:%M") if task.due_date else "unknown"
        return (
            f"<p>Hi {getattr(user, 'email', 'there')},</p>"
            f"<p>Task <strong>{task.title}</strong> is due on {due_str}.</p>"
            f"<p>Current status: {task.status}</p>"
        )

    def queue_size(self) -> int:
        return len(self._queue)

    def stats(self) -> dict:
        return {
            "processed": self._processed_count,
            "failed": self._failed_count,
            "queued": self.queue_size(),
            "running": self._running,
        }
