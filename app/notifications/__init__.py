"""Email Notification & Career Alert Automation Module for Job-AI Career Buddy."""

from app.notifications.email import (
    BaseEmailProvider,
    ConsoleEmailProvider,
    EmailConfigurationError,
    MockEmailProvider,
    SMTPEmailProvider,
    get_email_provider,
)
from app.notifications.models import (
    DeliveryResult,
    DeliveryStatus,
    EmailMessage,
    EmailPriority,
)
from app.notifications.renderer import EmailTemplateRenderer
from app.notifications.service import EmailNotificationService, sanitize_filename

__all__ = [
    "BaseEmailProvider",
    "ConsoleEmailProvider",
    "DeliveryResult",
    "DeliveryStatus",
    "EmailConfigurationError",
    "EmailMessage",
    "EmailNotificationService",
    "EmailPriority",
    "EmailTemplateRenderer",
    "MockEmailProvider",
    "SMTPEmailProvider",
    "get_email_provider",
    "sanitize_filename",
]
