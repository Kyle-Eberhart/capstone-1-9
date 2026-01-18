"""Database models."""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base



class User(Base):
    """User login model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String(50), nullable=False)  # "student" or "teacher"
    
class Student(Base):
    """Student model."""
    __tablename__ = "students"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    exams = relationship("Exam", back_populates="student")


class Teacher(Base):
    """Teacher model."""
    __tablename__ = "teachers"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)  # For future password auth
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    exam_templates = relationship("ExamTemplate", back_populates="teacher")


class ExamTemplate(Base):
    """Exam template created by teacher."""
    __tablename__ = "exam_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Time limit settings
    time_limit_type = Column(String(50), default="none")  # "none", "per_question", "total"
    time_limit_minutes = Column(Integer, nullable=True)  # Minutes for time limit
    
    # Grading settings
    grading_type = Column(String(50), default="per_question")  # "per_question", "overall"
    exam_rubric_type = Column(String(50), nullable=True)  # "percentage", "letter", None
    exam_rubric = Column(Text, nullable=True)  # JSON string for exam-level rubric
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    teacher = relationship("Teacher", back_populates="exam_templates")
    custom_questions = relationship("CustomQuestion", back_populates="exam_template", cascade="all, delete-orphan")
    exam_accesses = relationship("ExamAccess", back_populates="exam_template", cascade="all, delete-orphan")


class CustomQuestion(Base):
    """Custom question created by teacher."""
    __tablename__ = "custom_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    exam_template_id = Column(Integer, ForeignKey("exam_templates.id"), nullable=False)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    rubric = Column(Text, nullable=False)  # Required for teacher-created questions
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    exam_template = relationship("ExamTemplate", back_populates="custom_questions")


class ExamAccess(Base):
    """Controls who can access an exam template."""
    __tablename__ = "exam_accesses"
    
    id = Column(Integer, primary_key=True, index=True)
    exam_template_id = Column(Integer, ForeignKey("exam_templates.id"), nullable=False)
    student_username = Column(String(100), nullable=False)  # Username of student who can access
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    exam_template = relationship("ExamTemplate", back_populates="exam_accesses")


class Exam(Base):
    """Exam session model."""
    __tablename__ = "exams"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    exam_template_id = Column(Integer, ForeignKey("exam_templates.id"), nullable=True)  # Link to template if teacher-created
    status = Column(String(50), default="in_progress")  # in_progress, completed
    final_grade = Column(Float, nullable=True)
    final_explanation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    student = relationship("Student", back_populates="exams")
    exam_template = relationship("ExamTemplate")
    questions = relationship("Question", back_populates="exam")


class Question(Base):
    """Exam question model."""
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    rubric = Column(Text, nullable=True)
    student_answer = Column(Text, nullable=True)
    grade = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    is_followup = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    exam = relationship("Exam", back_populates="questions")

