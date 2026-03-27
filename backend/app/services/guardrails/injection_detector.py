"""
Prompt Injection Detection using DistilBERT fine-tuned on prompt-injection dataset.
Uses Hugging Face `protectai/deberta-v3-base-prompt-injection-v2` or
fallback `deepset/deberta-v3-base-injection` for zero-shot detection.
For MVP: Use a simpler heuristic + small model approach to reduce memory.
"""
import re
from dataclasses import dataclass
from transformers import pipeline

# Sensitivity thresholds
THRESHOLDS = {
    "strict": 0.5,
    "moderate": 0.7,
    "lenient": 0.85,
}

# Heuristic patterns (fast pre-check before model inference)
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(if\s+you\s+are|a)\s+",
    r"pretend\s+(to\s+be|you\s+are)\s+",
    r"forget\s+(everything|all)\s+(you|your)",
    r"new\s+instruction[s]?\s*[:;]",
    r"system\s*prompt\s*[:;]",
    r"override\s+(all\s+)?safety",
    r"jailbreak",
    r"DAN\s+mode",
    r"\[INST\]",
    r"<\|system\|>",
]


@dataclass
class InjectionResult:
    is_injection: bool
    confidence: float
    method: str  # "heuristic" or "model"
    matched_pattern: str | None = None


class InjectionDetector:
    def __init__(self):
        self._classifier = None
        self._patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

    @property
    def is_ready(self) -> bool:
        return self._classifier is not None

    def load_model(self):
        """Call during app startup (lifespan). Loads model into memory once."""
        self._classifier = pipeline(
            "text-classification",
            model="protectai/deberta-v3-base-prompt-injection-v2",
            device=-1,  # CPU only for MVP
            truncation=True,
            max_length=512,
        )

    def detect(self, text: str, sensitivity: str = "moderate") -> InjectionResult:
        threshold = THRESHOLDS.get(sensitivity, 0.7)

        # Step 1: Fast heuristic check
        for pattern in self._patterns:
            match = pattern.search(text)
            if match:
                return InjectionResult(
                    is_injection=True,
                    confidence=0.99,
                    method="heuristic",
                    matched_pattern=match.group(),
                )

        # Step 2: Model inference (if model loaded)
        if self._classifier:
            result = self._classifier(text[:512])[0]
            label = result["label"].upper()
            score = result["score"]
            if label == "INJECTION" and score >= threshold:
                return InjectionResult(
                    is_injection=True,
                    confidence=round(score, 4),
                    method="model",
                )

        return InjectionResult(is_injection=False, confidence=0.0, method="model")


# Singleton instance
injection_detector = InjectionDetector()
