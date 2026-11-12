# Roadmap

Planned items. No code yet.

## 1. In-app notifications

Local only. Nothing is sent outside the app.

- **Storage:** a `notifications` table, filled by sync and by scheduled checks.
- **Events:**
  - new rejection
  - new interview
  - new assessment
  - upcoming interview
  - stale applications (14+ days without activity)
  - weekly summary
  - mail needs reconnecting
- **API:** list notifications, unread count, mark one as read, mark all as read.
- **UI:** a bell with an unread badge, and a notifications page.
- **Retention:** notifications are cleaned up automatically after 90 days.

## 2. Published Docker image

- GitHub Actions builds the image on release tags and pushes it to
  `ghcr.io/youssefamr74/job-public`.
- Multi-arch: `linux/amd64` and `linux/arm64`.
- The README quick start switches to the published image, so users no longer
  need to clone the repo.
