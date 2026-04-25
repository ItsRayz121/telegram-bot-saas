import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app

logger = logging.getLogger(__name__)


# ── Low-level transport helpers ────────────────────────────────────────────────

def _send_via_resend(api_key: str, from_email: str, to_email: str,
                     subject: str, html_body: str) -> None:
    """POST to Resend API. Raises RuntimeError on non-2xx response.
    The api_key is passed in but never logged."""
    import requests as _req
    resp = _req.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"from": from_email, "to": [to_email], "subject": subject, "html": html_body},
        timeout=10,
    )
    if not resp.ok:
        try:
            detail = resp.json().get("message", resp.text[:200])
        except Exception:
            detail = f"HTTP {resp.status_code}"
        raise RuntimeError(f"Resend rejected the request: {detail}")


def _send_via_smtp(cfg, from_email: str, to_email: str, subject: str,
                   html_body: str, text_body: str = None) -> None:
    """Send via SMTP/TLS. SMTP credentials are never logged."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(cfg["SMTP_SERVER"], cfg["SMTP_PORT"]) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
        server.sendmail(from_email, to_email, msg.as_string())


# ── Public dispatcher ──────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, html_body: str, text_body: str = None) -> bool:
    """Send an email via the configured provider (Resend or SMTP).

    Returns True on success.
    Raises RuntimeError with a safe, user-facing message on any failure.
    API keys and SMTP passwords are NEVER included in log output or exceptions.
    """
    cfg = current_app.config
    provider = (cfg.get("EMAIL_PROVIDER") or "").strip().lower()
    from_email = (cfg.get("FROM_EMAIL") or "").strip()

    if not provider:
        raise RuntimeError(
            "Email is not configured on this server. "
            "Please contact support."
        )
    if not from_email:
        raise RuntimeError("FROM_EMAIL environment variable is not set.")

    try:
        if provider == "resend":
            api_key = cfg.get("RESEND_API_KEY", "")
            if not api_key:
                raise RuntimeError("RESEND_API_KEY is not configured.")
            _send_via_resend(api_key, from_email, to_email, subject, html_body)

        elif provider == "smtp":
            if not cfg.get("SMTP_USERNAME"):
                raise RuntimeError("SMTP credentials are not configured.")
            _send_via_smtp(cfg, from_email, to_email, subject, html_body, text_body)

        else:
            raise RuntimeError(
                f"Unknown EMAIL_PROVIDER '{provider}'. "
                "Set EMAIL_PROVIDER to 'resend' or 'smtp'."
            )

        logger.info("Email sent via %s to %s | subject: %s", provider, to_email, subject)
        return True

    except RuntimeError:
        # Re-raise safe messages unchanged so callers can pass them to users
        raise
    except Exception as exc:
        # Wrap unexpected transport errors — never expose credentials
        logger.error("Email delivery failed via %s to %s: %s", provider, to_email, exc)
        raise RuntimeError("Email delivery failed. Please try again later.") from exc


# ── HTML template ──────────────────────────────────────────────────────────────

def _base_template(content, title):
    return f"""<!DOCTYPE html>
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
    .tip {{ background: #0d1117; border-left: 3px solid #667eea; padding: 12px 16px;
            border-radius: 4px; font-size: 13px; color: #909090; margin-top: 24px; }}
    .footer {{ padding: 24px; text-align: center; border-top: 1px solid #2a2a4a;
               color: #606070; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🤖 Telegizer</h1>
      <p>Your Telegram community management platform</p>
    </div>
    <div class="body">{content}</div>
    <div class="footer">
      <p>© 2025 Telegizer. All rights reserved.</p>
      <p>You're receiving this because you have an account with us.</p>
    </div>
  </div>
</body>
</html>"""


# ── Email templates ────────────────────────────────────────────────────────────

def send_verification_email(to_email, full_name, verification_token):
    verify_url = f"{current_app.config['FRONTEND_URL']}/verify-email?token={verification_token}"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Thanks for signing up for Telegizer! Please verify your email address to unlock all features.</p>
    <p>Click the button below — this link expires in <strong>24 hours</strong>.</p>
    <a href="{verify_url}" class="btn">Verify My Email</a>
    <p style="margin-top:24px;font-size:12px;color:#606070;">
      Or copy this link:<br>{verify_url}
    </p>
    <p>If you didn't create an account, you can safely ignore this email.</p>
    <div class="tip">
      💡 <strong>Tip:</strong> If you don't see this email in your inbox,
      check your <strong>spam or junk folder</strong> and mark it as "Not Spam".
    </div>
    """
    return send_email(
        to_email,
        "Verify your Telegizer email address",
        _base_template(content, "Verify Email"),
        f"Verify your Telegizer email: {verify_url}",
    )


def send_password_reset_email(to_email, full_name, reset_token):
    reset_url = f"{current_app.config['FRONTEND_URL']}/reset-password?token={reset_token}"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>We received a request to reset your password. Click the button below to choose a new one.</p>
    <p>This link expires in <strong>1 hour</strong>. If you didn't request a reset, you can safely ignore this email.</p>
    <a href="{reset_url}" class="btn">Reset Password</a>
    <p style="margin-top:24px;font-size:12px;color:#606070;">Or copy this link: {reset_url}</p>
    <div class="tip">
      💡 If you don't see this email, check your spam folder.
    </div>
    """
    return send_email(
        to_email,
        "Reset your Telegizer password",
        _base_template(content, "Reset Password"),
        f"Reset your Telegizer password: {reset_url}",
    )


def send_welcome_email(to_email, full_name):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Welcome to Telegizer! Your account has been created successfully.</p>
    <p>Here's what you can do with your free account:</p>
    <ul class="feature-list">
      <li>Add 1 Telegram bot</li>
      <li>Basic moderation commands</li>
      <li>Welcome messages</li>
      <li>Member management</li>
    </ul>
    <p>Ready to get started?</p>
    <a href="{current_app.config['FRONTEND_URL']}/dashboard" class="btn">Go to Dashboard</a>
    """
    return send_email(
        to_email,
        "Welcome to Telegizer!",
        _base_template(content, "Welcome"),
        f"Hi {full_name}, welcome to Telegizer! Visit {current_app.config['FRONTEND_URL']}/dashboard",
    )


def send_subscription_confirmation(to_email, full_name, plan_name, expires_at):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your <strong>{plan_name}</strong> plan has been activated!</p>
    <p>Active until: <strong>{expires_at}</strong></p>
    <a href="{current_app.config['FRONTEND_URL']}/dashboard" class="btn">Go to Dashboard</a>
    <p>Thank you for your support!</p>
    """
    return send_email(
        to_email,
        f"Subscription Confirmed — {plan_name} Plan",
        _base_template(content, "Subscription Confirmed"),
    )


def send_subscription_cancelled(to_email, full_name):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your subscription has been cancelled. You'll retain access until the end of your current period,
    then your account will revert to the Free tier.</p>
    <a href="{current_app.config['FRONTEND_URL']}/pricing" class="btn">Resubscribe</a>
    """
    return send_email(
        to_email,
        "Telegizer Subscription Cancelled",
        _base_template(content, "Subscription Cancelled"),
    )


def send_payment_failed(to_email, full_name):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>We were unable to process your payment. Please update your payment method to avoid service interruption.</p>
    <a href="{current_app.config['FRONTEND_URL']}/pricing" class="btn">Update Payment Method</a>
    """
    return send_email(
        to_email,
        "Telegizer Payment Failed — Action Required",
        _base_template(content, "Payment Failed"),
    )


def send_bot_added_notification(to_email, full_name, bot_name, bot_username):
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your bot <strong>{bot_name}</strong> (@{bot_username}) has been added to Telegizer!</p>
    <p>Add your bot to Telegram groups to start managing them.</p>
    <a href="{current_app.config['FRONTEND_URL']}/dashboard" class="btn">Manage Bots</a>
    """
    return send_email(
        to_email,
        f"Bot Added: {bot_name}",
        _base_template(content, "Bot Added"),
    )
