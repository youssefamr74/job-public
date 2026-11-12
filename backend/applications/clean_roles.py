"""Apply the role cleanup (classifier/role_quality.py) once to roles already stored.

A role the cleanup changes is rewritten ("Position: Nurse" -> "Nurse"); a role it rejects (a sentence, the
company's name, a department alone) becomes "Unknown". Roles the user typed are never touched: applications
they added by hand, and roles they edited (a "role" edit on the timeline). role_group is recomputed, and the
old role is kept in raw_metadata["role_before_cleanup"].

    python -m applications.clean_roles            # dry run: report only
    python -m applications.clean_roles --apply    # save the changes
"""

import argparse
import asyncio
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from applications.models import Application
from applications.role_groups import role_group
from auth.models import User
from classifier.normalization import make_fingerprint
from classifier.role_quality import not_a_role, tidy_role


def role_edited_by_user(app: Application) -> bool:
    edits = (app.raw_metadata or {}).get("edits") or []
    return app.source == "manual" or any(isinstance(e, dict) and e.get("field") == "role" for e in edits)


def cleaned_role(role: Optional[str], company: Optional[str]) -> str:
    if not role or role == "Unknown":
        return "Unknown"
    return "Unknown" if not_a_role(role, company) else tidy_role(role)


def _counts(apps: list[Application], roles: dict) -> dict:
    values = [roles[app.id] for app in apps]
    known = [r for r in values if r != "Unknown"]
    return {
        "known roles": len(known),
        "Unknown roles": len(values) - len(known),
        "distinct roles": len({r.lower() for r in known}),
        "role groups": len({role_group(roles[a.id], a.company) for a in apps} - {None}),
    }


async def clean_stored_roles(db: AsyncSession, user: User, apply: bool = False) -> dict:
    apps = list((await db.execute(select(Application).where(Application.user_id == user.id))).scalars().all())
    owner_of = {a.application_fingerprint: a.id for a in apps if a.application_fingerprint}
    before = {a.id: a.role or "Unknown" for a in apps}
    after = dict(before)
    report = {"applied": apply, "rewritten": 0, "rejected": 0, "skipped_user_edited": 0, "changes": []}

    for app in apps:
        if role_edited_by_user(app):
            report["skipped_user_edited"] += 1
            continue
        new = cleaned_role(app.role, app.company)
        if new == (app.role or "Unknown"):
            continue
        after[app.id] = new
        report["rejected" if new == "Unknown" else "rewritten"] += 1
        report["changes"].append((app.company, app.role, new))
        if apply:
            fingerprint = make_fingerprint(app.company, new, app.applied_date)
            if fingerprint and owner_of.get(fingerprint, app.id) != app.id:
                fingerprint = None
            if app.application_fingerprint and owner_of.get(app.application_fingerprint) == app.id:
                del owner_of[app.application_fingerprint]
            if fingerprint:
                owner_of[fingerprint] = app.id
            app.raw_metadata = {**(app.raw_metadata or {}), "role_before_cleanup": app.role}
            app.role = new  # recomputes role_group
            app.application_fingerprint = fingerprint

    if apply:
        await db.commit()
    report["before"] = _counts(apps, before)
    report["after"] = _counts(apps, after)
    return report


def _print_report(report: dict, show_changes: bool) -> None:
    print(f"{'Saved' if report['applied'] else 'Dry run (nothing saved)'}: "
          f"{report['rewritten']} rewritten, {report['rejected']} set to Unknown, "
          f"{report['skipped_user_edited']} skipped (added or edited by you).")
    print("\n                  before  after")
    for name, value in report["before"].items():
        print(f"  {name:<15} {value:>6} {report['after'][name]:>6}")
    if show_changes and report["changes"]:
        print("\nChanges:")
        for company, old, new in report["changes"]:
            print(f"  {company} / {old}  ->  {new}")


async def _main(apply: bool, show_changes: bool) -> None:
    import applications.models  # noqa: F401
    import auth.models  # noqa: F401
    import companion.models  # noqa: F401
    import cv.models  # noqa: F401
    import goals.models  # noqa: F401
    import mail.models  # noqa: F401
    import diagnostics.models  # noqa: F401
    import ai.models  # noqa: F401
    import opportunities.models  # noqa: F401
    import sync_runs.models  # noqa: F401
    import notifications.models  # noqa: F401
    from auth.dependencies import get_local_user
    from database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user = await get_local_user(db)
        _print_report(await clean_stored_roles(db, user, apply=apply), show_changes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply the role cleanup to stored roles.")
    parser.add_argument("--apply", action="store_true", help="save the changes (default: report only)")
    parser.add_argument("--show", action="store_true", help="list every change")
    args = parser.parse_args()
    asyncio.run(_main(args.apply, args.show))
