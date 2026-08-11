"""
Simple email sending helper for BigThinkers.

Uses Python's built-in smtplib (no extra pip dependency, which keeps this
friendly for Termux). Reads credentials from environment variables so they
can be overridden without touching code, but falls back to the
BigThinkers organization account so password-reset emails work out of the box.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.environ.get("MAIL_PORT", "465"))
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "bigthinkersorganization@gmail.com")
# Gmail App Passwords are shown with spaces ("pkkc zbku kfjl wfxz") — strip them for login.
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "pkkc zbku kfjl wfxz").replace(" ", "")
MAIL_SENDER_NAME = os.environ.get("MAIL_SENDER_NAME", "BigThinkers")


def send_email(to_email, subject, html_body, text_body=None):
    """Send an email via Gmail SMTP over SSL. Returns True on success, False otherwise."""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[mail] MAIL_USERNAME/MAIL_PASSWORD not configured — skipping send.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{MAIL_SENDER_NAME} <{MAIL_USERNAME}>"
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT, timeout=15) as server:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_USERNAME, [to_email], msg.as_string())
        return True
    except Exception as exc:
        print(f"[mail] Failed to send email to {to_email}: {exc}")
        return False


def send_reset_code_email(to_email, first_name, code):
    subject = "Your BigThinkers password reset code"

    text_body = (
        f"Hi {first_name},\n\n"
        f"Your BigThinkers password reset code is: {code}\n"
        f"This code expires in 10 minutes.\n\n"
        f"If you did not request this, you can safely ignore this email.\n\n"
        f"— BigThinkers"
    )

    html_body = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;
                padding:24px;background:#f8f4ec;border-radius:12px;">
      <h2 style="color:#0d1b2a;margin-top:0;">BigThinkers Password Reset</h2>
      <p style="color:#0d1b2a;">Hi {first_name},</p>
      <p style="color:#0d1b2a;">Use the code below to reset your BigThinkers password.
        This code expires in <strong>10 minutes</strong>.</p>
      <div style="font-size:32px;font-weight:700;letter-spacing:8px;color:#c9a24b;
                  background:#0d1b2a;padding:16px;text-align:center;border-radius:10px;
                  margin:20px 0;">{code}</div>
      <p style="color:#667;font-size:13px;">If you did not request a password reset,
        you can safely ignore this email — your password will not change.</p>
      <p style="color:#667;font-size:13px;">— BigThinkers Team</p>
    </div>
    """

    return send_email(to_email, subject, html_body, text_body)
