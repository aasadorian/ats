from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.utils import request_user


@login_required
def home(request: HttpRequest) -> HttpResponse:
    memberships = (
        request_user(request)
        .memberships.filter(is_active=True)
        .select_related("league")
        .order_by("league__name")
    )
    return render(request, "core/home.html", {"memberships": memberships})


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
