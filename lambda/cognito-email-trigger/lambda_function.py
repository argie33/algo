"""
Cognito Custom Message Lambda Trigger

Intercepts Cognito email events (sign-up, password reset, etc.) and sends via AWS SES.
Allows custom email templates and professional branding.

Events:
- CustomMessage_SignUp: User confirms sign-up code
- CustomMessage_ForgotPassword: User requests password reset
- CustomMessage_AdminCreateUser: Admin creates user
- CustomMessage_ResendCode: User requests resend of confirmation code
"""

import logging
import threading
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ses_client = None
_ses_client_lock = threading.Lock()


def get_ses_client():
    """Lazy-load SES client to avoid credential loading during imports (thread-safe)."""
    global _ses_client
    if _ses_client is None:
        with _ses_client_lock:
            # Double-check pattern to avoid race conditions
            if _ses_client is None:
                _ses_client = boto3.client("ses", region_name="us-east-1")
    return _ses_client


# Configuration
SENDER_EMAIL = "argeropolos@gmail.com"
SENDER_NAME = "Bullseye Trading"


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle Cognito custom message trigger."""

    trigger_source = event.get("triggerSource")

    # CRITICAL: Validate Cognito event structure before accessing nested fields
    request_data = event.get("request")
    if request_data is None:
        raise RuntimeError(
            "[COGNITO_EMAIL_TRIGGER] CRITICAL: Missing 'request' key in Cognito event. "
            "Cannot extract user attributes or confirmation code. Check Cognito trigger configuration."
        )

    user_attributes = request_data.get("userAttributes")
    if user_attributes is None:
        raise RuntimeError(
            "[COGNITO_EMAIL_TRIGGER] CRITICAL: Missing 'userAttributes' in Cognito request. "
            "Cognito trigger must provide user attributes. Check trigger configuration."
        )

    code_parameter = request_data.get("codeParameter")
    if not code_parameter:
        raise RuntimeError(
            "[COGNITO_EMAIL_TRIGGER] CRITICAL: Confirmation code missing from Cognito request. "
            "Cannot send authentication code without valid codeParameter. Check Cognito trigger configuration."
        )

    email = user_attributes.get("email")
    if not email:
        raise RuntimeError(
            "[COGNITO_EMAIL_TRIGGER] CRITICAL: User email missing from attributes. "
            "Cannot send confirmation email without recipient address."
        )

    logger.info(f"Cognito trigger: {trigger_source} for user {email}")

    try:
        if trigger_source == "CustomMessage_SignUp":
            subject, html_body = build_signup_email(email, code_parameter)
        elif trigger_source == "CustomMessage_ForgotPassword":
            subject, html_body = build_password_reset_email(email, code_parameter)
        elif trigger_source == "CustomMessage_ResendCode":
            subject, html_body = build_resend_code_email(email, code_parameter)
        elif trigger_source == "CustomMessage_AdminCreateUser":
            subject, html_body = build_admin_create_user_email(email, code_parameter)
        else:
            logger.warning(f"Unknown trigger source: {trigger_source}")
            return event

        # Send via SES
        send_email(email, subject, html_body)
        logger.info(f"Email sent successfully to {email}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to send email: {error_msg}", exc_info=True)
        raise

    # Return event unchanged (Cognito won't send its default email)
    return event


def send_email(recipient: str, subject: str, html_body: str) -> None:
    """Send email via AWS SES."""
    get_ses_client().send_email(
        Source=f"{SENDER_NAME} <{SENDER_EMAIL}>",
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
        },
    )


def build_signup_email(email: str, code: str) -> tuple[str, str]:
    """Build sign-up confirmation email."""
    subject = "Verify Your Bullseye Trading Account"
    html = """
    <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2>Welcome to Bullseye Trading</h2>
                <p>Thank you for signing up. Please confirm your email address by entering this code:</p>
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; font-size: 24px; font-weight: bold; font-family: monospace; letter-spacing: 2px;">
                    {code}
                </div>
                <p>This code expires in 24 hours.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">If you didn't sign up for this account, please ignore this email.</p>
            </div>
        </body>
    </html>
    """
    return subject, html


def build_password_reset_email(email: str, code: str) -> tuple[str, str]:
    """Build password reset email."""
    subject = "Reset Your Bullseye Trading Password"
    html = """
    <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2>Password Reset Request</h2>
                <p>We received a request to reset your password. Enter this code to proceed:</p>
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; font-size: 24px; font-weight: bold; font-family: monospace; letter-spacing: 2px;">
                    {code}
                </div>
                <p>This code expires in 24 hours.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">If you didn't request a password reset, please secure your account immediately.</p>
            </div>
        </body>
    </html>
    """
    return subject, html


def build_resend_code_email(email: str, code: str) -> tuple[str, str]:
    """Build resend confirmation code email."""
    subject = "Your Bullseye Trading Confirmation Code"
    html = """
    <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2>Confirmation Code</h2>
                <p>Here's your new confirmation code:</p>
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; font-size: 24px; font-weight: bold; font-family: monospace; letter-spacing: 2px;">
                    {code}
                </div>
                <p>This code expires in 24 hours.</p>
            </div>
        </body>
    </html>
    """
    return subject, html


def build_admin_create_user_email(email: str, code: str) -> tuple[str, str]:
    """Build admin-created user welcome email."""
    subject = "Welcome to Bullseye Trading - Set Your Password"
    html = """
    <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2>Welcome to Bullseye Trading</h2>
                <p>Your account has been created. Set your password using this code:</p>
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; font-size: 24px; font-weight: bold; font-family: monospace; letter-spacing: 2px;">
                    {code}
                </div>
                <p>This code expires in 24 hours.</p>
            </div>
        </body>
    </html>
    """
    return subject, html
