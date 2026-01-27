"""Main FastAPI application."""
import logging
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_
from sqlalchemy.orm import joinedload
from datetime import datetime, timezone, timedelta
from app.api.router import api_router
from app.db.base import Base, engine
from app.db.session import get_db
from app.db.models import User, Course, Exam, Student, Enrollment, Question, Notification
from app.db.repo import QuestionRepository, StudentRepository
from app.core.grading.generator import QuestionGenerator
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Import seeding function
from app.db.seed_users import seed_users

# Setup logging
setup_logging()

# Create database tables
Base.metadata.create_all(bind=engine)

# Seed users if they don’t already exist
#seed_users()

# Create FastAPI app
app = FastAPI(
    title="BlueVox",
    description="AI-powered oral exam grading system",
    version="0.1.0"
)

# Include API routes
app.include_router(api_router, prefix="/api")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
env = Environment(loader=FileSystemLoader("app/templates"))


def render_template(template_name: str, context: dict) -> HTMLResponse:
    """Render a Jinja2 template."""
    template = env.get_template(template_name)
    html_content = template.render(**context)
    return HTMLResponse(content=html_content)

@app.get("/student/dashboard", response_class=HTMLResponse)
async def student_dashboard(request: Request, db: Session = Depends(get_db)):
    """Student dashboard page with personalized welcome, courses, and exams."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Use first_name if available, otherwise fallback to "Student"
    first_name = user.first_name if user.first_name else "Student"
    
    # Get or create Student record
    student_record = db.query(Student).filter(Student.username == user.email).first()
    
    # Get student's enrolled courses
    student_courses = []
    if student_record:
        # Get enrollments for this student
        enrollments = db.query(Enrollment).filter(
            Enrollment.student_id == student_record.id
        ).all()
        
        for enrollment in enrollments:
            course = enrollment.course
            if course:  # Course might be deleted
                student_courses.append({
                    "course_number": course.course_number,
                    "section": course.section,
                    "quarter_year": course.quarter_year,
                    "course": course
                })
    
    # Get open exams available to the student (published, not terminated, template exams)
    now = datetime.now(timezone.utc)
    open_exams_query = db.query(Exam).filter(
        Exam.date_published.isnot(None),  # Must be published
        Exam.status != "terminated",  # Not terminated
        Exam.student_id.is_(None)  # Only template exams (instructor-created)
    ).order_by(Exam.date_published.desc())
    
    open_exams = open_exams_query.all()
    
    # Filter out exams student has already completed
    available_open_exams = []
    if student_record:
        for exam in open_exams:
            # Check if student has completed this exam
            completed = db.query(Exam).filter(
                Exam.course_number == exam.course_number,
                Exam.section == exam.section,
                Exam.exam_name == exam.exam_name,
                Exam.quarter_year == exam.quarter_year,
                Exam.student_id == student_record.id,
                Exam.status == "completed"
            ).first()
            
            if not completed:
                # Get student name from exam if it's a student exam
                available_open_exams.append({
                    "exam_id": exam.exam_id,
                    "course_number": exam.course_number,
                    "section": exam.section,
                    "exam_name": exam.exam_name,
                    "quarter_year": exam.quarter_year,
                    "instructor_name": exam.instructor_name,
                    "status": "active" if exam.date_published else "not_started",
                    "date_published": exam.date_published,
                    "date_start": exam.date_start,
                    "date_end": exam.date_end,
                    "is_timed": exam.is_timed,
                    "duration_hours": exam.duration_hours,
                    "duration_minutes": exam.duration_minutes
                })
    else:
        # No student record yet, show all open exams
        for exam in open_exams:
            available_open_exams.append({
                "exam_id": exam.exam_id,
                "course_number": exam.course_number,
                "section": exam.section,
                "exam_name": exam.exam_name,
                "quarter_year": exam.quarter_year,
                "instructor_name": exam.instructor_name,
                "status": "active" if exam.date_published else "not_started",
                "date_published": exam.date_published,
                "date_start": exam.date_start,
                "date_end": exam.date_end,
                "is_timed": exam.is_timed,
                "duration_hours": exam.duration_hours,
                "duration_minutes": exam.duration_minutes
            })
    
    # Get previous exams (completed by student or closed/terminated)
    previous_exams = []
    if student_record:
        # Get all student exams (completed, in_progress on closed exams, etc.)
        student_exams_all = db.query(Exam).filter(
            Exam.student_id == student_record.id
        ).order_by(Exam.completed_at.desc().nulls_last()).all()
        
        # Track which exams we've already added (by exam_id)
        added_exam_ids = set()
        
        for exam in student_exams_all:
            if exam.exam_id not in added_exam_ids:
                added_exam_ids.add(exam.exam_id)
                previous_exams.append({
                    "exam_id": exam.exam_id,
                    "course_number": exam.course_number,
                    "section": exam.section,
                    "exam_name": exam.exam_name,
                    "quarter_year": exam.quarter_year,
                    "instructor_name": exam.instructor_name,
                    "status": exam.status,
                    "final_grade": exam.final_grade,
                    "completed_at": exam.completed_at,
                    "date_published": exam.date_published,
                    "date_start": exam.date_start,
                    "date_end": exam.date_end
                })
        
        # Get closed/terminated template exams that student may have seen but didn't complete
        closed_template_exams = db.query(Exam).filter(
            Exam.date_published.isnot(None),
            or_(
                Exam.status == "terminated",
                and_(Exam.date_end_availability.isnot(None), Exam.date_end_availability < now)
            ),
            Exam.student_id.is_(None)  # Template exams
        ).order_by(Exam.date_end_availability.desc().nulls_last()).all()
        
        # Add closed template exams that student didn't complete (but were available)
        for exam in closed_template_exams:
            # Check if we already added this exam (student completed it)
            template_exam_id = exam.exam_id
            if template_exam_id not in added_exam_ids:
                # Check if student attempted but didn't complete it
                student_attempt = db.query(Exam).filter(
                    Exam.course_number == exam.course_number,
                    Exam.section == exam.section,
                    Exam.exam_name == exam.exam_name,
                    Exam.quarter_year == exam.quarter_year,
                    Exam.student_id == student_record.id
                ).first()
                
                if student_attempt:
                    # Student attempted but didn't complete - add it
                    added_exam_ids.add(template_exam_id)
                    previous_exams.append({
                        "exam_id": template_exam_id,
                        "course_number": exam.course_number,
                        "section": exam.section,
                        "exam_name": exam.exam_name,
                        "quarter_year": exam.quarter_year,
                        "instructor_name": exam.instructor_name,
                        "status": "terminated" if exam.status == "terminated" else "closed",
                        "final_grade": student_attempt.final_grade if student_attempt else None,
                        "completed_at": student_attempt.completed_at if student_attempt else None,
                        "date_published": exam.date_published,
                        "date_start": exam.date_start,
                        "date_end": exam.date_end,
                        "date_end_availability": exam.date_end_availability
                    })
        
        # Sort previous exams by completion date or end availability date
        # Normalize all datetimes to timezone-aware for comparison
        def normalize_datetime(dt):
            if dt is None:
                return datetime.min.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None:
                # Naive datetime, assume UTC
                return dt.replace(tzinfo=timezone.utc)
            return dt
        
        previous_exams.sort(key=lambda x: (
            normalize_datetime(x["completed_at"]),
            normalize_datetime(x.get("date_end_availability"))
        ), reverse=True)
    
    # Get notifications for the user
    from app.services.notification_service import NotificationService
    notification_service = NotificationService()
    notifications = notification_service.get_user_notifications(db, user.id, unread_only=False, limit=10)
    unread_count = notification_service.get_unread_count(db, user.id)
    
    error = request.query_params.get("error", "")
    
    return render_template("student_dashboard.html", {
        "request": request,
        "first_name": first_name,
        "student_courses": student_courses,
        "open_exams": available_open_exams,
        "previous_exams": previous_exams,
        "notifications": notifications,
        "unread_count": unread_count,
        "error": error
    })

@app.get("/student/search-course", response_class=HTMLResponse)
async def student_search_course(
    request: Request,
    course_number: str = None,
    section: str = None,
    db: Session = Depends(get_db)
):
    """Handle course search and redirect to course page."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "student":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get query parameters
    course_number = request.query_params.get("course_number", "").strip().upper()
    section = request.query_params.get("section", "").strip()
    
    if not course_number or not section:
        return RedirectResponse(url="/student/dashboard?error=Please provide both course number and section", status_code=302)
    
    # Verify course exists
    course = db.query(Course).filter(
        Course.course_number == course_number.upper(),
        Course.section == section
    ).first()
    
    if not course:
        return RedirectResponse(url=f"/student/dashboard?error=Course {course_number} Section {section} not found", status_code=302)
    
    # Redirect to student course page
    return RedirectResponse(url=f"/student/course/{course_number}/{section}", status_code=302)

@app.get("/student/course/{course_number}/{section}", response_class=HTMLResponse)
async def student_course_page(
    request: Request,
    course_number: str,
    section: str,
    db: Session = Depends(get_db)
):
    """Display course page with registration option or open exams for students."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "student":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get course from database
    course = db.query(Course).filter(
        Course.course_number == course_number.upper(),
        Course.section == section
    ).first()
    
    if not course:
        return RedirectResponse(url="/student/dashboard?error=course_not_found", status_code=302)
    
    # Get or create Student record for this user
    student_record = db.query(Student).filter(Student.username == user.email).first()
    if not student_record:
        student_record = Student(username=user.email)
        db.add(student_record)
        db.commit()
        db.refresh(student_record)
    
    # Check if student is enrolled in this course
    enrollment = db.query(Enrollment).filter(
        Enrollment.student_id == student_record.id,
        Enrollment.course_id == course.id
    ).first()
    
    is_enrolled = enrollment is not None
    
    # If not enrolled, show registration page
    if not is_enrolled:
        error = request.query_params.get("error", "")
        success = request.query_params.get("success", "")
        return render_template("student_course_page.html", {
            "request": request,
            "course_number": course_number.upper(),
            "section": section,
            "quarter_year": course.quarter_year,
            "course": course,
            "is_enrolled": False,
            "open_exams": [],
            "error": error,
            "success": success
        })
    
    # Student is enrolled - show open exams
    # Query open exams for this course/section (published, not terminated)
    # Only show template exams (instructor-created exams with no student_id)
    open_exams = db.query(Exam).filter(
        Exam.course_number == course_number.upper(),
        Exam.section == section,
        Exam.quarter_year == course.quarter_year,
        Exam.date_published.isnot(None),  # Must be published
        Exam.status != "terminated",  # Not terminated
        Exam.student_id.is_(None)  # Only template exams (not student-specific)
    ).order_by(Exam.date_published.desc()).all()
    
    # Filter out exams that this student has already completed
    available_exams = []
    for exam in open_exams:
        # Check if this student has already taken this exam
        existing_student_exam = db.query(Exam).filter(
            Exam.course_number == exam.course_number,
            Exam.section == exam.section,
            Exam.exam_name == exam.exam_name,
            Exam.quarter_year == exam.quarter_year,
            Exam.student_id == student_record.id,
            Exam.status == "completed"
        ).first()
        
        if not existing_student_exam:
            available_exams.append(exam)
    
    error = request.query_params.get("error", "")
    
    return render_template("student_course_page.html", {
        "request": request,
        "course_number": course_number.upper(),
        "section": section,
        "quarter_year": course.quarter_year,
        "course": course,
        "is_enrolled": True,
        "open_exams": available_exams,
        "error": error
    })

@app.post("/student/course/{course_number}/{section}/register")
async def student_register_course(
    request: Request,
    course_number: str,
    section: str,
    db: Session = Depends(get_db)
):
    """Register student for a course."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "student":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get course from database
    course = db.query(Course).filter(
        Course.course_number == course_number.upper(),
        Course.section == section
    ).first()
    
    if not course:
        return RedirectResponse(url=f"/student/course/{course_number}/{section}?error=course_not_found", status_code=302)
    
    # Get or create Student record for this user
    student_record = db.query(Student).filter(Student.username == user.email).first()
    if not student_record:
        student_record = Student(username=user.email)
        db.add(student_record)
        db.commit()
        db.refresh(student_record)
    
    # Check if already enrolled
    existing_enrollment = db.query(Enrollment).filter(
        Enrollment.student_id == student_record.id,
        Enrollment.course_id == course.id
    ).first()
    
    if existing_enrollment:
        return RedirectResponse(url=f"/student/course/{course_number}/{section}?error=already_enrolled", status_code=302)
    
    # Create enrollment
    try:
        enrollment = Enrollment(
            student_id=student_record.id,
            course_id=course.id
        )
        db.add(enrollment)
        db.commit()
        return RedirectResponse(url=f"/student/course/{course_number}/{section}?success=enrolled", status_code=302)
    except IntegrityError:
        db.rollback()
        return RedirectResponse(url=f"/student/course/{course_number}/{section}?error=enrollment_failed", status_code=302)

@app.get("/student/exam/{exam_id}", response_class=HTMLResponse)
async def student_exam_details_page(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Display exam details page for students with option to start exam."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "student":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database (using exam_id string, not id integer)
    # This gets the template exam (instructor-created exam with no student)
    exam = db.query(Exam).filter(
        Exam.exam_id == exam_id,
        Exam.student_id.is_(None)  # Template exam (no student)
    ).first()
    
    if not exam:
        return RedirectResponse(url="/student/dashboard?error=exam_not_found", status_code=302)
    
    # Verify exam is available (published and not terminated)
    if not exam.date_published or exam.status == "terminated":
        return RedirectResponse(url="/student/dashboard?error=This exam is not available", status_code=302)
    
    # Get or create Student record for this user
    student_record = db.query(Student).filter(Student.username == user.email).first()
    
    # Check if student has already started this exam
    # Look for exam with same course, section, exam_name, quarter, and student
    student_exam = None
    if student_record:
        student_exam = db.query(Exam).filter(
            Exam.course_number == exam.course_number,
            Exam.section == exam.section,
            Exam.exam_name == exam.exam_name,
            Exam.quarter_year == exam.quarter_year,
            Exam.student_id == student_record.id
        ).first()
    
    # Check if student has already completed this exam
    completed_exam = None
    if student_exam and student_exam.status == "completed":
        completed_exam = student_exam
    
    error = request.query_params.get("error", "")
    
    return render_template("student_exam_details.html", {
        "request": request,
        "exam": exam,
        "student_exam": student_exam,
        "completed_exam": completed_exam,
        "error": error
    })

@app.post("/student/exam/{exam_id}/start")
async def student_start_exam(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Start an exam for a student."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "student":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database (template exam - instructor-created with no student)
    exam = db.query(Exam).filter(
        Exam.exam_id == exam_id,
        Exam.student_id.is_(None)  # Template exam (no student)
    ).first()
    
    if not exam:
        return RedirectResponse(url="/student/dashboard?error=exam_not_found", status_code=302)
    
    # Verify exam is available (published and not terminated)
    if not exam.date_published or exam.status == "terminated":
        return RedirectResponse(url=f"/student/exam/{exam_id}?error=This exam is not available", status_code=302)
    
    # Get or create Student record for this user
    student_record = db.query(Student).filter(Student.username == user.email).first()
    if not student_record:
        student_record = Student(username=user.email)
        db.add(student_record)
        db.commit()
        db.refresh(student_record)
    
    # Check if student has already started this exam
    # Look for exam with same course, section, exam_name, quarter, and student
    student_exam = db.query(Exam).filter(
        Exam.course_number == exam.course_number,
        Exam.section == exam.section,
        Exam.exam_name == exam.exam_name,
        Exam.quarter_year == exam.quarter_year,
        Exam.student_id == student_record.id
    ).first()
    
    now = datetime.now(timezone.utc)
    
    if student_exam:
        # Student has already started this exam
        if student_exam.status == "completed":
            return RedirectResponse(url=f"/student/exam/{exam_id}?error=You have already completed this exam", status_code=302)
        
        # Ensure duration values are copied from template (in case they're missing)
        if exam.is_timed and (student_exam.duration_hours is None or student_exam.duration_minutes is None):
            student_exam.duration_hours = exam.duration_hours
            student_exam.duration_minutes = exam.duration_minutes
            db.commit()
        
        # Check if student exam has questions, if not generate them (safety check for incomplete generation)
        student_questions = QuestionRepository.get_by_exam(db, student_exam.id)
        if not student_questions:
            # Generate questions for this student's unique exam
            exam_topic = ""
            num_questions = 5  # Default
            additional_details = ""
            
            if exam.final_explanation:
                lines = exam.final_explanation.split('\n', 1)
                if lines[0].startswith("Topic:"):
                    exam_topic = lines[0].replace("Topic:", "").strip()
                    if len(lines) > 1 and lines[1].startswith("Additional Details:"):
                        additional_details = lines[1].replace("Additional Details:", "").strip()
                else:
                    additional_details = exam.final_explanation
            
            if not exam_topic:
                exam_topic = f"{exam.course_number} - {exam.exam_name}"
            
            template_questions = QuestionRepository.get_by_exam(db, exam.id)
            if template_questions:
                num_questions = len(template_questions)
            
            generator = QuestionGenerator()
            try:
                generated_exam = await generator.generate_exam(
                    topic=exam_topic,
                    num_questions=num_questions,
                    additional_details=additional_details if additional_details else ""
                )
                
                for gen_question in generated_exam.questions:
                    QuestionRepository.create(
                        db=db,
                        exam_id=student_exam.id,
                        question_number=gen_question.question_number,
                        question_text=gen_question.question_text,
                        context=gen_question.context,
                        rubric=gen_question.rubric,
                        is_followup=False
                    )
                db.commit()
            except Exception as e:
                logger.error(f"Error generating questions for existing student exam: {e}")
                return RedirectResponse(url=f"/student/exam/{exam_id}?error=Error generating exam questions: {str(e)}", status_code=302)
        
        # Continue existing exam - redirect to exam taking page
        return RedirectResponse(url=f"/api/exam/{student_exam.id}", status_code=302)
    else:
        # Create new exam session for this student
        # Generate unique exam_id for this student's exam session
        new_exam_id = f"{exam.exam_id}-student-{student_record.id}-{int(now.timestamp())}"
        
        # Create new exam session based on the template exam
        # Simply copy the duration values - timer will calculate end time in JavaScript
        new_student_exam = Exam(
            exam_id=new_exam_id,
            course_number=exam.course_number,
            section=exam.section,
            exam_name=exam.exam_name,
            quarter_year=exam.quarter_year,
            instructor_name=exam.instructor_name,
            instructor_id=exam.instructor_id,
            student_id=student_record.id,
            status="in_progress",
            date_published=exam.date_published,
            is_timed=exam.is_timed,
            duration_hours=exam.duration_hours,  # Simply copy from template
            duration_minutes=exam.duration_minutes,  # Simply copy from template
            final_explanation=exam.final_explanation  # Copy LLM prompt
        )
        
        # Note: We don't calculate date_end here anymore - timer uses duration_hours/minutes directly
        
        try:
            db.add(new_student_exam)
            db.commit()
            db.refresh(new_student_exam)
            
            # Generate questions for this student's unique exam
            # Get topic and number of questions from template exam's metadata
            exam_topic = ""
            num_questions = 5  # Default
            additional_details = ""
            
            if exam.final_explanation:
                # Parse metadata: "Topic: <topic>\n\nAdditional Details: <details>"
                lines = exam.final_explanation.split('\n', 1)
                if lines[0].startswith("Topic:"):
                    exam_topic = lines[0].replace("Topic:", "").strip()
                    if len(lines) > 1 and lines[1].startswith("Additional Details:"):
                        additional_details = lines[1].replace("Additional Details:", "").strip()
                else:
                    # Old format, use as additional details
                    additional_details = exam.final_explanation
            
            # If no topic found, use a default
            if not exam_topic:
                exam_topic = f"{exam.course_number} - {exam.exam_name}"
            
            # Get number of questions from template exam (count existing questions)
            template_questions = QuestionRepository.get_by_exam(db, exam.id)
            if template_questions:
                num_questions = len(template_questions)
            
            # Generate questions using AI
            logger.info(f"Starting question generation for student exam {new_student_exam.id}, topic: {exam_topic}, num_questions: {num_questions}")
            generator = QuestionGenerator()
            try:
                generated_exam = await generator.generate_exam(
                    topic=exam_topic,
                    num_questions=num_questions,
                    additional_details=additional_details if additional_details else ""
                )
                
                logger.info(f"Successfully generated {len(generated_exam.questions)} questions for student exam {new_student_exam.id}")
                
                # Create questions for student's exam
                for gen_question in generated_exam.questions:
                    QuestionRepository.create(
                        db=db,
                        exam_id=new_student_exam.id,
                        question_number=gen_question.question_number,
                        question_text=gen_question.question_text,
                        context=gen_question.context,
                        rubric=gen_question.rubric,
                        is_followup=False
                    )
                db.commit()
                logger.info(f"Successfully saved {len(generated_exam.questions)} questions to database for student exam {new_student_exam.id}")
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Error generating questions for student exam {new_student_exam.id}: {e}\n{error_trace}")
                db.rollback()
                return RedirectResponse(url=f"/student/exam/{exam_id}?error=Error generating exam questions: {str(e)}", status_code=302)
            
            # Redirect to exam taking page
            return RedirectResponse(url=f"/api/exam/{new_student_exam.id}", status_code=302)
        except IntegrityError as e:
            db.rollback()
            # Exam session might already exist, try to find it
            existing = db.query(Exam).filter(
                Exam.course_number == exam.course_number,
                Exam.section == exam.section,
                Exam.exam_name == exam.exam_name,
                Exam.quarter_year == exam.quarter_year,
                Exam.student_id == student_record.id,
                Exam.status != "completed"
            ).first()
            if existing:
                return RedirectResponse(url=f"/api/exam/{existing.id}", status_code=302)
            return RedirectResponse(url=f"/student/exam/{exam_id}?error=Error starting exam: {str(e)}", status_code=302)

@app.get("/teacher/dashboard", response_class=HTMLResponse)
async def teacher_dashboard(request: Request, db: Session = Depends(get_db)):
    """Teacher dashboard page with personalized welcome."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Use first_name if available, otherwise fallback to "Teacher"
    first_name = user.first_name if user.first_name else "Teacher"
    
    # Query courses for this instructor from database
    courses = db.query(Course).filter(Course.instructor_id == user.id).all()
    
    # Query open exams for this instructor (only published exams that students can take, not terminated)
    # Join with Student to get student info, then try to match with User
    open_exams_query = db.query(Exam).outerjoin(
        Student, Exam.student_id == Student.id
    ).filter(
        Exam.instructor_id == user.id,
        Exam.date_published.isnot(None),  # Only published exams
        Exam.status != "terminated"  # Not terminated
    ).order_by(Exam.date_published.desc())  # Show most recent first
    
    # Build exam data with student info
    open_exams = []
    for exam in open_exams_query.all():
        student = None
        user_obj = None
        
        if exam.student_id:
            student = db.query(Student).filter(Student.id == exam.student_id).first()
            if student:
                # Try to find User by email (assuming username might be email)
                user_obj = db.query(User).filter(User.email == student.username).first()
        
        # Calculate percent if final_grade exists
        percent = exam.final_grade * 100 if exam.final_grade else None
        
        # Calculate letter grade
        grade = None
        if percent is not None:
            if percent >= 90:
                grade = "A"
            elif percent >= 80:
                grade = "B"
            elif percent >= 70:
                grade = "C"
            elif percent >= 60:
                grade = "D"
            else:
                grade = "F"
        
        open_exams.append({
            "exam_id": exam.exam_id,
            "student_id": user_obj.student_id if user_obj else (student.username if student else None),
            "first_name": user_obj.first_name if user_obj else None,
            "last_name": user_obj.last_name if user_obj else None,
            "status": exam.status,
            "percent": percent,
            "grade": grade,
            "date_started": exam.created_at if exam.student_id else None,
            "date_completed": exam.completed_at,
            "date_published": exam.date_published
        })
    
    # Query closed exams for this instructor (terminated or completed)
    now = datetime.now(timezone.utc)
    closed_exams_query = db.query(Exam).outerjoin(
        Student, Exam.student_id == Student.id
    ).filter(
        Exam.instructor_id == user.id,
        Exam.date_published.isnot(None),  # Must have been published
        or_(
            Exam.status == "terminated",
            Exam.status == "completed",
            and_(Exam.date_end_availability.isnot(None), Exam.date_end_availability < now)
        )
    ).order_by(Exam.date_end_availability.desc(), Exam.completed_at.desc(), Exam.date_published.desc()).all()  # Show most recently closed first
    
    # Build closed exam data with student info
    closed_exams = []
    for exam in closed_exams_query:
        student = None
        user_obj = None
        
        if exam.student_id:
            student = db.query(Student).filter(Student.id == exam.student_id).first()
            if student:
                # Try to find User by email (assuming username might be email)
                user_obj = db.query(User).filter(User.email == student.username).first()
        
        # Calculate percent if final_grade exists
        percent = exam.final_grade * 100 if exam.final_grade else None
        
        # Calculate letter grade
        grade = None
        if percent is not None:
            if percent >= 90:
                grade = "A"
            elif percent >= 80:
                grade = "B"
            elif percent >= 70:
                grade = "C"
            elif percent >= 60:
                grade = "D"
            else:
                grade = "F"
        
        closed_exams.append({
            "exam_id": exam.exam_id,
            "student_id": user_obj.student_id if user_obj else (student.username if student else None),
            "first_name": user_obj.first_name if user_obj else None,
            "last_name": user_obj.last_name if user_obj else None,
            "status": exam.status,
            "percent": percent,
            "grade": grade,
            "date_started": exam.created_at if exam.student_id else None,
            "date_completed": exam.completed_at,
            "date_published": exam.date_published,
            "date_end_availability": exam.date_end_availability
        })
    
    # Get notifications for the user
    from app.services.notification_service import NotificationService
    notification_service = NotificationService()
    notifications = notification_service.get_user_notifications(db, user.id, unread_only=False, limit=10)
    unread_count = notification_service.get_unread_count(db, user.id)
    
    return render_template("teacher_dashboard.html", {
        "request": request,
        "first_name": first_name,
        "courses": courses,
        "open_exams": open_exams,
        "closed_exams": closed_exams,
        "notifications": notifications,
        "unread_count": unread_count
    })

@app.get("/teacher/register-course", response_class=HTMLResponse)
async def register_course_page(request: Request, db: Session = Depends(get_db)):
    """Display the register new course form."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Generate year options (20-35 for years 2020-2035 in short format)
    year_options = [str(year) for year in range(20, 36)]
    
    error = request.query_params.get("error", "")
    
    return render_template("register_course.html", {
        "request": request,
        "year_options": year_options,
        "error": error
    })

@app.post("/teacher/register-course")
async def register_course(
    request: Request,
    course_number: str = Form(...),
    quarter: str = Form(...),
    year: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle course registration form submission."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get sections from form (as list) - FastAPI form data
    form_data = await request.form()
    sections_raw = form_data.getlist("sections[]")
    # If getlist doesn't work, try getting as single value first
    if not sections_raw:
        # Fallback: check if it's a single value
        single_section = form_data.get("sections[]")
        sections = [single_section] if single_section else []
    else:
        sections = sections_raw
    
    # Validate input
    if not sections or len(sections) == 0:
        return RedirectResponse(url="/teacher/register-course?error=At least one section is required", status_code=302)
    
    # Convert course_number to uppercase
    course_number = course_number.upper().strip()
    
    # Build quarter_year string (e.g., "Spring26")
    quarter_year = f"{quarter}{year}"
    
    # Create a course record for each section
    created_courses = []
    errors = []
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
            
        try:
            # Check if course already exists
            existing = db.query(Course).filter(
                Course.course_number == course_number,
                Course.section == section,
                Course.quarter_year == quarter_year,
                Course.instructor_id == user.id
            ).first()
            
            if existing:
                errors.append(f"Course {course_number} Section {section} for {quarter_year} already exists")
                continue
            
            # Create new course
            course = Course(
                course_number=course_number,
                section=section,
                quarter_year=quarter_year,
                instructor_id=user.id
            )
            db.add(course)
            created_courses.append(course)
            
        except IntegrityError as e:
            db.rollback()
            errors.append(f"Error creating {course_number} Section {section}: {str(e)}")
    
    # Commit all courses
    if created_courses:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            return RedirectResponse(url=f"/teacher/register-course?error=Error saving courses: {str(e)}", status_code=302)
    
    # If there were errors but some courses were created, show success but note errors
    if errors and created_courses:
        # Redirect with success - courses were created despite some errors
        return RedirectResponse(url="/teacher/dashboard?warning=Some courses already existed", status_code=302)
    elif errors and not created_courses:
        # All failed
        error_msg = "; ".join(errors)
        return RedirectResponse(url=f"/teacher/register-course?error={error_msg}", status_code=302)
    
    # Success - redirect to dashboard
    return RedirectResponse(url="/teacher/dashboard?success=course_registered", status_code=302)

@app.get("/teacher/create-exam", response_class=HTMLResponse)
async def create_exam_page(request: Request, db: Session = Depends(get_db)):
    """Display the create new exam form."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get courses for this instructor and group by course_number
    all_courses = db.query(Course).filter(Course.instructor_id == user.id).all()
    
    # Get unique course numbers (to avoid duplicates in dropdown)
    unique_course_numbers = sorted(set(course.course_number for course in all_courses))
    
    # Create a dict mapping course_number to list of courses (for sections and quarters)
    courses_by_number = {}
    for course in all_courses:
        if course.course_number not in courses_by_number:
            courses_by_number[course.course_number] = []
        courses_by_number[course.course_number].append(course)
    
    error = request.query_params.get("error", "")
    
    return render_template("create_exam.html", {
        "request": request,
        "all_courses": all_courses,  # Full list for JavaScript
        "unique_course_numbers": unique_course_numbers,  # For dropdown
        "courses_by_number": courses_by_number,  # For grouping
        "error": error
    })

@app.post("/teacher/create-exam")
async def create_exam(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle exam creation form submission."""
    try:
        # Get form data manually to handle missing fields gracefully
        form_data = await request.form()
        
        # Get email from cookie
        email = request.cookies.get("username")
        if not email:
            return RedirectResponse(url="/?error=login_required", status_code=302)
        
        # Get user from database
        user = db.query(User).filter(User.email == email).first()
        if not user or user.role != "teacher":
            return RedirectResponse(url="/?error=login_required", status_code=302)
        
        # Extract form fields with error handling
        course_number = form_data.get("course_number", "").strip()
        quarter_year = form_data.get("quarter_year", "").strip()
        exam_name = form_data.get("exam_name", "").strip()
        exam_topic = form_data.get("exam_topic", "").strip()
        num_questions_str = form_data.get("num_questions", "").strip()
        llm_prompt = form_data.get("llm_prompt", "").strip()  # Additional details (optional)
        
        # Extract timed exam fields
        is_timed = form_data.get("is_timed", "no") == "yes"
        duration_hours = None
        duration_minutes = None
        
        if is_timed:
            try:
                duration_hours = int(form_data.get("duration_hours", 0))
                duration_minutes = int(form_data.get("duration_minutes", 0))
                # Validate duration is greater than 0
                if duration_hours == 0 and duration_minutes == 0:
                    return RedirectResponse(url="/teacher/create-exam?error=Duration must be greater than 0 for timed exams", status_code=302)
            except (ValueError, TypeError):
                return RedirectResponse(url="/teacher/create-exam?error=Invalid duration values", status_code=302)
        
        # Validate required fields
        if not course_number:
            return RedirectResponse(url="/teacher/create-exam?error=Course number is required", status_code=302)
        if not quarter_year:
            return RedirectResponse(url="/teacher/create-exam?error=Quarter/Year is required", status_code=302)
        if not exam_name:
            return RedirectResponse(url="/teacher/create-exam?error=Exam name is required", status_code=302)
        if not exam_topic:
            return RedirectResponse(url="/teacher/create-exam?error=Exam topic is required", status_code=302)
        if not num_questions_str:
            return RedirectResponse(url="/teacher/create-exam?error=Number of questions is required", status_code=302)
        
        # Validate and parse number of questions
        try:
            num_questions = int(num_questions_str)
            if num_questions < 1 or num_questions > 30:
                return RedirectResponse(url="/teacher/create-exam?error=Number of questions must be between 1 and 30", status_code=302)
        except (ValueError, TypeError):
            return RedirectResponse(url="/teacher/create-exam?error=Invalid number of questions", status_code=302)
        
        # Get sections from form (as list from checkboxes)
        sections_raw = form_data.getlist("sections[]")
        if not sections_raw:
            single_section = form_data.get("sections[]")
            sections = [single_section] if single_section else []
        else:
            sections = sections_raw
        
        # Validate input
        if not sections or len(sections) == 0:
            return RedirectResponse(url="/teacher/create-exam?error=At least one section must be selected", status_code=302)
        
        # Remove duplicates and empty strings
        sections = list(set([s.strip() for s in sections if s and s.strip()]))
        if not sections:
            return RedirectResponse(url="/teacher/create-exam?error=At least one section must be selected", status_code=302)
        
        # Validate that all sections belong to the same course and quarter/year
        courses_for_sections = db.query(Course).filter(
            Course.course_number == course_number.upper(),
            Course.section.in_(sections),
            Course.instructor_id == user.id
        ).all()
        
        # Check that all sections exist and match the quarter/year
        valid_sections = []
        validation_errors = []
        for section in sections:
            matching_course = next((c for c in courses_for_sections if c.section == section), None)
            if not matching_course:
                validation_errors.append(f"Section {section} not found for course {course_number}")
                continue
            if matching_course.quarter_year != quarter_year:
                validation_errors.append(f"Section {section} is for {matching_course.quarter_year}, not {quarter_year}")
                continue
            valid_sections.append(section)
        
        if not valid_sections:
            error_msg = "; ".join(validation_errors) if validation_errors else "No valid sections selected"
            return RedirectResponse(url=f"/teacher/create-exam?error={error_msg}", status_code=302)
        
        # Use only valid sections
        sections = valid_sections
        
        # Get instructor name
        instructor_name = f"{user.first_name} {user.last_name}"
        
        # Generate exam questions using AI
        generator = QuestionGenerator()
        try:
            generated_exam = await generator.generate_exam(
                topic=exam_topic,
                num_questions=num_questions,
                additional_details=llm_prompt if llm_prompt else ""
            )
        except Exception as e:
            import traceback
            error_details = str(e)
            error_trace = traceback.format_exc()
            logger.error(f"Error generating exam questions: {error_details}")
            logger.error(f"Traceback: {error_trace}")
            # Truncate error message if too long for URL
            if len(error_details) > 200:
                error_details = error_details[:200] + "..."
            return RedirectResponse(url=f"/teacher/create-exam?error=Error generating exam questions: {error_details}", status_code=302)
        
        # Create an exam for each selected section
        created_exams = []
        errors = []
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            # Verify the course belongs to this instructor
            course = db.query(Course).filter(
                Course.course_number == course_number.upper(),
                Course.section == section,
                Course.quarter_year == quarter_year,
                Course.instructor_id == user.id
            ).first()
            
            if not course:
                errors.append(f"Course {course_number} Section {section} for {quarter_year} not found or access denied")
                continue
            
            # Generate exam_id: course_number-section-exam_name-quarter_year
            exam_id = f"{course_number.upper()}-{section}-{exam_name.lower().replace(' ', '-')}-{quarter_year}"
            
            # Check if exam with this ID already exists
            existing_exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
            if existing_exam:
                if existing_exam.status != "terminated":
                    # Active exam exists, cannot create duplicate
                    errors.append(f"Exam '{exam_name}' for Section {section} already exists")
                    continue
                else:
                    # Terminated exam exists, rename it to make room for new exam
                    # Add timestamp suffix to terminated exam's ID
                    timestamp_suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                    existing_exam.exam_id = f"{existing_exam.exam_id}-terminated-{timestamp_suffix}"
                    try:
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        errors.append(f"Error updating terminated exam for Section {section}: {str(e)}")
                        continue
            
            # Create new exam (not published yet, status = "not_started")
            # Store topic and additional details in final_explanation in a structured format
            # Format: "Topic: <topic>\n\nAdditional Details: <details>"
            exam_metadata = f"Topic: {exam_topic}"
            if llm_prompt:
                exam_metadata += f"\n\nAdditional Details: {llm_prompt}"
            
            exam = Exam(
                exam_id=exam_id,
                course_number=course_number.upper(),
                section=section,
                exam_name=exam_name,
                quarter_year=quarter_year,
                instructor_name=instructor_name,
                instructor_id=user.id,
                status="not_started",  # Not yet published
                # Store topic and additional details in final_explanation field
                final_explanation=exam_metadata,
                # Timed exam fields
                is_timed=is_timed,
                duration_hours=duration_hours if is_timed else None,
                duration_minutes=duration_minutes if is_timed else None,
                # student_id is None for teacher-created exam templates (students will be assigned when they start)
                student_id=None
            )
            
            try:
                db.add(exam)
                created_exams.append(exam)
            except IntegrityError as e:
                errors.append(f"Error creating exam for Section {section}: {str(e)}")
        
        # Commit all exams at once
        if created_exams:
            try:
                db.commit()
                # Refresh all created exams
                for exam in created_exams:
                    db.refresh(exam)
                
                # Create questions for all exams (they all share the same questions)
                for exam in created_exams:
                    for gen_question in generated_exam.questions:
                        QuestionRepository.create(
                            db=db,
                            exam_id=exam.id,
                            question_number=gen_question.question_number,
                            question_text=gen_question.question_text,
                            context=gen_question.context,
                            rubric=gen_question.rubric,
                            is_followup=False
                        )
                
                db.commit()
            except Exception as e:
                db.rollback()
                return RedirectResponse(url=f"/teacher/create-exam?error=Error saving exams: {str(e)}", status_code=302)
        
        # Handle results
        if errors and not created_exams:
            # All failed
            error_msg = "; ".join(errors)
            return RedirectResponse(url=f"/teacher/create-exam?error={error_msg}", status_code=302)
        elif errors and created_exams:
            # Some succeeded, some failed
            return RedirectResponse(url=f"/teacher/dashboard?warning=Some exams created successfully. Issues: {'; '.join(errors)}", status_code=302)
        
        # Success - redirect to review page for the first exam
        # If multiple exams created, they all have the same LLM prompt, so review one to update all
        if len(created_exams) >= 1:
            # Redirect to review page for the first exam
            exam = created_exams[0]
            return RedirectResponse(url=f"/teacher/exam/{exam.exam_id}/review", status_code=302)
        else:
            # This shouldn't happen, but redirect to dashboard
            return RedirectResponse(url=f"/teacher/dashboard?error=No exams created", status_code=302)
            
    except Exception as e:
        # Catch any unexpected errors
        import traceback
        error_details = str(e)
        print(f"Error in create_exam: {error_details}")
        print(traceback.format_exc())
        return RedirectResponse(url=f"/teacher/create-exam?error=Unexpected error: {error_details}", status_code=302)

@app.get("/teacher/course/{course_number}/{section}", response_class=HTMLResponse)
async def course_page(
    request: Request,
    course_number: str,
    section: str,
    db: Session = Depends(get_db)
):
    """Display course page with exams."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get course from database (verify it belongs to this instructor)
    course = db.query(Course).filter(
        Course.course_number == course_number.upper(),
        Course.section == section,
        Course.instructor_id == user.id
    ).first()
    
    if not course:
        return RedirectResponse(url="/teacher/dashboard?error=course_not_found", status_code=302)
    
    # Query open exams for this course/section (published, not completed, not terminated)
    open_exams = db.query(Exam).filter(
        Exam.course_number == course_number.upper(),
        Exam.section == section,
        Exam.quarter_year == course.quarter_year,
        Exam.date_published.isnot(None),  # Must be published
        Exam.status != "completed",  # Not completed
        Exam.status != "terminated"  # Not terminated
    ).order_by(Exam.date_published.desc()).all()
    
    # Query closed exams for this course/section (completed, terminated, or past end date)
    now = datetime.now(timezone.utc)
    closed_exams = db.query(Exam).filter(
        Exam.course_number == course_number.upper(),
        Exam.section == section,
        Exam.quarter_year == course.quarter_year,
        or_(
            Exam.status == "completed",
            Exam.status == "terminated",
            and_(Exam.date_end_availability.isnot(None), Exam.date_end_availability < now)
        )
    ).order_by(Exam.date_end_availability.desc()).all()
    
    return render_template("course_page.html", {
        "request": request,
        "course_number": course_number.upper(),
        "section": section,
        "quarter_year": course.quarter_year,
        "open_exams": open_exams,
        "closed_exams": closed_exams
    })

@app.get("/teacher/exam/{exam_id}/review", response_class=HTMLResponse)
async def exam_review_page(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Display exam review page where instructor can edit and publish."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database (using exam_id string, not id integer)
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    
    if not exam:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Verify exam belongs to this instructor
    if exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=access_denied", status_code=302)
    
    # Get all exams with the same course_number, exam_name, and quarter_year (in case multiple sections)
    related_exams = db.query(Exam).filter(
        Exam.instructor_id == user.id,
        Exam.course_number == exam.course_number,
        Exam.exam_name == exam.exam_name,
        Exam.quarter_year == exam.quarter_year,
        Exam.date_published.is_(None)  # Only unpublished
    ).order_by(Exam.section).all()
    
    # Create combined exam_id with all sections
    sections_list = sorted([e.section for e in related_exams])
    sections_str = '-'.join(sections_list)
    combined_exam_id = f"{exam.course_number}-{sections_str}-{exam.exam_name.lower().replace(' ', '-')}-{exam.quarter_year}"
    
    # Get questions for this exam
    questions = QuestionRepository.get_by_exam(db, exam.id)
    questions = sorted(questions, key=lambda q: q.question_number)
    
    # Extract topic and additional details from final_explanation
    # Format: "Topic: <topic>\n\nAdditional Details: <details>" or just topic
    exam_topic = ""
    additional_details = ""
    if exam.final_explanation:
        # Try to parse topic and details
        lines = exam.final_explanation.split('\n', 1)
        if lines[0].startswith("Topic:"):
            exam_topic = lines[0].replace("Topic:", "").strip()
            if len(lines) > 1 and lines[1].startswith("Additional Details:"):
                additional_details = lines[1].replace("Additional Details:", "").strip()
        else:
            # Old format, just use as additional details
            additional_details = exam.final_explanation
    
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
    
    return render_template("exam_review.html", {
        "request": request,
        "exam": exam,
        "related_exams": related_exams,
        "combined_exam_id": combined_exam_id,
        "sections_list": sections_list,
        "questions": questions,
        "exam_topic": exam_topic,
        "additional_details": additional_details,
        "error": error,
        "success": success
    })

@app.post("/teacher/exam/{exam_id}/update")
async def update_exam(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Update exam LLM prompt/criteria."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam or exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Get form data
    form_data = await request.form()
    llm_prompt = form_data.get("llm_prompt", "").strip()
    
    if not llm_prompt:
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=LLM prompt cannot be empty", status_code=302)
    
    # Update this exam and all related unpublished exams with the same criteria
    related_exams = db.query(Exam).filter(
        Exam.instructor_id == user.id,
        Exam.course_number == exam.course_number,
        Exam.exam_name == exam.exam_name,
        Exam.quarter_year == exam.quarter_year,
        Exam.date_published.is_(None)  # Only unpublished
    ).all()
    
    for related_exam in related_exams:
        related_exam.final_explanation = llm_prompt
    
    try:
        db.commit()
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?success=Exam criteria updated", status_code=302)
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Error updating exam: {str(e)}", status_code=302)

@app.post("/teacher/exam/{exam_id}/regenerate")
async def regenerate_exam_questions(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Regenerate exam questions using AI."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam or exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Don't allow regeneration if exam is published
    if exam.date_published:
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Cannot regenerate questions for published exam", status_code=302)
    
    # Get form data
    form_data = await request.form()
    exam_topic = form_data.get("exam_topic", "").strip()
    num_questions_str = form_data.get("num_questions", "").strip()
    additional_details = form_data.get("additional_details", "").strip()
    
    # Validate
    if not exam_topic:
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Topic is required", status_code=302)
    if not num_questions_str:
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Number of questions is required", status_code=302)
    
    try:
        num_questions = int(num_questions_str)
        if num_questions < 1 or num_questions > 30:
            return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Number of questions must be between 1 and 30", status_code=302)
    except (ValueError, TypeError):
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Invalid number of questions", status_code=302)
    
    # Get all related exams (same course, exam name, quarter) that are unpublished
    related_exams = db.query(Exam).filter(
        Exam.instructor_id == user.id,
        Exam.course_number == exam.course_number,
        Exam.exam_name == exam.exam_name,
        Exam.quarter_year == exam.quarter_year,
        Exam.date_published.is_(None)  # Only unpublished
    ).all()
    
    # Generate new questions
    generator = QuestionGenerator()
    try:
        generated_exam = await generator.generate_exam(
            topic=exam_topic,
            num_questions=num_questions,
            additional_details=additional_details if additional_details else ""
        )
    except Exception as e:
        import traceback
        error_details = str(e)
        print(f"Error regenerating exam questions: {error_details}")
        print(traceback.format_exc())
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Error generating exam questions: {error_details}", status_code=302)
    
    # Delete existing questions and create new ones for all related exams
    try:
        for related_exam in related_exams:
            # Delete existing questions
            existing_questions = QuestionRepository.get_by_exam(db, related_exam.id)
            for question in existing_questions:
                db.delete(question)
            
            # Create new questions
            for gen_question in generated_exam.questions:
                QuestionRepository.create(
                    db=db,
                    exam_id=related_exam.id,
                    question_number=gen_question.question_number,
                    question_text=gen_question.question_text,
                    context=gen_question.context,
                    rubric=gen_question.rubric,
                    is_followup=False
                )
        
        # Update exam metadata
        exam_metadata = f"Topic: {exam_topic}"
        if additional_details:
            exam_metadata += f"\n\nAdditional Details: {additional_details}"
        
        for related_exam in related_exams:
            related_exam.final_explanation = exam_metadata
        
        db.commit()
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?success=Exam questions regenerated successfully", status_code=302)
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Error regenerating questions: {str(e)}", status_code=302)

@app.post("/teacher/exam/{exam_id}/publish")
async def publish_exam(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Publish exam so it appears in open exams and is available to students."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam or exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Get all related exams (same course, exam name, quarter) that are unpublished
    related_exams = db.query(Exam).filter(
        Exam.instructor_id == user.id,
        Exam.course_number == exam.course_number,
        Exam.exam_name == exam.exam_name,
        Exam.quarter_year == exam.quarter_year,
        Exam.date_published.is_(None)  # Only unpublished
    ).all()
    
    # Publish all related exams at once
    now = datetime.now(timezone.utc)
    for related_exam in related_exams:
        related_exam.date_published = now
        related_exam.status = "active"  # Change from "not_started" to "active"
    
    try:
        db.commit()
        
        # Create notifications for enrolled students
        from app.services.notification_service import NotificationService
        notification_service = NotificationService()
        
        # Find the course for this exam
        course = db.query(Course).filter(
            Course.course_number == exam.course_number,
            Course.section == exam.section,
            Course.quarter_year == exam.quarter_year,
            Course.instructor_id == user.id
        ).first()
        
        if course:
            # Get all enrolled students
            enrollments = db.query(Enrollment).filter(Enrollment.course_id == course.id).all()
            for enrollment in enrollments:
                # Get student's user record
                student_user = db.query(User).filter(User.email == enrollment.student.username).first()
                if student_user:
                    notification_service.create_notification(
                        db=db,
                        user_id=student_user.id,
                        notification_type="exam_available",
                        title=f"New Exam Available: {exam.exam_name}",
                        message=f"A new exam '{exam.exam_name}' is now available for {exam.course_number} - Section {exam.section}.",
                        related_exam_id=exam.id,
                        related_course_id=course.id
                    )
        
        return RedirectResponse(url=f"/teacher/dashboard?success=Exam published successfully", status_code=302)
    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"/teacher/exam/{exam_id}/review?error=Error publishing exam: {str(e)}", status_code=302)

@app.get("/teacher/exam/{exam_id}", response_class=HTMLResponse)
async def exam_details_page(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Display exam details page."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database (using exam_id string, not id integer)
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    
    if not exam:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Verify exam belongs to this instructor
    if exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=access_denied", status_code=302)
    
    # Check if this is a student exam (has student_id)
    is_student_exam = exam.student_id is not None
    questions = []
    student = None
    
    if is_student_exam:
        # Get all questions and answers for this student's exam
        questions = QuestionRepository.get_by_exam(db, exam.id)
        questions = sorted(questions, key=lambda q: q.question_number)
        
        # Get student information
        student = db.query(Student).filter(Student.id == exam.student_id).first()
    
    return render_template("exam_details.html", {
        "request": request,
        "exam": exam,
        "is_student_exam": is_student_exam,
        "questions": questions,
        "student": student
    })

@app.post("/teacher/exam/{exam_id}/terminate")
async def terminate_exam(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Terminate exam so it's no longer available to students."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam or exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Get all related exams (same course, exam name, quarter) that are not terminated
    related_exams = db.query(Exam).filter(
        Exam.instructor_id == user.id,
        Exam.course_number == exam.course_number,
        Exam.exam_name == exam.exam_name,
        Exam.quarter_year == exam.quarter_year,
        Exam.status != "terminated"  # Only not yet terminated
    ).all()
    
    # Terminate all related exams at once
    now = datetime.now(timezone.utc)
    for related_exam in related_exams:
        related_exam.status = "terminated"
        related_exam.date_end_availability = now  # Set end availability to now
    
    try:
        db.commit()
        return RedirectResponse(url=f"/teacher/dashboard?success=Exam terminated successfully", status_code=302)
    except Exception as e:
        db.rollback()
        logger.error(f"Error terminating exam: {e}")
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?error=Failed to terminate exam", status_code=302)


@app.post("/teacher/exam/{exam_id}/alter-grades")
async def alter_grades(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Submit grade alterations for disputed exam - shows confirmation page."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam or exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Only allow for disputed or completed exams
    if exam.status not in ["disputed", "completed"]:
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?error=Can only alter grades for disputed or completed exams", status_code=302)
    
    # Get form data
    form_data = await request.form()
    
    # Get all questions for this exam
    questions = QuestionRepository.get_by_exam(db, exam.id)
    questions = sorted(questions, key=lambda q: q.question_number)
    
    # Store original and new grades for confirmation
    grade_changes = []
    original_final_grade = exam.final_grade * 100 if exam.final_grade else None
    
    # Check for question grade changes
    for question in questions:
        grade_key = f"question_grade_{question.id}"
        new_grade_str = form_data.get(grade_key, "").strip()
        
        original_grade = question.grade * 100 if question.grade is not None else None
        
        if new_grade_str:
            try:
                new_grade = float(new_grade_str)
                if new_grade != original_grade:
                    grade_changes.append({
                        "question": question,
                        "original_grade": original_grade,
                        "new_grade": new_grade
                    })
            except ValueError:
                pass
    
    # Check for final grade change
    final_grade_str = form_data.get("final_grade", "").strip()
    new_final_grade = None
    if final_grade_str:
        try:
            new_final_grade = float(final_grade_str)
        except ValueError:
            pass
    
    # Get grade change reason
    grade_change_reason = form_data.get("grade_change_reason", "").strip()
    
    # Store form data for confirmation page (convert to dict for template)
    form_data_dict = dict(form_data)
    
    return render_template("confirm_alter_grades.html", {
        "request": request,
        "exam": exam,
        "questions": questions,
        "grade_changes": grade_changes,
        "original_final_grade": original_final_grade,
        "new_final_grade": new_final_grade,
        "grade_change_reason": grade_change_reason,
        "form_data": form_data_dict
    })


@app.post("/teacher/exam/{exam_id}/confirm-alter")
async def confirm_alter_grades(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Apply confirmed grade alterations."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam or exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Only allow for disputed or completed exams
    if exam.status not in ["disputed", "completed"]:
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?error=Can only alter grades for disputed or completed exams", status_code=302)
    
    # Get form data
    form_data = await request.form()
    
    # Store original final grade for notification
    original_final_grade = exam.final_grade
    
    # Update question grades
    questions = QuestionRepository.get_by_exam(db, exam.id)
    for question in questions:
        grade_key = f"question_grade_{question.id}"
        new_grade_str = form_data.get(grade_key, "").strip()
        
        if new_grade_str:
            try:
                new_grade_percent = float(new_grade_str)
                new_grade_decimal = new_grade_percent / 100.0  # Convert to 0.0-1.0
                
                # Update question grade (keep existing feedback)
                question.grade = new_grade_decimal
            except ValueError:
                pass
    
    # Update final grade
    final_grade_str = form_data.get("final_grade", "").strip()
    if final_grade_str:
        try:
            new_final_grade_percent = float(final_grade_str)
            exam.final_grade = new_final_grade_percent / 100.0  # Convert to 0.0-1.0
        except ValueError:
            pass
    else:
        # Recalculate final grade from question grades
        grades = [q.grade for q in questions if q.grade is not None]
        if grades:
            avg_grade = sum(grades) / len(grades)
            exam.final_grade = avg_grade  # Already in 0.0-1.0 format
    
    # Store grade change reason and instructor
    grade_change_reason = form_data.get("grade_change_reason", "").strip()
    if grade_change_reason:
        exam.grade_change_reason = grade_change_reason
    exam.grade_changed_by = user.id
    
    # Change status from disputed back to completed (if it was disputed)
    if exam.status == "disputed":
        exam.status = "completed"
    
    # Notify student if this is a student exam
    if exam.student_id:
        student = db.query(Student).filter(Student.id == exam.student_id).first()
        if student:
            # Find the student's User account
            student_user = db.query(User).filter(User.email == student.username).first()
            if student_user:
                from app.services.notification_service import NotificationService
                notification_service = NotificationService()
                
                # Build notification message
                old_grade_str = f"{original_final_grade * 100:.1f}%" if original_final_grade else "N/A"
                new_grade_str = f"{exam.final_grade * 100:.1f}%" if exam.final_grade else "N/A"
                instructor_name = user.first_name + " " + user.last_name if (user.first_name or user.last_name) else user.email
                
                message = f"Your grade for {exam.exam_name} ({exam.course_number}-{exam.section}) has been changed from {old_grade_str} to {new_grade_str} by {instructor_name}."
                if grade_change_reason:
                    message += f"\n\nReason: {grade_change_reason}"
                
                notification_service.create_notification(
                    db=db,
                    user_id=student_user.id,
                    notification_type="grade_changed",
                    title=f"Grade Changed: {exam.exam_name}",
                    message=message,
                    related_exam_id=exam.id
                )
    
    try:
        db.commit()
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?success=Grades updated successfully. Student has been notified.", status_code=302)
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating grades: {e}")
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?error=Failed to update grades", status_code=302)


@app.post("/teacher/exam/{exam_id}/reopen")
async def reopen_exam(
    request: Request,
    exam_id: str,
    db: Session = Depends(get_db)
):
    """Reopen a disputed exam for the student to retake."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get exam from database
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam or exam.instructor_id != user.id:
        return RedirectResponse(url="/teacher/dashboard?error=exam_not_found", status_code=302)
    
    # Only allow for disputed exams
    if exam.status != "disputed":
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?error=Can only reopen disputed exams", status_code=302)
    
    # Change status from disputed to active (open)
    exam.status = "active"
    # Clear dispute reason
    exam.dispute_reason = None
    
    try:
        db.commit()
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?success=Exam reopened successfully. Student can now retake the exam.", status_code=302)
    except Exception as e:
        db.rollback()
        logger.error(f"Error reopening exam: {e}")
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?error=Failed to reopen exam", status_code=302)

@app.get("/teacher/manage-students", response_class=HTMLResponse)
async def manage_students_page(request: Request, db: Session = Depends(get_db)):
    """Display the manage students page."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get all courses for this instructor with enrollments loaded
    courses = db.query(Course).options(joinedload(Course.enrollments).joinedload(Enrollment.student)).filter(Course.instructor_id == user.id).all()
    
    # Get all users for name lookup
    all_users = db.query(User).all()
    
    return render_template("manage_students.html", {
        "request": request,
        "courses": courses,
        "all_users": all_users
    })

@app.post("/teacher/manage-students/add-to-course")
async def add_student_to_course(
    request: Request,
    db: Session = Depends(get_db),
    student_email: str = Form(...),
    course_id: int = Form(...)
):
    """Add a student to a course."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Verify course belongs to instructor
    course = db.query(Course).filter(Course.id == course_id, Course.instructor_id == user.id).first()
    if not course:
        return RedirectResponse(url="/teacher/manage-students?error=Course not found or access denied", status_code=302)
    
    # Verify student user exists
    student_user = db.query(User).filter(User.email == student_email, User.role == "student").first()
    if not student_user:
        return RedirectResponse(url=f"/teacher/manage-students?error=Student with email {student_email} not found", status_code=302)
    
    # Get or create Student record
    student_record = StudentRepository.get_or_create(db, student_email)
    
    # Check if enrollment already exists
    existing_enrollment = db.query(Enrollment).filter(
        Enrollment.student_id == student_record.id,
        Enrollment.course_id == course_id
    ).first()
    
    if existing_enrollment:
        return RedirectResponse(url=f"/teacher/manage-students?error=Student is already enrolled in this course", status_code=302)
    
    # Create enrollment
    try:
        enrollment = Enrollment(
            student_id=student_record.id,
            course_id=course_id
        )
        db.add(enrollment)
        db.commit()
        return RedirectResponse(url=f"/teacher/manage-students?success=Student {student_email} added to {course.course_number} - Section {course.section}", status_code=302)
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error adding student to course: {e}")
        return RedirectResponse(url=f"/teacher/manage-students?error=Failed to add student to course", status_code=302)

@app.post("/teacher/manage-students/remove-from-course")
async def remove_student_from_course(
    request: Request,
    db: Session = Depends(get_db),
    enrollment_id: int = Form(...)
):
    """Remove a student from a course."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get enrollment and verify course belongs to instructor
    enrollment = db.query(Enrollment).join(Course).filter(
        Enrollment.id == enrollment_id,
        Course.instructor_id == user.id
    ).first()
    
    if not enrollment:
        return RedirectResponse(url="/teacher/manage-students?error=Enrollment not found or access denied", status_code=302)
    
    try:
        student_email = enrollment.student.username
        course_info = f"{enrollment.course.course_number} - Section {enrollment.course.section}"
        db.delete(enrollment)
        db.commit()
        return RedirectResponse(url=f"/teacher/manage-students?success=Student {student_email} removed from {course_info}", status_code=302)
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing student from course: {e}")
        return RedirectResponse(url=f"/teacher/manage-students?error=Failed to remove student from course", status_code=302)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root page - role selection."""
    return render_template("login_selection.html", {"request": request})

@app.get("/student/login", response_class=HTMLResponse)
async def student_login_page(request: Request):
    """Student login page."""
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
    return render_template("login.html", {"request": request, "error": error, "success": success})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Signup page - create new account."""
    error = request.query_params.get("error", "")
    return render_template("signup.html", {"request": request, "error": error})

@app.get("/teacher/login", response_class=HTMLResponse)
async def teacher_login_page(request: Request):
    """Teacher login page."""
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
    return render_template("teacher_login.html", {"request": request, "error": error, "success": success})


@app.get("/teacher/exams", response_class=HTMLResponse)
async def teacher_exams_page(request: Request, db: Session = Depends(get_db)):
    """Display all exams page."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get filter parameter
    filter_type = request.query_params.get("filter", "all")
    
    # Query exams for this instructor
    exams_query = db.query(Exam).filter(Exam.instructor_id == user.id)
    
    if filter_type == "open":
        exams_query = exams_query.filter(
            Exam.date_published.isnot(None),
            Exam.status != "terminated",
            Exam.status != "completed"
        )
    elif filter_type == "closed":
        exams_query = exams_query.filter(
            or_(Exam.status == "terminated", Exam.status == "completed")
        )
    
    exams = exams_query.order_by(Exam.created_at.desc()).all()
    
    # Build exam data
    exam_list = []
    for exam in exams:
        student = None
        if exam.student_id:
            student = db.query(Student).filter(Student.id == exam.student_id).first()
        
        exam_list.append({
            "exam_id": exam.exam_id,
            "exam_name": exam.exam_name,
            "course_number": exam.course_number,
            "section": exam.section,
            "quarter_year": exam.quarter_year,
            "status": exam.status,
            "date_published": exam.date_published,
            "date_start": exam.date_start,
            "date_end": exam.date_end,
            "final_grade": exam.final_grade,
            "student": student.username if student else None
        })
    
    return render_template("teacher_exams.html", {
        "request": request,
        "exams": exam_list,
        "filter_type": filter_type
    })

@app.get("/teacher/analytics", response_class=HTMLResponse)
async def teacher_analytics_page(request: Request, db: Session = Depends(get_db)):
    """Display analytics page."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get statistics
    total_exams = db.query(Exam).filter(Exam.instructor_id == user.id).count()
    total_courses = db.query(Course).filter(Course.instructor_id == user.id).count()
    total_students = db.query(Enrollment).join(Course).filter(Course.instructor_id == user.id).distinct(Enrollment.student_id).count()
    
    completed_exams = db.query(Exam).filter(
        Exam.instructor_id == user.id,
        Exam.status == "completed"
    ).count()
    
    return render_template("teacher_analytics.html", {
        "request": request,
        "total_exams": total_exams,
        "total_courses": total_courses,
        "total_students": total_students,
        "completed_exams": completed_exams
    })

@app.get("/teacher/settings", response_class=HTMLResponse)
async def teacher_settings_page(request: Request, db: Session = Depends(get_db)):
    """Display settings page."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    return render_template("teacher_settings.html", {
        "request": request,
        "user": user
    })

@app.get("/teacher/notifications", response_class=HTMLResponse)
async def teacher_notifications_page(request: Request, db: Session = Depends(get_db)):
    """Display all notifications page."""
    # Get email from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get user from database
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "teacher":
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    # Get all notifications
    notifications = db.query(Notification).filter(
        Notification.user_id == user.id
    ).order_by(Notification.created_at.desc()).all()
    
    unread_count = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.is_read == False
    ).count()
    
    return render_template("teacher_notifications.html", {
        "request": request,
        "notifications": notifications,
        "unread_count": unread_count
    })

@app.get("/question/{question_id}", response_class=HTMLResponse)
async def question_page(request: Request, question_id: int):
    """Dummy question page for testing login."""
    # You can later render question.html template here
    return render_template("question.html", {"request": request, "question_id": question_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)