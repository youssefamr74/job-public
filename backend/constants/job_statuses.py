"""Application statuses, allowed transitions, and the priority used to pick the best match by company."""

import enum


class ApplicationStatus(str, enum.Enum):
    APPLIED = "Applied"
    ASSESSMENT = "Assessment"
    INTERVIEW = "Interview"
    REJECTED = "Rejected"
    OFFER = "Offer"
    NEEDS_REVIEW = "Needs Review"


class ApplicationSource(str, enum.Enum):
    GMAIL = "gmail"
    MANUAL = "manual"


VALID_STATUSES = {s.value for s in ApplicationStatus}

STATUS_CHOICES = "Applied|Assessment|Interview|Offer|Rejected|Needs Review"

STATUS_PRIORITY = {
    "Applied":      1,
    "Assessment":   2,
    "Interview":    3,
    "Offer":        4,
    "Rejected":     0,
    "Needs Review": -1,
}

TERMINAL_STATUSES = {"Rejected", "Offer"}

# Any reply from the employer counts as a response, a rejection included.
# Needs Review does not: it only means the classifier was unsure.
RESPONSE_STATUSES = {"Assessment", "Interview", "Offer", "Rejected"}

# Statuses that create a companion moment, mapped to their moment_type.
MOMENT_TYPE_BY_STATUS = {
    "Rejected":   "rejection",
    "Interview":  "interview",
    "Assessment": "assessment",
    "Offer":      "offer",
}

VALID_TRANSITIONS = {
    "Applied":      {"Assessment", "Interview", "Rejected", "Offer", "Needs Review"},
    "Assessment":   {"Interview", "Rejected", "Offer", "Needs Review"},
    "Interview":    {"Offer", "Rejected", "Needs Review"},
    "Offer":        set(),
    "Rejected":     set(),
    "Needs Review": {"Applied", "Assessment", "Interview", "Offer", "Rejected"},
}
