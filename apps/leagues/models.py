from datetime import date, time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.leagues.schedule import lock_times
from apps.nfl.models import Game, Season, Week


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class League(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=40, unique=True)
    timezone = models.CharField(max_length=64, default="America/Los_Angeles")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class LeagueSeason(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name="seasons")
    season = models.ForeignKey(
        Season, on_delete=models.PROTECT, related_name="league_seasons"
    )

    class Meta:
        ordering = ("league", "-season__year")
        constraints = (
            models.UniqueConstraint(
                fields=("league", "season"), name="leagues_leagueseason_unique"
            ),
        )

    def __str__(self) -> str:
        return f"{self.league} {self.season}"


class PickType(models.TextChoices):
    AGAINST_SPREAD = "against_spread", "Against the spread"
    STRAIGHT_UP = "straight_up", "Straight up"


class GameSelection(models.TextChoices):
    ALL_GAMES = "all_games", "All games"
    COMMISSIONER_SLATE = "commissioner_slate", "Commissioner selects games"


class LineMode(models.TextChoices):
    FIXED_AT_LOCK = "fixed_at_lock", "Fixed at spread lock"
    VARIABLE = "variable", "Line when the pick is made"
    CLOSING = "closing", "Closing line"


class LineSource(models.TextChoices):
    MEDIAN_US_BOOKS = "median_us_books", "Median of US sportsbooks"


class HalfPointRounding(models.TextChoices):
    FAVORITE_GIVES = "favorite_gives", "Favorite gives the half point"
    FAVORITE_GETS = "favorite_gets", "Favorite gets the half point"


class PushScoring(models.TextChoices):
    HALF_POINTS = "half_points", "Half points"
    LOSS = "loss", "Loss"
    WIN = "win", "Win"


class OffLineHandling(models.TextChoices):
    UNPICKABLE_UNTIL_POSTED = "unpickable_until_posted", "Unpickable until posted"
    HOLD_WEEK = "hold_week", "Hold the week for the commissioner"


class OffLineCutoff(models.TextChoices):
    FIRST_KICKOFF_OF_WEEK = "first_kickoff_of_week", "First kickoff of the week"
    GAME_LOCK = "game_lock", "The game's own lock"


class OffLineFallback(models.TextChoices):
    VOID = "void", "Void for the week"
    FAVORITE_MINUS_HALF = "favorite_minus_half", "Favorite -0.5"
    PICKEM_STRAIGHT_UP = "pickem_straight_up", "Straight up"


class PickVisibility(models.TextChoices):
    AT_GAME_LOCK = "at_game_lock", "When each game locks"
    AT_WEEKLY_DEADLINE = "at_weekly_deadline", "At the weekly deadline"


class AutoPick(models.TextChoices):
    OFF = "off", "Off"
    RANDOM = "random", "Random"
    HOME = "home", "Home team"
    FAVORITE = "favorite", "Favorite"
    UNDERDOG = "underdog", "Underdog"


class TiebreakerGame(models.TextChoices):
    LAST_GAME_OF_WEEK = "last_game_of_week", "Last game of the week"
    COMMISSIONER_SELECTS = "commissioner_selects", "Commissioner selects"


class TiebreakerType(models.TextChoices):
    TOTAL_POINTS = "total_points", "Total points"
    MARGIN_OF_VICTORY = "margin_of_victory", "Margin of victory"


class WeeklyPrizeMetric(models.TextChoices):
    POINTS = "points", "Points"
    WINS = "wins", "Correct picks"


class SeasonType(models.TextChoices):
    REGULAR_SEASON = "regular_season", "Regular season"


def default_reminder_times() -> list[dict[str, object]]:
    return [
        {"weekday": Weekday.THURSDAY.value, "time": "12:00"},
        {"weekday": Weekday.SUNDAY.value, "time": "08:00"},
    ]


class LeagueSettings(models.Model):
    """Commissioner-configurable rules; field meanings are documented in docs/08."""

    league_season = models.OneToOneField(
        LeagueSeason, on_delete=models.CASCADE, related_name="settings"
    )

    pick_type = models.CharField(
        max_length=20, choices=PickType.choices, default=PickType.AGAINST_SPREAD
    )
    game_selection = models.CharField(
        max_length=20, choices=GameSelection.choices, default=GameSelection.ALL_GAMES
    )
    points_per_win = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )

    best_bets_per_week = models.PositiveSmallIntegerField(
        default=1, validators=[MaxValueValidator(5)]
    )
    best_bet_bonus = models.PositiveSmallIntegerField(default=2)
    best_bet_required = models.BooleanField(default=False)
    best_bet_team_once_per_season = models.BooleanField(default=False)

    line_mode = models.CharField(
        max_length=20, choices=LineMode.choices, default=LineMode.FIXED_AT_LOCK
    )
    spread_lock_weekday = models.PositiveSmallIntegerField(
        choices=Weekday.choices, default=Weekday.TUESDAY
    )
    spread_lock_time = models.TimeField(default=time(3, 0))
    line_source = models.CharField(
        max_length=32, choices=LineSource.choices, default=LineSource.MEDIAN_US_BOOKS
    )
    half_point_lines = models.BooleanField(default=True)
    half_point_rounding = models.CharField(
        max_length=20,
        choices=HalfPointRounding.choices,
        default=HalfPointRounding.FAVORITE_GIVES,
    )
    push_scoring = models.CharField(
        max_length=16, choices=PushScoring.choices, default=PushScoring.HALF_POINTS
    )
    off_line_handling = models.CharField(
        max_length=32,
        choices=OffLineHandling.choices,
        default=OffLineHandling.UNPICKABLE_UNTIL_POSTED,
    )
    off_line_cutoff = models.CharField(
        max_length=32,
        choices=OffLineCutoff.choices,
        default=OffLineCutoff.FIRST_KICKOFF_OF_WEEK,
    )
    off_line_fallback = models.CharField(
        max_length=32, choices=OffLineFallback.choices, default=OffLineFallback.VOID
    )

    picks_lock_weekday = models.PositiveSmallIntegerField(
        choices=Weekday.choices, default=Weekday.SUNDAY
    )
    picks_lock_time = models.TimeField(default=time(10, 0))
    game_lock_offset_minutes = models.PositiveSmallIntegerField(default=0)
    grace_period_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    pick_visibility = models.CharField(
        max_length=20,
        choices=PickVisibility.choices,
        default=PickVisibility.AT_GAME_LOCK,
    )
    future_week_picks = models.BooleanField(default=False)

    autopick = models.CharField(
        max_length=16, choices=AutoPick.choices, default=AutoPick.OFF
    )
    autopick_max_weeks = models.PositiveSmallIntegerField(default=0)
    autopick_tiebreaker_guess = models.PositiveSmallIntegerField(default=40)

    tiebreaker_game = models.CharField(
        max_length=24,
        choices=TiebreakerGame.choices,
        default=TiebreakerGame.LAST_GAME_OF_WEEK,
    )
    tiebreaker_type = models.CharField(
        max_length=20,
        choices=TiebreakerType.choices,
        default=TiebreakerType.TOTAL_POINTS,
    )

    underdog_outright_bonus = models.PositiveSmallIntegerField(default=0)
    tiebreaker_exact_bonus = models.PositiveSmallIntegerField(default=0)
    over_under_points = models.PositiveSmallIntegerField(default=0)
    drop_worst_week = models.BooleanField(default=False)

    weekly_prize_enabled = models.BooleanField(default=True)
    weekly_prize_metric = models.CharField(
        max_length=8,
        choices=WeeklyPrizeMetric.choices,
        default=WeeklyPrizeMetric.POINTS,
    )
    season_points_prize_enabled = models.BooleanField(default=True)
    season_points_prize_places = models.PositiveSmallIntegerField(default=1)
    best_bet_prize_enabled = models.BooleanField(default=True)
    best_bet_prize_places = models.PositiveSmallIntegerField(default=1)
    prize_amounts = models.JSONField(default=dict, blank=True)

    reminder_times = models.JSONField(default=default_reminder_times)
    season_type = models.CharField(
        max_length=20, choices=SeasonType.choices, default=SeasonType.REGULAR_SEASON
    )

    class Meta:
        verbose_name_plural = "league settings"

    def __str__(self) -> str:
        return f"Settings for {self.league_season}"

    def clean(self) -> None:
        reference_sunday = date(2026, 9, 13)
        spreads_at, picks_at = lock_times(
            reference_sunday,
            spread_weekday=self.spread_lock_weekday,
            spread_time=self.spread_lock_time,
            picks_weekday=self.picks_lock_weekday,
            picks_time=self.picks_lock_time,
            timezone_name="UTC",
        )
        if spreads_at >= picks_at:
            raise ValidationError("Lines must lock before the weekly pick deadline.")


class LeagueWeekStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    PUBLISHED = "published", "Published"
    IN_PROGRESS = "in_progress", "In progress"
    FINAL = "final", "Final"


class LeagueWeek(models.Model):
    league_season = models.ForeignKey(
        LeagueSeason, on_delete=models.CASCADE, related_name="weeks"
    )
    week = models.ForeignKey(
        Week, on_delete=models.PROTECT, related_name="league_weeks"
    )
    spreads_lock_at = models.DateTimeField()
    picks_lock_at = models.DateTimeField()
    tiebreaker_game = models.ForeignKey(
        Game, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(
        max_length=16,
        choices=LeagueWeekStatus.choices,
        default=LeagueWeekStatus.SCHEDULED,
    )

    class Meta:
        ordering = ("league_season", "week__number")
        constraints = (
            models.UniqueConstraint(
                fields=("league_season", "week"), name="leagues_leagueweek_unique"
            ),
        )

    def __str__(self) -> str:
        return f"{self.league_season.league} {self.week}"


class Role(models.TextChoices):
    MEMBER = "member", "Member"
    COMMISSIONER = "commissioner", "Commissioner"


class Membership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    league = models.ForeignKey(
        League, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("league", "user__display_name")
        constraints = (
            models.UniqueConstraint(
                fields=("user", "league"), name="leagues_membership_unique"
            ),
        )

    def __str__(self) -> str:
        return f"{self.user} in {self.league}"

    @property
    def is_commissioner(self) -> bool:
        return self.is_active and self.role == Role.COMMISSIONER


class InviteQuerySet(models.QuerySet["Invite"]):
    def pending(self) -> "InviteQuerySet":
        return self.filter(
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )


class Invite(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField()
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = InviteQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        constraints = (
            models.CheckConstraint(
                condition=Q(accepted_at__isnull=True) | Q(revoked_at__isnull=True),
                name="leagues_invite_not_accepted_and_revoked",
            ),
        )

    def __str__(self) -> str:
        return f"Invite for {self.email} to {self.league}"

    @property
    def is_usable(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )
