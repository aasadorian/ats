from django.urls import path

from apps.picks import views

app_name = "picks"

urlpatterns = [
    path("leagues/<slug:slug>/picks/", views.sheet, name="sheet"),
    path("leagues/<slug:slug>/picks/grid/", views.grid, name="grid"),
    path("leagues/<slug:slug>/picks/pick/", views.make_pick, name="pick"),
    path("leagues/<slug:slug>/picks/clear/", views.clear_pick, name="clear"),
    path("leagues/<slug:slug>/picks/best-bet/", views.best_bet, name="best_bet"),
    path("leagues/<slug:slug>/picks/tiebreaker/", views.tiebreaker, name="tiebreaker"),
]
