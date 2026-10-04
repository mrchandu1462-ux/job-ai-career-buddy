"""ATS-Parser-Safe DOCX Resume Exporter using standard single-column layout and typography."""

import os
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor

from app.resume.models import TailoredResume


class DOCXResumeExporter:
    """Exports validated TailoredResume models to single-column ATS-compliant Microsoft Word (.docx) files."""

    def __init__(self, output_dir: str = "artifacts/resumes"):
        self.output_dir = output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def export(self, resume: TailoredResume, filename: str | None = None) -> str:
        """
        Generate ATS-safe DOCX file:
        - 1.0 inch standard margins
        - Single column, linear reading flow
        - Standard typography (Calibri/Arial, 10.5-11pt body, bold 13pt headings)
        - Standard bullets
        - ZERO tables, textboxes, shapes, graphics, or icons
        """
        if not filename:
            filename = f"{resume.resume_id}.docx"
        output_path = os.path.join(self.output_dir, filename)

        doc = Document()

        # Set 1-inch standard page margins on section
        section = doc.sections[0]
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

        # Base style configuration
        normal_style = doc.styles["Normal"]
        normal_style.font.name = "Calibri"
        normal_style.font.size = Pt(10.5)
        normal_style.font.color.rgb = RGBColor(30, 30, 30)

        # 1. Header (Candidate Name)
        name_para = doc.add_paragraph()
        name_run = name_para.add_run(resume.candidate_name.upper())
        name_run.bold = True
        name_run.font.size = Pt(18)
        name_run.font.color.rgb = RGBColor(10, 25, 47)
        name_para.paragraph_format.space_after = Pt(2)

        # Contact Info Line
        contact_parts: list[str] = []
        for key in ["location", "email", "phone", "github", "linkedin"]:
            val = resume.contact_info.get(key)
            if val:
                contact_parts.append(val)

        if contact_parts:
            contact_para = doc.add_paragraph()
            contact_run = contact_para.add_run(" | ".join(contact_parts))
            contact_run.font.size = Pt(9.5)
            contact_run.font.color.rgb = RGBColor(80, 80, 80)
            contact_para.paragraph_format.space_after = Pt(12)

        # Helper for adding section headings
        def add_section_heading(title: str) -> None:
            heading_para = doc.add_paragraph()
            heading_para.paragraph_format.space_before = Pt(10)
            heading_para.paragraph_format.space_after = Pt(4)
            heading_para.paragraph_format.keep_with_next = True
            h_run = heading_para.add_run(title.upper())
            h_run.bold = True
            h_run.font.size = Pt(12)
            h_run.font.color.rgb = RGBColor(10, 25, 47)

        # 2. Professional Summary
        if resume.professional_summary:
            add_section_heading("Professional Summary")
            summary_para = doc.add_paragraph()
            summary_para.paragraph_format.space_after = Pt(8)
            s_run = summary_para.add_run(resume.professional_summary)
            s_run.font.size = Pt(10.5)

        # 3. Technical Skills
        if resume.technical_skills_by_category:
            add_section_heading("Technical Skills")
            for category, skills in resume.technical_skills_by_category.items():
                p = doc.add_paragraph(style="List Bullet")
                p.paragraph_format.space_after = Pt(2)
                cat_run = p.add_run(f"{category}: ")
                cat_run.bold = True
                cat_run.font.size = Pt(10)
                skills_run = p.add_run(", ".join(skills))
                skills_run.font.size = Pt(10)

        # 4. Technical Projects
        if resume.projects:
            add_section_heading("Technical Projects")
            for proj in resume.projects:
                p_hdr = doc.add_paragraph()
                p_hdr.paragraph_format.space_before = Pt(6)
                p_hdr.paragraph_format.space_after = Pt(2)
                p_hdr.paragraph_format.keep_with_next = True

                title_run = p_hdr.add_run(proj.title)
                title_run.bold = True
                title_run.font.size = Pt(11)

                if proj.role:
                    role_run = p_hdr.add_run(f" | {proj.role}")
                    role_run.italic = True
                    role_run.font.size = Pt(10)

                if proj.technologies:
                    tech_run = p_hdr.add_run(f" ({', '.join(proj.technologies)})")
                    tech_run.font.size = Pt(9.5)
                    tech_run.font.color.rgb = RGBColor(90, 90, 90)

                for bullet in proj.bullets:
                    b_para = doc.add_paragraph(style="List Bullet")
                    b_para.paragraph_format.space_after = Pt(2)
                    b_run = b_para.add_run(bullet.text)
                    b_run.font.size = Pt(10)

        # 5. Experience & Training (if present)
        if resume.experience:
            add_section_heading("Experience & Training")
            for exp in resume.experience:
                exp_hdr = doc.add_paragraph()
                exp_hdr.paragraph_format.space_before = Pt(6)
                exp_hdr.paragraph_format.space_after = Pt(2)
                exp_hdr.paragraph_format.keep_with_next = True

                exp_title_run = exp_hdr.add_run(f"{exp.title} - {exp.company}")
                exp_title_run.bold = True
                exp_title_run.font.size = Pt(11)

                dates = []
                if exp.start_date:
                    dates.append(exp.start_date)
                if exp.end_date:
                    dates.append(exp.end_date)
                if dates or exp.location:
                    meta_str = " | ".join(filter(None, [" - ".join(dates), exp.location]))
                    meta_run = exp_hdr.add_run(f" ({meta_str})")
                    meta_run.font.size = Pt(9.5)
                    meta_run.font.color.rgb = RGBColor(90, 90, 90)

                for bullet in exp.bullets:
                    b_para = doc.add_paragraph(style="List Bullet")
                    b_para.paragraph_format.space_after = Pt(2)
                    b_run = b_para.add_run(bullet.text)
                    b_run.font.size = Pt(10)

        # 6. Education
        if resume.education:
            add_section_heading("Education")
            for edu in resume.education:
                edu_para = doc.add_paragraph(style="List Bullet")
                edu_para.paragraph_format.space_after = Pt(3)

                deg_run = edu_para.add_run(edu.degree)
                deg_run.bold = True
                deg_run.font.size = Pt(10.5)

                inst_run = edu_para.add_run(f" - {edu.institution} (Graduation: {edu.graduation_year})")
                inst_run.font.size = Pt(10)

                if edu.gpa_or_score:
                    gpa_run = edu_para.add_run(f" | CGPA: {edu.gpa_or_score}")
                    gpa_run.font.size = Pt(10)

        # 7. Certifications & Coursework
        if resume.certifications:
            add_section_heading("Certifications & Coursework")
            for cert in resume.certifications:
                cert_para = doc.add_paragraph(style="List Bullet")
                cert_para.paragraph_format.space_after = Pt(2)
                cert_run = cert_para.add_run(cert)
                cert_run.font.size = Pt(10)

        doc.save(output_path)
        return output_path
