"""
PII Redaction Service.
Detects and redacts: Aadhaar, PAN, Email, Phone (Indian), UPI IDs.
Uses RegEx for structured patterns + spaCy for named entities.
"""

import re
from dataclasses import dataclass, field


@dataclass
class RedactionItem:
    type: str  # "aadhaar" | "pan" | "email" | "phone" | "upi"
    original: str  # The matched text (partially masked)
    replacement: str  # The placeholder


@dataclass
class RedactionResult:
    sanitized_text: str
    redactions: list[RedactionItem] = field(default_factory=list)
    pii_found: bool = False


# Indian PII patterns
PII_PATTERNS = {
    "aadhaar": {
        "regex": re.compile(r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4})\b"),
        "replacement": "[AADHAAR_REDACTED]",
        "mask": lambda m: f"XXXX-XXXX-{m.group()[-4:]}",
    },
    "pan": {
        "regex": re.compile(r"\b([A-Z]{5}\d{4}[A-Z])\b"),
        "replacement": "[PAN_REDACTED]",
        "mask": lambda m: f"XXXXX{m.group()[-5:]}",
    },
    "email": {
        "regex": re.compile(r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"),
        "replacement": "[EMAIL_REDACTED]",
        "mask": lambda m: f"{m.group()[:2]}***@***",
    },
    "phone": {
        "regex": re.compile(r"\b(\+91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})\b"),
        "replacement": "[PHONE_REDACTED]",
        "mask": lambda m: f"XXXXXX{m.group()[-4:]}",
    },
    "upi": {
        "regex": re.compile(r"\b([a-zA-Z0-9._%+\-]+@[a-z]{2,})\b"),
        "replacement": "[UPI_REDACTED]",
        "mask": lambda m: f"***@{m.group().split('@')[1]}",
    },
}


class PIIRedactor:
    def __init__(self):
        self._nlp = None  # spaCy model (optional enhancement)

    def load_model(self):
        """Load spaCy model for NER-based detection (optional, loaded at startup)."""
        try:
            import spacy

            self._nlp = spacy.load("en_core_web_sm")
        except (ImportError, OSError):
            self._nlp = None  # Fallback to regex-only

    def redact(self, text: str, pii_types: list[str] | None = None) -> RedactionResult:
        """
        Scan text and replace detected PII with placeholders.

        Args:
            text: Input text to scan
            pii_types: List of PII types to check. None = all types.

        Returns:
            RedactionResult with sanitized text and list of redactions.
        """
        if pii_types is None:
            pii_types = list(PII_PATTERNS.keys())

        redactions: list[RedactionItem] = []
        sanitized = text

        # Process each PII type
        for pii_type in pii_types:
            if pii_type not in PII_PATTERNS:
                continue

            pattern_config = PII_PATTERNS[pii_type]
            regex = pattern_config["regex"]
            replacement = pattern_config["replacement"]
            mask_fn = pattern_config["mask"]

            matches = list(regex.finditer(sanitized))

            # Process in reverse order to preserve string positions
            for match in reversed(matches):
                # Skip UPI if it looks like a regular email (has common domain)
                if pii_type == "upi":
                    domain = match.group().split("@")[1] if "@" in match.group() else ""
                    if domain in (
                        "gmail",
                        "gmail.com",
                        "yahoo",
                        "yahoo.com",
                        "outlook",
                        "outlook.com",
                        "hotmail",
                        "hotmail.com",
                        "proton",
                        "proton.me",
                    ):
                        continue  # This is an email, not UPI

                masked = mask_fn(match)
                redactions.append(
                    RedactionItem(
                        type=pii_type,
                        original=masked,
                        replacement=replacement,
                    )
                )
                sanitized = (
                    sanitized[: match.start()] + replacement + sanitized[match.end() :]
                )

        return RedactionResult(
            sanitized_text=sanitized,
            redactions=redactions,
            pii_found=len(redactions) > 0,
        )


# Singleton instance
pii_redactor = PIIRedactor()
