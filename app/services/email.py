import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def send_reset_email(to_email: str, reset_url: str) -> bool:
    """Send password reset email via Resend API."""
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set — logging reset URL instead")
        logger.info("Password reset URL for %s: %s", to_email, reset_url)
        return True

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.reset_from_email,
                "to": [to_email],
                "subject": "Reset your Frenmo password",
                "html": f"""
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
                """,
            },
        )

    if response.status_code == 200:
        logger.info("Reset email sent to %s", to_email)
        return True

    logger.error("Failed to send reset email: %s %s", response.status_code, response.text)
    return False
