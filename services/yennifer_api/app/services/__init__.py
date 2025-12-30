"""
Services module for Yennifer API.

Contains external service integrations like email (SendGrid).
"""

from .email import EmailService, send_email, send_sync_notification, send_token_expiry_alert

__all__ = [
    "EmailService",
    "send_email",
    "send_sync_notification",
    "send_token_expiry_alert",
]

