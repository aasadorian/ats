from django.contrib import admin

from apps.picks.models import Pick, WeeklyEntry


@admin.register(Pick)
class PickAdmin(admin.ModelAdmin[Pick]):
    list_display = ("membership", "game", "team", "is_best_bet", "updated_at")
    list_filter = ("week", "is_best_bet")
    list_select_related = (
        "membership__user",
        "game__home_team",
        "game__away_team",
        "team",
    )


@admin.register(WeeklyEntry)
class WeeklyEntryAdmin(admin.ModelAdmin[WeeklyEntry]):
    list_display = ("membership", "league_week", "tiebreaker_guess", "updated_at")
