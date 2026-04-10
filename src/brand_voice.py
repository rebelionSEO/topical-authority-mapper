"""Brand voice extraction from PDF and integration into cluster insights."""

import json
import logging
import os
import re
from typing import Optional

from src.config import CACHE_DIR

logger = logging.getLogger(__name__)

BRAND_PROFILE_TEMPLATE = {
    "brand_name": "",
    "tone": [],
    "writing_style": {
        "sentence_length": "medium",
        "complexity": "intermediate",
    },
    "audience": "",
    "do": [],
    "dont": [],
    "example_phrases": [],
    "content_goals": [],
}

# Section markers to look for in brand voice PDFs
SECTION_PATTERNS = {
    "tone": r"(?i)(tone|voice|personality|brand tone|tone of voice)",
    "audience": r"(?i)(audience|target|demographic|reader|customer)",
    "do": r"(?i)(do|should|always|best practice|guideline)",
    "dont": r"(?i)(don.?t|avoid|never|do not|should not)",
    "goals": r"(?i)(goal|objective|mission|purpose|aim)",
    "style": r"(?i)(style|writing|format|language|complexity)",
}


def extract_brand_voice_from_pdf(pdf_path: str) -> dict:
    """
    Extract brand voice from a PDF document.

    Processes the PDF once and returns a structured brand profile.
    """
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        logger.error("PyPDF2 not installed. Run: pip install PyPDF2")
        return BRAND_PROFILE_TEMPLATE.copy()

    if not os.path.exists(pdf_path):
        logger.error("PDF not found: %s", pdf_path)
        return BRAND_PROFILE_TEMPLATE.copy()

    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    if not full_text.strip():
        logger.warning("No text extracted from PDF: %s", pdf_path)
        return BRAND_PROFILE_TEMPLATE.copy()

    return _parse_brand_text(full_text)


def _parse_brand_text(text: str) -> dict:
    """Parse extracted text into structured brand profile."""
    profile = BRAND_PROFILE_TEMPLATE.copy()
    profile["writing_style"] = BRAND_PROFILE_TEMPLATE["writing_style"].copy()

    lines = text.split("\n")
    lines = [l.strip() for l in lines if l.strip()]

    current_section = None

    for line in lines:
        # Detect section headers
        for section, pattern in SECTION_PATTERNS.items():
            if re.search(pattern, line) and len(line) < 80:
                current_section = section
                break

        if not current_section:
            continue

        # Extract bullet points or sentences
        clean = re.sub(r"^[\-\*\u2022\d\.]+\s*", "", line).strip()
        if len(clean) < 5 or len(clean) > 200:
            continue

        if current_section == "tone":
            _extract_tone_words(clean, profile)
        elif current_section == "audience":
            if not profile["audience"]:
                profile["audience"] = clean
        elif current_section == "do":
            if clean.lower() not in [d.lower() for d in profile["do"]]:
                profile["do"].append(clean)
        elif current_section == "dont":
            if clean.lower() not in [d.lower() for d in profile["dont"]]:
                profile["dont"].append(clean)
        elif current_section == "goals":
            _extract_goals(clean, profile)
        elif current_section == "style":
            _extract_style(clean, profile)

    # Trim lists to reasonable size
    profile["do"] = profile["do"][:8]
    profile["dont"] = profile["dont"][:8]
    profile["content_goals"] = profile["content_goals"][:5]

    return profile


def _extract_tone_words(text: str, profile: dict):
    """Extract tone descriptors from text."""
    tone_words = [
        "professional", "friendly", "authoritative", "casual", "formal",
        "warm", "direct", "empathetic", "confident", "approachable",
        "educational", "conversational", "technical", "reassuring", "bold",
    ]
    for word in tone_words:
        if word in text.lower() and word not in profile["tone"]:
            profile["tone"].append(word)


def _extract_goals(text: str, profile: dict):
    """Extract content goals from text."""
    goal_words = ["educate", "convert", "build trust", "inform", "engage", "retain", "acquire"]
    for word in goal_words:
        if word in text.lower() and word not in profile["content_goals"]:
            profile["content_goals"].append(word)


def _extract_style(text: str, profile: dict):
    """Extract writing style info from text."""
    if any(w in text.lower() for w in ["short", "concise", "brief"]):
        profile["writing_style"]["sentence_length"] = "short"
    elif any(w in text.lower() for w in ["long", "detailed", "thorough"]):
        profile["writing_style"]["sentence_length"] = "long"

    if any(w in text.lower() for w in ["simple", "plain", "easy"]):
        profile["writing_style"]["complexity"] = "simple"
    elif any(w in text.lower() for w in ["advanced", "technical", "complex"]):
        profile["writing_style"]["complexity"] = "advanced"


def load_or_create_brand_profile(pdf_path: Optional[str] = None, profile_path: Optional[str] = None) -> dict:
    """
    Load existing brand profile or create one from PDF.

    Priority:
    1. Load from profile_path if it exists (never reprocess PDF)
    2. Extract from pdf_path and save to profile_path
    3. Return empty template
    """
    if profile_path is None:
        profile_path = os.path.join(CACHE_DIR, "brand_profile.json")

    # Check for existing profile
    if os.path.exists(profile_path):
        logger.info("Loading existing brand profile from %s", profile_path)
        with open(profile_path, "r") as f:
            return json.load(f)

    # Extract from PDF
    if pdf_path:
        logger.info("Extracting brand voice from PDF: %s", pdf_path)
        profile = extract_brand_voice_from_pdf(pdf_path)
        save_brand_profile(profile, profile_path)
        return profile

    logger.info("No brand profile found. Using empty template.")
    return BRAND_PROFILE_TEMPLATE.copy()


def save_brand_profile(profile: dict, path: Optional[str] = None):
    """Save brand profile to JSON."""
    if path is None:
        path = os.path.join(CACHE_DIR, "brand_profile.json")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)
    logger.info("Saved brand profile to %s", path)


def generate_content_recommendation(cluster_name: str, keywords: list[str], brand_profile: dict) -> dict:
    """
    Generate a content recommendation for a cluster based on brand voice.

    Returns structured recommendation with tone, angle, content type, and CTA style.
    """
    # Determine content type from keywords
    content_type = _infer_content_type(keywords)

    # Align tone with brand profile
    tone = brand_profile.get("tone", ["professional"])
    if not tone:
        tone = ["professional"]
    tone_str = ", ".join(tone[:3])

    # Generate angle
    angle = _generate_angle(cluster_name, keywords, content_type)

    # CTA style based on content goals
    goals = brand_profile.get("content_goals", [])
    cta_style = _determine_cta_style(goals, content_type)

    return {
        "content_type": content_type,
        "tone": tone_str,
        "angle": angle,
        "cta_style": cta_style,
    }


def _infer_content_type(keywords: list[str]) -> str:
    """Infer content type from cluster keywords."""
    kw_text = " ".join(keywords).lower()

    if any(w in kw_text for w in ["how to", "guide", "step", "tutorial", "process"]):
        return "How-to Guide"
    if any(w in kw_text for w in ["vs", "compare", "comparison", "difference", "versus"]):
        return "Comparison Page"
    if any(w in kw_text for w in ["best", "top", "review", "list"]):
        return "Listicle / Roundup"
    if any(w in kw_text for w in ["what is", "definition", "meaning", "explained"]):
        return "Educational Article"
    if any(w in kw_text for w in ["cost", "price", "pricing", "fee", "rate"]):
        return "Pricing / Cost Guide"
    if any(w in kw_text for w in ["service", "solution", "product", "offer"]):
        return "Service / Landing Page"
    return "Educational + Conversion Hybrid"


def _generate_angle(cluster_name: str, keywords: list[str], content_type: str) -> str:
    """Generate a content angle suggestion."""
    top_kw = keywords[0] if keywords else cluster_name
    angles = {
        "How-to Guide": f"Step-by-step breakdown of {top_kw} with actionable takeaways",
        "Comparison Page": f"Objective comparison highlighting key differences in {top_kw}",
        "Listicle / Roundup": f"Curated list with expert-backed recommendations for {top_kw}",
        "Educational Article": f"Clear, authoritative explanation of {top_kw} with examples",
        "Pricing / Cost Guide": f"Transparent breakdown of {top_kw} with real-world benchmarks",
        "Service / Landing Page": f"Benefit-driven page focused on {top_kw} with trust signals",
        "Educational + Conversion Hybrid": f"In-depth guide on {top_kw} with embedded conversion paths",
    }
    return angles.get(content_type, f"Comprehensive coverage of {top_kw}")


def _determine_cta_style(goals: list[str], content_type: str) -> str:
    """Determine CTA style based on brand goals and content type."""
    if "convert" in goals and content_type in ("Service / Landing Page", "Pricing / Cost Guide"):
        return "Direct conversion (clear CTA, urgency-appropriate)"
    if "build trust" in goals:
        return "Soft trust-building (educational value first, subtle CTA)"
    if "educate" in goals:
        return "Value-first (resource download, newsletter, next-step guide)"
    return "Balanced (informative with clear next step)"
