from .base import *  # noqa: F403
from .base import AUTH_PASSWORD_VALIDATORS

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
WHITENOISE_AUTOREFRESH = True

AUTH_PASSWORD_VALIDATORS = [
    v
    for v in AUTH_PASSWORD_VALIDATORS
    if not v["NAME"].endswith("PwnedPasswordValidator")
]
