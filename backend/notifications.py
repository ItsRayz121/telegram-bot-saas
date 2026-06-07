import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app

logger = logging.getLogger(__name__)


# ── Low-level transport helpers ────────────────────────────────────────────────

def _send_via_resend(api_key: str, from_email: str, to_email: str,
                     subject: str, html_body: str, text_body: str = None,
                     unsubscribe_url: str = None) -> None:
    """POST to Resend API. Raises RuntimeError on non-2xx response.
    The api_key is passed in but never logged."""
    import requests as _req
    payload = {"from": from_email, "to": [to_email], "subject": subject, "html": html_body}
    if text_body:
        payload["text"] = text_body
    if unsubscribe_url:
        payload["headers"] = {
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
    resp = _req.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )
    if not resp.ok:
        try:
            detail = resp.json().get("message", resp.text[:200])
        except Exception:
            detail = f"HTTP {resp.status_code}"
        raise RuntimeError(f"Resend rejected the request: {detail}")


def _send_via_smtp(cfg, from_email: str, to_email: str, subject: str,
                   html_body: str, text_body: str = None,
                   unsubscribe_url: str = None) -> None:
    """Send via SMTP/TLS. SMTP credentials are never logged."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(cfg["SMTP_SERVER"], cfg["SMTP_PORT"]) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
        server.sendmail(from_email, to_email, msg.as_string())


# ── Public dispatcher ──────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, html_body: str, text_body: str = None,
               unsubscribe_url: str = None) -> bool:
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
            _send_via_resend(api_key, from_email, to_email, subject, html_body,
                             text_body=text_body, unsubscribe_url=unsubscribe_url)

        elif provider == "smtp":
            if not cfg.get("SMTP_USERNAME"):
                raise RuntimeError("SMTP credentials are not configured.")
            _send_via_smtp(cfg, from_email, to_email, subject, html_body,
                           text_body=text_body, unsubscribe_url=unsubscribe_url)

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

def _base_template(content, title, unsubscribe_url: str = None):
    frontend_url = "https://telegizer.com"
    try:
        from flask import current_app
        frontend_url = current_app.config.get("FRONTEND_URL", frontend_url)
    except RuntimeError:
        pass

    unsubscribe_line = ""
    if unsubscribe_url:
        unsubscribe_line = (
            f'<p>Don\'t want these emails? '
            f'<a href="{unsubscribe_url}" style="color:#667eea;">Unsubscribe</a></p>'
        )

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
    .header {{ background: linear-gradient(135deg, #2563EB 0%, #7C3AED 100%);
               padding: 32px; text-align: center; }}
    .header h1 {{ margin: 0; color: white; font-size: 28px; font-weight: 800; }}
    .header p {{ margin: 8px 0 0; color: rgba(255,255,255,0.85); font-size: 14px; }}
    .body {{ padding: 32px; }}
    .body p {{ line-height: 1.6; color: #c0c0d0; margin: 0 0 16px; }}
    .btn {{ display: inline-block; padding: 14px 28px; background: #2563EB;
            color: white; text-decoration: none; border-radius: 8px;
            font-weight: 600; margin: 16px 0; }}
    .feature-list {{ list-style: none; padding: 0; margin: 16px 0; }}
    .feature-list li {{ padding: 8px 0; border-bottom: 1px solid #2a2a4a; color: #c0c0d0; }}
    .feature-list li:before {{ content: "✓ "; color: #2563EB; font-weight: bold; }}
    .tip {{ background: #0d1117; border-left: 3px solid #2563EB; padding: 12px 16px;
            border-radius: 4px; font-size: 13px; color: #909090; margin-top: 24px; }}
    .footer {{ padding: 24px; text-align: center; border-top: 1px solid #2a2a4a;
               color: #606070; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Telegizer</h1>
      <p>Telegram community management platform</p>
    </div>
    <div class="body">{content}</div>
    <div class="footer">
      <p>© 2026 Telegizer · <a href="{frontend_url}/privacy" style="color:#667eea;">Privacy Policy</a></p>
      <p>You're receiving this because you have an account at telegizer.com.</p>
      {unsubscribe_line}
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


def send_verification_code_email(to_email, full_name, code):
    """Send a 6-digit verification code (used by the in-bot email verification flow)."""
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Here is your Telegizer verification code. Enter it back in the Telegram bot to
    finish linking your email — it expires in <strong>10 minutes</strong>.</p>
    <p style="text-align:center;margin:28px 0;">
      <span style="font-size:34px;font-weight:700;letter-spacing:10px;
                   color:#3d8ef8;font-family:monospace;">{code}</span>
    </p>
    <p>If you didn't request this, you can safely ignore this email.</p>
    <div class="tip">
      💡 <strong>Tip:</strong> Never share this code with anyone.
    </div>
    """
    return send_email(
        to_email,
        "Your Telegizer verification code",
        _base_template(content, "Verification Code"),
        f"Your Telegizer verification code is {code} (expires in 10 minutes).",
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


def send_onboarding_day3_email(to_email, full_name):
    dashboard_url = f"{current_app.config['FRONTEND_URL']}/dashboard"
    unsub_url = f"{current_app.config['FRONTEND_URL']}/settings?unsubscribe=onboarding"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>It's been 3 days since you joined Telegizer — hope you're settling in!</p>
    <p>Here are a few power features worth trying:</p>
    <ul class="feature-list">
      <li><strong>AutoMod</strong> — auto-remove spam, links, and bad words</li>
      <li><strong>Scheduled Messages</strong> — post content on a recurring schedule</li>
      <li><strong>Welcome Messages</strong> — greet new members automatically</li>
      <li><strong>Group Analytics</strong> — see who's active and when</li>
    </ul>
    <p>Any questions? Reply to this email — I read every message personally.</p>
    <a href="{dashboard_url}" class="btn">Open Dashboard</a>
    """
    return send_email(
        to_email,
        "Quick tips to get more from Telegizer",
        _base_template(content, "3-Day Tips", unsubscribe_url=unsub_url),
        text_body=f"Hi {full_name}, here are some power features to try in Telegizer: "
                  f"AutoMod, Scheduled Messages, Welcome Messages, Group Analytics. "
                  f"Open your dashboard at {dashboard_url}",
        unsubscribe_url=unsub_url,
    )


def send_onboarding_day7_email(to_email, full_name):
    pricing_url = f"{current_app.config['FRONTEND_URL']}/pricing"
    unsub_url = f"{current_app.config['FRONTEND_URL']}/settings?unsubscribe=onboarding"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>You've been on Telegizer for a week — great to have you!</p>
    <p>If you're managing an active community, upgrading to <strong>Pro ($9/mo)</strong> unlocks:</p>
    <ul class="feature-list">
      <li>3 custom bots &amp; unlimited groups</li>
      <li>AI-powered auto-replies &amp; daily digests</li>
      <li>90-day analytics dashboard</li>
      <li>Webhook integrations &amp; automations</li>
      <li>Priority support</li>
    </ul>
    <a href="{pricing_url}" class="btn">View Pricing</a>
    <p style="margin-top:16px;font-size:0.85em;color:#94a3b8;">
      Not ready? No worries — your free account stays active forever, no credit card needed.
    </p>
    """
    return send_email(
        to_email,
        "Ready to level up your Telegram community?",
        _base_template(content, "Upgrade to Pro", unsubscribe_url=unsub_url),
        text_body=f"Hi {full_name}, upgrade to Telegizer Pro ($9/mo) for unlimited bots, "
                  f"AI features, and advanced analytics. View pricing at {pricing_url}",
        unsubscribe_url=unsub_url,
    )


def send_subscription_confirmation(to_email, full_name, plan_name, expires_at):
    dashboard_url = f"{current_app.config['FRONTEND_URL']}/dashboard"
    billing_url = f"{current_app.config['FRONTEND_URL']}/billing"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your <strong>{plan_name}</strong> plan has been activated!</p>
    <p>Active until: <strong>{expires_at}</strong></p>
    <a href="{dashboard_url}" class="btn">Go to Dashboard</a>
    <p>Thank you for supporting Telegizer!</p>
    <p style="margin-top:24px;font-size:12px;color:#606070;">
      Manage or cancel your subscription at any time from
      <a href="{billing_url}" style="color:#667eea;">your billing page</a>.
    </p>
    """
    return send_email(
        to_email,
        f"Subscription Confirmed — {plan_name} Plan",
        _base_template(content, "Subscription Confirmed"),
        text_body=f"Hi {full_name}, your {plan_name} plan is now active until {expires_at}. "
                  f"Manage your subscription at {billing_url}",
    )


def send_subscription_cancelled(to_email, full_name):
    pricing_url = f"{current_app.config['FRONTEND_URL']}/pricing"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your subscription has been cancelled. You'll retain paid-plan access until the end of your
    current period, then your account reverts to the Free tier automatically.</p>
    <p>Your data and bots are safe — the Free plan remains active indefinitely.</p>
    <a href="{pricing_url}" class="btn">Resubscribe anytime</a>
    """
    return send_email(
        to_email,
        "Telegizer Subscription Cancelled",
        _base_template(content, "Subscription Cancelled"),
        text_body=f"Hi {full_name}, your Telegizer subscription has been cancelled. "
                  f"Your account reverts to the Free tier at the end of your billing period. "
                  f"Resubscribe at {pricing_url}",
    )


def send_payment_failed(to_email, full_name):
    pricing_url = f"{current_app.config['FRONTEND_URL']}/pricing"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>We were unable to process your payment. Please retry or contact
    <a href="mailto:support@telegizer.com" style="color:#667eea;">support@telegizer.com</a>
    if you believe this is an error.</p>
    <a href="{pricing_url}" class="btn">Retry Payment</a>
    """
    return send_email(
        to_email,
        "Telegizer Payment Failed — Action Required",
        _base_template(content, "Payment Failed"),
        text_body=f"Hi {full_name}, we couldn't process your payment. "
                  f"Please retry at {pricing_url} or contact support@telegizer.com",
    )


def send_referral_conversion_email(to_email, referrer_name, referred_first_name, total_referrals):
    dashboard_url = f"{current_app.config['FRONTEND_URL']}/settings"
    content = f"""
    <p>Hi <strong>{referrer_name}</strong>,</p>
    <p>Great news — <strong>{referred_first_name}</strong> just joined Telegizer using your referral link and verified their email!</p>
    <p>You now have <strong>{total_referrals} verified referral{"s" if total_referrals != 1 else ""}</strong> in total.</p>
    <p>Keep sharing your link to unlock more rewards:</p>
    <ul class="feature-list">
      <li>3 referrals — 1 month Pro free</li>
      <li>10 referrals — 3 months Pro free</li>
      <li>25 referrals — lifetime Pro discount</li>
    </ul>
    <a href="{dashboard_url}" class="btn">View My Referrals</a>
    <div class="tip">
      💡 Share your referral link with community managers, Telegram group owners,
      or anyone who could benefit from automated moderation and analytics.
    </div>
    """
    return send_email(
        to_email,
        f"{referred_first_name} joined Telegizer with your referral link!",
        _base_template(content, "Referral Conversion"),
        f"Hi {referrer_name}, {referred_first_name} just joined Telegizer using your referral link! "
        f"You now have {total_referrals} verified referral{'s' if total_referrals != 1 else ''}.",
    )


def send_subscription_expiry_warning(to_email: str, full_name: str,
                                     plan_name: str, expires_at: str,
                                     days_left: int) -> bool:
    """Warn the user that their subscription is expiring soon.

    days_left is the integer number of days remaining (e.g. 5 or 1).
    """
    urgency = "soon" if days_left > 1 else "tomorrow"
    billing_url = f"{current_app.config['FRONTEND_URL']}/billing"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your <strong>{plan_name.capitalize()} Plan</strong> expires <strong>{urgency}</strong>
    on <strong>{expires_at}</strong>.</p>
    <p>To keep all your bots, scheduled messages, analytics, and advanced features running
    without interruption, renew your subscription before it expires.</p>
    <a href="{billing_url}" class="btn">Renew Now</a>
    <p style="margin-top:16px;font-size:13px;color:#909090;">
      If you don't renew, your account will revert to the Free tier and some features
      will stop working.
    </p>
    <div class="tip">
      💡 All your data is preserved — renewing restores full access instantly.
    </div>
    """
    urgency_label = f"{days_left} day{'s' if days_left != 1 else ''}"
    return send_email(
        to_email,
        f"Your Telegizer {plan_name.capitalize()} Plan expires in {urgency_label}",
        _base_template(content, "Subscription Expiring Soon"),
        f"Hi {full_name}, your {plan_name} plan expires on {expires_at}. "
        f"Renew at {billing_url} to avoid service interruption.",
    )


def send_subscription_expired(to_email: str, full_name: str, plan_name: str) -> bool:
    """Day-of-expiry email — fires once when subscription lapses (3-day grace period begins)."""
    billing_url = f"{current_app.config['FRONTEND_URL']}/billing"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your <strong>{plan_name.capitalize()} Plan</strong> has expired today.</p>
    <p>You have a <strong>3-day grace period</strong> — all paid features remain active until then.
    Renew now to stay uninterrupted.</p>
    <a href="{billing_url}" class="btn">Renew Now</a>
    <p style="margin-top:16px;font-size:13px;color:#909090;">
      After the grace period your account reverts to Free. All your data is safe and restores
      instantly when you renew.
    </p>
    """
    return send_email(
        to_email,
        f"Your Telegizer {plan_name.capitalize()} Plan has expired",
        _base_template(content, "Subscription Expired"),
        f"Hi {full_name}, your {plan_name} plan expired. Renew within 3 days at {billing_url}.",
    )


def send_feature_highlight_email(to_email, full_name):
    """Day-5 lifecycle email — spotlight AI features users haven't tried yet."""
    dashboard_url = f"{current_app.config['FRONTEND_URL']}/ark"
    pricing_url = f"{current_app.config['FRONTEND_URL']}/pricing"
    unsub_url = f"{current_app.config['FRONTEND_URL']}/settings?unsubscribe=onboarding"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Most Telegizer users start with moderation — but the platform goes much deeper.
    Here's what community managers love after their first week:</p>
    <ul class="feature-list">
      <li><strong>Echo AI Assistant</strong> — observes your group and surfaces tasks, decisions, and action items automatically</li>
      <li><strong>AI Knowledge Base</strong> — paste your FAQ once, the bot answers member questions 24/7</li>
      <li><strong>Daily Digests</strong> — a summary of what happened in your group, delivered every morning</li>
      <li><strong>Smart Reminders</strong> — set a reminder in plain text and Echo handles the rest</li>
    </ul>
    <p>These features are available on the Pro plan. If you haven't tried them yet, you're leaving the best part untouched.</p>
    <a href="{dashboard_url}" class="btn">Explore Echo Assistant</a>
    <p style="margin-top:16px;font-size:13px;color:#909090;">
      Not on Pro yet? <a href="{pricing_url}" style="color:#667eea;">See what's included →</a>
    </p>
    """
    return send_email(
        to_email,
        "The Telegizer feature most admins discover too late",
        _base_template(content, "AI Features Spotlight", unsubscribe_url=unsub_url),
        text_body=f"Hi {full_name}, Echo AI Assistant, Knowledge Base, and Daily Digests are the features "
                  f"community managers love most. Explore them at {dashboard_url}",
        unsubscribe_url=unsub_url,
    )


def send_community_growth_email(to_email, full_name):
    """Day-21 lifecycle email — growth playbook / case study framing."""
    dashboard_url = f"{current_app.config['FRONTEND_URL']}/dashboard"
    unsub_url = f"{current_app.config['FRONTEND_URL']}/settings?unsubscribe=onboarding"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Three weeks in — here are the moves that separate fast-growing communities from stagnant ones:</p>
    <ul class="feature-list">
      <li><strong>Post on a schedule</strong> — groups with 3+ scheduled posts per week retain 2× more members</li>
      <li><strong>Gamify participation</strong> — XP + levels give members a reason to stay active every day</li>
      <li><strong>Track your invite links</strong> — knowing your best acquisition source lets you double down on it</li>
      <li><strong>Run a monthly poll</strong> — community input creates ownership and reduces churn</li>
    </ul>
    <p>All of this is built into Telegizer. The groups that grow consistently are the ones that use automation to stay consistent even when the admin is offline.</p>
    <a href="{dashboard_url}" class="btn">Open Your Dashboard</a>
    <div class="tip">
      💡 <strong>Quick win:</strong> Go to your Groups page and enable a weekly scheduled recap post — takes 2 minutes, runs forever.
    </div>
    """
    return send_email(
        to_email,
        "What growing Telegram communities do differently",
        _base_template(content, "Growth Playbook", unsubscribe_url=unsub_url),
        text_body=f"Hi {full_name}, the communities that grow fastest use scheduled posts, XP systems, "
                  f"and invite tracking. Here's how to apply it: {dashboard_url}",
        unsubscribe_url=unsub_url,
    )


def send_upgrade_nudge_email(to_email, full_name):
    """Day-30 lifecycle email — final upgrade push for persistent free users."""
    pricing_url = f"{current_app.config['FRONTEND_URL']}/pricing"
    unsub_url = f"{current_app.config['FRONTEND_URL']}/settings?unsubscribe=onboarding"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>You've been running your community on Telegizer for a month — that's great.</p>
    <p>If you're still on the Free plan, here's the honest truth: the features that make the biggest difference are on Pro.</p>
    <ul class="feature-list">
      <li>AI auto-replies that answer member questions without you</li>
      <li>Daily group digests so you never miss what matters</li>
      <li>90-day analytics so you can see what's actually working</li>
      <li>Unlimited groups for your custom bot</li>
      <li>Member CRM to track who your most valuable contributors are</li>
    </ul>
    <p><strong>Pro is $9/month.</strong> That's less than a coffee per week to run your community on autopilot.</p>
    <a href="{pricing_url}" class="btn">Upgrade to Pro — $9/month</a>
    <p style="margin-top:16px;font-size:13px;color:#909090;">
      14-day money-back guarantee. Pay with crypto — no card required.
    </p>
    """
    return send_email(
        to_email,
        "One month in — here's what Pro unlocks for $9",
        _base_template(content, "Upgrade to Pro", unsubscribe_url=unsub_url),
        text_body=f"Hi {full_name}, you've been on Telegizer for a month. Pro is $9/month and unlocks "
                  f"AI auto-replies, digests, 90-day analytics, and unlimited groups. "
                  f"14-day money-back guarantee. See pricing at {pricing_url}",
        unsubscribe_url=unsub_url,
    )


def send_bot_added_notification(to_email, full_name, bot_name, bot_username):
    dashboard_url = f"{current_app.config['FRONTEND_URL']}/dashboard"
    content = f"""
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>Your bot <strong>{bot_name}</strong> (@{bot_username}) has been connected to Telegizer.</p>
    <p>Add your bot as an admin to any Telegram group to start managing it from your dashboard.</p>
    <a href="{dashboard_url}" class="btn">Go to Dashboard</a>
    """
    return send_email(
        to_email,
        f"Bot Connected: {bot_name}",
        _base_template(content, "Bot Connected"),
        text_body=f"Hi {full_name}, your bot {bot_name} (@{bot_username}) is now connected to Telegizer. "
                  f"Add it as admin to a Telegram group and manage it at {dashboard_url}",
    )
