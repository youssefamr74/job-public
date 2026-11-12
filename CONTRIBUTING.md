# Contributing

Jōb is early. Small, focused changes are easiest to review.

## Run the tests

From the `backend` folder, with Python 3.13:

```sh
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```

Run the whole suite before you open a pull request. Each test uses its own in-memory database.

For the web app, from the `web` folder with Node 20:

```sh
npm install
npm run lint && npm run typecheck && npm test
```

## Tests never contain real emails

Use made-up data only. Companies, people and addresses must be invented, for example
`Brightwave Careers <jobs@brightwave.example>`. Do not paste real emails, names, addresses or
links into tests, issues or pull requests, even with parts removed.

If you find an email the rules get wrong, write a short synthetic email that has the same shape
and use that.

## Add classifier phrases

The phrases live in `backend/constants/email_signals.py`:

- Status: `STRONG_REJECTION_PATTERNS`, `WEAK_REJECTION_PATTERNS`, `CONFIRMATION_PATTERNS`,
  `INTERVIEW_PATTERNS`, `ASSESSMENT_PATTERNS`, `OFFER_PATTERNS`.
- Filtering noise: the blocked sender, subject and body lists, and the job alert and social lists.
- Generic categories (calendar invites, account mail, surveys, outreach, marketing) are in
  `backend/classifier/categories.py`.

Steps:

1. Add the phrase as a lowercase regular expression. Keep it specific. A broad phrase will match
   emails it should not.
2. Add a synthetic case to `backend/tests/classifier_corpus.py` with the expected company, role and
   status. Add a case that must not match, if the phrase could be too broad.
3. Run `pytest`.

Prefer rules that fit a whole kind of email over rules for one company.

## Add role spellings

Analytics groups applications by the core of the job title: "Senior Nurse (m/w/d) - Berlin" counts as
Nurse. The rules in `backend/applications/role_groups.py` remove seniority and type words, bracketed parts,
gender markers, job ids, places and work modes for any profession. They never use a list of professions.

Equivalent spellings live in `backend/constants/role_synonyms.json`, one object per language:

```json
"de": { "entwicklerin": "entwickler", "software entwickler": "softwareentwickler" }
```

- Each entry maps a variant to the spelling to use. Both are matched as whole words.
- Write them lowercase, without accents, with spaces instead of hyphens ("ksiegowa", not "Księgowa").
  Case, accents and hyphens are ignored when matching, so "Full-Stack" and "full stack" are the same.
- Add only spellings of the same job: other gender forms, abbreviations, split or joined words. Two different
  jobs that a user wants counted together are a merge in Analytics, not a synonym.
- Copy the file to `web/src/demo/role_synonyms.json` too. A web test checks that they match.

Add a case to `backend/tests/test_role_groups.py` (`SAME_GROUP` or `DIFFERENT`) and run `pytest`. Stored
groups are recomputed when the backend starts.

### Words that tell a role from other text

`backend/constants/role_words.json` holds the words used by `backend/classifier/role_quality.py` to reject
text extracted as a role that isn't one: sentences, the company's name, a department or kind of position on
its own ("Digital", "Working student"), or more than 3 words without a job-title word. Add words lowercase
and without accents, add a case to `backend/tests/test_role_quality.py`, and copy the file to
`web/src/demo/role_words.json`.
