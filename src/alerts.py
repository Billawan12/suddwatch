"""
alerts.py — SuddWatch Alert Dispatch System
============================================
Sends SMS alerts via Twilio and email alerts via Gmail SMTP
when flood events are detected above configured thresholds.

Alert triggers (from config.py):
  - Flood extent >= ALERT_FLOOD_THRESHOLD_HA (default: 500 ha)
  - Affected population >= ALERT_POPULATION_THRESHOLD (default: 1000)

Usage:
    from src.alerts import AlertManager
    alerter = AlertManager(config)
    results = alerter.send_flood_alert(risk_summary, event_id)
"""

import logging
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Manages SMS and email alert dispatch for flood events.

    Integrates with:
      - Twilio REST API for SMS delivery
      - Gmail SMTP for email delivery
      - src/database.py for logging alert records

    Design decisions:
      - SMS is sent first (faster, higher delivery rate on poor networks)
      - Email follows with full situation report
      - Each delivery is logged to the database regardless of success/failure
      - Failed deliveries are retried once before being marked as failed
      - Alert is only triggered if flood metrics exceed configured thresholds
    """

    def __init__(self, config):
        self.config = config
        self._twilio_client = None
        self._validated = False

    # ── Twilio client (lazy initialisation) ───────────────────
    def _get_twilio_client(self):
        """
        Lazily initialise the Twilio client.
        Twilio is only imported if SMS is actually needed,
        avoiding import errors on systems without twilio installed.
        """
        if self._twilio_client is None:
            try:
                from twilio.rest import Client
                self._twilio_client = Client(
                    self.config.twilio_account_sid,
                    self.config.twilio_auth_token,
                )
                logger.info("Twilio client initialised")
            except ImportError:
                logger.error("twilio package not installed. Run: pip install twilio")
                raise
            except Exception as e:
                logger.error(f"Twilio client initialisation failed: {e}")
                raise
        return self._twilio_client

    # ── Alert threshold check ─────────────────────────────────
    def should_alert(self, risk_summary: dict) -> tuple[bool, str]:
        """
        Check whether a flood event meets the alert threshold.

        Returns:
            (should_send: bool, reason: str)

        Logic:
            Alert is triggered if EITHER flood extent OR affected population
            exceeds the configured threshold. Both thresholds must be set
            in config.py / .env file.
        """
        flood_ha  = float(risk_summary.get("flood_extent_ha", 0))
        pop       = int(risk_summary.get("affected_population_estimate", 0))
        threshold_ha  = float(getattr(self.config, "alert_flood_threshold_ha",  500))
        threshold_pop = int(getattr(self.config, "alert_population_threshold",  1000))

        reasons = []
        if flood_ha >= threshold_ha:
            reasons.append(f"flood extent {flood_ha:,.0f} ha ≥ threshold {threshold_ha:,.0f} ha")
        if pop >= threshold_pop:
            reasons.append(f"affected population {pop:,} ≥ threshold {threshold_pop:,}")

        if reasons:
            return True, "; ".join(reasons)
        return False, (
            f"below thresholds (flood: {flood_ha:.0f}/{threshold_ha:.0f} ha, "
            f"pop: {pop:,}/{threshold_pop:,})"
        )

    # ── SMS formatting ────────────────────────────────────────
    def _format_sms(self, risk_summary: dict, event_id: str) -> str:
        """
        Format a concise SMS message (max 160 chars per segment).

        SMS must be brief — field workers may have poor connectivity
        and read on basic feature phones. Key info only:
        location, extent, population, event ID.
        """
        flood_ha  = float(risk_summary.get("flood_extent_ha", 0))
        pop       = int(risk_summary.get("affected_population_estimate", 0))
        villages  = risk_summary.get("affected_villages", [])
        top_village = villages[0].get("village_name", "—") if villages else "—"

        # Determine severity
        high_risk = [v for v in villages if v.get("flood_risk_percentage", 0) >= 75]
        severity  = "CRITICAL" if len(high_risk) >= 2 else "WARNING"

        msg = (
            f"[SUDDWATCH {severity}] {event_id}\n"
            f"Flood: {flood_ha:,.0f} ha | Pop at risk: {pop:,}\n"
            f"Top area: {top_village}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Dashboard: http://localhost:8501"
        )
        return msg

    # ── Email formatting ──────────────────────────────────────
    def _format_email(self, risk_summary: dict, event_id: str) -> tuple[str, str, str]:
        """
        Format a full HTML + plain-text situation report email.

        Returns:
            (subject, plain_text_body, html_body)

        The email contains:
          - Event summary (extent, population, latency, IoU)
          - Affected villages table (top 10)
          - Inaccessible roads list
          - Health facilities at risk
          - Link to dashboard
        """
        flood_ha  = float(risk_summary.get("flood_extent_ha", 0))
        pop       = int(risk_summary.get("affected_population_estimate", 0))
        villages  = risk_summary.get("affected_villages", [])
        roads     = risk_summary.get("inaccessible_roads", [])
        health    = risk_summary.get("health_facilities_at_risk", [])
        stats     = risk_summary.get("summary_statistics", {})
        ts        = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

        subject = (
            f"[SuddWatch] Flood Alert — {event_id} — "
            f"{flood_ha:,.0f} ha — {pop:,} affected"
        )

        # Plain text version
        plain = f"""
SUDDWATCH FLOOD SITUATION REPORT
{'='*50}
Event ID:  {event_id}
Time:      {ts}

FLOOD METRICS
{'─'*50}
Flood Extent:          {flood_ha:,.0f} ha
Affected Population:   {pop:,}
High-risk Villages:    {stats.get('high_risk_villages', 0)}
Inaccessible Roads:    {stats.get('total_roads_inaccessible', 0)}
Health Facilities:     {stats.get('total_health_facilities_at_risk', 0)}

TOP AFFECTED VILLAGES
{'─'*50}
"""
        for v in villages[:10]:
            plain += (
                f"  {v.get('village_name','—'):20s} "
                f"Pop: {v.get('estimated_population',0):6,}  "
                f"Risk: {v.get('flood_risk_percentage',0):.0f}%\n"
            )

        if roads:
            plain += f"\nINACCESSIBLE ROADS\n{'─'*50}\n"
            for r in roads[:5]:
                plain += (
                    f"  {r.get('name','—')} ({r.get('segment_length_km',0):.0f} km) "
                    f"— Alt: {r.get('alt_route','None')}\n"
                )

        if health:
            plain += f"\nHEALTH FACILITIES AT RISK\n{'─'*50}\n"
            for h in health[:5]:
                plain += f"  {h.get('name','—')} [{h.get('facility_type','—')}]\n"

        plain += f"\nDashboard: http://localhost:8501\n"
        plain += f"Generated by SuddWatch v2.4.1 — Sudd Basin, South Sudan\n"

        # HTML version
        village_rows = "".join(
            f"<tr>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #30363d;'>"
            f"{v.get('village_name','—')}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #30363d;text-align:right;'>"
            f"{v.get('estimated_population',0):,}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #30363d;text-align:right;'>"
            f"{v.get('flood_risk_percentage',0):.0f}%</td>"
            f"</tr>"
            for v in villages[:10]
        )

        html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'DM Mono', monospace; background: #0d1117; color: #e6edf3;
           margin: 0; padding: 24px; }}
    .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px;
             padding: 20px; margin-bottom: 16px; }}
    .header {{ background: #010409; border-bottom: 1px solid #30363d; padding: 16px 24px;
               margin: -24px -24px 24px -24px; }}
    .kpi {{ display: inline-block; margin-right: 24px; }}
    .kpi-label {{ font-size: 10px; color: #8b949e; text-transform: uppercase;
                  letter-spacing: 0.05em; }}
    .kpi-value {{ font-size: 24px; font-weight: 700; color: #0ea5e9; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ padding: 8px 12px; text-align: left; color: #8b949e; font-size: 10px;
          text-transform: uppercase; border-bottom: 1px solid #30363d; }}
    .badge-high {{ background: rgba(248,81,73,0.1); color: #f85149;
                   border: 1px solid rgba(248,81,73,0.3); padding: 2px 6px;
                   border-radius: 4px; font-size: 10px; }}
    .footer {{ font-size: 10px; color: #8b949e; text-align: center;
               border-top: 1px solid #30363d; padding-top: 16px; margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="header">
    <strong style="font-size:18px;letter-spacing:0.025em;">⚡ SUDDWATCH</strong>
    <span style="color:#8b949e;margin-left:12px;">Flood Situation Report · {ts}</span>
  </div>

  <div class="card">
    <div style="font-size:12px;color:#8b949e;margin-bottom:12px;">
      EVENT: <strong style="color:#e6edf3;">{event_id}</strong>
    </div>
    <div class="kpi">
      <div class="kpi-label">Flood Extent</div>
      <div class="kpi-value">{flood_ha:,.0f} ha</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Affected Pop.</div>
      <div class="kpi-value" style="color:#f59e0b;">{pop:,}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">High-risk Villages</div>
      <div class="kpi-value" style="color:#f85149;">{stats.get('high_risk_villages', 0)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Roads Blocked</div>
      <div class="kpi-value" style="color:#e6edf3;">{stats.get('total_roads_inaccessible', 0)}</div>
    </div>
  </div>

  <div class="card">
    <div style="font-size:12px;font-weight:600;margin-bottom:12px;">
      Affected Villages (Top 10)
    </div>
    <table>
      <thead>
        <tr>
          <th>Village</th>
          <th style="text-align:right">Population</th>
          <th style="text-align:right">Risk %</th>
        </tr>
      </thead>
      <tbody>{village_rows}</tbody>
    </table>
  </div>

  <div style="text-align:center;margin-top:24px;">
    <a href="http://localhost:8501"
       style="background:#1a7fd4;color:white;padding:10px 24px;
              border-radius:4px;text-decoration:none;font-weight:600;">
      Open Dashboard
    </a>
  </div>

  <div class="footer">
    Generated by SuddWatch v2.4.1 — Sudd Basin, South Sudan<br>
    This is an automated alert from the flood detection pipeline.
  </div>
</body>
</html>
"""
        return subject, plain.strip(), html

    # ── SMS dispatch ──────────────────────────────────────────
    def send_sms(self, message: str, event_id: str,
                 db_manager=None) -> list[dict]:
        """
        Send SMS to all recipients in config.sms_recipients.

        Each recipient gets an individual message (Twilio best practice).
        Results are logged to the database.

        Returns:
            List of result dicts: [{recipient, status, sid, error}]
        """
        recipients = getattr(self.config, "sms_recipients", "")
        if not recipients:
            logger.warning("No SMS recipients configured — skipping SMS alerts")
            return []

        # Handle both List[str] (from config.py) and comma-separated string
        if isinstance(recipients, list):
            recipient_list = [r.strip() for r in recipients if r.strip()]
        else:
            recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]
        results = []

        try:
            client = self._get_twilio_client()
        except Exception as e:
            logger.error(f"Cannot send SMS — Twilio unavailable: {e}")
            return [{"recipient": r, "status": "failed",
                     "sid": None, "error": str(e)} for r in recipient_list]

        for recipient in recipient_list:
            result = {"recipient": recipient, "status": "pending",
                      "sid": None, "error": None}
            for attempt in range(2):  # one retry
                try:
                    msg = client.messages.create(
                        body=message,
                        from_=self.config.twilio_phone_number,
                        to=recipient,
                    )
                    result["status"] = "delivered"
                    result["sid"]    = msg.sid
                    logger.info(f"SMS sent to {recipient} — SID: {msg.sid}")
                    break
                except Exception as e:
                    if attempt == 0:
                        logger.warning(f"SMS attempt 1 failed for {recipient}: {e}. Retrying...")
                        time.sleep(2)
                    else:
                        result["status"] = "failed"
                        result["error"]  = str(e)
                        logger.error(f"SMS failed for {recipient} after 2 attempts: {e}")

            # Log to database
            if db_manager:
                try:
                    db_manager.insert_alert(event_id, {
                        "channel":          "sms",
                        "recipient":        recipient,
                        "delivery_status":  result["status"],
                        "sent_timestamp":   datetime.now().isoformat(),
                        "error_reason":     result.get("error"),
                        "message_preview":  message[:100] if len(message) > 100 else message,
                    })
                except Exception as e:
                    logger.warning(f"Failed to log SMS alert to DB: {e}")

            results.append(result)

        return results

    # ── Email dispatch ────────────────────────────────────────
    def send_email(self, subject: str, plain_body: str, html_body: str,
                   event_id: str, db_manager=None) -> list[dict]:
        """
        Send HTML situation report email to all recipients.

        Uses Gmail SMTP with TLS. Sends one email per recipient
        so each delivery can be tracked individually in the database.

        Returns:
            List of result dicts: [{recipient, status, error}]
        """
        recipients = getattr(self.config, "email_recipients", "")
        if not recipients:
            logger.warning("No email recipients configured — skipping email alerts")
            return []

        # Handle both List[str] (from config.py) and comma-separated string
        if isinstance(recipients, list):
            recipient_list = [r.strip() for r in recipients if r.strip()]
        else:
            recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]
        smtp_user     = getattr(self.config, "smtp_user", "")
        smtp_password = getattr(self.config, "smtp_password", "")
        smtp_host     = getattr(self.config, "smtp_host", "smtp.gmail.com")
        smtp_port     = int(getattr(self.config, "smtp_port", 587))

        if not smtp_user or not smtp_password:
            logger.error("SMTP credentials not configured — skipping email alerts")
            return [{"recipient": r, "status": "failed",
                     "error": "SMTP not configured"} for r in recipient_list]

        results = []

        for recipient in recipient_list:
            result = {"recipient": recipient, "status": "pending", "error": None}
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"]    = f"SuddWatch Alerts <{smtp_user}>"
                msg["To"]      = recipient

                msg.attach(MIMEText(plain_body, "plain"))
                msg.attach(MIMEText(html_body,  "html"))

                # Try SSL (port 465) first, fall back to TLS (port 587)
                try:
                    with smtplib.SMTP_SSL(smtp_host, 465, timeout=30) as server:
                        server.login(smtp_user, smtp_password)
                        server.sendmail(smtp_user, recipient, msg.as_string())
                except Exception:
                    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                        server.ehlo()
                        server.starttls()
                        server.login(smtp_user, smtp_password)
                        server.sendmail(smtp_user, recipient, msg.as_string())

                result["status"] = "delivered"
                logger.info(f"Email sent to {recipient}")

            except smtplib.SMTPAuthenticationError:
                result["status"] = "failed"
                result["error"]  = "SMTP authentication failed — check credentials"
                logger.error(f"Email auth failed for {recipient}")
            except smtplib.SMTPException as e:
                result["status"] = "failed"
                result["error"]  = str(e)
                logger.error(f"Email failed for {recipient}: {e}")
            except Exception as e:
                result["status"] = "failed"
                result["error"]  = str(e)
                logger.error(f"Unexpected email error for {recipient}: {e}")

            # Log to database
            if db_manager:
                try:
                    db_manager.insert_alert(event_id, {
                        "channel":          "email",
                        "recipient":        recipient,
                        "delivery_status":  result["status"],
                        "sent_timestamp":   datetime.now().isoformat(),
                        "error_reason":     result.get("error"),
                        "message_preview":  subject[:100],
                    })
                except Exception as e:
                    logger.warning(f"Failed to log email alert to DB: {e}")

            results.append(result)

        return results

    # ── Main dispatch method ──────────────────────────────────
    def send_flood_alert(self, risk_summary: dict, event_id: str,
                         db_manager=None) -> dict:
        """
        Main entry point called by pipeline.py after risk assessment.

        Checks thresholds, formats messages, sends SMS then email,
        and returns a summary of all delivery results.

        Args:
            risk_summary: dict output from risk_assessment.py assess()
            event_id:     scene ID string for database logging
            db_manager:   optional DatabaseManager for logging

        Returns:
            {
              "alert_triggered": bool,
              "reason": str,
              "sms_results": [...],
              "email_results": [...],
              "total_sent": int,
              "total_failed": int,
            }
        """
        should_send, reason = self.should_alert(risk_summary)

        if not should_send:
            logger.info(f"Alert not triggered for {event_id}: {reason}")
            return {
                "alert_triggered": False,
                "reason":          reason,
                "sms_results":     [],
                "email_results":   [],
                "total_sent":      0,
                "total_failed":    0,
            }

        logger.info(f"Alert triggered for {event_id}: {reason}")

        # Format messages
        sms_text             = self._format_sms(risk_summary, event_id)
        subject, plain, html = self._format_email(risk_summary, event_id)

        # Dispatch SMS first (faster delivery on poor networks)
        sms_results   = self.send_sms(sms_text, event_id, db_manager)

        # Then email with full report
        email_results = self.send_email(subject, plain, html, event_id, db_manager)

        all_results  = sms_results + email_results
        total_sent   = sum(1 for r in all_results if r["status"] == "delivered")
        total_failed = sum(1 for r in all_results if r["status"] == "failed")

        logger.info(
            f"Alert dispatch complete for {event_id}: "
            f"{total_sent} delivered, {total_failed} failed"
        )

        return {
            "alert_triggered": True,
            "reason":          reason,
            "sms_results":     sms_results,
            "email_results":   email_results,
            "total_sent":      total_sent,
            "total_failed":    total_failed,
        }

    # ── Self-test ─────────────────────────────────────────────
    def test_connectivity(self) -> dict:
        """
        Test Twilio and SMTP connectivity without sending real alerts.
        Called during system startup to validate credentials.

        Returns:
            {"twilio": bool, "smtp": bool, "errors": [str]}
        """
        results = {"twilio": False, "smtp": False, "errors": []}

        # Test Twilio
        try:
            client = self._get_twilio_client()
            # Just fetch account info — no message sent
            client.api.accounts(self.config.twilio_account_sid).fetch()
            results["twilio"] = True
            logger.info("Twilio connectivity OK")
        except Exception as e:
            results["errors"].append(f"Twilio: {e}")
            logger.warning(f"Twilio connectivity failed: {e}")

        # Test SMTP
        try:
            smtp_host     = getattr(self.config, "smtp_host", "smtp.gmail.com")
            smtp_port     = int(getattr(self.config, "smtp_port", 587))
            smtp_user     = getattr(self.config, "smtp_user", "")
            smtp_password = getattr(self.config, "smtp_password", "")
            with smtplib.SMTP_SSL(smtp_host, 465, timeout=10) as server:
                server.login(smtp_user, smtp_password)
            results["smtp"] = True
            logger.info("SMTP connectivity OK")
        except Exception as e:
            results["errors"].append(f"SMTP: {e}")
            logger.warning(f"SMTP connectivity failed: {e}")

        return results


# ── Module self-test ──────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from src.config import Config, setup_logging

    setup_logging("INFO")
    cfg     = Config()
    alerter = AlertManager(cfg)

    # Test with a sample risk summary
    sample_risk = {
        "flood_extent_ha":               1200.0,
        "affected_population_estimate":  6637,
        "affected_villages": [
            {"village_name": "Bor South", "estimated_population": 12400,
             "flood_risk_percentage": 87},
            {"village_name": "Akobo East", "estimated_population": 8200,
             "flood_risk_percentage": 74},
        ],
        "inaccessible_roads": [
            {"name": "Bor-Malakal A1", "segment_length_km": 142,
             "alt_route": "Air only"},
        ],
        "health_facilities_at_risk": [
            {"name": "Bor State Hospital", "facility_type": "Hospital"},
        ],
        "summary_statistics": {
            "total_villages_affected":        121,
            "total_roads_inaccessible":       116,
            "total_health_facilities_at_risk":  4,
            "high_risk_villages":              23,
        },
    }

    should, reason = alerter.should_alert(sample_risk)
    print(f"\nAlert triggered: {should}")
    print(f"Reason: {reason}")

    sms = alerter._format_sms(sample_risk, "EVT-TEST-001")
    print(f"\nSMS preview ({len(sms)} chars):\n{sms}")

    subj, plain, html = alerter._format_email(sample_risk, "EVT-TEST-001")
    print(f"\nEmail subject: {subj}")
    print(f"Plain text ({len(plain)} chars) — first 300 chars:\n{plain[:300]}")
    print("\nSelf-test complete — credentials needed for live dispatch")
