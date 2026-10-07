from django.urls import path

from apps.standings import views

app_name = "standings"

urlpatterns = [
    path("leagues/<slug:slug>/standings/", views.season, name="season"),
    path("leagues/<slug:slug>/standings/week/", views.week, name="week"),
]
