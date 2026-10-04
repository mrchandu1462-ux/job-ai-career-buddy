"""ATS-Parser-Safe Resume Formatter producing clean single-column Markdown and Plaintext."""

from app.resume.models import TailoredResume


class ATSResumeFormatter:
    """Renders tailored resumes into clean single-column, parser-safe formats."""

    @staticmethod
    def render_markdown(resume: TailoredResume) -> str:
        """Render resume as clean, single-column ATS-friendly Markdown."""
        lines: list[str] = []

        # 1. Header & Contact
        lines.append(f"# {resume.candidate_name.upper()}")
        contact_parts = []
        if "location" in resume.contact_info:
            contact_parts.append(resume.contact_info["location"])
        if "email" in resume.contact_info:
            contact_parts.append(resume.contact_info["email"])
        if "phone" in resume.contact_info:
            contact_parts.append(resume.contact_info["phone"])
        if "github" in resume.contact_info:
            contact_parts.append(resume.contact_info["github"])
        if "linkedin" in resume.contact_info:
            contact_parts.append(resume.contact_info["linkedin"])

        if contact_parts:
            lines.append(" | ".join(contact_parts))
        lines.append("")

        # 2. Professional Summary
        lines.append("## PROFESSIONAL SUMMARY")
        lines.append(resume.professional_summary)
        lines.append("")

        # 3. Technical Skills
        lines.append("## TECHNICAL SKILLS")
        for cat, skills in resume.technical_skills_by_category.items():
            lines.append(f"- **{cat}**: {', '.join(skills)}")
        lines.append("")

        # 4. Projects
        lines.append("## TECHNICAL PROJECTS")
        for p in resume.projects:
            tech_str = f" ({', '.join(p.technologies)})" if p.technologies else ""
            role_str = f" | {p.role}" if p.role else ""
            lines.append(f"### {p.title}{role_str}{tech_str}")
            for b in p.bullets:
                lines.append(f"- {b.text}")
            lines.append("")

        # 5. Experience (if present)
        if resume.experience:
            lines.append("## EXPERIENCE & TRAINING")
            for exp in resume.experience:
                date_str = f" ({exp.start_date} - {exp.end_date})" if exp.start_date and exp.end_date else ""
                loc_str = f", {exp.location}" if exp.location else ""
                lines.append(f"### {exp.title} - {exp.company}{loc_str}{date_str}")
                for b in exp.bullets:
                    lines.append(f"- {b.text}")
                lines.append("")

        # 6. Education
        lines.append("## EDUCATION")
        for edu in resume.education:
            gpa_str = f" | CGPA: {edu.gpa_or_score}" if edu.gpa_or_score else ""
            lines.append(f"- **{edu.degree}** - {edu.institution} (Graduation: {edu.graduation_year}){gpa_str}")
        lines.append("")

        # 7. Certifications (if present)
        if resume.certifications:
            lines.append("## CERTIFICATIONS & COURSEWORK")
            for c in resume.certifications:
                lines.append(f"- {c}")
            lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def render_plaintext(resume: TailoredResume) -> str:
        """Render resume as pure plain-text without markdown symbols."""
        lines: list[str] = []

        # 1. Header
        lines.append(resume.candidate_name.upper())
        contact_parts = [v for v in resume.contact_info.values() if v]
        if contact_parts:
            lines.append(" | ".join(contact_parts))
        lines.append("=" * 60)
        lines.append("")

        # 2. Summary
        lines.append("PROFESSIONAL SUMMARY")
        lines.append("-" * 40)
        lines.append(resume.professional_summary)
        lines.append("")

        # 3. Skills
        lines.append("TECHNICAL SKILLS")
        lines.append("-" * 40)
        for cat, skills in resume.technical_skills_by_category.items():
            lines.append(f"{cat}: {', '.join(skills)}")
        lines.append("")

        # 4. Projects
        lines.append("TECHNICAL PROJECTS")
        lines.append("-" * 40)
        for p in resume.projects:
            tech_str = f" [{', '.join(p.technologies)}]" if p.technologies else ""
            lines.append(f"{p.title}{tech_str}")
            for b in p.bullets:
                lines.append(f"  * {b.text}")
            lines.append("")

        # 5. Experience
        if resume.experience:
            lines.append("EXPERIENCE & TRAINING")
            lines.append("-" * 40)
            for exp in resume.experience:
                lines.append(f"{exp.title} - {exp.company}")
                for b in exp.bullets:
                    lines.append(f"  * {b.text}")
                lines.append("")

        # 6. Education
        lines.append("EDUCATION")
        lines.append("-" * 40)
        for edu in resume.education:
            gpa_str = f" (CGPA: {edu.gpa_or_score})" if edu.gpa_or_score else ""
            lines.append(f"{edu.degree} - {edu.institution}, {edu.graduation_year}{gpa_str}")
        lines.append("")

        # 7. Certifications
        if resume.certifications:
            lines.append("CERTIFICATIONS & COURSEWORK")
            lines.append("-" * 40)
            for c in resume.certifications:
                lines.append(f"* {c}")
            lines.append("")

        return "\n".join(lines).strip()
