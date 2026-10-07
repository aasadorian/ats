import csv
from datetime import date

from django.core.paginator import Paginator
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.utils import request_user
from apps.activity.models import ActivityEvent, Category
from apps.activity.selectors import (
    LogFilters,
    commissioner_log,
    league_feed,
    member_activity,
    visible,
)
from apps.leagues.models import League, Membership
from apps.leagues.permissions import commissioner_required, league_member_required

PAGE_SIZE = 50


@league_member_required
def feed(request: HttpRequest, league: League, membership: Membership) -> HttpResponse:
    return _page(request, league, membership, league_feed(league), "League activity")


@league_member_required
def mine(request: HttpRequest, league: League, membership: Membership) -> HttpResponse:
    events = member_activity(league, request_user(request))
    return _page(request, league, membership, events, "My activity")


@commissioner_required
def log(request: HttpRequest, league: League, membership: Membership) -> HttpResponse:
    filters = _filters(request, league)
    events = commissioner_log(league, filters)
    if request.GET.get("format") == "csv":
        return _csv(events, request_user(request), league)
    members = league.memberships.select_related("user").order_by("user__display_name")
    return _page(
        request,
        league,
        membership,
        events,
        "Activity log",
        extra={
            "filters": filters,
            "members": members,
            "categories": Category.choices,
            "show_filters": True,
        },
    )


def _page(
    request: HttpRequest,
    league: League,
    membership: Membership,
    events: QuerySet[ActivityEvent],
    title: str,
    extra: dict[str, object] | None = None,
) -> HttpResponse:
    page = Paginator(events, PAGE_SIZE).get_page(request.GET.get("page"))
    viewer = request_user(request)
    now = timezone.now()
    context: dict[str, object] = {
        "league": league,
        "membership": membership,
        "title": title,
        "page": page,
        "rows": [visible(event, viewer, now) for event in page.object_list],
        "query": request.GET.copy(),
    }
    context.update(extra or {})
    return render(request, "activity/log.html", context)


def _filters(request: HttpRequest, league: League) -> LogFilters:
    member_id = request.GET.get("member", "")
    member = (
        User.objects.filter(pk=member_id, memberships__league=league).first()
        if member_id.isdigit()
        else None
    )
    week = request.GET.get("week", "")
    return LogFilters(
        member=member,
        week_number=int(week) if week.isdigit() else None,
        category=request.GET.get("category", ""),
        event_type=request.GET.get("event_type", "").strip(),
        since=_date(request.GET.get("since", "")),
        until=_date(request.GET.get("until", "")),
    )


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _csv(events: QuerySet[ActivityEvent], viewer: User, league: League) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{league.slug}-activity.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        [
            "occurred_at",
            "event_type",
            "actor",
            "member",
            "week",
            "summary",
            "before",
            "after",
        ]
    )
    now = timezone.now()
    for event in events.iterator():
        row = visible(event, viewer, now)
        writer.writerow(
            [
                event.occurred_at.isoformat(),
                event.event_type,
                event.actor or event.actor_type,
                event.subject_user or "",
                event.league_week.week.number if event.league_week else "",
                row.summary,
                row.before or "",
                row.after or "",
            ]
        )
    return response
