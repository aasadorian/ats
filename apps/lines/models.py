from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.leagues.models import LeagueSeason
from apps.nfl.models import Game


class SpreadKind(models.TextChoices):
    LOCKED = "locked", "Locked at spread lock"
    CLOSING = "closing", "Closing line"


class SpreadStatus(models.TextChoices):
    POSTED = "posted", "Posted"
    OFF = "off", "Off the board"
    VOID = "void", "Void for the week"


class Spread(models.Model):
    league_season = models.ForeignKey(
        LeagueSeason, on_delete=models.CASCADE, related_name="spreads"
    )
    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="spreads")
    kind = models.CharField(
        max_length=8, choices=SpreadKind.choices, default=SpreadKind.LOCKED
    )
    status = models.CharField(
        max_length=8, choices=SpreadStatus.choices, default=SpreadStatus.POSTED
    )
    home_line = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    feed_line = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    book_count = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(max_length=40)
    locked_at = models.DateTimeField(null=True, blank=True)
    overridden = models.BooleanField(default=False)

    class Meta:
        ordering = ("game__kickoff_at",)
        constraints = (
            models.UniqueConstraint(
                fields=("league_season", "game", "kind"), name="lines_spread_unique"
            ),
            models.CheckConstraint(
                condition=Q(status=SpreadStatus.POSTED, home_line__isnull=False)
                | ~Q(status=SpreadStatus.POSTED),
                name="lines_spread_posted_has_line",
            ),
        )

    def __str__(self) -> str:
        return f"{self.game} {format_line(self.home_line)}"

    @property
    def away_line(self) -> Decimal | None:
        return None if self.home_line is None else -self.home_line


class OddsSnapshot(models.Model):
    fetched_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=40)
    payload = models.JSONField()

    class Meta:
        ordering = ("-fetched_at",)

    def __str__(self) -> str:
        return f"{self.source} at {self.fetched_at:%Y-%m-%d %H:%M}"


def format_line(line: Decimal | None) -> str:
    if line is None:
        return "OFF"
    if line == 0:
        return "PK"
    return f"{line:+.1f}"
