"""Everything the Analytics page shows for a date range, worked out from the applications in one pass."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import ceil
from statistics import median
from typing import Iterable, Literal, Optional

from pydantic import BaseModel

from applications.role_groups import effective_group, group_labels, label_for
from applications.schemas import ApplicationResponse, parse_dt
from constants.job_statuses import RESPONSE_STATUSES
from utils.timeutil import local_date

Range = Literal["30", "60", "all"]

# Smaller role groups fold into "Other roles": at least 3 applications, or 2% of them with more data.
ROLE_MIN_APPLICATIONS = 3
ROLE_MIN_SHARE = 0.02
WEEKDAY_MIN_APPLICATIONS = 10
MAX_WEEKS = 52
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class Headline(BaseModel):
    applications: int
    per_week: float
    replied: int
    response_rate: Optional[float]
    median_days_to_reply: Optional[float]
    replies_timed: int
    goal_days_met: int
    goal_days: int
    daily_goal: int


class WeekCount(BaseModel):
    week_start: date
    count: int


class FunnelStep(BaseModel):
    step: Literal["Applied", "Got a reply", "Assessment", "Interview", "Offer"]
    count: int
    rate: Optional[float]


class RateRow(BaseModel):
    label: str
    applied: int
    replied: int
    response_rate: Optional[float]
    enough: bool = True


class RoleTitle(BaseModel):
    title: str
    applied: int
    replied: int


class MergedGroup(BaseModel):
    key: str
    label: str


class RoleGroupRow(BaseModel):
    """One role group. key is None for applications without a role ("Role not found")."""
    key: Optional[str]
    label: str
    applied: int
    replied: int
    response_rate: Optional[float]
    # At least role_min_applications. Smaller groups fold into "Other roles".
    enough: bool
    # The exact titles counted in the group, most applications first.
    titles: list[RoleTitle]
    # Groups the user merged into this one, for "Undo merge".
    merged: list[MergedGroup] = []


class AnalyticsOverview(BaseModel):
    range: Range
    since: Optional[date]
    headline: Headline
    per_week: list[WeekCount]
    funnel: list[FunnelStep]
    by_role: list[RoleGroupRow]
    # The fewest applications a role group needs to get its own row.
    role_min_applications: int = ROLE_MIN_APPLICATIONS
    by_weekday: list[RateRow]


class WeeklyReview(BaseModel):
    week_start: date
    week_end: date
    applications_this_week: int
    applications_last_week: int
    responses_this_week: int
    interviews_this_week: int = 0
    ai_configured: bool = False
    goals_met_this_week: int
    streak: int
    highlight: Optional[str] = None
    concern: Optional[str] = None
    focus_items: Optional[list[str]] = None


def _rate(part: int, whole: int) -> Optional[float]:
    return round(part / whole * 100, 1) if whole else None


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _status_events(app: ApplicationResponse) -> list[tuple[datetime, str]]:
    """Dated status changes, from emails and from the user's own edits."""
    meta = app.raw_metadata or {}
    events = []
    for event in meta.get("history") or []:
        if isinstance(event, dict) and (when := parse_dt(event.get("date"))) and event.get("status"):
            events.append((when, event["status"]))
    for edit in meta.get("edits") or []:
        if isinstance(edit, dict) and edit.get("field") == "status" and (when := parse_dt(edit.get("date"))):
            events.append((when, edit.get("to") or ""))
    return sorted(events)


def replied(app: ApplicationResponse) -> bool:
    """Any answer from the employer counts, a rejection included."""
    return app.status in RESPONSE_STATUSES or app.progress_step >= 2 or any(
        status in RESPONSE_STATUSES for _, status in _status_events(app)
    )


def days_to_first_reply(app: ApplicationResponse) -> Optional[float]:
    """From applying to the first reply. Unknown when the reply is the first email seen: then the
    application date is just that email's date."""
    applied = parse_dt(app.applied_date)
    if applied is None:
        return None
    seen_before = app.source == "manual"
    for when, status in _status_events(app):
        if status in RESPONSE_STATUSES:
            return (when - applied).total_seconds() / 86400 if seen_before and when >= applied else None
        seen_before = True
    return None


def _display_title(role: Optional[str]) -> str:
    title = " ".join((role or "").split())
    return title if title and title.lower() != "unknown" else "No role found"


def role_minimum(total: int) -> int:
    return max(ROLE_MIN_APPLICATIONS, ceil(total * ROLE_MIN_SHARE))


def role_rows(apps: list[ApplicationResponse], merges: dict[str, str], labels: dict[str, str],
              minimum: int = ROLE_MIN_APPLICATIONS) -> list[RoleGroupRow]:
    """Response rate per role group, with the exact titles in each. Every group is returned; `enough`
    marks the ones with at least `minimum` applications. Most applications first."""
    groups: dict[Optional[str], list[ApplicationResponse]] = {}
    for app in apps:
        key = effective_group(app.role, app.role_group, app.role_group_override, merges, app.company)
        groups.setdefault(key, []).append(app)

    rows = []
    for key, members in groups.items():
        titles: dict[str, list[ApplicationResponse]] = {}
        shown: dict[str, str] = {}
        for app in members:
            title = _display_title(app.role)
            titles.setdefault(title.lower(), []).append(app)
            shown.setdefault(title.lower(), title)
        title_rows = [RoleTitle(title=shown[t], applied=len(m), replied=sum(1 for a in m if replied(a)))
                      for t, m in titles.items()]
        title_rows.sort(key=lambda row: (-row.applied, row.title.lower()))
        answered = sum(1 for app in members if replied(app))
        merged = sorted(
            (MergedGroup(key=source, label=label_for(source, labels))
             for source, target in merges.items() if target == key),
            key=lambda group: group.label.lower(),
        ) if key is not None else []
        rows.append(RoleGroupRow(
            key=key, label=label_for(key, labels), applied=len(members), replied=answered,
            response_rate=_rate(answered, len(members)), enough=len(members) >= minimum,
            titles=title_rows, merged=merged,
        ))
    # Most applications first.
    rows.sort(key=lambda row: (-row.applied, row.key is None, row.label.lower()))
    return rows


def build_overview(
    apps: Iterable[ApplicationResponse],
    range_: Range,
    goal_days_met: int,
    daily_goal: int,
    now: Optional[datetime] = None,
    merges: Optional[dict[str, str]] = None,
) -> AnalyticsOverview:
    now = now or datetime.now(timezone.utc)
    today = local_date(now)
    since = None if range_ == "all" else today - timedelta(days=int(range_) - 1)

    apps_list = list(apps)
    tracked = []
    for app in apps_list:
        applied = parse_dt(app.applied_date)
        if app.status == "Needs Review" or applied is None:
            continue
        if since is None or local_date(applied) >= since:
            tracked.append((app, local_date(applied)))

    total = len(tracked)
    first_day = since or min((day for _, day in tracked), default=today)
    weeks_span = max(((today - first_day).days + 1) / 7, 1)
    answered = [app for app, _ in tracked if replied(app)]
    timings = [d for app in answered if (d := days_to_first_reply(app)) is not None]

    headline = Headline(
        applications=total,
        per_week=round(total / weeks_span, 1),
        replied=len(answered),
        response_rate=_rate(len(answered), total),
        median_days_to_reply=round(median(timings), 1) if timings else None,
        replies_timed=len(timings),
        goal_days_met=goal_days_met,
        goal_days=7,
        daily_goal=daily_goal,
    )

    first_week = _monday(first_day)
    last_week = _monday(today)
    week_count = min((last_week - first_week).days // 7 + 1, MAX_WEEKS)
    starts = [last_week - timedelta(weeks=i) for i in reversed(range(week_count))]
    counts = dict.fromkeys(starts, 0)
    for _, day in tracked:
        week = _monday(day)
        if week in counts:
            counts[week] += 1
    per_week = [WeekCount(week_start=week, count=count) for week, count in counts.items()]

    steps = [
        ("Applied", total),
        ("Got a reply", len(answered)),
        ("Assessment", sum(1 for app, _ in tracked if app.progress_step >= 2)),
        ("Interview", sum(1 for app, _ in tracked if app.progress_step >= 3)),
        ("Offer", sum(1 for app, _ in tracked if app.progress_step >= 4)),
    ]
    funnel = [FunnelStep(step=step, count=count, rate=_rate(count, total)) for step, count in steps]

    minimum = role_minimum(total)
    by_role = role_rows([app for app, _ in tracked], merges or {}, minimum=minimum, labels=group_labels(
        (app.role, app.company, app.role_group_override) for app in apps_list
    ))

    by_weekday = []
    for index, name in enumerate(WEEKDAYS):
        members = [app for app, day in tracked if day.weekday() == index]
        answered_count = sum(1 for app in members if replied(app))
        enough = len(members) >= WEEKDAY_MIN_APPLICATIONS
        by_weekday.append(RateRow(label=name, applied=len(members), replied=answered_count,
                                  response_rate=_rate(answered_count, len(members)) if enough else None,
                                  enough=enough))

    return AnalyticsOverview(range=range_, since=since, headline=headline, per_week=per_week, funnel=funnel,
                             by_role=by_role, role_min_applications=minimum,
                             by_weekday=by_weekday)
