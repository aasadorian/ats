from django.contrib import admin

from apps.leagues.models import (
    Invite,
    League,
    LeagueSeason,
    LeagueSettings,
    LeagueWeek,
    Membership,
)


class MembershipInline(admin.TabularInline[Membership, League]):
    model = Membership
    extra = 0
    fields = ("user", "role", "is_active", "joined_at", "deactivated_at")
    readonly_fields = ("joined_at",)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin[League]):
    list_display = ("name", "slug", "timezone", "created_at")
    inlines = (MembershipInline,)


@admin.register(LeagueSeason)
class LeagueSeasonAdmin(admin.ModelAdmin[LeagueSeason]):
    list_display = ("league", "season")


@admin.register(LeagueSettings)
class LeagueSettingsAdmin(admin.ModelAdmin[LeagueSettings]):
    list_display = ("league_season", "pick_type", "line_mode", "best_bets_per_week")


@admin.register(LeagueWeek)
class LeagueWeekAdmin(admin.ModelAdmin[LeagueWeek]):
    list_display = (
        "__str__",
        "spreads_lock_at",
        "picks_lock_at",
        "tiebreaker_game",
        "status",
    )
    list_filter = ("league_season", "status")
    list_select_related = (
        "league_season__league",
        "week__season",
        "tiebreaker_game__home_team",
        "tiebreaker_game__away_team",
    )


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin[Invite]):
    list_display = (
        "email",
        "league",
        "role",
        "created_at",
        "expires_at",
        "accepted_at",
    )
    list_filter = ("league",)
    exclude = ("token_hash",)
    readonly_fields = ("accepted_at", "accepted_by", "revoked_at")
