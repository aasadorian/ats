from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import InviteSignupView

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/signup/", InviteSignupView.as_view(), name="account_signup"),
    path("accounts/", include("allauth.urls")),
    path("", include("apps.leagues.urls")),
    path("", include("apps.lines.urls")),
    path("", include("apps.picks.urls")),
    path("", include("apps.standings.urls")),
    path("", include("apps.core.urls")),
]
