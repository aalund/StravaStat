# StravaStat

Jobs der analyserer din Strava-profil. Første job: **anbefalet FTP-indstilling**
baseret på dine spinning-timer (MOWL® / Intelligent Cycling).

## Sådan beregnes FTP'en

Jobbet finder dine MOWL/spinning-sessioner på Strava, henter wattstrømmene for
hver session og beregner:

- **Bedste 20-minutters gennemsnitseffekt × 0,95** (klassisk Coggan-estimat)
- **Bedste 60-minutters gennemsnitseffekt** (bruges direkte, hvis du har en
  session på mindst 55 minutter)

Den **anbefalede FTP** er den højeste troværdige kandidat, afrundet til nærmeste
5 W. Rapporten indeholder pr. session: varighed, gennemsnitswatt, Normalized
Power og bedste 5/20 min.

## Opsætning

1. Opret en Strava-app på <https://www.strava.com/settings/api> (Callback
   Domain kan fx være `localhost`).
2. Godkend adgang med `activity:read_all`-scope og gem dit **refresh token**.
   Nemmest er at åbne i en browser (erstat `YOUR_CLIENT_ID`):

   ```
   https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&approval_prompt=auto&scope=activity:read_all
   ```

   Byt derefter koden til et token (erstat `YOUR_CLIENT_ID`, `YOUR_CLIENT_SECRET`
   og `CODE`):

   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=YOUR_CLIENT_ID -d client_secret=YOUR_CLIENT_SECRET \
     -d code=CODE -d grant_type=authorization_code
   ```

   Brug `refresh_token` fra svaret.
3. Sæt miljøvariablerne:

   ```bash
   export STRAVA_CLIENT_ID=...
   export STRAVA_CLIENT_SECRET=...
   export STRAVA_REFRESH_TOKEN=...
   ```

## Kør lokalt

```bash
pip install -r requirements.txt
python -m stravastat.job --days 90 --keyword MOWL --json report.json
```

- `--days` (default 90): hvor langt tilbage jobbet kigger
- `--keyword` (default `MOWL`): ord der genkender spinning-sessioner i titlen.
  Sessioner optaget på indendørs cykel (`trainer=true`, type Ride/VirtualRide)
  tælles også med.
- `--json`: skriv rapporten som JSON-fil

## Mail

Rapporten (inkl. den anbefalede FTP i emnelinjen) kan sendes pr. mail:

```bash
python -m stravastat.email --report report.json --to dig@example.com
```

SMTP-indstillinger læses fra miljøvariablerne `SMTP_HOST`, `SMTP_PORT`
(default 465, implicit TLS; brug 587 hvis din server kræver STARTTLS),
`SMTP_USER`, `SMTP_PASSWORD` og valgfrit `SMTP_FROM`.

## Kør som planlagt job

`.github/workflows/ftp-job.yml` kører jobbet **hver mandag kl. 06:00 UTC** (og
kan afvikles manuelt via *Run workflow*) og sender rapporten til
henrik@aalund.eu. Tilføj disse repository-secrets under
*Settings → Secrets and variables → Actions*:

- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` (og evt. `SMTP_PORT`, default 465)

Rapporten uploades desuden som artifact.

## Test

```bash
python -m unittest discover -s tests -v
```
