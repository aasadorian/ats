from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.usersessions.models import UserSession
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.activity.services import record_event, scrub_identity


@transaction.atomic
def delete_account(user: User) -> None:
    """Anonymize the account but keep its picks so league history is unchanged."""
    old_email, old_name = user.email, user.display_name
    anonymous = f"Former member #{user.pk}"
    record_event(event_type="account.deleted", summary=f"{user} deleted their account")

    user.email = f"deleted-{user.pk}@invalid.example"
    user.display_name = anonymous
    user.is_active = False
    user.set_unusable_password()
    user.save()
    EmailAddress.objects.filter(user=user).delete()
    Authenticator.objects.filter(user=user).delete()
    UserSession.objects.filter(user=user).delete()
    user.memberships.filter(is_active=True).update(
        is_active=False, deactivated_at=timezone.now()
    )
    scrub_identity({old_email: anonymous, old_name: anonymous})
