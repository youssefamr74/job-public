from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from typing import Literal, Optional, Any
from datetime import date, datetime, timezone
import uuid

from constants.job_statuses import ApplicationStatus

NO_REPLY_STATUSES = {"Applied", "Assessment"}
NO_REPLY_AFTER_DAYS = 14
FOLLOWUP_SNOOZE_DAYS = 7

# The 4 steps of the progress bar: Applied, Reply, Interview, Offer.
PROGRESS_STEP = {"Applied": 1, "Needs Review": 1, "Assessment": 2, "Interview": 3, "Offer": 4}

# raw_metadata keys written by the user, kept when a sync rewrites the metadata.
USER_METADATA_KEYS = ("edits", "followup_snoozed_until")

StatusValue = Literal["Applied", "Assessment", "Interview", "Rejected", "Offer", "Needs Review"]


def parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class TimelineEvent(BaseModel):
    date: Optional[datetime]
    kind: Literal["email", "edit"]
    subject: Optional[str] = None
    change: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: uuid.UUID
    company: Optional[str]
    role: Optional[str]
    status: str
    applied_date: Optional[datetime]
    source: Optional[str]
    notes: Optional[str]
    interview_date: Optional[datetime] = None
    location: Optional[str] = None
    raw_metadata: Optional[dict[str, Any]] = None
    action_needed: bool = False
    manually_modified: bool = False
    # The role's group key for Analytics, and what the user said it counts as ("Count as").
    role_group: Optional[str] = None
    role_group_override: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("applied_date", "interview_date", mode="after")
    @classmethod
    def as_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        """SQLite returns naive datetimes; they are stored in UTC."""
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value

    def _history(self) -> list[dict]:
        return [e for e in (self.raw_metadata or {}).get("history") or [] if isinstance(e, dict)]

    def _edits(self) -> list[dict]:
        return [e for e in (self.raw_metadata or {}).get("edits") or [] if isinstance(e, dict)]

    @computed_field
    @property
    def email_count(self) -> int:
        return len(self._history())

    @computed_field
    @property
    def last_activity_at(self) -> Optional[datetime]:
        dates = [parse_dt(e.get("date")) for e in self._history() + self._edits()]
        dates = [d for d in dates if d is not None]
        applied = parse_dt(self.applied_date)
        if applied:
            dates.append(applied)
        return max(dates) if dates else None

    @computed_field
    @property
    def no_reply_days(self) -> Optional[int]:
        """Days without any activity, for applications still waiting on the employer for 14+ days."""
        if self.status not in NO_REPLY_STATUSES or self.last_activity_at is None:
            return None
        days = (datetime.now(timezone.utc) - self.last_activity_at).days
        return days if days >= NO_REPLY_AFTER_DAYS else None

    @computed_field
    @property
    def interview_held(self) -> bool:
        """The interview date has passed and the status is still Interview."""
        interview = parse_dt(self.interview_date)
        return self.status == "Interview" and interview is not None and interview < datetime.now(timezone.utc)

    @computed_field
    @property
    def no_news_days(self) -> Optional[int]:
        """Days since the interview, or since the last email after it, for an interview that was held."""
        if not self.interview_held:
            return None
        emails = [parse_dt(e.get("date")) for e in self._history()]
        since = max(d for d in (parse_dt(self.interview_date), *emails) if d is not None)
        return max((datetime.now(timezone.utc) - since).days, 0)

    @computed_field
    @property
    def followup_snoozed_until(self) -> Optional[datetime]:
        return parse_dt((self.raw_metadata or {}).get("followup_snoozed_until"))

    @computed_field
    @property
    def needs_followup(self) -> bool:
        """A held interview to ask about, unless the user said "no answer yet" in the last 7 days."""
        snoozed = self.followup_snoozed_until
        return self.interview_held and not (snoozed and snoozed > datetime.now(timezone.utc))

    @computed_field
    @property
    def progress_step(self) -> int:
        """Furthest step reached (1 to 4). A rejection keeps the steps reached before it."""
        statuses = [self.status] + [e.get("status") for e in self._history()]
        for edit in self._edits():
            if edit.get("field") == "status":
                statuses += [edit.get("from"), edit.get("to")]
        step = max((PROGRESS_STEP.get(s or "", 1) for s in statuses), default=1)
        if self.interview_date is not None:
            step = max(step, PROGRESS_STEP["Interview"])
        return step

    @computed_field
    @property
    def timeline(self) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        previous: Optional[str] = None
        for event in self._history():
            status = event.get("status")
            if previous is None:
                change = status
            elif status and status != previous:
                change = f"{previous} to {status}"
            else:
                change = None
            previous = status or previous
            events.append(TimelineEvent(
                date=parse_dt(event.get("date")), kind="email", subject=event.get("subject"), change=change,
            ))
        for edit in self._edits():
            field = edit.get("field")
            if field == "interview":
                events.append(TimelineEvent(
                    date=parse_dt(edit.get("date")), kind="edit", subject="Interview went on to a next round",
                ))
                continue
            label = "Status changed by you" if field == "status" else f"{str(field).capitalize()} edited by you"
            events.append(TimelineEvent(
                date=parse_dt(edit.get("date")), kind="edit", subject=label,
                change=f"{edit.get('from') or 'empty'} to {edit.get('to') or 'empty'}",
            ))
        events.sort(key=lambda e: e.date or datetime.min.replace(tzinfo=timezone.utc))
        return events


class ApplicationUpdate(BaseModel):
    status: Optional[StatusValue] = None
    notes: Optional[str] = Field(default=None, max_length=20_000)
    action_needed: Optional[bool] = None


class ApplicationMetadataUpdate(BaseModel):
    company: Optional[str] = Field(default=None, max_length=255)
    role: Optional[str] = Field(default=None, max_length=255)
    interview_date: Optional[datetime] = None
    raw_metadata: Optional[dict[str, Any]] = None
    # "Count as" in Analytics. Empty or null goes back to the role's own group.
    role_group_override: Optional[str] = Field(default=None, max_length=255)

    @field_validator("interview_date", mode="before")
    @classmethod
    def accept_plain_date(cls, value: Any) -> Any:
        if isinstance(value, str) and len(value) == 10:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("Invalid interview_date format. Use YYYY-MM-DD.")
        return value


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    status: StatusValue = ApplicationStatus.APPLIED.value
    applied_date: Optional[date] = None

    @field_validator("company", "role")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value


class InterviewOutcome(BaseModel):
    outcome: Literal["rejected", "next_round", "offer", "no_answer"]


class TodayItem(BaseModel):
    id: uuid.UUID
    company: Optional[str]
    role: Optional[str]
    date: Optional[datetime] = None
    days: Optional[int] = None


class AttentionItem(TodayItem):
    reason: Literal["interview_held", "action_needed", "no_reply"]


class WeekNumbers(BaseModel):
    applied: int
    replies: int
    interviews: int


class TodayResponse(BaseModel):
    coming_up: list[TodayItem]
    attention: list[AttentionItem]
    this_week: WeekNumbers


class StaleApplicationResponse(BaseModel):
    id: uuid.UUID
    company: Optional[str]
    role: Optional[str]
    status: str
    applied_date: Optional[datetime]
    days_since_update: int

    model_config = ConfigDict(from_attributes=True)
