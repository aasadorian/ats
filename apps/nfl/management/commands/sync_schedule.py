from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.nfl.feeds.espn import EspnFeedError, EspnScheduleProvider
from apps.nfl.services import sync_schedule


def current_season_year() -> int:
    today = timezone.localdate()
    return today.year if today.month >= 3 else today.year - 1


class Command(BaseCommand):
    help = "Import or refresh the NFL regular-season schedule from ESPN."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--season", type=int, default=None)
        parser.add_argument("--week", type=int, action="append", dest="weeks")

    def handle(self, *args: Any, **options: Any) -> None:
        season = options["season"] or current_season_year()
        try:
            result = sync_schedule(
                EspnScheduleProvider(), season_year=season, weeks=options["weeks"]
            )
        except EspnFeedError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f"Season {season}: {result.weeks} weeks, "
            f"{result.games_created} games created, "
            f"{result.games_updated} updated."
        )
        for game in result.rescheduled:
            self.stdout.write(f"Rescheduled: {game}")
        for game in result.postponed:
            self.stdout.write(f"Postponed: {game}")
