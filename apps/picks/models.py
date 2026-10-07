from django.db import models

from apps.leagues.models import LeagueWeek, Membership
from apps.nfl.models import Game, Team, Week


class Pick(models.Model):
    membership = models.ForeignKey(
        Membership, on_delete=models.PROTECT, related_name="picks"
    )
    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="picks")
    week = models.ForeignKey(Week, on_delete=models.PROTECT, related_name="picks")
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="+")
    is_best_bet = models.BooleanField(default=False)
    home_line_at_pick = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("game__kickoff_at",)
        constraints = (
            models.UniqueConstraint(
                fields=("membership", "game"), name="picks_pick_member_game_unique"
            ),
        )
        indexes = (models.Index(fields=("membership", "week")),)

    def __str__(self) -> str:
        star = " (best bet)" if self.is_best_bet else ""
        return f"{self.membership.user}: {self.team} in {self.game}{star}"


class WeeklyEntry(models.Model):
    membership = models.ForeignKey(
        Membership, on_delete=models.PROTECT, related_name="weekly_entries"
    )
    league_week = models.ForeignKey(
        LeagueWeek, on_delete=models.PROTECT, related_name="entries"
    )
    tiebreaker_guess = models.PositiveSmallIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "weekly entries"
        constraints = (
            models.UniqueConstraint(
                fields=("membership", "league_week"),
                name="picks_weeklyentry_unique",
            ),
        )

    def __str__(self) -> str:
        return f"{self.membership.user} {self.league_week}"
