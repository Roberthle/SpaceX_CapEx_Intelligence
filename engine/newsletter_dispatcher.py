#!/usr/bin/env python3
"""
SpaceX CapEx Intelligence — Daily Newsletter Dispatcher
Queries 3 high-propensity masked leads and broadcasts them to all subscribers.
Can be executed daily via a cron job (Render Cron or crontab).
"""

import os
import json
import sqlite3
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("NewsletterDispatcher")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "purchases.db")
CACHE_PATH = os.path.join(BASE_DIR, "cache", "scored_leads.json")

def load_smtp_config():
    """Load SMTP configuration from environment variables or a local .env file."""
    # Check for local .env file if running locally
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.strip().startswith("#") and "=" in line:
                    key, val = line.strip().split("=", 1)
                    os.environ[key.strip()] = val.strip()

    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_email": os.environ.get("SMTP_FROM", "SpaceX CapEx Intelligence <newsletter@spacex-capex.com>"),
        "app_url": os.environ.get("APP_URL", "https://spacex-capex-intelligence.onrender.com"),
    }

def mask_name(name):
    """Obfuscate company name — show first letter + bullets per word."""
    if not name:
        return 'Confidential Business'
    SUFFIXES = {'LLC','INC','CORP','LTD','LP','DBA','L.L.C.','INC.','CORP.','L.P.','CO.','CO'}
    parts = name.split()
    out = []
    for p in parts:
        if p.upper().rstrip('.') in SUFFIXES or len(p) <= 2:
            out.append(p)
        else:
            out.append(p[0] + '•' * min(len(p) - 1, 8))
    return ' '.join(out)

def get_newsletter_leads():
    """Retrieve 3 high-propensity leads from the scored leads cache."""
    if not os.path.exists(CACHE_PATH):
        logger.error(f"Scored leads cache not found at: {CACHE_PATH}")
        return []

    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
        
        leads = data.get("leads", [])
        if not leads:
            return []

        # Filter for high propensity (Priority or Hot)
        premium_leads = [l for l in leads if l.get("score_tier") in ["priority", "hot"]]
        if not premium_leads:
            premium_leads = sorted(leads, key=lambda l: l.get("propensity_score", 0), reverse=True)

        # Take top 3 leads
        selected = premium_leads[:3]
        
        newsletter_leads = []
        for lead in selected:
            # Apply strict masking
            newsletter_leads.append({
                "masked_name": mask_name(lead.get("company_name", "")),
                "city": lead.get("city", "Unknown City"),
                "state": lead.get("state", "XX"),
                "asset": lead.get("predicted_asset", "Industrial Equipment"),
                "lender": lead.get("secured_party", "Private Lender"),
                "score": lead.get("propensity_score", 0.0),
                "tier": lead.get("score_tier_label", "Hot"),
                "days_remaining": lead.get("days_to_lapse", 180),
                "nearest_node": lead.get("nearest_node", "SpaceX Epicenter"),
                "node_dist": lead.get("nearest_node_dist_km", 0.0),
            })
        return newsletter_leads

    except Exception as e:
        logger.error(f"Error loading newsletter leads: {e}")
        return []

def get_subscribers():
    """Retrieve subscriber emails from purchases.db."""
    if not os.path.exists(DB_PATH):
        logger.warning(f"Database purchases.db not found at: {DB_PATH}. No subscribers to send to.")
        return []

    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT email FROM subscribers").fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Database error reading subscribers: {e}")
        return []

def build_newsletter_html(leads, app_url):
    """Compiles a gorgeous space-tech dark-mode responsive HTML newsletter."""
    today_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    
    lead_cards_html = ""
    for idx, lead in enumerate(leads):
        tier_color = "#00ff88" if lead["tier"].lower() == "priority" else "#ff4444"
        lead_cards_html += f"""
        <!-- Lead Card -->
        <div style="background-color: #111d2e; border: 1px solid #1e3048; border-radius: 8px; padding: 18px; margin-bottom: 16px;">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td>
                        <span style="font-family: monospace; font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: #7a9bb5;">LEAD #0{idx+1} · {lead["city"]}, {lead["state"]}</span>
                    </td>
                    <td align="right">
                        <span style="font-family: monospace; font-size: 11px; font-weight: bold; padding: 2px 6px; border-radius: 4px; background-color: {tier_color}22; color: {tier_color}; border: 1px solid {tier_color}44;">
                            {lead["tier"].upper()} ({lead["score"]:.1f})
                        </span>
                    </td>
                </tr>
            </table>
            <h3 style="font-family: 'D-DIN', 'DIN', sans-serif, Arial; font-size: 18px; font-weight: bold; color: #e8f4f8; margin: 10px 0 6px 0;">{lead["masked_name"]}</h3>
            <p style="font-family: Arial, sans-serif; font-size: 13px; color: #7a9bb5; margin: 0 0 12px 0;">
                Filing maturing in <strong style="color: #00d4ff;">{lead["days_remaining"]} days</strong>. High-probability replacement candidate.
            </p>
            
            <table width="100%" cellpadding="0" cellspacing="0" style="border-top: 1px solid #1e3048; padding-top: 8px;">
                <tr>
                    <td width="50%" style="font-family: Arial, sans-serif; font-size: 12px; color: #5a7088; padding: 4px 0;">
                        Asset: <strong style="color: #e8f4f8;">{lead["asset"]}</strong>
                    </td>
                    <td width="50%" style="font-family: Arial, sans-serif; font-size: 12px; color: #5a7088; padding: 4px 0;">
                        Lender: <strong style="color: #e8f4f8;">{lead["lender"]}</strong>
                    </td>
                </tr>
                <tr>
                    <td colspan="2" style="font-family: Arial, sans-serif; font-size: 12px; color: #5a7088; padding: 4px 0;">
                        Proximity: <strong style="color: #00d4ff;">{lead["node_dist"]:.1f} km</strong> to <strong style="color: #e8f4f8;">{lead["nearest_node"]}</strong>
                    </td>
                </tr>
            </table>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <title>Daily Rocket Fuel</title>
</head>
<body style="background-color: #06090f; color: #e8f4f8; font-family: Arial, sans-serif; margin: 0; padding: 0; -webkit-font-smoothing: antialiased;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #06090f; padding: 24px 12px;">
        <tr>
            <td align="center">
                <table width="100%" style="max-width: 580px; background-color: #0d1520; border: 1px solid #1e3048; border-radius: 12px; padding: 24px; text-align: left;">
                    
                    <!-- Header -->
                    <tr>
                        <td align="center" style="border-bottom: 1px solid #1e3048; padding-bottom: 20px;">
                            <div style="font-family: 'D-DIN', 'DIN', sans-serif, Arial; font-size: 22px; font-weight: bold; letter-spacing: 0.15em; color: #e8f4f8; text-transform: uppercase;">
                                🚀 SPACEX <span style="color: #00d4ff;">CAPEX</span>
                            </div>
                            <div style="font-family: monospace; font-size: 11px; color: #7a9bb5; margin-top: 4px; letter-spacing: 0.05em;">
                                DAILY LEAD INTELLIGENCE · {today_str}
                            </div>
                        </td>
                    </tr>
                    
                    <!-- Intro -->
                    <tr>
                        <td style="padding: 20px 0 10px 0;">
                            <p style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5; color: #e8f4f8; margin: 0;">
                                Maturing heavy machinery UCC filings detected near major aerospace infrastructure epicenters. Here are today's <strong>3 top-propensity masked leads</strong> ready for targeting.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Leads Block -->
                    <tr>
                        <td style="padding: 10px 0;">
                            {lead_cards_html}
                        </td>
                    </tr>
                    
                    <!-- Call To Action -->
                    <tr>
                        <td align="center" style="padding: 15px 0 25px 0; border-bottom: 1px solid #1e3048;">
                            <p style="font-family: Arial, sans-serif; font-size: 13px; color: #7a9bb5; margin-bottom: 14px;">
                                Unlock full contact details, lender risk audits, and live hiring signals instantly:
                            </p>
                            <a href="{app_url}" target="_blank" style="background-color: #00d4ff; color: #06090f; font-family: 'D-DIN', sans-serif; font-weight: bold; font-size: 14px; text-decoration: none; padding: 12px 30px; border-radius: 4px; letter-spacing: 0.08em; text-transform: uppercase; display: inline-block; box-shadow: 0 0 12px rgba(0, 212, 255, 0.4);">
                                Launch Terminal
                            </a>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td align="center" style="padding-top: 20px; font-family: monospace; font-size: 10px; color: #3a5068; line-height: 1.4;">
                            SpaceX CapEx Intelligence · Powered by Real UCC Maturing Feeds<br />
                            This is an automated intelligence summary sent to active subscribers.<br />
                            To unsubscribe, contact support or remove email from local portal settings.
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

def main():
    logger.info("Initializing Daily Newsletter Dispatcher...")
    
    # 1. Load config
    config = load_smtp_config()
    
    if not config["user"] or not config["password"]:
        logger.error("SMTP_USER and SMTP_PASSWORD environment variables are not configured. Dispatch aborted.")
        print("ERROR: SMTP credentials missing in environment variables.")
        return

    # 2. Get leads
    leads = get_newsletter_leads()
    if not leads:
        logger.error("No qualified leads found to populate the newsletter. Dispatch aborted.")
        return
    logger.info(f"Loaded {len(leads)} high-propensity leads for newsletter.")

    # 3. Get subscribers
    subscribers = get_subscribers()
    if not subscribers:
        logger.info("No active subscribers in the database. Dispatch complete (0 sent).")
        return
    logger.info(f"Loaded {len(subscribers)} newsletter subscribers.")

    # 4. Compile HTML
    html_content = build_newsletter_html(leads, config["app_url"])

    # 5. Broadcast to subscribers
    success_count = 0
    failure_count = 0

    try:
        # Establish connection
        logger.info(f"Connecting to SMTP host: {config['host']}:{config['port']}...")
        server = smtplib.SMTP(config["host"], config["port"])
        server.ehlo()
        if config["port"] == 587:
            server.starttls()
            server.ehlo()
        
        server.login(config["user"], config["password"])
        logger.info("SMTP Authentication Successful.")

        for recipient in subscribers:
            try:
                # Build message
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"🛰️ Daily Rocket Fuel: 3 Maturing CapEx Targets Detected"
                msg["From"] = config["from_email"]
                msg["To"] = recipient

                msg.attach(MIMEText(html_content, "html"))

                # Send
                server.sendmail(config["from_email"], recipient, msg.as_string())
                logger.info(f"Successfully delivered newsletter to: {recipient}")
                success_count += 1
            except Exception as se:
                logger.error(f"Failed to deliver newsletter to {recipient}: {se}")
                failure_count += 1

        server.quit()
        logger.info(f"Daily newsletter broadcast completed. Success: {success_count} | Failures: {failure_count}")

    except Exception as e:
        logger.error(f"Critical SMTP Session Error: {e}")

if __name__ == "__main__":
    main()
