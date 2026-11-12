"""Job alerts and social mail never become applications; recruiter conversations do get through."""

import pytest

from classifier.heuristics import filter_reason
from classifier.text import clean_text

CASES = [
    ("LinkedIn <jobalerts-noreply@linkedin.com>", "Data Engineer at Brightwave", "Brightwave Warsaw", "job_alert"),
    ("LinkedIn <jobs-noreply@linkedin.com>", "New jobs similar to Data Engineer at Northwind Labs", "", "job_alert"),
    ("LinkedIn <jobs-noreply@linkedin.com>", "Brightwave is hiring for Data Engineer", "", "job_alert"),
    ("LinkedIn <jobs-noreply@linkedin.com>", "Jordan, apply now to Lumen Analytics", "", "job_alert"),
    ("LinkedIn <jobs-noreply@linkedin.com>", "Recommendations based on your activity", "", "job_alert"),
    ("LinkedIn <jobs-noreply@linkedin.com>", "Expand your search: 12 jobs you may be interested in", "", "job_alert"),
    ("Pracuj.pl <oferty@pracuj.pl>", "Nowe oferty dla Ciebie: Data Engineer", "", "job_alert"),
    ("justjoin.it <alerts@justjoin.it>", "5 new offers matching Python", "", "job_alert"),
    ("Indeed <alert@indeed.com>", "Data Engineer jobs for you", "", "job_alert"),
    ("Glassdoor <noreply@glassdoor.com>", "Recommended jobs for you", "", "job_alert"),
    ("No Fluff Jobs <hello@nofluffjobs.com>", "New offers in your area", "", "job_alert"),
    ("Indeed <donotreply@match.indeed.com>", "Data Engineer @ Brightwave", "", "job_alert"),
    ("Glassdoor <info@glassdoor.com>", "Job hunting? See who's hiring on the list", "", "job_alert"),
    ("Glassdoor Community <noreply@glassdoor.com>", "This came up in an interview", "", "social"),
    ("LinkedIn <messages-noreply@linkedin.com>", "people viewed your profile", "", "social"),
    ("LinkedIn <messages-noreply@linkedin.com>", "Brightwave is hiring for Data Engineer", "", "job_alert"),
    ("Taylor via LinkedIn <messaging-digest-noreply@linkedin.com>", "Taylor just messaged you", "", "social"),
    ("LinkedIn <invitations@linkedin.com>", "Jordan, you have 3 new connections", "", "social"),
    ('"Pracuj.pl - Status aplikacji" <noreply@aplikacje.pracuj.pl>', "Podsumowanie Twoich aplikacji", "", "social"),
    ("Code Practice <no-reply@leetcode.com>", "Weekly Digest", "Try this coding challenge", "social"),
    ("Brightwave Engineering <blog@brightwave.example>", "Our monthly newsletter", "We are hiring engineers", "social"),
    ("LinkedIn <news@em.linkedin.com>", "You're invited: career talks", "Join our job offer webinar", "social"),
    ("Community <noreply@redditmail.com>", "Hi all!", "I got a job offer yesterday", "social"),
    ("Taylor Reed via LinkedIn <hit-reply@linkedin.com>", "Message replied: Data Engineer opportunity", "", None),
    ("LinkedIn <jobs-noreply@linkedin.com>", "Jordan, your application was sent to Brightwave", "", None),
    ("LinkedIn <jobs-noreply@linkedin.com>", "Your application to Data Analyst at Lumen Analytics", "", None),
    ("Brightwave Careers <jobs@brightwave.example>", "Thank you for applying", "We received your application.", None),
]


@pytest.mark.parametrize("sender,subject,body,expected", CASES, ids=[c[1][:40] for c in CASES])
def test_filter_reason(sender, subject, body, expected):
    decision = filter_reason(sender, clean_text(subject), clean_text(body))
    assert (decision[0] if decision else None) == expected
