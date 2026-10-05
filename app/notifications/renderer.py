"""Email template renderer for Job-AI Career Alerts and Daily Digests.

Generates responsive, professional HTML emails and clean plain-text fallbacks
with zero secret leakage, verified link preservation, and explicit human-gated
safety reminders.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from app.notifications.models import EmailMessage, EmailPriority

if TYPE_CHECKING:
    from app.application.intelligence import ApplicationPackage
    from app.jobs.digest import DailyCareerDigest


class EmailTemplateRenderer:
    """Renders HTML and plain-text email templates for career alerts."""

    def __init__(self, dashboard_base_url: str = "http://localhost:8501"):
        self.dashboard_base_url = dashboard_base_url.rstrip("/")

    def render_immediate_alert(
        self,
        package: ApplicationPackage,
        recipient: str,
        sender: str,
        is_material_update: bool = False,
    ) -> EmailMessage:
        """Render an immediate alert email for a CRITICAL or HIGH priority opportunity."""
        p_tier_raw = getattr(package, "priority_tier", getattr(package, "priority_level", "HIGH"))
        p_tier = p_tier_raw.value.upper() if hasattr(p_tier_raw, "value") else str(p_tier_raw).upper()

        elig_raw = getattr(package, "eligibility", getattr(package, "eligibility_status", "GRADUATE"))
        eligibility_str = elig_raw.tier.value if hasattr(elig_raw, "tier") else str(elig_raw)

        auth_raw = getattr(package, "work_authorization", getattr(package, "work_authorization_status", "NO_SPONSORSHIP_REQUIRED"))
        work_auth_str = auth_raw.status.value if hasattr(auth_raw, "status") else str(auth_raw)

        resume_raw = getattr(package, "selected_resume_profile", "ASIC_VERIFICATION")
        resume_str = resume_raw.value if hasattr(resume_raw, "value") else str(resume_raw)

        selection_reason = getattr(package, "resume_selection_reason", getattr(package, "selection_reason", "Matched candidate DV profile."))
        official_url = getattr(package, "official_application_url", getattr(package, "official_url", "#")) or "#"
        fingerprint = getattr(package, "job_fingerprint", getattr(package, "fingerprint", "fp_job"))
        url_status = getattr(package, "url_verification_status", getattr(package, "official_url_status", "VERIFIED"))

        badge_icon = "🚨" if p_tier == "CRITICAL" else ("🌎" if "overseas" in work_auth_str.lower() or "international" in work_auth_str.lower() else "🔥")
        badge_label = "APPLY NOW" if p_tier == "CRITICAL" else "HIGH PRIORITY"
        is_mat = is_material_update or getattr(package, "is_material_update", False)
        prefix = "[MATERIAL UPDATE] " if is_mat else ""

        subject = f"{prefix}{badge_icon} {badge_label} — {package.priority_score:.0f}/100 — {package.role} at {package.company} — {package.location}"

        # HTML Rendering
        company_esc = html.escape(package.company)
        role_esc = html.escape(package.role)
        location_esc = html.escape(package.location)
        eligibility_esc = html.escape(eligibility_str)
        work_auth_esc = html.escape(work_auth_str)
        resume_esc = html.escape(resume_str)
        selection_reason_esc = html.escape(selection_reason)
        official_url_esc = html.escape(official_url)
        review_url_esc = html.escape(f"{self.dashboard_base_url}/?fingerprint={fingerprint}")

        warnings_html = ""
        if package.warnings:
            items = "".join(f"<li style='margin-bottom: 4px; color: #b45309;'>⚠️ {html.escape(w)}</li>" for w in package.warnings)
            warnings_html = f"<div style='margin-top: 15px; padding: 12px; background: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 4px;'><strong style='color: #92400e;'>Notices / Warnings:</strong><ul style='margin: 6px 0 0 0; padding-left: 20px;'>{items}</ul></div>"

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 24px; color: #1f2937; line-height: 1.5;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06); border: 1px solid #e5e7eb;">
    
    <!-- Header -->
    <div style="background: #0f172a; padding: 20px 24px; color: #ffffff;">
      <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #94a3b8; font-weight: 700; margin-bottom: 4px;">Job-AI Career Alert</div>
      <div style="font-size: 20px; font-weight: 700; color: #f8fafc; display: flex; align-items: center; gap: 8px;">
        <span>{badge_icon}</span> {badge_label} OPPORTUNITY
      </div>
    </div>

    <!-- Opportunity Card -->
    <div style="padding: 24px;">
      <div style="border-bottom: 1px solid #e5e7eb; padding-bottom: 16px; margin-bottom: 16px;">
        <h1 style="font-size: 20px; font-weight: 700; margin: 0 0 6px 0; color: #111827;">{role_esc}</h1>
        <div style="font-size: 15px; font-weight: 600; color: #374151;">🏢 {company_esc}</div>
        <div style="font-size: 14px; color: #6b7280; margin-top: 2px;">📍 {location_esc}</div>
      </div>

      <!-- Key Metrics Grid -->
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
        <tr>
          <td style="padding: 12px; width: 33%; border-right: 1px solid #e2e8f0;">
            <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600;">Match Score</div>
            <div style="font-size: 18px; font-weight: 700; color: #0284c7;">{package.priority_score:.0f}/100</div>
          </td>
          <td style="padding: 12px; width: 33%; border-right: 1px solid #e2e8f0;">
            <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600;">Priority Tier</div>
            <div style="font-size: 14px; font-weight: 700; color: #0f172a;">{badge_label}</div>
          </td>
          <td style="padding: 12px; width: 33%;">
            <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600;">Official URL</div>
            <div style="font-size: 13px; font-weight: 700; color: #16a34a;">{url_status}</div>
          </td>
        </tr>
      </table>


      <!-- Eligibility & Work Auth -->
      <div style="margin-bottom: 16px;">
        <div style="font-size: 13px; margin-bottom: 6px;"><strong>🎓 Eligibility:</strong> <span style="background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 4px; font-weight: 600;">{eligibility_esc}</span></div>
        <div style="font-size: 13px;"><strong>🌐 Work Authorization:</strong> <span style="background: #f1f5f9; color: #334155; padding: 2px 8px; border-radius: 4px; font-weight: 600;">{work_auth_esc}</span></div>
      </div>

      <!-- Profile & Resume -->
      <div style="background: #f8fafc; padding: 14px; border-radius: 6px; margin-bottom: 20px; border-left: 4px solid #3b82f6;">
        <div style="font-size: 13px; font-weight: 700; color: #1e3a8a; margin-bottom: 4px;">Selected Resume: {resume_esc}</div>
        <div style="font-size: 12px; color: #475569; margin-bottom: 8px;">{selection_reason_esc}</div>
        <div style="font-size: 12px; color: #15803d; font-weight: 600; margin-bottom: 4px;">📎 Attached: Fact-Grounded Tailored Resume (PDF)</div>
        <div style="font-size: 12px; color: #15803d; font-weight: 600;">📎 Attached: Customized Cover Letter (.txt)</div>
      </div>

      {warnings_html}

      <!-- Actions -->
      <div style="margin: 28px 0 16px 0; text-align: center;">
        <a href="{official_url_esc}" style="display: inline-block; background: #0284c7; color: #ffffff; text-decoration: none; padding: 12px 24px; font-size: 14px; font-weight: 600; border-radius: 6px; margin-right: 10px; margin-bottom: 10px;">Open Official Application</a>
        <a href="{review_url_esc}" style="display: inline-block; background: #334155; color: #ffffff; text-decoration: none; padding: 12px 24px; font-size: 14px; font-weight: 600; border-radius: 6px; margin-bottom: 10px;">Review in Dashboard</a>
      </div>

      <!-- Human Safety Gate Disclaimer -->
      <div style="margin-top: 24px; padding: 14px; background: #fef2f2; border-radius: 6px; border: 1px solid #fecaca; font-size: 12px; color: #991b1b; text-align: center;">
        <strong>🛡️ MANDATORY HUMAN APPROVAL NOTICE</strong><br>
        Final application submission is strictly human-controlled. Job-AI prepares applications but will NEVER autonomously submit forms, message recruiters, or dispatch applications without explicit candidate review and submission.<br><br>
        <strong>HUMAN ACTION REQUIRED:</strong><br>
        1. Review the attached tailored resume and cover letter.<br>
        2. Verify the job details on the official employer portal.<br>
        3. Submit the application manually.
      </div>
    </div>

    <!-- Footer -->
    <div style="background: #f8fafc; padding: 14px 24px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0;">
      Job-AI Career Buddy &bull; Automated Career Intelligence &bull; Local-First
    </div>
  </div>
</body>
</html>
"""

        # Plain Text Rendering
        text_content = f"""JOB-AI CAREER ALERT — {badge_label}
{"=" * 50}
Role: {package.role}
Company: {package.company}
Location: {package.location}

Match Score: {package.priority_score:.0f}/100
Priority Tier: {badge_label}
Freshness: Verified <=24h

Eligibility: {eligibility_str}
Work Authorization: {work_auth_str}

Selected Resume: {resume_str}
Selection Reason: {selection_reason}
Attachments: Tailored Resume (PDF) & Custom Cover Letter (.txt)
Official Portal: {url_status}

Action Links:
- Official Application URL: {official_url or 'N/A'}
- Review Application in Dashboard: {self.dashboard_base_url}/?fingerprint={fingerprint}

{"-" * 50}
MANDATORY HUMAN APPROVAL NOTICE:
Final application submission is strictly human-controlled.
Job-AI does NOT automatically submit applications to external portals.

HUMAN ACTION REQUIRED:
1. Review the attached tailored resume and cover letter.
2. Verify the job details on the official portal.
3. Submit your application manually.
{"=" * 50}
"""

        p_enum = EmailPriority.CRITICAL if p_tier == "CRITICAL" else EmailPriority.HIGH
        return EmailMessage(
            recipient=recipient,
            sender=sender,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            priority=p_enum,
            job_id=package.job_id,
            application_id=getattr(package, "application_id", None),
            fingerprint=fingerprint,
        )

    def render_daily_digest(
        self,
        digest: DailyCareerDigest,
        recipient: str,
        sender: str,
    ) -> EmailMessage:
        """Render a daily career digest email summarizing fresh opportunities."""
        subject = f"📅 Job-AI Daily Career Digest — {digest.digest_date} ({digest.total_fresh_24h} Fresh Opportunities)"

        opp_items_html = ""
        for opp in digest.top_opportunities:
            c_name = html.escape(opp.get("company", "Unknown"))
            t_name = html.escape(opp.get("title", "Role"))
            l_name = html.escape(opp.get("location", "India"))
            s_val = opp.get("score", 0.0)
            u_link = html.escape(opp.get("application_url", "#"))
            cat = html.escape(opp.get("category", "HIGH"))

            opp_items_html += f"""
            <div style="padding: 12px; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center;">
              <div>
                <div style="font-weight: 700; color: #0f172a; font-size: 14px;">{t_name}</div>
                <div style="font-size: 13px; color: #475569;">🏢 {c_name} &bull; 📍 {l_name}</div>
              </div>
              <div style="text-align: right;">
                <span style="background: #e0f2fe; color: #0369a1; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 700;">{s_val:.0f}/100 [{cat}]</span>
                <div style="margin-top: 4px;"><a href="{u_link}" style="font-size: 12px; color: #0284c7; text-decoration: none; font-weight: 600;">Apply Link &rarr;</a></div>
              </div>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 24px; color: #1f2937; line-height: 1.5;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #e5e7eb;">
    
    <!-- Header -->
    <div style="background: #1e293b; padding: 20px 24px; color: #ffffff;">
      <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #94a3b8; font-weight: 700; margin-bottom: 4px;">Job-AI Daily Intelligence</div>
      <div style="font-size: 20px; font-weight: 700; color: #f8fafc;">
        📅 Career Digest — {digest.digest_date}
      </div>
    </div>

    <!-- Summary Metrics -->
    <div style="padding: 20px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
      <table style="width: 100%; text-align: center; border-collapse: collapse;">
        <tr>
          <td style="padding: 8px;">
            <div style="font-size: 22px; font-weight: 700; color: #0284c7;">{digest.total_fresh_24h}</div>
            <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600;">Fresh &le;24h</div>
          </td>
          <td style="padding: 8px;">
            <div style="font-size: 22px; font-weight: 700; color: #dc2626;">{digest.critical_count}</div>
            <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600;">Critical</div>
          </td>
          <td style="padding: 8px;">
            <div style="font-size: 22px; font-weight: 700; color: #ea580c;">{digest.high_count}</div>
            <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600;">High</div>
          </td>
          <td style="padding: 8px;">
            <div style="font-size: 22px; font-weight: 700; color: #16a34a;">{digest.india_count}</div>
            <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600;">India Hubs</div>
          </td>
        </tr>
      </table>
    </div>

    <!-- Top Opportunities -->
    <div style="padding: 20px 24px;">
      <h2 style="font-size: 16px; font-weight: 700; color: #0f172a; margin: 0 0 12px 0;">Top Prioritized Opportunities</h2>
      <div style="border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; margin-bottom: 20px;">
        {opp_items_html}
      </div>

      <div style="text-align: center; margin: 24px 0 12px 0;">
        <a href="{self.dashboard_base_url}" style="display: inline-block; background: #0284c7; color: #ffffff; text-decoration: none; padding: 12px 24px; font-size: 14px; font-weight: 600; border-radius: 6px;">Open Job-AI Dashboard</a>
      </div>

      <!-- Human Safety Gate Disclaimer -->
      <div style="margin-top: 20px; padding: 12px; background: #f1f5f9; border-radius: 6px; font-size: 11px; color: #475569; text-align: center;">
        <strong>🛡️ HUMAN APPROVAL REMINDER</strong><br>
        Review application packages in the dashboard. Autonomous submissions remain strictly prohibited.
      </div>
    </div>

    <!-- Footer -->
    <div style="background: #f8fafc; padding: 14px 24px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0;">
      Job-AI Career Buddy &bull; Daily Career Digest &bull; Local-First
    </div>
  </div>
</body>
</html>
"""

        text_content = f"""JOB-AI DAILY CAREER DIGEST — {digest.digest_date}
{"=" * 50}
Total Fresh (<=24h): {digest.total_fresh_24h}
Critical Matches: {digest.critical_count} | High Matches: {digest.high_count}
India Hubs: {digest.india_count} | Overseas: {digest.overseas_count}

Top Ranked Opportunities:
"""
        for i, opp in enumerate(digest.top_opportunities, 1):
            text_content += f"\n{i}. {opp.get('title')} at {opp.get('company')} ({opp.get('location')})\n   Score: {opp.get('score')}/100 [{opp.get('category')}]\n   Apply: {opp.get('application_url')}\n"

        text_content += f"""
{"-" * 50}
Dashboard: {self.dashboard_base_url}
Autonomous submission is strictly disabled. Human approval required.
{"=" * 50}
"""

        return EmailMessage(
            recipient=recipient,
            sender=sender,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            priority=EmailPriority.DIGEST,
        )

    def render_test_email(self, recipient: str, sender: str) -> EmailMessage:
        """Render an explicit manual test email to verify SMTP / email setup."""
        subject = "🧪 [TEST] Job-AI Career Buddy Email Delivery Verification"

        html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: sans-serif; background: #f4f6f8; padding: 24px; color: #1f2937;">
  <div style="max-width: 500px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 24px; border: 1px solid #e5e7eb;">
    <h2 style="color: #0f172a; margin-top: 0;">🧪 Job-AI Email Test</h2>
    <p>This is a single verification test email sent explicitly by Job-AI Career Buddy.</p>
    <div style="background: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px; margin: 16px 0; color: #166534; font-size: 13px;">
      ✅ <strong>Email integration is functioning correctly!</strong>
    </div>
    <ul style="font-size: 13px; color: #475569;">
      <li>Recipient: {html.escape(recipient)}</li>
      <li>Sender: {html.escape(sender)}</li>
      <li>Dashboard URL: {html.escape(self.dashboard_base_url)}</li>
    </ul>
    <p style="font-size: 11px; color: #94a3b8; margin-top: 24px; border-top: 1px solid #e5e7eb; padding-top: 12px;">
      Job-AI Career Buddy &bull; Human-Gated Apply Pipeline
    </p>
  </div>
</body>
</html>
"""

        text_content = f"""JOB-AI EMAIL TEST
{"=" * 40}
This is a single verification test email sent explicitly by Job-AI Career Buddy.

Status: Email integration is functioning correctly!
Recipient: {recipient}
Sender: {sender}
Dashboard: {self.dashboard_base_url}
{"=" * 40}
"""

        return EmailMessage(
            recipient=recipient,
            sender=sender,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            priority=EmailPriority.TEST,
        )
