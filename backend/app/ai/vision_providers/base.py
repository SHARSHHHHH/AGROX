"""Vision provider interface.

CRITICAL BOUNDARY
-----------------
A vision provider returns a CANDIDATE OBSERVATION and nothing else. It never
prescribes treatment, never names a pesticide and never states a dose. Its
output is fed into the deterministic IPM/severity engines, which decide what
the farmer is actually told.

This is enforced structurally: VisionObservation has no field in which a
treatment could be expressed.

Schema returned by every provider:
    {"crop": str, "problem": str, "confidence": float,
     "symptoms": list[str], "severity": str}
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

# Below this we refuse to act. Mirrors the disease/pest confidence gate.
MIN_CONFIDENCE = 0.55

VALID_SEVERITY = ("none", "mild", "moderate", "severe", "unknown")
VALID_KINDS = ("disease", "pest", "healthy", "unknown")


class VisionProviderError(Exception):
    def __init__(self, kind: str, message: str, provider: str = ""):
        self.kind = kind
        self.provider = provider
        super().__init__(message)


@dataclass
class VisionObservation:
    """What the model claims it can see. Deliberately treatment-free."""

    crop: str = ""
    problem: str = ""                     # disease or pest label, or "Healthy"
    kind: str = "unknown"                 # disease | pest | healthy | unknown
    confidence: float = 0.0
    symptoms: List[str] = field(default_factory=list)
    severity: str = "unknown"             # visual impression only
    coverage_hint: Optional[str] = None    # sparse | moderate | widespread
    visible_evidence: str = ""
    provider: str = ""
    uncertain: bool = True

    def __post_init__(self):
        self.confidence = max(0.0, min(1.0, float(self.confidence or 0.0)))

        if self.severity not in VALID_SEVERITY:
            self.severity = "unknown"
        if self.kind not in VALID_KINDS:
            self.kind = "unknown"

        # A low-confidence observation is marked uncertain here, once, so no
        # downstream caller has to remember to check the threshold.
        self.uncertain = self.confidence < MIN_CONFIDENCE or self.kind == "unknown"

    def to_dict(self) -> dict:
        return {
            "crop": self.crop,
            "problem": self.problem,
            "kind": self.kind,
            "confidence": round(self.confidence, 2),
            "symptoms": self.symptoms,
            "severity": self.severity,
            "coverage_hint": self.coverage_hint,
            "visible_evidence": self.visible_evidence,
            "provider": self.provider,
            "uncertain": self.uncertain,
        }


class BaseVisionProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def analyze(self, image_path: str, crop: str = "") -> VisionObservation:
        """Return a candidate observation, or raise VisionProviderError."""

    def describe(self) -> dict:
        return {"provider": self.name}
