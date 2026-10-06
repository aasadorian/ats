from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.activity.context import event_context
from apps.lines.feeds.odds_api import OddsApiProvider, OddsFeedError
from apps.lines.services import lock_spreads, refresh_off_lines


class Command(BaseCommand):
    help = (
        "Lock lines for weeks past their spread lock time, then post or void lines "
        "for games that were off the board. Safe to run every 15 minutes."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        provider = OddsApiProvider(settings.ODDS_API_KEY)
        try:
            with event_context("job:lock_spreads"):
                locked = lock_spreads(provider)
                refreshed = refresh_off_lines(provider)
        except OddsFeedError as exc:
            raise CommandError(str(exc)) from exc

        for week in locked.weeks_published + refreshed.weeks_published:
            self.stdout.write(f"Published {week}")
        self.stdout.write(
            f"Lines posted: {locked.lines_posted + refreshed.lines_posted}, "
            f"off: {locked.lines_off}, voided: {refreshed.lines_voided}"
        )
        for game in locked.low_book_games:
            self.stdout.write(f"Fewer than 3 books: {game}")
