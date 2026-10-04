"""ATS-Parser-Safe PDF Resume Exporter using standard single-column selectable flowables."""

import os
from pathlib import Path
from xml.sax import saxutils

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.resume.models import TailoredResume


class PDFResumeExporter:
    """Exports validated TailoredResume models to ATS-parser-safe, searchable, selectable PDF documents."""

    def __init__(self, output_dir: str = "artifacts/resumes"):
        self.output_dir = output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def export(self, resume: TailoredResume, filename: str | None = None) -> str:
        """
        Generate ATS-safe PDF file:
        - 54pt (0.75 in) standard margins
        - Single column, linear reading flow
        - Standard typography (Helvetica, 9.5-10pt body, bold 12pt headings)
        - Clean bullet points (&bull;)
        - Selectable & extractable text
        - ZERO tables, images, multi-columns, or complex layouts
        """
        if not filename:
            filename = f"{resume.resume_id}.pdf"
        output_path = os.path.join(self.output_dir, filename)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ATS_Name",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=3,
        )

        contact_style = ParagraphStyle(
            "ATS_Contact",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#475569"),
            spaceAfter=8,
        )

        section_heading_style = ParagraphStyle(
            "ATS_SectionHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        )

        body_style = ParagraphStyle(
            "ATS_Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=5,
        )

        subheading_style = ParagraphStyle(
            "ATS_Subheading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=4,
            spaceAfter=2,
            keepWithNext=True,
        )

        bullet_style = ParagraphStyle(
            "ATS_Bullet",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            leftIndent=14,
            firstLineIndent=-10,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=2,
        )

        story = []

        # 1. Candidate Name
        story.append(Paragraph(saxutils.escape(resume.candidate_name.upper()), title_style))

        # Contact line
        contact_parts: list[str] = []
        for key in ["location", "email", "phone", "github", "linkedin"]:
            val = resume.contact_info.get(key)
            if val:
                contact_parts.append(saxutils.escape(val))
        if contact_parts:
            story.append(Paragraph(" | ".join(contact_parts), contact_style))

        # 2. Professional Summary
        if resume.professional_summary:
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading_style))
            story.append(Paragraph(saxutils.escape(resume.professional_summary), body_style))

        # 3. Technical Skills
        if resume.technical_skills_by_category:
            story.append(Paragraph("TECHNICAL SKILLS", section_heading_style))
            for category, skills in resume.technical_skills_by_category.items():
                cat_esc = saxutils.escape(category)
                skills_esc = saxutils.escape(", ".join(skills))
                story.append(Paragraph(f"&bull; <b>{cat_esc}</b>: {skills_esc}", bullet_style))
            story.append(Spacer(1, 4))

        # 4. Technical Projects
        if resume.projects:
            story.append(Paragraph("TECHNICAL PROJECTS", section_heading_style))
            for proj in resume.projects:
                p_title = saxutils.escape(proj.title)
                role_str = f" | <i>{saxutils.escape(proj.role)}</i>" if proj.role else ""
                tech_str = f" ({saxutils.escape(', '.join(proj.technologies))})" if proj.technologies else ""
                story.append(Paragraph(f"<b>{p_title}</b>{role_str}{tech_str}", subheading_style))

                for bullet in proj.bullets:
                    b_esc = saxutils.escape(bullet.text)
                    story.append(Paragraph(f"&bull; {b_esc}", bullet_style))
                story.append(Spacer(1, 2))

        # 5. Experience & Training (if present)
        if resume.experience:
            story.append(Paragraph("EXPERIENCE & TRAINING", section_heading_style))
            for exp in resume.experience:
                e_title = saxutils.escape(exp.title)
                e_comp = saxutils.escape(exp.company)
                dates = []
                if exp.start_date:
                    dates.append(saxutils.escape(exp.start_date))
                if exp.end_date:
                    dates.append(saxutils.escape(exp.end_date))
                date_str = f" ({' - '.join(dates)})" if dates else ""
                story.append(Paragraph(f"<b>{e_title} - {e_comp}</b>{date_str}", subheading_style))

                for bullet in exp.bullets:
                    b_esc = saxutils.escape(bullet.text)
                    story.append(Paragraph(f"&bull; {b_esc}", bullet_style))
                story.append(Spacer(1, 2))

        # 6. Education
        if resume.education:
            story.append(Paragraph("EDUCATION", section_heading_style))
            for edu in resume.education:
                deg_esc = saxutils.escape(edu.degree)
                inst_esc = saxutils.escape(edu.institution)
                gpa_str = f" | CGPA: {saxutils.escape(edu.gpa_or_score)}" if edu.gpa_or_score else ""
                story.append(
                    Paragraph(
                        f"&bull; <b>{deg_esc}</b> - {inst_esc} (Graduation: {edu.graduation_year}){gpa_str}",
                        bullet_style,
                    )
                )
            story.append(Spacer(1, 4))

        # 7. Certifications & Coursework
        if resume.certifications:
            story.append(Paragraph("CERTIFICATIONS & COURSEWORK", section_heading_style))
            for cert in resume.certifications:
                story.append(Paragraph(f"&bull; {saxutils.escape(cert)}", bullet_style))

        doc.build(story)
        return output_path
