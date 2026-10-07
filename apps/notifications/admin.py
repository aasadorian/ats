from django.contrib import admin

from apps.notifications.models import Dispatch, NotificationPreference


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin[Dispatch]):
    list_display = ("kind", "league_week", "key", "sent_at", "recipients")
    list_filter = ("kind",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin[NotificationPreference]):
    list_display = ("user", "kind", "enabled")
