from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.accounts.models import User
from apps.leagues.models import Membership
from apps.nfl.models import Game


def notify_pick_entered(
    target: Membership, game: Game, *, actor: User, reason: str
) -> None:
    send_mail(
        subject=f"{actor} updated your pick in {target.league}",
        message=render_to_string(
            "email/pick_entered.txt",
            {"target": target, "game": game, "actor": actor, "reason": reason},
        ),
        from_email=None,
        recipient_list=[target.user.email],
    )
