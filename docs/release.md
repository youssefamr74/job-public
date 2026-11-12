# Release checklist

1. On `main`, make sure CI is green: backend tests, web lint, typecheck, tests and build.
2. Update the screenshots in `docs/screenshots/` if the screens changed. Take them from the demo
   (`npm run build:demo`, then `npx vite preview --mode demo`) at 1440x900. Never use real data.
3. Tag the release and push the tag:

   ```sh
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The `Release` workflow builds the image for linux/amd64 and linux/arm64 and pushes
   `ghcr.io/youssefamr74/job-public:0.1.0` and `:latest`.
4. Check the image runs: download `docker-compose.release.yml` into an empty folder as
   `docker-compose.yml`, run `docker compose up -d`, and open <http://localhost:8000>.
5. Write the release notes on GitHub.

## After the first release

The package is private when GitHub creates it. Make it public once: on GitHub, open
Packages > job-public > Package settings, and set the visibility to Public. Without this,
`docker compose pull` fails for everyone else.
