from typing import Any, ClassVar

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models.functions import Lower


class EmailUserManager(UserManager["User"]):
    def _create_user_with_email(
        self, email: str, password: str | None, **extra_fields: Any
    ) -> "User":
        if not email:
            raise ValueError("Users must have an email address.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(  # type: ignore[override]
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user_with_email(email, password, **extra_fields)

    def create_superuser(  # type: ignore[override]
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self._create_user_with_email(email, password, **extra_fields)


class User(AbstractUser):
    username = None  # type: ignore[assignment]
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]

    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(max_length=40, blank=True)
    timezone = models.CharField(max_length=64, default="America/Los_Angeles")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects = EmailUserManager()  # type: ignore[misc]

    class Meta:
        constraints = (
            models.UniqueConstraint(
                Lower("email"), name="accounts_user_email_ci_unique"
            ),
        )

    def __str__(self) -> str:
        return self.display_name or self.email

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = self.email.lower()
        super().save(*args, **kwargs)
