from django.urls import path

from apps.lines import views

app_name = "lines"

urlpatterns = [
    path("leagues/<slug:slug>/lines/", views.review, name="review"),
    path(
        "leagues/<slug:slug>/lines/<int:pk>/override/",
        views.override,
        name="override",
    ),
]
