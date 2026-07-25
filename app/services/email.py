import logging
import aiosmtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


async def send_reset_email(to_email: str, reset_url: str) -> bool:
    """Send password reset email via Gmail SMTP."""
    if not settings.smtp_password:
        logger.warning("SMTP_PASSWORD not set — logging reset URL instead")
        logger.info("Password reset URL for %s: %s", to_email, reset_url)
        return True

    html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
            <h2 style="color: #1D1D1F; font-size: 24px; font-weight: 700; letter-spacing: -0.02em;">Reset your password</h2>
            <p style="color: #6E6E73; font-size: 15px; line-height: 1.6;">
                Someone requested a password reset for your Frenmo account. Click the button below to set a new password.
            </p>
            <a href="{reset_url}" style="display: inline-block; background: #007AFF; color: #FFFFFF; padding: 12px 32px; border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 15px; margin: 20px 0;">
                Reset Password
            </a>
            <p style="color: #AEAEB2; font-size: 13px; margin-top: 24px;">
                This link expires in 30 minutes. If you didn't request this, ignore this email.
            </p>
        </div>
    """

    msg = EmailMessage()
    msg["Subject"] = "Reset your Frenmo password"
    msg["From"] = settings.smtp_from_email
    msg["To"] = to_email
    msg.set_content("Reset your Frenmo password: " + reset_url)
    msg.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=settings.smtp_from_email,
            password=settings.smtp_password,
        )
        logger.info("Reset email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send reset email: %s", e)
        return False
