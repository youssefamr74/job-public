# Security

## Reporting a vulnerability

Please report it privately. Do not open a public issue.

Use GitHub private vulnerability reporting: open the repository, go to the **Security** tab, and
choose **Report a vulnerability**. Describe what you found and how to reproduce it. Use made-up data
in your report, not real emails or credentials.

I will answer as soon as I can. This is a personal project, so there is no fixed response time.

## Scope and design

Jōb is meant to run on your own computer, on localhost. The API has no login. Anyone who can reach
the port can read your applications and use your connected accounts.

- Docker Compose publishes the port on `127.0.0.1` only. Do not change it to `0.0.0.0` or put the
  app on a public network.
- Mail credentials and AI API keys are stored encrypted in `data`. The key is in `data/secret.key`,
  or in `SECRET_KEY` if you set it. Protect the whole `data` folder.
- Email content is never written to the sync history or to error messages.

Reports that need the API to be exposed to a network, or access to your `data` folder, are out of
scope. Reports about the points above are welcome.
