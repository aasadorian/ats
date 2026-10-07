from pathlib import Path
from typing import Any

import django_stubs_ext
import environ

django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])
ADMIN_URL: str = env("DJANGO_ADMIN_URL", default="admin/")
SITE_URL: str = env("SITE_URL", default="http://localhost:8000")
ODDS_API_KEY: str = env("ODDS_API_KEY", default="")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.usersessions",
    "django_htmx",
    "apps.accounts",
    "apps.core",
    "apps.nfl",
    "apps.activity",
    "apps.leagues",
    "apps.lines",
    "apps.picks",
    "apps.standings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "allauth.usersessions.middleware.UserSessionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.activity.middleware.EventContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

_VALIDATORS = "django.contrib.auth.password_validation"
AUTH_PASSWORD_VALIDATORS: list[dict[str, Any]] = [
    {
        "NAME": f"{_VALIDATORS}.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "display_name")},
    },
    {
        "NAME": f"{_VALIDATORS}.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": f"{_VALIDATORS}.CommonPasswordValidator"},
    {"NAME": f"{_VALIDATORS}.NumericPasswordValidator"},
    {"NAME": "apps.accounts.validators.PwnedPasswordValidator"},
]

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_SESSION_REMEMBER = None
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
ACCOUNT_ADAPTER = "apps.accounts.adapters.InviteOnlyAccountAdapter"
ACCOUNT_SIGNUP_FORM_CLASS = "apps.accounts.forms.SignupDetailsForm"
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
COMMISSIONER_MFA_REQUIRED = env.bool("COMMISSIONER_MFA_REQUIRED", default=True)

LOGIN_REDIRECT_URL = "core:home"
LOGIN_URL = "account_login"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
