"""Exam service for managing exam workflow."""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.models import Exam, Question, ExamTemplate, CustomQuestion, ExamAccess
from app.db.repo import ExamRepository, QuestionRepository, StudentRepository
from app.core.grading.generator import QuestionGenerator
from app.core.grading.grader import AnswerGrader
from app.core.grading.finalizer import FinalGradeCalculator
from app.core.grading.thresholds import should_ask_followup
from app.settings import get_settings
import logging

logger = logging.getLogger(__name__)

class ExamService:
    """Service for managing exam sessions and workflow."""
    
    def __init__(self):
        self.settings = get_settings()
        # Initialize these lazily - they create LLMClient which requires API key
        # Only create them when actually needed (in methods that use them)
        self._question_generator = None
        self._answer_grader = None
        self._final_grade_calculator = None
    
    @property
    def question_generator(self):
        """Lazily initialize question generator."""
        if self._question_generator is None:
            self._question_generator = QuestionGenerator()
        return self._question_generator
    
    @property
    def answer_grader(self):
        """Lazily initialize answer grader."""
        if self._answer_grader is None:
            self._answer_grader = AnswerGrader()
        return self._answer_grader
    
    @property
    def final_grade_calculator(self):
        """Lazily initialize final grade calculator."""
        if self._final_grade_calculator is None:
            self._final_grade_calculator = FinalGradeCalculator()
        return self._final_grade_calculator
    
    async def start_exam(self, db: Session, username: str, exam_template_id: Optional[int] = None) -> Exam:
        """Start a new exam session for a student."""
        student = StudentRepository.get_or_create(db, username)
        
        # If exam_template_id is provided, use teacher-created exam
        if exam_template_id:
            # Check if student has access
            access = db.query(ExamAccess).filter(
                ExamAccess.exam_template_id == exam_template_id,
                ExamAccess.student_username == username,
                ExamAccess.is_active == True
            ).first()
            
            if not access:
                raise ValueError(f"Student {username} does not have access to this exam")
            
            # Get exam template
            exam_template = db.query(ExamTemplate).filter(
                ExamTemplate.id == exam_template_id,
                ExamTemplate.is_active == True
            ).first()
            
            if not exam_template:
                raise ValueError("Exam template not found or inactive")
            
            # Create exam linked to template
            exam = ExamRepository.create(db, student.id, exam_template_id)
            
            # Load questions from template
            custom_questions = db.query(CustomQuestion).filter(
                CustomQuestion.exam_template_id == exam_template_id
            ).order_by(CustomQuestion.question_number).all()
            
            if not custom_questions:
                raise ValueError("Exam template has no questions")
            
            # Create exam questions from template
            for custom_q in custom_questions:
                QuestionRepository.create(
                    db,
                    exam.id,
                    custom_q.question_number,
                    custom_q.question_text,
                    custom_q.context,
                    custom_q.rubric
                )
        else:
            # Default: Generate AI questions (original behavior)
            exam = ExamRepository.create(db, student.id)
            
            # Generate initial questions
            for i in range(1, self.settings.exam_question_count + 1):
                try:
                    generated = await self.question_generator.generate_question(
                        topic="Computer Science",
                        difficulty="Intermediate",
                        question_number=i
                    )
                    QuestionRepository.create(
                        db,
                        exam.id,
                        i,
                        generated.question_text,
                        generated.context,
                        generated.rubric
                    )
                except Exception as e:
                    logger.warning(f"Error generating question {i} (likely no API key): {e}")
                    # Create different fallback questions based on question number
                    generated = await self.question_generator.generate_question(
                        topic="Computer Science",
                        difficulty="Intermediate",
                        question_number=i
                    )

        return exam
    
    async def get_current_question(self, db: Session, exam_id: int) -> Optional[Question]:
        """Get the current unanswered question for an exam."""
        questions = QuestionRepository.get_by_exam(db, exam_id)
        for question in questions:
            if question.student_answer is None:
                return question
        return None
    
    async def submit_answer(self, db: Session, question_id: int, answer: str) -> Question:
        """Submit an answer for a question."""
        question = QuestionRepository.update_answer(db, question_id, answer)
        
        if question:
            # Grade the answer
            try:
                grading_result = await self.answer_grader.grade_answer(
                    question.question_text,
                    question.context or "",
                    question.rubric or "",
                    answer
                )
                QuestionRepository.update_grade(
                    db,
                    question_id,
                    grading_result.grade,
                    grading_result.feedback
                )
            except Exception as e:
                logger.error(f"Error grading answer: {e}")
        
        return question
    
    async def complete_exam(self, db: Session, exam_id: int) -> Exam:
        """Calculate final grade and complete the exam."""
        questions = QuestionRepository.get_by_exam(db, exam_id)
        
        # Collect scores and feedback
        scores = []
        feedbacks = []
        for q in questions:
            if q.grade is not None:
                scores.append(q.grade)
                feedbacks.append(q.feedback or "")
        
        # Calculate final grade
        try:
            final_result = await self.final_grade_calculator.calculate_final_grade(
                scores,
                feedbacks
            )
            
            ExamRepository.update_status(
                db,
                exam_id,
                "completed",
                final_result.final_grade,
                final_result.explanation
            )
        except Exception as e:
            logger.error(f"Error calculating final grade: {e}")
            # Fallback: simple average
            avg_grade = sum(scores) / len(scores) if scores else 0.0
            ExamRepository.update_status(
                db,
                exam_id,
                "completed",
                avg_grade,
                f"Final grade calculated as average: {avg_grade:.1f}"
            )
        
        exam = ExamRepository.get(db, exam_id)
        return exam
    
    def get_exam_status(self, db: Session, exam_id: int) -> dict:
        """Get current status of an exam."""
        exam = ExamRepository.get(db, exam_id)
        if not exam:
            return None
        
        questions = QuestionRepository.get_by_exam(db, exam_id)
        answered_count = sum(1 for q in questions if q.student_answer is not None)
        
        return {
            "exam_id": exam.id,
            "status": exam.status,
            "questions_completed": answered_count,
            "total_questions": len(questions),
            "current_question": answered_count + 1 if exam.status == "in_progress" else None
        }

