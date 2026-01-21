"""Database repository for CRUD operations."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.db.models import Student, Exam, Question


class StudentRepository:
    """Repository for student operations."""
    
    @staticmethod
    def get_or_create(db: Session, username: str) -> Student:
        """Get existing student or create new one."""
        student = db.query(Student).filter(Student.username == username).first()
        if not student:
            student = Student(username=username)
            db.add(student)
            db.commit()
            db.refresh(student)
        return student


class ExamRepository:
    """Repository for exam operations."""
    
    @staticmethod
    def create(db: Session, student_id: int, exam_template_id: Optional[int] = None) -> Exam:
        """Create a new exam session."""
        exam = Exam(student_id=student_id, exam_template_id=exam_template_id)
        db.add(exam)
        db.commit()
        db.refresh(exam)
        return exam
    
    @staticmethod
    def get(db: Session, exam_id: int) -> Optional[Exam]:
        """Get exam by ID."""
        return db.query(Exam).filter(Exam.id == exam_id).first()
    
    @staticmethod
    def update_status(db: Session, exam_id: int, status: str, final_grade: Optional[float] = None, final_explanation: Optional[str] = None):
        """Update exam status and final grade."""
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if exam:
            exam.status = status
            if final_grade is not None:
                exam.final_grade = final_grade
            if final_explanation:
                exam.final_explanation = final_explanation
            db.commit()
            db.refresh(exam)
        return exam


class QuestionRepository:
    """Repository for question operations."""
    
    @staticmethod
    def create(db: Session, exam_id: int, question_number: int, question_text: str, 
               context: Optional[str] = None, rubric: Optional[str] = None, is_followup: bool = False) -> Question:
        """Create a new question."""
        question = Question(
            exam_id=exam_id,
            question_number=question_number,
            question_text=question_text,
            context=context,
            rubric=rubric,
            is_followup=is_followup
        )
        db.add(question)
        db.commit()
        db.refresh(question)
        return question
    
    @staticmethod
    def get(db: Session, question_id: int) -> Optional[Question]:
        """Get question by ID."""
        return db.query(Question).filter(Question.id == question_id).first()
    
    @staticmethod
    def get_by_exam(db: Session, exam_id: int) -> List[Question]:
        """Get all questions for an exam."""
        return db.query(Question).filter(Question.exam_id == exam_id).order_by(Question.question_number).all()
    
    @staticmethod
    def update_answer(db: Session, question_id: int, answer: str):
        """Update student answer for a question."""
        question = db.query(Question).filter(Question.id == question_id).first()
        if question:
            question.student_answer = answer
            db.commit()
            db.refresh(question)
        return question
    
    @staticmethod
    def update_grade(db: Session, question_id: int, grade: float, feedback: str):
        """Update grade and feedback for a question."""
        question = db.query(Question).filter(Question.id == question_id).first()
        if question:
            question.grade = grade
            question.feedback = feedback
            db.commit()
            db.refresh(question)
        return question

