from django.urls import path

from apps.activity import views

app_name = "activity"

urlpatterns = [
    path("leagues/<slug:slug>/activity/", views.feed, name="feed"),
    path("leagues/<slug:slug>/activity/mine/", views.mine, name="mine"),
    path("leagues/<slug:slug>/activity/log/", views.log, name="log"),
]
