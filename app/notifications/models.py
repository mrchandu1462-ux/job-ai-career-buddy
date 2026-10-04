"""Models and enums for Job-AI Email Notification & Career Alert Automation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import DeliveryStatus


class EmailPriority(str, Enum):
    """Email priority levels mapped to candidate application priority."""

    CRITICAL = "CRITICAL"  # 90-100: Send immediately (🚨)
    HIGH = "HIGH"          # 80-89: Send immediately (🔥)
    APPLY = "APPLY"        # 70-79: Include in daily digest (🟢)
    WATCH = "WATCH"        # 60-69: Dashboard / digest only (👀)
    SKIP = "SKIP"          # <60: No email (❌)
    DIGEST = "DIGEST"      # Daily digest email (📅)
    TEST = "TEST"          # Explicit manual test email (🧪)


class EmailMessage(BaseModel):
    """Encapsulates a fully formatted outbound email message."""

    model_config = ConfigDict(extra="forbid")

    recipient: str = Field(..., min_length=1, description="Destination email address.")
    sender: str = Field(..., min_length=1, description="From email address.")
    subject: str = Field(..., min_length=1, description="Subject line.")
    html_content: str = Field(..., min_length=1, description="Rendered responsive HTML body.")
    text_content: str = Field(..., min_length=1, description="Plain text fallback body.")
    priority: EmailPriority = Field(default=EmailPriority.HIGH)
    job_id: int | None = None
    application_id: int | None = None
    notification_id: int | None = None
    fingerprint: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class DeliveryResult(BaseModel):
    """Result of an email delivery attempt."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether delivery succeeded.")
    provider: str = Field(..., description="Provider name (smtp, console, sendgrid, mock).")
    provider_message_id: str | None = Field(default=None, description="Provider transaction ID.")
    attempts: int = Field(default=1, ge=1)
    status: DeliveryStatus = Field(default=DeliveryStatus.SENT)
    error_message: str | None = None
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of attempt.")
    dry_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
