from datetime import UTC, date, datetime, timedelta
from itertools import count

from apps.accounts.models import User
from apps.leagues.models import League
from apps.leagues.services import create_league
from apps.nfl.models import Game, Season, Team, Week

_ids = count(1)
SEASON_YEAR = 2026
FIRST_SUNDAY = date(2026, 9, 13)


def make_user(email: str | None = None, display_name: str = "") -> User:
    n = next(_ids)
    return User.objects.create_user(
        email=email or f"user{n}@example.com",
        password="correct-horse-battery",
        display_name=display_name or f"User {n}",
    )


TEAM_NAMES = {
    "SEA": ("Seattle", "Seahawks"),
    "NE": ("New England", "Patriots"),
    "KC": ("Kansas City", "Chiefs"),
    "BUF": ("Buffalo", "Bills"),
    "DAL": ("Dallas", "Cowboys"),
    "NYG": ("New York", "Giants"),
    "LAR": ("Los Angeles", "Rams"),
    "SF": ("San Francisco", "49ers"),
}


def make_team(abbreviation: str) -> Team:
    location, name = TEAM_NAMES[abbreviation]
    team, _ = Team.objects.get_or_create(
        external_id=abbreviation,
        defaults={"abbreviation": abbreviation, "location": location, "name": name},
    )
    return team


def make_season(weeks: int = 2) -> Season:
    season, _ = Season.objects.get_or_create(year=SEASON_YEAR)
    for number in range(1, weeks + 1):
        sunday = FIRST_SUNDAY + timedelta(weeks=number - 1)
        week, _ = Week.objects.get_or_create(
            season=season,
            number=number,
            defaults={
                "starts_at": datetime.combine(
                    sunday - timedelta(days=5), datetime.min.time(), UTC
                ),
                "ends_at": datetime.combine(
                    sunday + timedelta(days=3), datetime.min.time(), UTC
                ),
                "sunday": sunday,
            },
        )
        make_game(week, "SEA", "NE", kickoff_offset=timedelta(days=-3, hours=1))
        make_game(week, "KC", "BUF", kickoff_offset=timedelta(hours=17))
        make_game(week, "DAL", "NYG", kickoff_offset=timedelta(days=1, hours=1))
    return season


def make_game(week: Week, home: str, away: str, *, kickoff_offset: timedelta) -> Game:
    kickoff = datetime.combine(week.sunday, datetime.min.time(), UTC) + kickoff_offset
    game, _ = Game.objects.get_or_create(
        external_id=f"{week.season.year}-{week.number}-{home}-{away}",
        defaults={
            "week": week,
            "home_team": make_team(home),
            "away_team": make_team(away),
            "kickoff_at": kickoff,
        },
    )
    return game


def make_league(commissioner: User | None = None, slug: str = "office") -> League:
    make_season()
    return create_league(
        name=f"League {slug}",
        slug=slug,
        commissioner=commissioner or make_user(),
        season_year=SEASON_YEAR,
    )
