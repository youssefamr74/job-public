"""The user's role groups: listing them, merging one into another, undoing a merge, and AI suggestions.
Grouping itself is in applications/role_groups.py."""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai.clients import AIError
from ai.service import complete_text
from applications.models import Application, RoleGroupMerge
from applications.role_groups import effective_group, group_key, group_labels, label_for, resolve, role_group
from auth.models import User
from classifier.utils import extract_json

logger = logging.getLogger(__name__)

MAX_SUGGESTION_GROUPS = 200


class RoleGroup(BaseModel):
    key: str
    label: str
    applied: int


class MergeRule(BaseModel):
    source: str
    source_label: str
    target: str
    target_label: str


class RoleGroups(BaseModel):
    """Every group the user has, all time, after merges. For "Merge into..." and "Count as"."""
    groups: list[RoleGroup]
    merges: list[MergeRule]


class MergeRequest(BaseModel):
    source: str = Field(min_length=1, max_length=255)
    target: str = Field(min_length=1, max_length=255)


class Suggestion(BaseModel):
    source: str
    source_label: str
    target: str
    target_label: str
    reason: Optional[str] = None


class Suggestions(BaseModel):
    suggestions: list[Suggestion]


async def load_merges(db: AsyncSession, user: User) -> dict[str, str]:
    rows = await db.execute(select(RoleGroupMerge).where(RoleGroupMerge.user_id == user.id))
    return {rule.source: rule.target for rule in rows.scalars().all()}


async def refresh_role_groups(db: AsyncSession) -> int:
    """Recomputes stored groups, for when the rules or role_synonyms.json changed. Returns how many changed."""
    rows = (await db.execute(
        select(Application.id, Application.role, Application.company, Application.role_group)
    )).all()
    changed = 0
    for app_id, role, company, stored in rows:
        group = role_group(role, company)
        if group != stored:
            await db.execute(update(Application).where(Application.id == app_id).values(role_group=group))
            changed += 1
    if changed:
        await db.commit()
    return changed


async def _apps(db: AsyncSession, user: User) -> list[tuple]:
    rows = await db.execute(
        select(Application.role, Application.company, Application.role_group, Application.role_group_override)
        .where(Application.user_id == user.id, Application.status != "Needs Review")
    )
    return [tuple(row) for row in rows.all()]


async def list_groups(db: AsyncSession, user: User) -> RoleGroups:
    apps = await _apps(db, user)
    merges = await load_merges(db, user)
    labels = group_labels((role, company, override) for role, company, _, override in apps)
    counts = Counter(effective_group(role, stored, override, merges, company)
                     for role, company, stored, override in apps)
    groups = [RoleGroup(key=key, label=label_for(key, labels), applied=count)
              for key, count in counts.items() if key is not None]
    groups.sort(key=lambda group: (-group.applied, group.label.lower()))
    rules = [MergeRule(source=s, source_label=label_for(s, labels), target=t, target_label=label_for(t, labels))
             for s, t in merges.items()]
    rules.sort(key=lambda rule: rule.source_label.lower())
    return RoleGroups(groups=groups, merges=rules)


async def merge_groups(db: AsyncSession, user: User, source: str, target: str) -> None:
    """From now on, applications in `source` count in `target`, new ones included."""
    source_key, target_key = group_key(source), group_key(target)
    if not source_key or not target_key or source_key == target_key:
        raise HTTPException(status_code=422, detail="Pick two different groups")
    merges = await load_merges(db, user)
    if resolve(target_key, merges) == source_key:
        raise HTTPException(status_code=409, detail="That group is already merged into this one")
    existing = await db.get(RoleGroupMerge, (user.id, source_key))
    if existing:
        existing.target = target_key
    else:
        db.add(RoleGroupMerge(user_id=user.id, source=source_key, target=target_key))
    await db.commit()


async def unmerge_group(db: AsyncSession, user: User, source: str) -> None:
    source_key = group_key(source)
    result = await db.execute(
        delete(RoleGroupMerge).where(RoleGroupMerge.user_id == user.id, RoleGroupMerge.source == source_key)
    )
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="That group isn't merged")
    await db.commit()


SUGGEST_SYSTEM = """You help a job seeker group the job titles they applied for, so their statistics make sense.
You get a list of role groups, one per line as `key | example title | applications`. Find groups that are the
same job written differently: other wording, language, gender form, abbreviation or spelling. Do not merge
different jobs, different specialisations, or a job with its manager. Answer with JSON only:
{"merges": [{"source": "<key>", "target": "<key>", "reason": "<a few words>"}]}
Use keys exactly as given. Merge the smaller group into the larger one. Return {"merges": []} if nothing fits."""


def _parse_suggestions(text: str, groups: dict[str, RoleGroup]) -> list[Suggestion]:
    try:
        data = json.loads(extract_json(text))
    except (json.JSONDecodeError, TypeError):
        logger.warning("Role group suggestions were not valid JSON")
        return []
    items = data.get("merges") if isinstance(data, dict) else None
    suggestions: list[Suggestion] = []
    used: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        source, target = item.get("source"), item.get("target")
        if source not in groups or target not in groups or source == target or source in used:
            continue
        reason = item.get("reason")
        used.add(source)
        suggestions.append(Suggestion(
            source=source, source_label=groups[source].label, target=target, target_label=groups[target].label,
            reason=str(reason)[:200] if reason else None,
        ))
    return suggestions


async def suggest_merges(db: AsyncSession, user: User) -> Suggestions:
    """Merges the AI proposes. Nothing is applied: the user accepts or rejects each one."""
    groups = (await list_groups(db, user)).groups[:MAX_SUGGESTION_GROUPS]
    if len(groups) < 2:
        return Suggestions(suggestions=[])
    listing = "\n".join(f"{g.key} | {g.label} | {g.applied}" for g in groups)
    text = await complete_text(SUGGEST_SYSTEM, [{"role": "user", "content": listing}], 1500)
    return Suggestions(suggestions=_parse_suggestions(text, {g.key: g for g in groups}))

