from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("account/notifications/", views.preferences, name="preferences"),
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
]
