import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app

logger = logging.getLogger(__name__)


def send_email(to_email, subject, html_body, text_body=None):
    try:
        cfg = current_app.config
        if not cfg.get("SMTP_USERNAME"):
            logger.warning("SMTP not configured, skipping email")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["FROM_EMAIL"]
        msg["To"] = to_email

        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(cfg["SMTP_SERVER"], cfg["SMTP_PORT"]) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
            server.sendmail(cfg["FROM_EMAIL"], to_email, msg.as_string())

        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def _base_template(content, title):
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #0f0f0f; color: #e0e0e0; margin: 0; padding: 0; }}
    .container {{ max-width: 600px; margin: 40px auto; background: #1a1a2e;
                  border-radius: 12px; overflow: hidden; border: 1px solid #2a2a4a; }}
    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
               padding: 32px; text-align: center; }}
    .header h1 {{ margin: 0; color: white; font-size: 28px; }}
    .header p {{ margin: 8px 0 0; color: rgba(255,255,255,0.85); font-size: 14px; }}
    .body {{ padding: 32px; }}
    .body p {{ line-height: 1.6; color: #c0c0d0; margin: 0 0 16px; }}
    .btn {{ display: inline-block; padding: 14px 28px; background: #667eea;
            color: white; text-decoration: none; border-radius: 8px;
            font-weight: 600; margin: 16px 0; }}
    .feature-list {{ list-style: none; padding: 0; margin: 16px 0; }}
    .feature-list li {{ padding: 8px 0; border-bottom: 1px solid #2a2a4a; color: #c0c0d0; }}
    .feature-list li:before {{ content: "✓ "; color: #667eea; font-weight: bold; }}
    .footer {{ padding: 24px; text-align: center; border-top: 1px solid #2a2a4a;
               color: #606070; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🤖 TelegramBot SaaS</h1>
      <p>Your Telegram community management platform</p>
    </div>
    <div class="body">{content}</div>
    <div class="footer">
      <p>© 2024 TelegramBot SaaS. All rights reserved.</p>
      <p>You're receiving this because you have an account with us.</p>
    </div>
  </div>
</body>
</html>
"""


def send_welcome_email(to_email, full_name):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Welcome to TelegramBot SaaS! Your account has been created successfully.</p>
    <p>Here's what you can do with your free account:</p>
    <ul class="feature-list">
      <li>Add 1 Telegram bot</li>
      <li>Basic moderation commands</li>
      <li>Welcome messages</li>
      <li>Member management</li>
    </ul>
    <p>Ready to get started?</p>
    <a href="{current_app.config['FRONTEND_URL']}/dashboard" class="btn">Go to Dashboard</a>
    <p>Need help? Reply to this email and we'll be happy to assist.</p>
    """
    return send_email(
        to_email,
        "Welcome to TelegramBot SaaS!",
        _base_template(content, "Welcome"),
        f"Hi {full_name}, welcome to TelegramBot SaaS! Visit {current_app.config['FRONTEND_URL']}/dashboard to get started.",
    )


def send_subscription_confirmation(to_email, full_name, plan_name, expires_at):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your subscription to the <strong>{plan_name}</strong> plan has been activated!</p>
    <p>Your subscription is active until: <strong>{expires_at}</strong></p>
    <p>You now have access to all {plan_name} features. Head to your dashboard to explore everything.</p>
    <a href="{current_app.config['FRONTEND_URL']}/dashboard" class="btn">Go to Dashboard</a>
    <p>Thank you for your support!</p>
    """
    return send_email(
        to_email,
        f"Subscription Confirmed - {plan_name} Plan",
        _base_template(content, "Subscription Confirmed"),
    )


def send_subscription_cancelled(to_email, full_name):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your subscription has been cancelled. You'll retain access to your plan features until the end of your current billing period.</p>
    <p>After that, your account will revert to the Free tier.</p>
    <p>We're sorry to see you go. If there's anything we could have done better, please let us know.</p>
    <a href="{current_app.config['FRONTEND_URL']}/pricing" class="btn">Resubscribe</a>
    """
    return send_email(
        to_email,
        "Subscription Cancelled",
        _base_template(content, "Subscription Cancelled"),
    )


def send_payment_failed(to_email, full_name):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>We were unable to process your payment for your TelegramBot SaaS subscription.</p>
    <p>Please update your payment method to avoid service interruption.</p>
    <a href="{current_app.config['FRONTEND_URL']}/pricing" class="btn">Update Payment Method</a>
    <p>If you need assistance, please contact our support team.</p>
    """
    return send_email(
        to_email,
        "Payment Failed - Action Required",
        _base_template(content, "Payment Failed"),
    )


def send_password_reset_email(to_email, full_name, reset_token):
    reset_url = f"{current_app.config['FRONTEND_URL']}/reset-password?token={reset_token}"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>We received a request to reset your password. Click the button below to choose a new one.</p>
    <p>This link expires in <strong>1 hour</strong>. If you didn't request a reset, you can safely ignore this email.</p>
    <a href="{reset_url}" class="btn">Reset Password</a>
    <p style="margin-top:24px;font-size:12px;color:#606070;">Or copy this link: {reset_url}</p>
    """
    return send_email(
        to_email,
        "Reset Your Password",
        _base_template(content, "Reset Password"),
        f"Reset your password: {reset_url}",
    )


def send_bot_added_notification(to_email, full_name, bot_name, bot_username):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your bot <strong>{bot_name}</strong> (@{bot_username}) has been successfully added to TelegramBot SaaS!</p>
    <p>Add your bot to Telegram groups to start managing them. Once the bot is in a group, it will appear in your dashboard.</p>
    <a href="{current_app.config['FRONTEND_URL']}/dashboard" class="btn">Manage Bots</a>
    """
    return send_email(
        to_email,
        f"Bot Added: {bot_name}",
        _base_template(content, "Bot Added"),
    )
