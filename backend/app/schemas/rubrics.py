"""Question, answer-key and rubric contracts - Part 2.

Part 2 answers one question: *what should a correct answer contain?* It is the
only part of the system that encodes academic judgement, and it does so as
data rather than as prose, so that Part 3 can apply it mechanically and a
human can audit it without reading any code.

Two invariants are enforced here rather than trusted:

1. **A rubric's criteria must sum to the question's maximum mark.** A rubric
   that sums to 4.5 out of 5 silently caps every student at 90%; one that sums
   to 5.5 lets the engine award more than the question is worth.
2. **Marks live only on criteria.** Nothing downstream may invent a mark that
   is not traceable to a criterion, which is what makes a score explainable.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CriterionIn(BaseModel):
    """One thing a marker looks for, and what it is worth."""

    position: int = Field(ge=1, description="Display and reporting order, 1-based.")
    description: str = Field(min_length=3, max_length=1000)
    max_marks: float = Field(gt=0, le=100)

    # What the criterion is really testing. The evaluator is shown these as
    # the meaning of the criterion, never as strings to match literally - a
    # student who writes the idea in their own words must still score.
    essential_concepts: list[str] = Field(default_factory=list)
    acceptable_alternatives: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)

    # False means all-or-nothing: a half-stated fact scores zero. Used for
    # criteria where a partial answer is not partially correct.
    allows_partial: bool = True
    # True marks a criterion the rest of the answer depends on, such as the
    # final numeric result. Getting these wrong costs confidence, not marks.
    load_bearing: bool = False

    model_config = ConfigDict(from_attributes=True)


class CriterionOut(CriterionIn):
    id: str


class RubricIn(BaseModel):
    marking_scheme: str | None = Field(default=None, max_length=5000)
    criteria: list[CriterionIn] = Field(min_length=1)
    scoring_rules: dict = Field(default_factory=dict)


class RubricOut(BaseModel):
    id: str
    question_id: str
    version: int
    is_active: bool
    marking_scheme: str | None = None
    scoring_rules: dict = Field(default_factory=dict)
    criteria: list[CriterionOut] = Field(default_factory=list)
    total_criterion_marks: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuestionIn(BaseModel):
    number: str | None = Field(default=None, max_length=20)
    text: str = Field(min_length=3, max_length=5000)
    topic: str | None = Field(default=None, max_length=160)
    question_type: str = Field(default="theory", max_length=40)
    max_marks: float = Field(gt=0, le=100)
    answer_key: str | None = Field(default=None, max_length=20_000)
    rubric: RubricIn | None = None


class QuestionOut(BaseModel):
    id: str
    exam_id: str
    number: str | None = None
    text: str
    topic: str | None = None
    question_type: str
    max_marks: float
    answer_key: str | None = None
    has_rubric: bool = False
    rubric: RubricOut | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExamIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    subject: str = Field(min_length=2, max_length=120)
    subject_code: str | None = Field(default=None, max_length=40)
    term: str | None = Field(default=None, max_length=80)
    questions: list[QuestionIn] = Field(default_factory=list)


class ExamOut(BaseModel):
    id: str
    title: str
    subject: str
    subject_code: str | None = None
    term: str | None = None
    question_count: int
    total_marks: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExamDetailOut(ExamOut):
    questions: list[QuestionOut] = Field(default_factory=list)


class RubricProblem(BaseModel):
    """One thing wrong with a rubric, and whether it blocks marking."""

    question: str
    severity: str  # "error" blocks evaluation; "warning" does not
    message: str


class RubricValidationOut(BaseModel):
    """Whether this exam's rubrics are fit to mark with.

    Run before a marking session. An exam with errors is not evaluated: a
    rubric that does not sum correctly produces scores that look reasonable
    and are wrong, which is the worst possible failure for this system.
    """

    exam_id: str
    is_valid: bool
    questions_checked: int
    criteria_checked: int
    total_marks: float
    problems: list[RubricProblem] = Field(default_factory=list)
