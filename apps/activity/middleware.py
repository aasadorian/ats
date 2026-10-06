from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.activity.context import event_context


class EventContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        with event_context("web", ip_address=request.META.get("REMOTE_ADDR")):
            return self.get_response(request)
