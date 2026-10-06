from django.contrib import admin

from apps.nfl.models import Game, Season, Team, Week


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin[Team]):
    list_display = ("abbreviation", "location", "name", "external_id")
    search_fields = ("abbreviation", "location", "name")


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin[Season]):
    list_display = ("year",)


@admin.register(Week)
class WeekAdmin(admin.ModelAdmin[Week]):
    list_display = ("__str__", "sunday", "starts_at", "ends_at")
    list_filter = ("season",)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin[Game]):
    list_display = (
        "__str__",
        "week",
        "kickoff_at",
        "status",
        "postponed_from",
        "home_score",
        "away_score",
    )
    list_filter = ("week__season", "week", "status")
    search_fields = ("home_team__abbreviation", "away_team__abbreviation")
    list_select_related = ("week__season", "home_team", "away_team")
