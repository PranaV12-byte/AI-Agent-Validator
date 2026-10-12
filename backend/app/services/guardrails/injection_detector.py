"""
Prompt Injection Detection using DistilBERT fine-tuned on prompt-injection dataset.
Uses Hugging Face `protectai/deberta-v3-base-prompt-injection-v2` or
fallback `deepset/deberta-v3-base-injection` for zero-shot detection.
For MVP: Use a simpler heuristic + small model approach to reduce memory.
"""
import re
from dataclasses import dataclass
import structlog
from transformers import pipeline

MAX_INJECTION_INPUT_CHARS = 8000
INJECTION_MODEL_MAX_TOKENS = 512
INJECTION_MODEL_TOKEN_OVERLAP = 128
MAX_INJECTION_MODEL_WINDOWS = 32

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
    complete: bool = True


class InjectionDetector:
    def __init__(self):
        self._classifier = None
        self._load_error: str | None = None
        self._patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

    @property
    def is_ready(self) -> bool:
        return self._classifier is not None

    def load_model(self):
        """Load only a locally cached model; startup must never download weights."""
        model_name = "protectai/deberta-v3-base-prompt-injection-v2"
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                local_files_only=True,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                model_name,
                local_files_only=True,
            )
            self._classifier = pipeline(
                "text-classification",
                model=model,
                tokenizer=tokenizer,
                device=-1,  # CPU only for MVP
                truncation=True,
                max_length=512,
            )
            self._load_error = None
        except Exception as exc:
            self._classifier = None
            self._load_error = type(exc).__name__
            structlog.get_logger().warning(
                "injection_model_unavailable",
                error_type=self._load_error,
                local_cache_only=True,
            )

    def detect(self, text: str, sensitivity: str = "moderate") -> InjectionResult:
        heuristic = self._heuristic_match(text)
        if heuristic is not None:
            return heuristic
        return self._classify_window(text[:INJECTION_MODEL_MAX_TOKENS], sensitivity)

    def detect_full_text(
        self,
        text: str,
        sensitivity: str = "moderate",
    ) -> InjectionResult:
        """Evaluate every bounded token window, or report an incomplete check.

        The classifier is limited to 512 tokens by its pipeline configuration.
        For longer inputs, tokenizer offsets create overlapping windows so a
        later segment is never silently discarded. Inputs and model-call count
        are bounded; unsupported windowing is an explicit incomplete result.
        """
        if len(text) > MAX_INJECTION_INPUT_CHARS:
            heuristic = self._heuristic_match(text[:MAX_INJECTION_INPUT_CHARS])
            return heuristic if heuristic is not None else self._incomplete("input_limit")
        heuristic = self._heuristic_match(text)
        if heuristic is not None:
            return heuristic
        if self._classifier is None:
            return self._incomplete("heuristic_only")

        windows = self._token_windows(text)
        if windows is None:
            return self._incomplete("model_windowing_unavailable")

        for window in windows:
            result = self._classify_window(window, sensitivity)
            if result.is_injection:
                return result
            if not result.complete:
                return result
        return InjectionResult(
            is_injection=False,
            confidence=0.0,
            method="model",
            complete=True,
        )

    def _heuristic_match(self, text: str) -> InjectionResult | None:
        for pattern in self._patterns:
            match = pattern.search(text)
            if match:
                return InjectionResult(
                    is_injection=True,
                    confidence=0.99,
                    method="heuristic",
                    matched_pattern=match.group(),
                    complete=True,
                )
        return None

    def _classify_window(self, text: str, sensitivity: str) -> InjectionResult:
        if self._classifier is None:
            return self._incomplete("heuristic_only")
        result = self._classifier(text)[0]
        label = result["label"].upper()
        score = result["score"]
        if label == "INJECTION" and score >= THRESHOLDS.get(sensitivity, 0.7):
            return InjectionResult(
                is_injection=True,
                confidence=round(score, 4),
                method="model",
                complete=True,
            )
        return InjectionResult(
            is_injection=False,
            confidence=0.0,
            method="model",
            complete=True,
        )

    @staticmethod
    def _incomplete(method: str) -> InjectionResult:
        return InjectionResult(
            is_injection=False,
            confidence=0.0,
            method=method,
            complete=False,
        )

    def _token_windows(self, text: str) -> tuple[str, ...] | None:
        tokenizer = getattr(self._classifier, "tokenizer", None)
        if not callable(tokenizer):
            return None
        try:
            encoded = tokenizer(
                text,
                add_special_tokens=False,
                return_offsets_mapping=True,
                truncation=False,
            )
            offsets = encoded["offset_mapping"]
            if offsets and isinstance(offsets[0][0], (list, tuple)):
                offsets = offsets[0]
            normalized = [
                (int(start), int(end))
                for start, end in offsets
                if int(end) > int(start)
            ]
        except Exception:
            # Slow tokenizers and malformed mappings cannot establish coverage.
            return None
        if not normalized:
            return None

        model_max = getattr(tokenizer, "model_max_length", INJECTION_MODEL_MAX_TOKENS)
        if not isinstance(model_max, int) or model_max <= 0 or model_max > 1_000_000:
            model_max = INJECTION_MODEL_MAX_TOKENS
        special_token_count = getattr(tokenizer, "num_special_tokens_to_add", None)
        try:
            special_count = int(special_token_count(pair=False)) if callable(special_token_count) else 2
        except (TypeError, ValueError, OverflowError):
            return None
        window_token_count = min(INJECTION_MODEL_MAX_TOKENS, model_max) - special_count
        if window_token_count <= INJECTION_MODEL_TOKEN_OVERLAP:
            return None
        stride = window_token_count - INJECTION_MODEL_TOKEN_OVERLAP

        windows: list[str] = []
        token_start = 0
        while token_start < len(normalized):
            token_end = min(token_start + window_token_count, len(normalized))
            char_start = 0 if token_start == 0 else normalized[token_start][0]
            char_end = (
                len(text)
                if token_end == len(normalized)
                else normalized[token_end - 1][1]
            )
            if char_end <= char_start:
                return None
            windows.append(text[char_start:char_end])
            if len(windows) > MAX_INJECTION_MODEL_WINDOWS:
                return None
            if token_end == len(normalized):
                break
            token_start += stride

        return tuple(windows)


# Singleton instance
injection_detector = InjectionDetector()
