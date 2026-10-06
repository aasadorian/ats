from django.contrib import admin
from django.http import HttpRequest

from apps.activity.models import ActivityEvent


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin[ActivityEvent]):
    list_display = (
        "occurred_at",
        "league",
        "event_type",
        "actor_type",
        "actor",
        "summary",
    )
    list_filter = ("category", "actor_type", "league")
    search_fields = ("summary", "event_type", "request_id")
    list_select_related = ("league", "actor")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: ActivityEvent | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: ActivityEvent | None = None
    ) -> bool:
        return False
