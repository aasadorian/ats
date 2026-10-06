import hashlib
import logging

import httpx
from django.core.exceptions import ValidationError

from apps.accounts.models import User

logger = logging.getLogger(__name__)

PWNED_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"


class PwnedPasswordValidator:
    """Reject passwords found in known breaches via the k-anonymity range API.

    Only the first five characters of the SHA-1 hash leave the server. If the
    service is unreachable the password is allowed rather than blocking signup.
    """

    def __init__(self, timeout: float = 3.0) -> None:
        self.timeout = timeout

    def validate(self, password: str, user: User | None = None) -> None:
        digest = hashlib.sha1(password.encode(), usedforsecurity=False)
        sha1 = digest.hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        try:
            body = self.fetch_range(prefix)
        except httpx.HTTPError:
            logger.warning("Pwned Passwords check unavailable; skipping")
            return
        for line in body.splitlines():
            candidate, _, count = line.partition(":")
            if candidate == suffix and int(count or 0) > 0:
                raise ValidationError(
                    "This password has appeared in a data breach. "
                    "Please choose a different one.",
                    code="password_pwned",
                )

    def fetch_range(self, prefix: str) -> str:
        response = httpx.get(
            PWNED_RANGE_URL.format(prefix=prefix),
            headers={"Add-Padding": "true"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text

    def get_help_text(self) -> str:
        return "Your password can't be one that has appeared in a data breach."
