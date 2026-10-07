from apps.accounts.models import User
from apps.leagues.models import Membership
from apps.nfl.models import Game
from apps.notifications.email import send
from apps.notifications.models import Kind


def notify_pick_entered(
    target: Membership, game: Game, *, actor: User, reason: str
) -> None:
    send(
        target.user,
        Kind.PICKS_ENTERED,
        subject=f"{actor} updated your pick in {target.league}",
        template="email/pick_entered.txt",
        context={"target": target, "game": game, "actor": actor, "reason": reason},
    )
