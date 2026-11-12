# Known issues

- **Duplicate opportunities in one thread.** Jōb keeps one opportunity per thread. A recruiter email
  that arrives without a thread id, or from a new thread, can still create a second row. Delete or
  ignore the extra row.
- **Lowercase person names as company.** A sender name written in lowercase, for example
  `jordan lee`, is not recognised as a person. It can be taken as the company name instead of the
  company from the sender's domain.
- **Converted opportunities do not always carry the interview status.** An opportunity converted by
  hand becomes an application with the status Applied, even if the recruiter has already invited you
  to an interview. Converting by a later email works only when that email names the company.
