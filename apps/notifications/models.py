from django.conf import settings
from django.db import models

from apps.leagues.models import LeagueWeek


class Kind(models.TextChoices):
    WEEK_OPEN = "week_open", "Week open for picks"
    REMINDERS = "reminders", "Pick reminders"
    WEEKLY_RESULTS = "weekly_results", "Weekly results"
    PICKS_ENTERED = "picks_entered", "A commissioner changed my picks"
    COMMISSIONER = "commissioner", "Commissioner notices (lines to review)"


class NotificationPreference(models.Model):
    """Opt-outs only: a missing row means the email is enabled."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("user", "kind"), name="notifications_preference_unique"
            ),
        )

    def __str__(self) -> str:
        return f"{self.user} {self.kind}={'on' if self.enabled else 'off'}"


class Dispatch(models.Model):
    """One row per notification batch sent, so the job never sends twice."""

    kind = models.CharField(max_length=20, choices=Kind.choices)
    league_week = models.ForeignKey(
        LeagueWeek, on_delete=models.CASCADE, related_name="dispatches"
    )
    key = models.CharField(max_length=40, blank=True)
    sent_at = models.DateTimeField()
    recipients = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-sent_at",)
        constraints = (
            models.UniqueConstraint(
                fields=("kind", "league_week", "key"),
                name="notifications_dispatch_unique",
            ),
        )

    def __str__(self) -> str:
        return f"{self.kind} {self.league_week} {self.key}"
