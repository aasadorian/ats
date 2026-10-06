from django.db import models
from django.db.models import F, Q


class Team(models.Model):
    external_id = models.CharField(max_length=32, unique=True)
    abbreviation = models.CharField(max_length=8)
    location = models.CharField(max_length=64)
    name = models.CharField(max_length=64)

    class Meta:
        ordering = ("abbreviation",)

    def __str__(self) -> str:
        return self.abbreviation

    @property
    def display_name(self) -> str:
        return f"{self.location} {self.name}"


class Season(models.Model):
    year = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ("-year",)

    def __str__(self) -> str:
        return str(self.year)


class Week(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="weeks")
    number = models.PositiveSmallIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    sunday = models.DateField()

    class Meta:
        ordering = ("season", "number")
        constraints = (
            models.UniqueConstraint(
                fields=("season", "number"), name="nfl_week_season_number_unique"
            ),
        )

    def __str__(self) -> str:
        return f"{self.season} Week {self.number}"


class GameStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    FINAL = "final", "Final"
    POSTPONED = "postponed", "Postponed"
    CANCELLED = "cancelled", "Cancelled"


class Game(models.Model):
    external_id = models.CharField(max_length=32, unique=True)
    week = models.ForeignKey(Week, on_delete=models.PROTECT, related_name="games")
    home_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="home_games"
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="away_games"
    )
    kickoff_at = models.DateTimeField()
    kickoff_is_tbd = models.BooleanField(default=False)
    postponed_from = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=GameStatus.choices, default=GameStatus.SCHEDULED
    )
    neutral_site = models.BooleanField(default=False)
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("kickoff_at", "external_id")
        indexes = (models.Index(fields=("week", "kickoff_at")),)
        constraints = (
            models.CheckConstraint(
                condition=~Q(home_team=F("away_team")),
                name="nfl_game_distinct_teams",
            ),
        )

    def __str__(self) -> str:
        return f"{self.away_team} @ {self.home_team}"
