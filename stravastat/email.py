"""Email delivery of the FTP recommendation report."""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

from .job import render

DEFAULT_PORT = 587


def parse_port(value: str | None, default: int = DEFAULT_PORT) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_message(
    subject: str, body: str, to_addr: str, from_addr: str | None = None
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr or to_addr
    message["To"] = to_addr
    message.set_content(body)
    return message


def send_email(
    message: EmailMessage,
    host: str,
    port: int,
    user: str | None = None,
    password: str | None = None,
    timeout: float = 30.0,
) -> None:
    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
    try:
        if port != 465:
            server.starttls(context=context)
        if user and password:
            server.login(user, password)
        server.send_message(message)
    finally:
        server.quit()


def subject_for(report: dict) -> str:
    ftp = report.get("recommended_ftp_watts")
    if ftp:
        return f"StravaStat: anbefalet FTP {ftp} W"
    return "StravaStat: ingen FTP-anbefaling denne uge"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stravastat-email", description="Send FTP-rapporten pr. mail."
    )
    parser.add_argument("--report", required=True, help="sti til JSON-rapporten")
    parser.add_argument("--to", required=True, help="modtagerens mailadresse")
    parser.add_argument("--from", dest="from_addr", default=os.environ.get("SMTP_FROM"))
    parser.add_argument("--host", default=os.environ.get("SMTP_HOST"))
    parser.add_argument(
        "--port", type=parse_port, default=parse_port(os.environ.get("SMTP_PORT"))
    )
    parser.add_argument("--user", default=os.environ.get("SMTP_USER"))
    parser.add_argument("--password", default=os.environ.get("SMTP_PASSWORD"))
    args = parser.parse_args(argv)

    missing = [
        name
        for name, value in (
            ("SMTP_HOST", args.host),
            ("SMTP_USER", args.user),
            ("SMTP_PASSWORD", args.password),
        )
        if not value
    ]
    if missing:
        print(
            "Mangler SMTP-indstillinger: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    with open(args.report, encoding="utf-8") as fh:
        report = json.load(fh)
    message = build_message(subject_for(report), render(report), args.to, args.from_addr)
    try:
        send_email(message, args.host, args.port, args.user, args.password)
    except (smtplib.SMTPException, OSError) as exc:
        print(f"Kunne ikke sende mail: {exc}", file=sys.stderr)
        return 1
    print(f"FTP-rapport sendt til {args.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
