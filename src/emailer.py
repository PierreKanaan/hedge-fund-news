"""
Builds an HTML digest from the analyzed report and sends it via Gmail SMTP
using an App Password (free, no third-party email service needed).
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

POSITION_COLORS = {"long": "#1a7f37", "short": "#c62828", "hold": "#8a6d00"}


def _item_html(item: dict) -> str:
    a = item.get("analysis", {})
    position = a.get("position", "hold")
    color = POSITION_COLORS.get(position, "#444")
    rationale_html = "".join(f"<li>{r}</li>" for r in a.get("rationale", []))
    tickers = ", ".join(item.get("tickers", [])) or "—"
    sentiment = item.get("sentiment", {})

    return f"""
    <div style="border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin-bottom:14px;">
      <div style="font-size:15px;font-weight:600;margin-bottom:4px;">
        <a href="{item['url']}" style="color:#111;text-decoration:none;">{item['title']}</a>
      </div>
      <div style="font-size:12px;color:#777;margin-bottom:8px;">
        {item.get('source','')} · tickers: {tickers} · FinBERT: {sentiment.get('label','n/a')}
        ({sentiment.get('confidence', 0)})
      </div>
      <div style="font-size:13px;color:#555;margin-bottom:8px;"><b>Catalyst:</b> {a.get('catalyst','')}</div>
      <div style="display:inline-block;background:{color};color:#fff;font-size:12px;
                  font-weight:600;padding:3px 10px;border-radius:12px;margin-bottom:6px;">
        {position.upper()} — {a.get('instrument','')} · confidence {a.get('confidence', 0):.0%}
      </div>
      <div style="font-size:12px;color:#555;margin-bottom:10px;"><b>Horizon:</b> {a.get('horizon','')}</div>
      <div style="font-size:13px;line-height:1.5;background:#f7f7f7;border-radius:6px;
                  padding:10px 12px;margin-bottom:10px;">
        <b>Talking points (read this to the class):</b><br>{a.get('explanation','')}
      </div>
      <div style="font-size:12px;color:#555;margin-bottom:4px;"><b>Cheat-sheet bullets:</b></div>
      <ul style="font-size:13px;margin:0 0 8px 18px;padding:0;">{rationale_html}</ul>
      <div style="font-size:12px;color:#8a3a00;"><b>If they ask "what could go wrong":</b> {a.get('risk','')}</div>
    </div>
    """


def build_digest_html(report: dict) -> str:
    items = report.get("items", [])
    generated_at = report.get("generated_at", "")
    body = "".join(_item_html(i) for i in items) or "<p>No relevant items found this run.</p>"
    return f"""
    <html><body style="font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:auto;">
      <h2 style="margin-bottom:4px;">Fund News Digest</h2>
      <div style="font-size:12px;color:#777;margin-bottom:20px;">Generated {generated_at}</div>
      {body}
    </body></html>
    """


def send_digest(report: dict) -> None:
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipients_raw = os.environ.get("EMAIL_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    if not (gmail_address and gmail_password and recipients):
        print("[emailer] missing GMAIL_ADDRESS / GMAIL_APP_PASSWORD / EMAIL_RECIPIENTS, skipping send")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Fund News Digest — {report.get('generated_at', '')[:10]}"
    msg["From"] = gmail_address
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(build_digest_html(report), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, recipients, msg.as_string())

    print(f"[emailer] digest sent to {len(recipients)} recipient(s)")
