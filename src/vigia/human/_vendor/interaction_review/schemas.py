"""Data schemas of the human-AI interaction layer reviewer.

These models are the common contract consumed by ALL approaches (B0, B1,
B2, and later p3/A4), so that the comparison between them is fair:
they all receive the same `Dossier` and they all emit `Finding`s with the same schema.

See the v0 plan and docs/adr/ for the rationale behind each decision.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- #
# Input: the system under review, normalized to a "dossier".
# --------------------------------------------------------------------------- #
class SourceKind(str, Enum):
    """Provenance of a dossier source.

    Provenance is first-class: a mismatch between what the TECHNICIAN
    believes the system does and what the END_USER experiences is, in itself, a
    signal of the interaction layer (see plan, section 2).
    """

    DOCUMENT = "document"      # imported documentation about the model/system
    TECHNICIAN = "technician"  # text from a technical profile (implements/maintains)
    END_USER = "end_user"      # text from an end user (uses the system)
    OTHER = "other"


class Source(BaseModel):
    """A piece of information about the system, with its provenance."""

    id: str = Field(..., description="Stable identifier, e.g. 'doc-card' or 'user-doctor-1'.")
    kind: SourceKind
    label: str = Field(..., description="Human-readable label of the source.")
    content: str = Field(..., description="Raw or transcribed text of the source.")


class Dossier(BaseModel):
    """Canonical representation of the AI system and its interaction.

    It is the normalized input consumed by all approaches. It is built from
    heterogeneous sources (documents, text from technicians and from users)
    via `ingest`.
    """

    system_name: str
    domain: str = Field(..., description="Domain, e.g. 'primary-care to gastro referral screening'.")
    summary: str = Field("", description="Brief summary of the system and its interaction flow.")
    sources: list[Source] = Field(default_factory=list)

    @field_validator("sources")
    @classmethod
    def _at_least_one_source(cls, v: list[Source]) -> list[Source]:
        if not v:
            raise ValueError("The dossier needs at least one source.")
        return v


# --------------------------------------------------------------------------- #
# Guidelines (HAX-18 / PAIR) encoded as linkable data.
# --------------------------------------------------------------------------- #
class GuidelineCorpus(str, Enum):
    HAX = "HAX"    # Microsoft, Amershi et al. 2019 (18 guidelines)
    PAIR = "PAIR"  # Google People + AI Guidebook
    IX = "IX"      # Interaction-layer eXtension (propia): riesgos no cubiertos por HAX/PAIR


class Guideline(BaseModel):
    """An atomic and linkable item of a guidelines corpus."""

    id: str = Field(..., description="Stable id, e.g. 'HAX-G1' or 'PAIR-FC-2'.")
    corpus: GuidelineCorpus
    group: str = Field(..., description="Phase (HAX) or chapter (PAIR) it belongs to.")
    title: str
    description: str
    good_example: str = Field(..., description="Example of good compliance.")
    bad_example: str = Field(..., description="Example of non-compliance / anti-pattern.")
    anti_patterns: list[str] = Field(
        default_factory=list,
        description="Concrete associated anti-patterns, for detection.",
    )
    remediations: list[str] = Field(
        default_factory=list,
        description="Curated, actionable remediations for this guideline. RENDER-ONLY: they are "
        "emitted in the report next to the findings that cite the guideline, and deliberately do "
        "NOT go into the generator prompt (that would push the model to parrot a generic fix "
        "instead of a system-specific recommendation).",
    )


# --------------------------------------------------------------------------- #
# Output: findings. Same schema for all approaches.
# --------------------------------------------------------------------------- #
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Finding(BaseModel):
    """A finding about the interaction layer.

    The core of the project: a useful finding is ANCHORED in three things
    (see `is_grounded`). A finding without anchoring is generic and, by the plan's
    definition of success, counts as a failure, not as a success.
    """

    id: str
    title: str
    guideline_ids: list[str] = Field(
        default_factory=list,
        description="Concrete guidelines it supports/breaks (anchor 1).",
    )
    locus: str = Field(
        "",
        description="CONCRETE point of the system the finding refers to (anchor 2).",
    )
    evidence: str = Field(
        "",
        description="Textual quote or reference from the input that supports it (anchor 3).",
    )
    anti_pattern: str | None = Field(None, description="Detected anti-pattern, if applicable.")
    severity: Severity = Severity.MEDIUM
    rationale: str = Field("", description="Why it is a problem in THIS system.")
    recommendation: str = Field("", description="Concrete recommended action.")
    merged_count: int = Field(
        1,
        ge=1,
        description="How many raw findings it consolidates (1 = not consolidated). Set by the "
        "dedup step; a value >1 means several passes described the same problem (often citing "
        "different guidelines) and were merged into this one.",
    )

    def is_grounded(self) -> bool:
        """True if the finding has the three anchors (guideline + locus + evidence).

        It is the operational non-genericity criterion used by `metrics`.
        """
        return bool(self.guideline_ids) and bool(self.locus.strip()) and bool(self.evidence.strip())


# --------------------------------------------------------------------------- #
# Golden set and adjudication (evaluation).
# --------------------------------------------------------------------------- #
class RevealedBy(str, Enum):
    """From which TYPE of dossier source a GoldenIssue is detectable.

    It is the axis of the testimony ablation: it allows measuring recall
    over the subset of problems that ONLY the end user's voice reveals,
    with and without those sources in the dossier. If the testimony is the product's
    differentiator, recall on `USER_ONLY` should collapse when removing the
    END_USER sources; if it does not change, the differentiator is in grounding/credibility, not in
    discovering new problems.
    """

    USER_ONLY = "user_only"  # only detectable from end user testimony (END_USER)
    TECH_ONLY = "tech_only"  # only from documentation / technical profile (DOCUMENT/TECHNICIAN)
    BOTH = "both"            # detectable from both: the doc describes it and the user experiences it
    UNKNOWN = "unknown"      # not yet labeled (default: does not participate in the ablation)


class GoldenIssue(BaseModel):
    """A known interaction problem of the golden case (answer key).

    Material derived from the user's private information: it lives under data/golden/
    (gitignored). The system does NOT see it during the blind run.
    """

    id: str
    description: str
    guideline_ids: list[str] = Field(default_factory=list)
    locus: str = ""
    severity: Severity = Severity.MEDIUM
    revealed_by: RevealedBy = Field(
        RevealedBy.UNKNOWN,
        description="Source that reveals the problem (testimony ablation). "
        "Default UNKNOWN: unlabeled golden do not participate in the ablation.",
    )


class AdjudicationLabel(str, Enum):
    """Label of a reported finding against the golden set."""

    TP_MATCH = "tp_match"          # real and matches a known GoldenIssue
    TP_NEW = "tp_new"              # real but was NOT in the golden (discovery)
    FP_GENERIC = "fp_generic"      # generic / not anchored: applies to any system
    FP_INCORRECT = "fp_incorrect"  # concrete but incorrect


class Adjudication(BaseModel):
    """Verdict on a `Finding`.

    Produced first by the LLM judge. `human_confirmed` distinguishes the automatic verdict
    from a validated one. NOTE (MVP): the human review is currently an EXTERNAL step
    (scripts/export_adjudicacion.py emits a review sheet, corrections are applied by hand);
    nothing writes `human_confirmed` automatically yet. The field is the hook for wiring an
    importer of those corrections later.
    """

    finding_id: str
    label: AdjudicationLabel
    matched_golden_id: str | None = Field(
        None, description="Id of the matched GoldenIssue, if label == TP_MATCH."
    )
    judge_rationale: str = ""
    human_confirmed: bool = False
