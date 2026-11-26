"""CLI job: analyse MOWL spinning sessions from Strava and recommend an FTP.

Credentials come from the environment (or flags):

- STRAVA_CLIENT_ID
- STRAVA_CLIENT_SECRET
- STRAVA_REFRESH_TOKEN

Usage:

    python -m stravastat.job --days 90 --keyword MOWL --json report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from .ftp import (
    FtpCandidate,
    PowerSeries,
    best_average_power,
    estimate_ftp_candidates,
    normalized_power,
    recommend_ftp,
    resample_to_seconds,
)
from .strava import StravaClient, StravaError

RIDE_TYPES = {"Ride", "VirtualRide"}
DEFAULT_KEYWORD = "MOWL"
DEFAULT_DAYS = 90


@dataclass
class SessionReport:
    activity_id: int
    name: str
    start_date: str
    duration_s: int
    matched_by: str
    avg_watts: float | None = None
    normalized_power: float | None = None
    best_5min: float | None = None
    best_20min: float | None = None
    ftp_candidates: list[dict] = field(default_factory=list)
    error: str | None = None


def matches_mowl(activity: dict, keyword: str) -> str | None:
    """Return why the activity counts as a spinning session, or None."""
    name = (activity.get("name") or "").lower()
    if keyword.lower() in name:
        return "name"
    if activity.get("trainer") and activity.get("type") in RIDE_TYPES:
        return "indoor ride"
    return None


def analyse_streams(streams: dict[str, list[float]]) -> dict:
    watts = streams.get("watts") or []
    times = streams.get("time") or []
    if not watts:
        return {}
    if times and len(times) == len(watts):
        try:
            watts = resample_to_seconds(times, watts)
        except ValueError:
            pass
    series = PowerSeries(watts=[float(w) for w in watts])
    result: dict = {
        "duration_s": len(series.watts),
        "avg_watts": round(sum(series.watts) / len(series.watts), 1),
        "normalized_power": (
            round(np, 1) if (np := normalized_power(series)) else None
        ),
        "ftp_candidates": [
            {"method": c.method, "ftp_watts": round(c.ftp_watts, 1), "source_value": round(c.source_value, 1)}
            for c in estimate_ftp_candidates(series)
        ],
    }
    for label, window in (("best_5min", 5 * 60), ("best_20min", 20 * 60)):
        best = best_average_power(series, window)
        if best is not None:
            result[label] = round(best[0], 1)
    return result


def run(days: int, keyword: str) -> dict:
    client = StravaClient(
        client_id=os.environ["STRAVA_CLIENT_ID"],
        client_secret=os.environ["STRAVA_CLIENT_SECRET"],
        refresh_token=os.environ["STRAVA_REFRESH_TOKEN"],
    )
    after = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    print(f"Henter aktiviteter fra de seneste {days} dage (sogeord: {keyword!r})...")
    sessions: list[SessionReport] = []
    analysed = 0
    for activity in client.get_activities(after_epoch=after):
        reason = matches_mowl(activity, keyword)
        if reason is None:
            continue
        report = SessionReport(
            activity_id=activity["id"],
            name=activity.get("name", ""),
            start_date=(activity.get("start_date_local") or "")[:16].replace("T", " "),
            duration_s=int(activity.get("moving_time") or activity.get("elapsed_time") or 0),
            matched_by=reason,
        )
        try:
            streams = client.get_streams(activity["id"])
            if streams and streams.get("watts"):
                result = analyse_streams(streams)
                report.avg_watts = result.get("avg_watts")
                report.normalized_power = result.get("normalized_power")
                report.best_5min = result.get("best_5min")
                report.best_20min = result.get("best_20min")
                report.ftp_candidates = result.get("ftp_candidates", [])
                analysed += 1
            else:
                report.error = "ingen wattdata i aktiviteten"
        except StravaError as exc:
            report.error = str(exc)
        sessions.append(report)
        print(
            f"  {report.start_date}  {report.name[:32]:<32}  "
            f"({report.error or f'{report.avg_watts} W avg'})"
        )

    all_candidates = [
        cand
        for session in sessions
        for cand in session.ftp_candidates
    ]
    candidate_objs = [
        FtpCandidate(ftp_watts=c["ftp_watts"], method=c["method"], source_value=c["source_value"])
        for c in all_candidates
    ]
    recommendation = recommend_ftp(candidate_objs)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keyword": keyword,
        "days": days,
        "sessions_found": len(sessions),
        "sessions_with_power": analysed,
        "recommended_ftp_watts": recommendation.ftp_watts if recommendation else None,
        "recommendation_method": recommendation.method if recommendation else None,
        "recommendation_source_value": (
            recommendation.source_value if recommendation else None
        ),
        "sessions": [asdict(s) for s in sessions],
    }


def render(result: dict) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"StravaStat - anbefalet FTP (MOWL spinning, seneste {result['days']} dage)")
    lines.append("=" * 78)
    lines.append(
        f"Fundet {result['sessions_found']} spinning-sessioner "
        f"({result['sessions_with_power']} med wattdata)"
    )
    lines.append("")
    lines.append(
        f"{'Dato':<17}{'Navn':<30}{'Varighed':>9}{'Avg W':>7}{'NP':>7}{'Best20':>8}"
    )
    lines.append("-" * 78)
    for s in result["sessions"]:
        minutes = s["duration_s"] // 60
        def fmt(value):
            return f"{value:.0f}" if isinstance(value, float) else "-"
        lines.append(
            f"{s['start_date']:<17}{s['name'][:29]:<30}"
            f"{minutes:>8}m{fmt(s['avg_watts']):>7}{fmt(s['normalized_power']):>7}"
            f"{fmt(s['best_20min']):>8}"
        )
        if s["error"]:
            lines.append(f"    ! {s['error']}")
    lines.append("")
    if result["recommended_ftp_watts"]:
        lines.append(f"ANBEFALET FTP-INDSTILLING: {result['recommended_ftp_watts']} W")
        lines.append(
            f"  baseret pa: {result['recommendation_method']} "
            f"(kildetermometer {result['recommendation_source_value']:.0f} W)"
        )
        lines.append(
            "  Saet denne vaerdi som FTP i MOWL-appen for at fa korrekte wattzoner."
        )
    else:
        lines.append(
            "Kunne ikke beregne en anbefaling: ingen sessioner med wattdata i perioden."
        )
        lines.append(
            "  Tip: Kob din MOWL-cykel til Strava (fx via MOWL-appen), sa wattmaalingen"
        )
        lines.append("  folger med til aktiviteterne.")
    lines.append("=" * 78)
    return "\n".join(lines)


def print_auth_guidance(exc: StravaError) -> None:
    if "read_permission" not in str(exc):
        return
    client_id = os.environ.get("STRAVA_CLIENT_ID", "YOUR_CLIENT_ID")
    authorize_url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}&response_type=code"
        "&approval_prompt=force&scope=activity:read_all"
    )
    print(
        "Refresh tokenet mangler tilladelsen activity:read_all.\n"
        "Sadan fikser du det:\n"
        "  1. Abner dette link i browseren og godkend: " + authorize_url + "\n"
        "  2. Byt `code` fra redirect-URL'en til et nyt token:\n"
        "     curl -X POST https://www.strava.com/oauth/token \\\n"
        "       -d client_id=... -d client_secret=... \\\n"
        "       -d code=KODEN -d grant_type=authorization_code\n"
        "  3. Erstat STRAVA_REFRESH_TOKEN (lokal shell eller GitHub secret) "
        "med `refresh_token` fra svaret.",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stravastat",
        description="Anbefalet FTP ud fra MOWL spinning-sessioner pa Strava.",
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS, help="antal dage tilbage at se paa"
    )
    parser.add_argument(
        "--keyword",
        default=os.environ.get("STRAVA_ACTIVITY_KEYWORD", DEFAULT_KEYWORD),
        help="navneord der identificerer spinning-sessioner (default: MOWL)",
    )
    parser.add_argument("--json", dest="json_path", help="skriv rapport som JSON fil")
    args = parser.parse_args(argv)

    missing = [
        var
        for var in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN")
        if not os.environ.get(var)
    ]
    if missing:
        print(
            "Mangler miljo-variable: " + ", ".join(missing) + "\n"
            "Se README.md for hvordan du opretter en Strava-app og faar et refresh token.",
            file=sys.stderr,
        )
        return 2

    try:
        result = run(days=args.days, keyword=args.keyword)
    except KeyError as exc:
        print(f"Mangler miljo-variable: {exc.args[0]}", file=sys.stderr)
        return 2
    except StravaError as exc:
        print_auth_guidance(exc)
        print(f"Strava-fejl: {exc}", file=sys.stderr)
        return 1

    print(render(result))
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        print(f"JSON-rapport skrevet til {args.json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
