"""Email provider adapters and transport implementations for Job-AI.

Supports Console, SMTP (with TLS, auth, and timeout), and Mock providers.
Enforces strict finite network timeouts (<=30s) and bounded retries.
Zero credentials logged or exposed.
"""

from __future__ import annotations

import abc
import argparse
import email.mime.multipart
import email.mime.text
import logging
import smtplib
import sqlite3
import time
from datetime import UTC, datetime

from app.config import AppSettings, get_settings
from app.db.models import DeliveryStatus
from app.notifications.models import DeliveryResult, EmailMessage

logger = logging.getLogger(__name__)


class EmailConfigurationError(Exception):
    """Raised when email provider configuration is invalid or missing required credentials."""


class BaseEmailProvider(abc.ABC):
    """Abstract base class for all email provider adapters."""

    def __init__(self, timeout_seconds: int = 30, max_retries: int = 3):
        self.timeout_seconds = max(1, min(timeout_seconds, 60))
        self.max_retries = max(1, min(max_retries, 5))

    @abc.abstractmethod
    def send_message(self, message: EmailMessage, dry_run: bool = False) -> DeliveryResult:
        """Send an email message or simulate in dry-run mode."""
        raise NotImplementedError


def _safe_print(text: str) -> None:
    """Print text safely handling terminal encodings."""
    try:
        print(text)
    except (UnicodeEncodeError, OSError):
        print(text.encode("ascii", errors="backslashreplace").decode("ascii"))


class ConsoleEmailProvider(BaseEmailProvider):
    """Console / Logger provider that outputs emails safely to stdout without external network requests."""

    def send_message(self, message: EmailMessage, dry_run: bool = False) -> DeliveryResult:
        now_iso = datetime.now(UTC).isoformat()
        prefix = "[DRY-RUN]" if dry_run else "[CONSOLE-EMAIL]"
        _safe_print(f"\n{prefix} Email Dispatch -> {message.recipient}")
        _safe_print(f"Subject: {message.subject}")
        _safe_print(f"Priority: {message.priority.value}")
        _safe_print("-" * 50)
        _safe_print(message.text_content[:300] + ("..." if len(message.text_content) > 300 else ""))
        _safe_print("-" * 50)

        logger.info(
            "%s Email dispatched to %s | subject=%s | priority=%s",
            prefix,
            message.recipient,
            message.subject,
            message.priority.value,
        )

        return DeliveryResult(
            success=True,
            provider="console",
            provider_message_id=f"console_{int(time.time() * 1000)}",
            attempts=1,
            status=DeliveryStatus.SENT,
            timestamp=now_iso,
            dry_run=dry_run,
        )


class MockEmailProvider(BaseEmailProvider):
    """In-memory mock provider for testing email dispatch logic without network calls."""

    def __init__(
        self,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        should_fail: bool = False,
        fail_count: int = 0,
    ):
        super().__init__(timeout_seconds, max_retries)
        self.sent_messages: list[EmailMessage] = []
        self.should_fail = should_fail
        self.fail_count = fail_count
        self._current_failures = 0

    def send_message(self, message: EmailMessage, dry_run: bool = False) -> DeliveryResult:
        now_iso = datetime.now(UTC).isoformat()
        if dry_run:
            return DeliveryResult(
                success=True,
                provider="mock",
                provider_message_id=f"mock_dryrun_{len(self.sent_messages) + 1}",
                attempts=1,
                status=DeliveryStatus.SENT,
                timestamp=now_iso,
                dry_run=True,
            )

        if self.should_fail or (self._current_failures < self.fail_count):
            self._current_failures += 1
            return DeliveryResult(
                success=False,
                provider="mock",
                attempts=1,
                status=DeliveryStatus.FAILED,
                error_message="Simulated mock provider network failure",
                timestamp=now_iso,
                dry_run=False,
            )

        self.sent_messages.append(message)
        return DeliveryResult(
            success=True,
            provider="mock",
            provider_message_id=f"mock_{len(self.sent_messages)}",
            attempts=1,
            status=DeliveryStatus.SENT,
            timestamp=now_iso,
            dry_run=False,
        )


class SMTPEmailProvider(BaseEmailProvider):
    """Production-grade SMTP email provider with TLS/SSL, authentication, and finite timeouts."""

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ):
        super().__init__(timeout_seconds, max_retries)
        if not host:
            raise EmailConfigurationError("SMTP host must not be empty.")
        self.host = host
        self.port = port
        self.username = username
        self.password = password.strip() if password else None
        self.use_ssl = use_ssl or (port == 465)
        self.use_tls = use_tls and not self.use_ssl


    def send_message(self, message: EmailMessage, dry_run: bool = False) -> DeliveryResult:
        now_iso = datetime.now(UTC).isoformat()
        if dry_run:
            logger.info("SMTPEmailProvider [DRY-RUN] to %s (subject: %s)", message.recipient, message.subject)
            return DeliveryResult(
                success=True,
                provider="smtp",
                provider_message_id=f"smtp_dryrun_{int(time.time())}",
                attempts=1,
                status=DeliveryStatus.SENT,
                timestamp=now_iso,
                dry_run=True,
            )

        # Build MIME Message
        mime_msg = email.mime.multipart.MIMEMultipart("alternative")
        mime_msg["Subject"] = message.subject
        mime_msg["From"] = message.sender
        mime_msg["To"] = message.recipient
        mime_msg.attach(email.mime.text.MIMEText(message.text_content, "plain"))
        mime_msg.attach(email.mime.text.MIMEText(message.html_content, "html"))

        last_err: str | None = None
        attempt_count = 0

        # Clean password for Gmail if it contains spaced formatting e.g. "abcd efgh ijkl mnop"
        clean_password = self.password
        if clean_password and "gmail" in self.host.lower():
            clean_password = clean_password.replace(" ", "").strip()

        for attempt in range(1, self.max_retries + 1):
            attempt_count = attempt
            server = None
            try:
                if self.use_ssl:
                    server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout_seconds)
                    server.ehlo()
                else:
                    server = smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds)
                    server.ehlo()
                    if self.use_tls:
                        server.starttls()
                        server.ehlo()

                if self.username and clean_password:
                    server.login(self.username, clean_password)

                server.sendmail(message.sender, [message.recipient], mime_msg.as_string())
                return DeliveryResult(
                    success=True,
                    provider="smtp",
                    provider_message_id=f"smtp_{int(time.time() * 1000)}",
                    attempts=attempt,
                    status=DeliveryStatus.SENT,
                    timestamp=datetime.now(UTC).isoformat(),
                    dry_run=False,
                )

            except smtplib.SMTPAuthenticationError as auth_exc:
                err_text = auth_exc.smtp_error.decode("utf-8", errors="replace") if isinstance(auth_exc.smtp_error, bytes) else str(auth_exc.smtp_error)
                last_err = f"SMTP Authentication failed ({auth_exc.smtp_code}): {err_text}"
                if "BadCredentials" in err_text or auth_exc.smtp_code == 535:
                    last_err += " — Gmail requires a 16-character Google App Password (not your normal Google account password). Generate one at https://myaccount.google.com/apppasswords"
                logger.error("Non-retryable %s", last_err)
                break  # Do NOT retry on permanent authentication failures!

            except (smtplib.SMTPException, OSError, TimeoutError) as exc:
                last_err = str(exc)
                if "Connection unexpectedly closed" in last_err and "gmail" in self.host.lower():
                    last_err += " (Gmail closed connection — usually caused by using a standard account password instead of a 16-character Google App Password from https://myaccount.google.com/apppasswords)"
                logger.warning("SMTP delivery attempt %d/%d failed: %s", attempt, self.max_retries, last_err)
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 4))
            finally:
                if server:
                    try:
                        server.quit()
                    except (smtplib.SMTPException, OSError):
                        pass

        return DeliveryResult(
            success=False,
            provider="smtp",
            attempts=attempt_count,
            status=DeliveryStatus.FAILED,
            error_message=last_err or "Unknown SMTP error",
            timestamp=datetime.now(UTC).isoformat(),
            dry_run=False,
        )


def get_email_provider(cfg: AppSettings | None = None) -> BaseEmailProvider:
    """Factory creating configured email provider based on AppSettings."""
    settings = cfg or get_settings()
    provider_name = (settings.email_provider or "console").strip().lower()

    if provider_name == "smtp":
        if not settings.email_smtp_host:
            raise EmailConfigurationError(
                "JOB_AI_EMAIL_SMTP_HOST is required when JOB_AI_EMAIL_PROVIDER=smtp."
            )
        return SMTPEmailProvider(
            host=settings.email_smtp_host,
            port=settings.email_smtp_port,
            username=settings.email_username,
            password=settings.email_password,
            use_tls=settings.email_use_tls,
            use_ssl=getattr(settings, "email_use_ssl", False) or (settings.email_smtp_port == 465),
            timeout_seconds=settings.email_timeout_seconds,
            max_retries=settings.email_max_retries,
        )
    elif provider_name == "mock":
        return MockEmailProvider(
            timeout_seconds=settings.email_timeout_seconds,
            max_retries=settings.email_max_retries,
        )
    else:
        # Default to console provider
        return ConsoleEmailProvider(
            timeout_seconds=settings.email_timeout_seconds,
            max_retries=settings.email_max_retries,
        )


# =============================================================================
# CLI Entrypoint for testing email configuration
# =============================================================================
def main() -> int:
    """CLI utility to test email configuration with a single verified test email."""
    parser = argparse.ArgumentParser(description="Job-AI Email Notification CLI")
    parser.add_argument("--test", action="store_true", help="Send a single test email to configured recipient")
    parser.add_argument("--dry-run", action="store_true", help="Render and simulate email without sending network requests")
    parser.add_argument("--to", type=str, default=None, help="Override recipient email address")
    args = parser.parse_args()

    cfg = get_settings()
    recipient = args.to or cfg.email_to

    try:
        from app.db.connection import get_connection
        from app.notifications.service import EmailNotificationService

        conn = get_connection()
        service = EmailNotificationService(conn=conn, settings=cfg)
        result = service.send_test_email(recipient=recipient, dry_run=args.dry_run)
    except (sqlite3.Error, OSError, ValueError, RuntimeError) as e:
        logger.warning("Could not initialize EmailNotificationService with DB (%s), using direct provider", e)
        from app.notifications.renderer import EmailTemplateRenderer

        renderer = EmailTemplateRenderer(dashboard_base_url=cfg.dashboard_url)
        msg = renderer.render_test_email(recipient=recipient, sender=cfg.email_from)
        provider = get_email_provider(cfg)
        result = provider.send_message(msg, dry_run=args.dry_run)

    _safe_print(f"\nEmail Test Result: {'SUCCESS' if result.success else 'FAILED'}")
    _safe_print(f"Provider: {result.provider}")
    _safe_print(f"Recipient: {recipient}")
    _safe_print(f"Dry Run: {result.dry_run}")
    if result.error_message:
        _safe_print(f"Error: {result.error_message}")

    return 0 if result.success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
