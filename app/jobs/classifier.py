"""Role classification engine categorizing semiconductor job opportunities."""

import re
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class RoleCategory(str, Enum):
    """Categorized role classifications for VLSI/semiconductor careers."""

    DESIGN_VERIFICATION = "DESIGN_VERIFICATION"
    DV = "DV"
    FUNCTIONAL_VERIFICATION = "FUNCTIONAL_VERIFICATION"
    ASIC_VERIFICATION = "ASIC_VERIFICATION"
    SOC_VERIFICATION = "SOC_VERIFICATION"
    RTL_DESIGN = "RTL_DESIGN"
    FPGA = "FPGA"
    EMBEDDED = "EMBEDDED"
    SEMICONDUCTOR_GRADUATE = "SEMICONDUCTOR_GRADUATE"
    VLSI = "VLSI"
    VERIFICATION_INTERN = "VERIFICATION_INTERN"
    RTL_INTERN = "RTL_INTERN"
    VLSI_INTERN = "VLSI_INTERN"
    GRADUATE_ENGINEER_TRAINEE = "GRADUATE_ENGINEER_TRAINEE"
    OTHER = "OTHER"


class RoleClassificationResult(BaseModel):
    """Result of role classification with explainable scoring and justification."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: RoleCategory = Field(..., description="Classified role category.")
    relevance_score: float = Field(..., ge=0.0, le=20.0, description="Relevance score contribution (0-20 points).")
    matched_keywords: list[str] = Field(default_factory=list, description="Keywords that matched.")
    justification: str = Field(..., min_length=1, description="Human-readable reason for the classification.")


class RoleClassifier:
    """Classifies semiconductor jobs into target role categories with transparent scoring."""

    UNRELATED_TITLES_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"\b(?:python\s*developer|web\s*developer|full[\s-]stack|backend|frontend|software\s*developer|"
        r"devops|cloud\s*engineer|data\s*scientist|data\s*engineer|marketing|sales|recruiter|hr\b|"
        r"accountant|civil\s*engineer|electrical\s*technician|electrician|facilities|wiring|maintenance|hvac)\b",
        re.IGNORECASE,
    )

    def classify(self, title: str, description: str = "") -> RoleClassificationResult:
        """Classify a job title and description into the appropriate RoleCategory with strict role identity checks."""
        title_lower = title.lower().strip()
        desc_lower = description.lower()
        combined = f"{title_lower} {desc_lower}"

        # Filter out clearly non-semiconductor / unrelated career tracks first
        if self.UNRELATED_TITLES_PATTERN.search(title_lower):
            return RoleClassificationResult(
                category=RoleCategory.OTHER,
                relevance_score=0.0,
                matched_keywords=["unrelated role title"],
                justification=f"Role title '{title}' belongs to a non-semiconductor / unrelated engineering track.",
            )

        # 1. Verification Intern
        if re.search(r"\b(?:verification|dv)\s*intern(?:ship)?\b", title_lower) or (
            re.search(r"\bintern(?:ship)?\b", title_lower) and re.search(r"\b(?:verification|uvm|systemverilog)\b", combined)
        ):
            return RoleClassificationResult(
                category=RoleCategory.VERIFICATION_INTERN,
                relevance_score=19.0,
                matched_keywords=["verification intern", "internship"],
                justification="Target verification internship opportunity ideally suited for 2025 fresher.",
            )

        # 2. RTL / Design Intern
        if re.search(r"\b(?:rtl|digital\s*design|asic|soc)\s*intern(?:ship)?\b", title_lower) or (
            re.search(r"\bintern(?:ship)?\b", title_lower) and re.search(r"\b(?:rtl|verilog|digital\s*design)\b", combined)
        ):
            return RoleClassificationResult(
                category=RoleCategory.RTL_INTERN,
                relevance_score=17.5,
                matched_keywords=["rtl intern", "digital design intern"],
                justification="Adjacent RTL / Digital Design internship opportunity with strong semiconductor relevance.",
            )

        # 3. VLSI Intern / General Hardware Intern
        if re.search(r"\bvlsi\s*intern(?:ship)?\b", title_lower) or (
            re.search(r"\bintern(?:ship)?\b", title_lower) and re.search(r"\bvlsi\b", combined)
        ):
            return RoleClassificationResult(
                category=RoleCategory.VLSI_INTERN,
                relevance_score=17.0,
                matched_keywords=["vlsi intern"],
                justification="General VLSI internship with entry-level semiconductor scope.",
            )

        # 4. Graduate Engineer Trainee (GET)
        if re.search(r"\b(?:graduate\s*engineer\s*trainee|\bget\b|trainee\s*engineer|college\s*trainee)\b", title_lower):
            return RoleClassificationResult(
                category=RoleCategory.GRADUATE_ENGINEER_TRAINEE,
                relevance_score=18.0,
                matched_keywords=["graduate engineer trainee", "get"],
                justification="Campus/Fresher Graduate Engineer Trainee position with structured onboarding.",
            )

        # 5. ASIC Verification
        if re.search(r"\basic\s*(?:verification|validation|dv)\b", title_lower) or (
            re.search(r"\basic\b", title_lower) and re.search(r"\bverification\b", combined)
        ):
            return RoleClassificationResult(
                category=RoleCategory.ASIC_VERIFICATION,
                relevance_score=20.0,
                matched_keywords=["asic verification", "asic dv"],
                justification="Direct core ASIC Verification engineering role aligning with primary career goal.",
            )

        # 6. SoC Verification
        if re.search(r"\bsoc\s*(?:verification|validation|dv)\b", title_lower) or (
            re.search(r"\bsoc\b", title_lower) and re.search(r"\bverification\b", combined)
        ):
            return RoleClassificationResult(
                category=RoleCategory.SOC_VERIFICATION,
                relevance_score=20.0,
                matched_keywords=["soc verification", "soc dv"],
                justification="Direct core SoC Verification engineering role aligning with primary career goal.",
            )

        # 7. Functional Verification
        if re.search(r"\bfunctional\s*verification\b", title_lower):
            return RoleClassificationResult(
                category=RoleCategory.FUNCTIONAL_VERIFICATION,
                relevance_score=20.0,
                matched_keywords=["functional verification"],
                justification="Direct core Functional Verification role matching candidate SV/UVM specialization.",
            )

        # 8. General Design Verification / DV / Verification Engineer / ASIC Validation
        if re.search(r"\b(?:design\s*verification|\bdv\s*engineer\b|verification\s*engineer|asic\s*validation)\b", title_lower):
            return RoleClassificationResult(
                category=RoleCategory.DESIGN_VERIFICATION,
                relevance_score=20.0,
                matched_keywords=["design verification", "verification engineer"],
                justification="Primary target Design Verification engineering role.",
            )

        # 9. RTL Design / Digital Design Engineer
        if re.search(r"\b(?:rtl|digital\s*design|logic\s*design)\b", title_lower):
            return RoleClassificationResult(
                category=RoleCategory.RTL_DESIGN,
                relevance_score=16.0,
                matched_keywords=["rtl design", "digital design"],
                justification="Adjacent RTL / Digital Design role where verification skills provide strong foundation.",
            )

        # 10. FPGA Engineer
        if re.search(r"\bfpga\b", title_lower):
            return RoleClassificationResult(
                category=RoleCategory.FPGA,
                relevance_score=15.0,
                matched_keywords=["fpga"],
                justification="FPGA design/prototyping role with direct digital hardware synthesis and simulation overlap.",
            )

        # 11. Embedded Systems / Firmware (Hardware interfacing)
        if re.search(r"\b(?:embedded\s*systems|firmware\s*engineer|embedded\s*hardware)\b", title_lower):
            return RoleClassificationResult(
                category=RoleCategory.EMBEDDED,
                relevance_score=14.0,
                matched_keywords=["embedded"],
                justification="Embedded systems engineering role with hardware-software interfacing scope.",
            )

        # 12. Semiconductor Graduate / Fresher Program
        if re.search(r"\b(?:semiconductor|vlsi|silicon|hardware)\s*(?:graduate|fresher|entry|campus)\b", combined):
            return RoleClassificationResult(
                category=RoleCategory.SEMICONDUCTOR_GRADUATE,
                relevance_score=18.0,
                matched_keywords=["semiconductor graduate"],
                justification="Specialized semiconductor/VLSI graduate onboarding program targeting entry-level talent.",
            )

        # 13. General VLSI Role
        if re.search(r"\bvlsi\b", title_lower):
            return RoleClassificationResult(
                category=RoleCategory.VLSI,
                relevance_score=16.0,
                matched_keywords=["vlsi"],
                justification="Core VLSI engineering position aligned with microelectronics fundamentals.",
            )

        # 14. Verification heavily featured in hardware role description
        dv_kw_count = sum(bool(re.search(rf"\b{kw}\b", desc_lower)) for kw in ["systemverilog", "uvm", "testbench", "coverage closure", "assertions", "sva"])
        if dv_kw_count >= 2 and any(re.search(rf"\b{hw}\b", title_lower) for hw in ["silicon", "hardware", "chip", "semiconductor", "engineer"]):
            return RoleClassificationResult(
                category=RoleCategory.DESIGN_VERIFICATION,
                relevance_score=15.0,
                matched_keywords=["hardware verification in description"],
                justification="Hardware role title with strong core verification responsibilities.",
            )

        # 15. Other semiconductor / hardware engineering
        if any(re.search(rf"\b{w}\b", combined) for w in ["semiconductor", "fpga", "hardware", "silicon", "vlsi"]):
            return RoleClassificationResult(
                category=RoleCategory.OTHER,
                relevance_score=10.0,
                matched_keywords=["semiconductor / hardware general"],
                justification="General hardware/semiconductor role with partial overlap.",
            )

        return RoleClassificationResult(
            category=RoleCategory.OTHER,
            relevance_score=5.0,
            matched_keywords=[],
            justification="Role has limited direct alignment with VLSI Design Verification.",
        )
