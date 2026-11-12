"""Re-run the rule-based classifier on applications already in the database, without fetching mail.

Only what the sync stored is available: the latest email's subject, sender and first 300
characters, plus the subject of every earlier email. When that isn't enough to decide a status,
the stored status is kept.

    python -m applications.reclassify            # dry run: report only
    python -m applications.reclassify --apply    # save the changes
"""

import argparse
import asyncio
from collections import Counter
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application
from applications.service import is_valid_transition, stored_status
from auth.models import User
from classifier.ats_intelligence import classify_email_deterministic, classify_status
from classifier.normalization import is_platform_name, make_fingerprint
from classifier.text import clean_text
from utils.timeutil import utc_now


def _event_status(subject: str, body: str, stored: Optional[str]) -> str:
    result = classify_status(clean_text(subject), clean_text(body))
    if result.status is None:
        return stored or "Needs Review"
    return stored_status(result.status, result.confidence)


def _fold(statuses: list[str]) -> str:
    status = statuses[0]
    for event_status in statuses[1:]:
        if event_status != status and is_valid_transition(status, event_status):
            status = event_status
    return status


def _known(value: Optional[str]) -> bool:
    return bool(value) and value != "Unknown" and not is_platform_name(value)


async def reclassify_applications(db: AsyncSession, user: User, apply: bool = False) -> dict:
    apps = (await db.execute(select(Application).where(Application.user_id == user.id))).scalars().all()
    owner_of = {a.application_fingerprint: a.id for a in apps if a.application_fingerprint}

    report = {
        "applied": apply, "checked": 0, "changed": 0, "skipped_manual": 0, "skipped_no_data": 0,
        "status_before": dict(Counter(a.status for a in apps)), "status_after": {}, "changes": [],
    }
    after: Counter = Counter()

    for app in apps:
        meta = app.raw_metadata or {}
        subject = meta.get("subject") or ""
        snippet = clean_text(meta.get("snippet") or "")
        if app.manually_modified:
            report["skipped_manual"] += 1
            after[app.status] += 1
            continue
        if not (subject or snippet):
            report["skipped_no_data"] += 1
            after[app.status] += 1
            continue
        report["checked"] += 1

        result = classify_email_deterministic(meta.get("sender") or "", subject, snippet)
        company = result["company"] if _known(result["company"]) else (app.company if _known(app.company) else "Unknown")
        role = result["role"] if result["role"] != "Unknown" else (app.role or "Unknown")

        history = meta.get("history") or []
        if history:
            statuses = [
                _event_status(event.get("subject") or "", snippet if i == len(history) - 1 else "", event.get("status"))
                for i, event in enumerate(history)
            ]
            status = _fold(statuses)
        else:
            statuses = []
            status = stored_status(result["status"], result["status_confidence"]) if result["status_found"] else app.status

        fingerprint = make_fingerprint(company, role, app.applied_date)
        if fingerprint and owner_of.get(fingerprint, app.id) != app.id:
            fingerprint = None
        after[status] += 1

        if (company, role, status) != (app.company, app.role, app.status):
            report["changed"] += 1
            report["changes"].append({
                "id": str(app.id),
                "before": {"company": app.company, "role": app.role, "status": app.status},
                "after": {"company": company, "role": role, "status": status},
            })

        if apply:
            if app.application_fingerprint and owner_of.get(app.application_fingerprint) == app.id:
                del owner_of[app.application_fingerprint]
            if fingerprint:
                owner_of[fingerprint] = app.id
            app.company, app.role, app.status = company, role, status
            app.application_fingerprint = fingerprint
            app.raw_metadata = {
                **meta,
                "snippet": snippet[:300],
                "history": [dict(event, status=s) for event, s in zip(history, statuses)] if history else history,
                "reclassified_at": utc_now().isoformat(),
            }

    if apply:
        await db.commit()
    report["status_after"] = dict(after)
    return report


def _print_report(report: dict) -> None:
    print(f"{'Saved' if report['applied'] else 'Dry run (nothing saved)'}: "
          f"checked {report['checked']}, {'changed' if report['applied'] else 'would change'} {report['changed']}, "
          f"skipped {report['skipped_manual']} edited by hand and {report['skipped_no_data']} without stored text.")
    statuses = sorted(set(report["status_before"]) | set(report["status_after"]))
    print("\nStatus           before  after")
    for status in statuses:
        print(f"  {status:<14} {report['status_before'].get(status, 0):>6} {report['status_after'].get(status, 0):>6}")
    if report["changes"]:
        print("\nChanges:")
        for change in report["changes"]:
            b, a = change["before"], change["after"]
            print(f"  {b['company']} / {b['role']} / {b['status']}  ->  {a['company']} / {a['role']} / {a['status']}")


async def _main(apply: bool) -> None:
    import applications.models  # noqa: F401
    import auth.models  # noqa: F401
    import companion.models  # noqa: F401
    import cv.models  # noqa: F401
    import goals.models  # noqa: F401
    import mail.models  # noqa: F401
    import diagnostics.models  # noqa: F401
    import ai.models  # noqa: F401
    from auth.dependencies import get_local_user
    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user = await get_local_user(db)
        _print_report(await reclassify_applications(db, user, apply=apply))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-classify stored applications with the rule-based classifier.")
    parser.add_argument("--apply", action="store_true", help="save the changes (default: report only)")
    asyncio.run(_main(parser.parse_args().apply))
