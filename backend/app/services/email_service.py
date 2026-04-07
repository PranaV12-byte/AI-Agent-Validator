"""Async email sending service using stdlib smtplib with run_in_executor.

Leave SMTP_HOST empty (the default) to disable actual sending — the URL is
then only logged, which is the behaviour used in development and tests.
"""

import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from app.config import settings

logger = structlog.get_logger()


def _send_sync(to: str, subject: str, html_body: str) -> None:
    """Blocking SMTP send — called via run_in_executor so it doesn't block the event loop."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    if settings.smtp_ssl:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx) as server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, to, msg.as_string())
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_tls:
                server.ehlo()
                server.starttls()
                server.ehlo()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, to, msg.as_string())


async def send_email(to: str, subject: str, html_body: str) -> None:
    """Send an HTML email. No-ops (with a warning log) when SMTP_HOST is not configured.

    SMTP failures are logged but never raised — callers treat email delivery
    as best-effort so that transactional endpoints (signup, password reset)
    always complete even when the mail provider is misconfigured or unavailable.
    """
    if not settings.smtp_host:
        logger.warning("email_not_configured_skipping_send", to=to, subject=subject)
        return
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_sync, to, subject, html_body)
    except Exception as exc:
        try:
            logger.error("email_send_failed", to=to, subject=subject, error=str(exc))
        except Exception:
            pass  # Never let logging failures propagate


async def send_password_reset_email(to: str, reset_url: str) -> None:
    subject = "Reset your Safebot password"
    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;color:#333;max-width:480px;margin:0 auto;padding:24px;">
  <h2 style="color:#00D474;">Reset your password</h2>
  <p>You requested a password reset for your Safebot account.</p>
  <p>Click the button below to set a new password. This link expires in <strong>15 minutes</strong>.</p>
  <p style="margin:24px 0;">
    <a href="{reset_url}"
       style="display:inline-block;padding:12px 28px;background:#00D474;color:#000;text-decoration:none;border-radius:6px;font-weight:700;font-size:15px;">
      Reset Password
    </a>
  </p>
  <p style="color:#888;font-size:12px;">If you did not request a password reset, you can safely ignore this email.</p>
  <p style="color:#888;font-size:12px;word-break:break-all;">Or copy this link:<br>{reset_url}</p>
</body>
</html>"""
    await send_email(to, subject, html_body)


async def send_verification_email(to: str, verify_url: str) -> None:
    subject = "Verify your Safebot email address"
    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;color:#333;max-width:480px;margin:0 auto;padding:24px;">
  <h2 style="color:#00D474;">Verify your email</h2>
  <p>Welcome to Safebot! Please verify your email address to activate your account.</p>
  <p style="margin:24px 0;">
    <a href="{verify_url}"
       style="display:inline-block;padding:12px 28px;background:#00D474;color:#000;text-decoration:none;border-radius:6px;font-weight:700;font-size:15px;">
      Verify Email
    </a>
  </p>
  <p style="color:#888;font-size:12px;">This link expires in <strong>24 hours</strong>.</p>
  <p style="color:#888;font-size:12px;word-break:break-all;">Or copy this link:<br>{verify_url}</p>
</body>
</html>"""
    await send_email(to, subject, html_body)
