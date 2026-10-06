from typing import Any

from allauth.account import signals as account_signals
from allauth.mfa import signals as mfa_signals
from django.contrib.auth import signals as auth_signals
from django.dispatch import receiver

from apps.accounts.models import User
from apps.activity.services import record_event

# Authentication libraries expose these events only as signals, so security
# events are recorded here rather than in a service function.


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}" if domain else "***"


@receiver(auth_signals.user_logged_in)
def on_login(sender: Any, request: Any, user: User, **kwargs: Any) -> None:
    record_event(event_type="auth.login", summary=f"{user} signed in", actor=user)


@receiver(auth_signals.user_login_failed)
def on_login_failed(sender: Any, credentials: dict[str, Any], **kwargs: Any) -> None:
    attempted = str(credentials.get("email") or credentials.get("username") or "")
    record_event(
        event_type="auth.login_failed",
        summary=f"Failed sign-in for {mask_email(attempted)}",
    )


@receiver(account_signals.password_changed)
def on_password_changed(sender: Any, request: Any, user: User, **kwargs: Any) -> None:
    record_event(
        event_type="auth.password_changed",
        summary=f"{user} changed their password",
        actor=user,
    )


@receiver(account_signals.password_reset)
def on_password_reset(sender: Any, request: Any, user: User, **kwargs: Any) -> None:
    record_event(
        event_type="auth.password_reset",
        summary=f"{user} reset their password",
        actor=user,
    )


@receiver(account_signals.email_changed)
def on_email_changed(sender: Any, request: Any, user: User, **kwargs: Any) -> None:
    record_event(
        event_type="auth.email_changed",
        summary=f"{user} changed their email address",
        actor=user,
    )


@receiver(mfa_signals.authenticator_added)
def on_mfa_added(sender: Any, request: Any, user: User, **kwargs: Any) -> None:
    record_event(
        event_type="auth.mfa_added",
        summary=f"{user} added two-factor authentication",
        actor=user,
    )


@receiver(mfa_signals.authenticator_removed)
def on_mfa_removed(sender: Any, request: Any, user: User, **kwargs: Any) -> None:
    record_event(
        event_type="auth.mfa_removed",
        summary=f"{user} removed two-factor authentication",
        actor=user,
    )
