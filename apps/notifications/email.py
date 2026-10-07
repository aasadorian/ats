from django.conf import settings
from django.core import signing
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse

from apps.accounts.models import User
from apps.notifications.models import Kind, NotificationPreference

UNSUBSCRIBE_SALT = "notifications.unsubscribe"


def wants(user: User, kind: Kind) -> bool:
    if not user.is_active:
        return False
    preference = NotificationPreference.objects.filter(user=user, kind=kind).first()
    return preference is None or preference.enabled


def unsubscribe_token(user: User, kind: Kind) -> str:
    return signing.dumps({"u": user.pk, "k": kind.value}, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token: str) -> tuple[int, Kind] | None:
    try:
        data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
        return int(data["u"]), Kind(data["k"])
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        return None


def send(
    user: User, kind: Kind, *, subject: str, template: str, context: dict[str, object]
) -> bool:
    """Send one opt-out-able email; returns False if the user has opted out."""
    if not wants(user, kind):
        return False
    url = settings.SITE_URL + reverse(
        "notifications:unsubscribe", args=[unsubscribe_token(user, kind)]
    )
    body = render_to_string(
        template,
        {
            **context,
            "user": user,
            "site_url": settings.SITE_URL,
            "unsubscribe_url": url,
        },
    )
    message = EmailMessage(
        subject=subject,
        body=body,
        to=[user.email],
        headers={
            "List-Unsubscribe": f"<{url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    message.send()
    return True
