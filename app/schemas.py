"""Pydantic schemas = the contract between pipeline steps.

Every claim the system makes carries `source_ids` (which customer sentences
support it) and an `origin`:
  stated      - the customer said it (near) explicitly
  implied     - a direct, unavoidable consequence of something stated
  assumption  - not supported by the input; must be confirmed with the customer
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Origin = Literal["stated", "implied", "assumption"]
Support = Literal["supported", "partial", "unsupported", "unchecked"]


# ---------- Step 1: gate ----------
class GateResult(BaseModel):
    is_software_requirement: bool
    input_kind: Literal["software_requirement", "partial_requirement", "not_software", "unclear"]
    domain: str = ""
    language: str = "en"
    reason: str = ""


# ---------- Step 2: extraction ----------
class ExtractedActor(BaseModel):
    name: str
    description: str = ""
    source_ids: list[str] = Field(default_factory=list)


class ExtractedNeed(BaseModel):
    actor: str = ""
    need: str
    quote: str = ""
    source_ids: list[str] = Field(default_factory=list)
    kind: Literal["capability", "quality", "constraint", "problem", "context"] = "capability"


class VagueTerm(BaseModel):
    term: str
    source_ids: list[str] = Field(default_factory=list)
    why_vague: str = ""


class Extraction(BaseModel):
    actors: list[ExtractedActor] = Field(default_factory=list)
    needs: list[ExtractedNeed] = Field(default_factory=list)
    vague_terms: list[VagueTerm] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    mentioned_technologies: list[str] = Field(default_factory=list)


# ---------- Step 3a: transformation ----------
class Requirement(BaseModel):
    id: str
    text: str
    actor: str = ""
    priority_hint: Literal["must", "should", "could", "unknown"] = "unknown"
    origin: Origin = "stated"
    source_ids: list[str] = Field(default_factory=list)
    support: Support = "unchecked"
    validation_notes: list[str] = Field(default_factory=list)


class UserStory(BaseModel):
    id: str
    as_a: str
    i_want: str
    so_that: str
    requirement_ids: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class RequirementsDraft(BaseModel):
    problem_statement: str
    actors: list[ExtractedActor] = Field(default_factory=list)
    functional_requirements: list[Requirement] = Field(default_factory=list)
    non_functional_requirements: list[Requirement] = Field(default_factory=list)
    user_stories: list[UserStory] = Field(default_factory=list)


# ---------- Step 3b: ambiguity analysis ----------
class MissingInfo(BaseModel):
    topic: str
    detail: str
    impact: Literal["high", "medium", "low"] = "medium"
    related_ids: list[str] = Field(default_factory=list)


class Question(BaseModel):
    question: str
    why_it_matters: str = ""
    priority: Literal["high", "medium", "low"] = "medium"
    related_ids: list[str] = Field(default_factory=list)


class EdgeCase(BaseModel):
    scenario: str
    expected_handling: str = "To be confirmed with customer"
    source_ids: list[str] = Field(default_factory=list)


class Assumption(BaseModel):
    statement: str
    reason: str = ""
    needs_confirmation: bool = True


class AmbiguityAnalysis(BaseModel):
    missing_information: list[MissingInfo] = Field(default_factory=list)
    clarifying_questions: list[Question] = Field(default_factory=list)
    edge_cases: list[EdgeCase] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)


# ---------- Step 4: verifier ----------
class Verdict(BaseModel):
    id: str
    support: Literal["supported", "partial", "unsupported"]
    unsupported_detail: str = ""


class VerificationResult(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)
