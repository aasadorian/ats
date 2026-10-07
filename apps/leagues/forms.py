from typing import ClassVar

from django import forms

from apps.leagues.models import LeagueSettings, Role


class InviteForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Role.choices, initial=Role.MEMBER)


class RoleForm(forms.Form):
    role = forms.ChoiceField(choices=Role.choices)


SETTINGS_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Picks and scoring",
        (
            "pick_type",
            "points_per_win",
            "best_bets_per_week",
            "best_bet_bonus",
            "push_scoring",
        ),
    ),
    (
        "Lines",
        (
            "half_point_lines",
            "half_point_rounding",
            "off_line_handling",
            "off_line_cutoff",
            "off_line_fallback",
        ),
    ),
    (
        "Lock times",
        (
            "spread_lock_weekday",
            "spread_lock_time",
            "picks_lock_weekday",
            "picks_lock_time",
            "game_lock_offset_minutes",
            "pick_visibility",
        ),
    ),
    (
        "Tiebreaker and prizes",
        (
            "tiebreaker_type",
            "weekly_prize_enabled",
            "weekly_prize_metric",
            "season_points_prize_enabled",
            "season_points_prize_places",
            "best_bet_prize_enabled",
            "best_bet_prize_places",
        ),
    ),
)


class LeagueSettingsForm(forms.ModelForm[LeagueSettings]):
    apply_to_season = forms.BooleanField(
        required=False,
        label="Apply scoring changes to the whole season",
        help_text="Required when changing scoring after the first week has opened; "
        "standings are recalculated for every week.",
    )

    class Meta:
        model = LeagueSettings
        fields = tuple(name for _, names in SETTINGS_SECTIONS for name in names)
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "spread_lock_time": forms.TimeInput(attrs={"type": "time"}),
            "picks_lock_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def sections(self) -> list[tuple[str, list[forms.BoundField]]]:
        return [
            (title, [self[name] for name in names])
            for title, names in SETTINGS_SECTIONS
        ]
