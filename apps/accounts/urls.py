from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("delete/", views.delete_account, name="delete"),
]
