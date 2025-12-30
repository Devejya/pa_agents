"""
Email Service Module using SendGrid.

Provides email sending capabilities for notifications:
- Sync success/failure notifications
- Token expiry alerts
- Admin notifications
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Personalization

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Email service using SendGrid.
    
    Provides methods for sending various notification emails.
    """
    
    def __init__(self):
        """Initialize the email service."""
        self.settings = get_settings()
        self._client: Optional[SendGridAPIClient] = None
        
    @property
    def client(self) -> Optional[SendGridAPIClient]:
        """Get or create the SendGrid client."""
        if self._client is None:
            api_key = self.settings.sendgrid_api_key
            if api_key:
                self._client = SendGridAPIClient(api_key=api_key)
        return self._client
    
    @property
    def is_configured(self) -> bool:
        """Check if email service is configured."""
        return bool(self.settings.sendgrid_api_key)
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> dict:
        """
        Send an email using SendGrid.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email body
            plain_content: Plain text email body (optional)
            from_email: Sender email (defaults to config)
            from_name: Sender name (defaults to config)
            
        Returns:
            Dict with 'success' and optionally 'error' or 'message_id'
        """
        if not self.is_configured:
            logger.warning("SendGrid API key not configured, skipping email")
            return {"success": False, "error": "Email service not configured"}
        
        try:
            message = Mail(
                from_email=Email(
                    from_email or self.settings.sendgrid_from_email,
                    from_name or self.settings.sendgrid_from_name,
                ),
                to_emails=To(to_email),
                subject=subject,
                html_content=Content("text/html", html_content),
            )
            
            if plain_content:
                message.add_content(Content("text/plain", plain_content))
            
            response = self.client.send(message)
            
            logger.info(f"Email sent to {to_email}: {subject} (status: {response.status_code})")
            
            return {
                "success": response.status_code in (200, 201, 202),
                "status_code": response.status_code,
                "message_id": response.headers.get("X-Message-Id"),
            }
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_sync_notification(
        self,
        to_email: str,
        sync_result: dict,
        sync_type: str = "contacts",
    ) -> dict:
        """
        Send a sync completion notification.
        
        Args:
            to_email: User's email
            sync_result: Sync result with added, updated, conflicts, errors
            sync_type: Type of sync (contacts, calendar, etc.)
            
        Returns:
            Email send result
        """
        success = sync_result.get("success", False)
        added = sync_result.get("added", 0)
        updated = sync_result.get("updated", 0)
        conflicts = sync_result.get("conflicts", 0)
        errors = sync_result.get("errors", [])
        
        if success:
            subject = f"✅ {sync_type.title()} Sync Complete"
            status_color = "#10B981"
            status_text = "Successful"
        else:
            subject = f"⚠️ {sync_type.title()} Sync Completed with Issues"
            status_color = "#F59E0B"
            status_text = "Completed with issues"
        
        html_content = self._generate_sync_email(
            sync_type=sync_type,
            status_text=status_text,
            status_color=status_color,
            added=added,
            updated=updated,
            conflicts=conflicts,
            errors=errors,
        )
        
        plain_content = f"""
{sync_type.title()} Sync {status_text}

Summary:
- Added: {added}
- Updated: {updated}
- Conflicts: {conflicts}
- Errors: {len(errors)}

{('Errors:' + chr(10) + chr(10).join('- ' + e for e in errors)) if errors else ''}

This is an automated message from Yennifer.
"""
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            plain_content=plain_content,
        )
    
    async def send_token_expiry_alert(
        self,
        to_email: str,
        provider: str = "Google",
        reauth_url: Optional[str] = None,
    ) -> dict:
        """
        Send an alert that OAuth tokens have expired.
        
        Args:
            to_email: User's email
            provider: OAuth provider name
            reauth_url: URL to re-authenticate
            
        Returns:
            Email send result
        """
        subject = f"🔑 {provider} Access Expired - Action Required"
        
        reauth_url = reauth_url or f"{self.settings.frontend_url}/login"
        
        html_content = self._generate_token_expiry_email(
            provider=provider,
            reauth_url=reauth_url,
        )
        
        plain_content = f"""
Your {provider} Access Has Expired

Your connection to {provider} has expired. To continue using Yennifer's features:

1. Visit: {reauth_url}
2. Sign in with your {provider} account
3. Grant the necessary permissions

This will restore access to your {provider} Calendar, Contacts, Drive, and other services.

If you didn't expect this email, please ignore it.

This is an automated message from Yennifer.
"""
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            plain_content=plain_content,
        )
    
    async def send_sync_failure_alert(
        self,
        to_email: str,
        sync_type: str,
        error_message: str,
        consecutive_failures: int = 1,
    ) -> dict:
        """
        Send an alert about sync failures.
        
        Args:
            to_email: User's email
            sync_type: Type of sync that failed
            error_message: Error details
            consecutive_failures: Number of consecutive failures
            
        Returns:
            Email send result
        """
        subject = f"❌ {sync_type.title()} Sync Failed"
        
        html_content = self._generate_sync_failure_email(
            sync_type=sync_type,
            error_message=error_message,
            consecutive_failures=consecutive_failures,
        )
        
        plain_content = f"""
{sync_type.title()} Sync Failed

We encountered an error syncing your {sync_type}:

{error_message}

This is failure #{consecutive_failures}. We'll continue trying, but you may need to re-authenticate if the problem persists.

Visit {self.settings.frontend_url}/login to re-connect your account.

This is an automated message from Yennifer.
"""
        
        return await self.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            plain_content=plain_content,
        )
    
    def _generate_sync_email(
        self,
        sync_type: str,
        status_text: str,
        status_color: str,
        added: int,
        updated: int,
        conflicts: int,
        errors: list,
        user_timezone: str = "America/New_York",
    ) -> str:
        """Generate HTML for sync notification email."""
        # Convert UTC to user's local timezone (default: US Eastern)
        try:
            tz = ZoneInfo(user_timezone)
            local_time = datetime.now(timezone.utc).astimezone(tz)
            timestamp = local_time.strftime("%B %d, %Y at %I:%M %p %Z")
        except Exception:
            # Fallback to UTC if timezone is invalid
            timestamp = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")
        
        error_section = ""
        if errors:
            error_items = "".join(f'<li style="margin-bottom: 8px; color: #DC2626;">{e}</li>' for e in errors[:5])
            if len(errors) > 5:
                error_items += f'<li style="color: #6B7280;">...and {len(errors) - 5} more</li>'
            error_section = f'''
            <tr>
              <td style="padding-top: 24px;">
                <h3 style="margin: 0 0 12px 0; color: #DC2626; font-size: 14px; font-weight: 600;">Errors</h3>
                <ul style="margin: 0; padding-left: 20px; font-size: 13px;">{error_items}</ul>
              </td>
            </tr>
            '''
        
        return f'''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{sync_type.title()} Sync Complete</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F9FAFB; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #F9FAFB;">
    <tr>
      <td align="center" style="padding: 40px 20px;">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width: 560px; width: 100%;">
          
          <!-- Header -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <span style="font-family: Georgia, serif; font-size: 24px; color: #7C3AED;">Yennifer</span>
            </td>
          </tr>
          
          <!-- Main Card -->
          <tr>
            <td style="background-color: #FFFFFF; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                
                <!-- Status Banner -->
                <tr>
                  <td style="background-color: {status_color}; padding: 16px 24px; border-radius: 12px 12px 0 0;">
                    <h1 style="margin: 0; color: #FFFFFF; font-size: 18px; font-weight: 600;">
                      {sync_type.title()} Sync {status_text}
                    </h1>
                  </td>
                </tr>
                
                <!-- Content -->
                <tr>
                  <td style="padding: 24px;">
                    <p style="margin: 0 0 20px 0; color: #6B7280; font-size: 14px;">
                      Completed on {timestamp}
                    </p>
                    
                    <!-- Stats Grid -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                      <tr>
                        <td style="width: 30%; text-align: center; padding: 16px; background-color: #F0FDF4; border-radius: 8px;">
                          <div style="font-size: 24px; font-weight: 600; color: #16A34A;">{added}</div>
                          <div style="font-size: 12px; color: #6B7280; margin-top: 4px;">Added</div>
                        </td>
                        <td style="width: 5%;"></td>
                        <td style="width: 30%; text-align: center; padding: 16px; background-color: #EFF6FF; border-radius: 8px;">
                          <div style="font-size: 24px; font-weight: 600; color: #2563EB;">{updated}</div>
                          <div style="font-size: 12px; color: #6B7280; margin-top: 4px;">Updated</div>
                        </td>
                        <td style="width: 5%;"></td>
                        <td style="width: 30%; text-align: center; padding: 16px; background-color: #FEF3C7; border-radius: 8px;">
                          <div style="font-size: 24px; font-weight: 600; color: #D97706;">{conflicts}</div>
                          <div style="font-size: 12px; color: #6B7280; margin-top: 4px;">Conflicts</div>
                        </td>
                      </tr>
                    </table>
                    
                    {error_section}
                  </td>
                </tr>
                
              </table>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td align="center" style="padding-top: 24px;">
              <p style="margin: 0; font-size: 12px; color: #9CA3AF;">
                This is an automated message from Yennifer. Please do not reply.
              </p>
            </td>
          </tr>
          
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
'''
    
    def _generate_token_expiry_email(
        self,
        provider: str,
        reauth_url: str,
    ) -> str:
        """Generate HTML for token expiry alert email."""
        return f'''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{provider} Access Expired</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F9FAFB; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #F9FAFB;">
    <tr>
      <td align="center" style="padding: 40px 20px;">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width: 560px; width: 100%;">
          
          <!-- Header -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <span style="font-family: Georgia, serif; font-size: 24px; color: #7C3AED;">Yennifer</span>
            </td>
          </tr>
          
          <!-- Main Card -->
          <tr>
            <td style="background-color: #FFFFFF; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 32px;">
              
              <!-- Icon -->
              <div style="text-align: center; margin-bottom: 24px;">
                <span style="display: inline-block; width: 64px; height: 64px; background-color: #FEF3C7; border-radius: 50%; line-height: 64px; font-size: 32px;">🔑</span>
              </div>
              
              <h1 style="margin: 0 0 16px 0; text-align: center; color: #1F2937; font-size: 20px; font-weight: 600;">
                Your {provider} Access Has Expired
              </h1>
              
              <p style="margin: 0 0 24px 0; text-align: center; color: #6B7280; font-size: 15px; line-height: 1.6;">
                To continue using Yennifer's features with your {provider} account, you'll need to reconnect.
              </p>
              
              <!-- CTA Button -->
              <div style="text-align: center; margin-bottom: 24px;">
                <a href="{reauth_url}" style="display: inline-block; padding: 14px 32px; background-color: #7C3AED; color: #FFFFFF; text-decoration: none; border-radius: 8px; font-weight: 500; font-size: 15px;">
                  Reconnect {provider}
                </a>
              </div>
              
              <p style="margin: 0; text-align: center; color: #9CA3AF; font-size: 13px;">
                This will restore access to your Calendar, Contacts, Drive, and other services.
              </p>
              
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td align="center" style="padding-top: 24px;">
              <p style="margin: 0; font-size: 12px; color: #9CA3AF;">
                If you didn't expect this email, please ignore it.
              </p>
            </td>
          </tr>
          
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
'''
    
    def _generate_sync_failure_email(
        self,
        sync_type: str,
        error_message: str,
        consecutive_failures: int,
    ) -> str:
        """Generate HTML for sync failure alert email."""
        return f'''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{sync_type.title()} Sync Failed</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F9FAFB; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #F9FAFB;">
    <tr>
      <td align="center" style="padding: 40px 20px;">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width: 560px; width: 100%;">
          
          <!-- Header -->
          <tr>
            <td align="center" style="padding-bottom: 24px;">
              <span style="font-family: Georgia, serif; font-size: 24px; color: #7C3AED;">Yennifer</span>
            </td>
          </tr>
          
          <!-- Main Card -->
          <tr>
            <td style="background-color: #FFFFFF; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
              
              <!-- Error Banner -->
              <div style="background-color: #FEE2E2; padding: 16px 24px; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0; color: #DC2626; font-size: 18px; font-weight: 600;">
                  ❌ {sync_type.title()} Sync Failed
                </h1>
              </div>
              
              <div style="padding: 24px;">
                <p style="margin: 0 0 16px 0; color: #6B7280; font-size: 14px;">
                  Failure #{consecutive_failures}
                </p>
                
                <!-- Error Box -->
                <div style="background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                  <p style="margin: 0; color: #DC2626; font-size: 14px; font-family: monospace;">
                    {error_message}
                  </p>
                </div>
                
                <p style="margin: 0 0 20px 0; color: #4B5563; font-size: 14px; line-height: 1.6;">
                  We'll continue trying to sync automatically. If the problem persists, you may need to reconnect your account.
                </p>
                
                <!-- CTA Button -->
                <div style="text-align: center;">
                  <a href="{self.settings.frontend_url}/login" style="display: inline-block; padding: 12px 24px; background-color: #7C3AED; color: #FFFFFF; text-decoration: none; border-radius: 8px; font-weight: 500; font-size: 14px;">
                    Reconnect Account
                  </a>
                </div>
              </div>
              
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td align="center" style="padding-top: 24px;">
              <p style="margin: 0; font-size: 12px; color: #9CA3AF;">
                This is an automated message from Yennifer.
              </p>
            </td>
          </tr>
          
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
'''


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


# Convenience functions
async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    plain_content: Optional[str] = None,
) -> dict:
    """Send an email."""
    return await get_email_service().send_email(to_email, subject, html_content, plain_content)


async def send_sync_notification(to_email: str, sync_result: dict, sync_type: str = "contacts") -> dict:
    """Send a sync notification."""
    return await get_email_service().send_sync_notification(to_email, sync_result, sync_type)


async def send_token_expiry_alert(to_email: str, provider: str = "Google") -> dict:
    """Send a token expiry alert."""
    return await get_email_service().send_token_expiry_alert(to_email, provider)


async def send_sync_failure_alert(
    to_email: str,
    sync_type: str,
    error_message: str,
    consecutive_failures: int = 1,
) -> dict:
    """Send a sync failure alert."""
    return await get_email_service().send_sync_failure_alert(
        to_email, sync_type, error_message, consecutive_failures
    )

