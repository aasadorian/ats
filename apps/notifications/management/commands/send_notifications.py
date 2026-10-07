from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.activity.context import event_context
from apps.notifications.services import send_notifications


class Command(BaseCommand):
    help = (
        "Send week-open emails, pick reminders and weekly results that are due. "
        "Each batch is sent once; run every 15 minutes."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        with event_context("job:send_notifications"):
            for line in send_notifications(timezone.now()):
                self.stdout.write(line)
