from django.contrib import admin

from apps.lines.models import OddsSnapshot, Spread


@admin.register(Spread)
class SpreadAdmin(admin.ModelAdmin[Spread]):
    list_display = (
        "game",
        "league_season",
        "kind",
        "status",
        "home_line",
        "feed_line",
        "book_count",
        "overridden",
    )
    list_filter = ("league_season", "status", "game__week")
    list_select_related = ("game__home_team", "game__away_team", "league_season")


@admin.register(OddsSnapshot)
class OddsSnapshotAdmin(admin.ModelAdmin[OddsSnapshot]):
    list_display = ("fetched_at", "source")
