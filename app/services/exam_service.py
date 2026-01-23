"""Exam service for managing exam workflow."""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.models import Exam, Question
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
    
    async def start_exam(self, db: Session, username: str) -> Exam:
        """Start a new exam session for a student."""
        student = StudentRepository.get_or_create(db, username)
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
        
        # Calculate final grade as simple average of question scores
        # Question grades are stored as 0-100, so we calculate average and store as decimal (0.0-1.0)
        # to match the template display format (final_grade * 100)
        if scores:
            avg_grade_percent = sum(scores) / len(scores)  # Average as percentage (0-100)
            final_grade_decimal = avg_grade_percent / 100.0  # Convert to decimal (0.0-1.0) for storage
            
            # Generate explanation
            explanation = f"Final grade calculated as average of {len(scores)} question(s): {avg_grade_percent:.1f}%"
            if len(scores) > 1:
                score_list = ", ".join([f"{s:.1f}%" for s in scores])
                explanation += f" (Individual scores: {score_list})"
            
            ExamRepository.update_status(
                db,
                exam_id,
                "completed",
                final_grade_decimal,
                explanation
            )
        else:
            # No scores available
            ExamRepository.update_status(
                db,
                exam_id,
                "completed",
                0.0,
                "No question scores available for final grade calculation."
            )
        
        exam = ExamRepository.get(db, exam_id)
        
        # Create notification for instructor when exam is completed
        if exam and exam.instructor_id:
            from app.services.notification_service import NotificationService
            notification_service = NotificationService()
            
            # Get student info for the notification
            student_name = "Student"
            if exam.student_id:
                from app.db.models import Student, User
                student = db.query(Student).filter(Student.id == exam.student_id).first()
                if student:
                    user = db.query(User).filter(User.email == student.username).first()
                    if user:
                        student_name = f"{user.first_name} {user.last_name}".strip() or student.username
            
            grade_percent = exam.final_grade * 100 if exam.final_grade else 0
            notification_service.create_notification(
                db=db,
                user_id=exam.instructor_id,
                notification_type="exam_complete",
                title=f"Exam Completed: {exam.exam_name}",
                message=f"{student_name} has completed the exam '{exam.exam_name}' for {exam.course_number} - Section {exam.section}. Final grade: {grade_percent:.1f}%",
                related_exam_id=exam.id,
                related_course_id=None
            )
        
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

