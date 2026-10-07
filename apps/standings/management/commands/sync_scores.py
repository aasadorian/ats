from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.activity.context import event_context
from apps.nfl.feeds.espn import EspnFeedError, EspnScheduleProvider
from apps.nfl.management.commands.sync_schedule import current_season_year
from apps.nfl.services import sync_scores
from apps.standings.services import update_week_statuses


class Command(BaseCommand):
    help = (
        "Update scores for games that have kicked off and aren't final, then "
        "advance week statuses. Makes no feed requests when nothing is live; "
        "run every 5 minutes."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        now = timezone.now()
        try:
            with event_context("job:sync_scores"):
                result = sync_scores(
                    EspnScheduleProvider(), season_year=current_season_year(), now=now
                )
                changes = update_week_statuses(now)
        except EspnFeedError as exc:
            raise CommandError(str(exc)) from exc

        if result is not None:
            self.stdout.write(f"Updated {result.games_updated} games.")
            for game in result.finals:
                self.stdout.write(f"Final: {game}")
        for change in changes:
            self.stdout.write(change)
