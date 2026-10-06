from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.activity.context import event_context
from apps.leagues.services import create_league
from apps.nfl.models import Season


class Command(BaseCommand):
    help = "Create a league for a season with its first commissioner."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--season", type=int, required=True)
        parser.add_argument("--commissioner-email", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        email = options["commissioner_email"].lower()
        commissioner = User.objects.filter(email=email).first()
        if commissioner is None:
            raise CommandError(f"No user with email {email}; create it first.")
        if not Season.objects.filter(year=options["season"]).exists():
            raise CommandError(
                f"Season {options['season']} not loaded; run sync_schedule first."
            )
        with event_context("command:create_league"):
            league = create_league(
                name=options["name"],
                slug=options["slug"],
                commissioner=commissioner,
                season_year=options["season"],
            )
        self.stdout.write(f"Created league {league} ({league.slug}).")
