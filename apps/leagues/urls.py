from django.urls import path

from apps.leagues import views

app_name = "leagues"

urlpatterns = [
    path("invites/<str:token>/", views.invite, name="invite"),
    path("leagues/<slug:slug>/", views.league_home, name="home"),
    path("leagues/<slug:slug>/members/", views.members, name="members"),
    path(
        "leagues/<slug:slug>/invites/<int:pk>/resend/",
        views.invite_resend,
        name="invite_resend",
    ),
    path(
        "leagues/<slug:slug>/invites/<int:pk>/revoke/",
        views.invite_revoke,
        name="invite_revoke",
    ),
    path(
        "leagues/<slug:slug>/members/<int:pk>/role/",
        views.membership_role,
        name="membership_role",
    ),
    path(
        "leagues/<slug:slug>/members/<int:pk>/deactivate/",
        views.membership_deactivate,
        name="membership_deactivate",
    ),
    path(
        "leagues/<slug:slug>/members/<int:pk>/reactivate/",
        views.membership_reactivate,
        name="membership_reactivate",
    ),
]
