from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.activity.services import prune_ip_addresses


class Command(BaseCommand):
    help = "Remove IP addresses from activity events older than 90 days. Run daily."

    def handle(self, *args: Any, **options: Any) -> None:
        count = prune_ip_addresses(timezone.now())
        self.stdout.write(f"Cleared IP addresses on {count} events.")
