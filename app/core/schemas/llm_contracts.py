"""Pydantic schemas for LLM response contracts."""
from pydantic import BaseModel, Field
from typing import Optional, List


class GeneratedQuestion(BaseModel):
    """Schema for generated question response."""
    question_text: str = Field(..., description="The exam question text")
    context: str = Field(..., description="Background context for the question")
    rubric: str = Field(..., description="Grading rubric for this question")


class GeneratedQuestionWithNumber(BaseModel):
    """Schema for generated question with question number."""
    question_number: int = Field(..., description="The question number (1-indexed)")
    question_text: str = Field(..., description="The exam question text")
    context: str = Field(..., description="Background context for the question")
    rubric: str = Field(..., description="Grading rubric for this question")


class GeneratedExam(BaseModel):
    """Schema for generated exam with multiple questions."""
    questions: List[GeneratedQuestionWithNumber] = Field(..., description="List of generated exam questions")


class GradingResult(BaseModel):
    """Schema for grading response."""
    grade: float = Field(..., ge=0.0, le=100.0, description="Grade out of 100")
    feedback: str = Field(..., description="Detailed feedback on the answer")
    strengths: List[str] = Field(default_factory=list, description="List of answer strengths")
    weaknesses: List[str] = Field(default_factory=list, description="List of answer weaknesses")


class FinalGrade(BaseModel):
    """Schema for final exam grade."""
    final_grade: float = Field(..., ge=0.0, le=100.0, description="Final exam grade out of 100")
    explanation: str = Field(..., description="Summary explanation of the final grade")
    question_scores: List[float] = Field(..., description="Individual question scores")


class FollowupQuestion(BaseModel):
    """Schema for follow-up question generation."""
    should_ask: bool = Field(..., description="Whether a follow-up question should be asked")
    question_text: Optional[str] = Field(None, description="Follow-up question text if should_ask is True")
    context: Optional[str] = Field(None, description="Context for the follow-up question")

