from django.conf import settings
from django.db import models


class Category(models.TextChoices):
    LINES = "lines", "Lines"
    PICKS = "picks", "Picks"
    GAMES = "games", "Games"
    STANDINGS = "standings", "Standings"
    SETTINGS = "settings", "Settings"
    MEMBERSHIP = "membership", "Membership"
    SECURITY = "security", "Security"
    NOTIFICATIONS = "notifications", "Notifications"


class ActorType(models.TextChoices):
    MEMBER = "member", "Member"
    COMMISSIONER = "commissioner", "Commissioner"
    ADMIN = "admin", "Admin"
    SYSTEM = "system", "System"


class ActivityEvent(models.Model):
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    league = models.ForeignKey(
        "leagues.League",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_events",
    )
    league_week = models.ForeignKey(
        "leagues.LeagueWeek",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_events",
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    event_type = models.CharField(max_length=48)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_events",
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_events_about",
    )
    object_type = models.CharField(max_length=32, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    summary = models.CharField(max_length=255)
    source = models.CharField(max_length=32)
    request_id = models.CharField(max_length=32)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("-id",)
        indexes = (
            models.Index(fields=("league", "occurred_at")),
            models.Index(fields=("league", "league_week", "category")),
            models.Index(fields=("actor", "occurred_at")),
            models.Index(fields=("subject_user", "occurred_at")),
            models.Index(fields=("object_type", "object_id")),
        )

    def __str__(self) -> str:
        return f"{self.occurred_at:%Y-%m-%d %H:%M} {self.event_type}: {self.summary}"
