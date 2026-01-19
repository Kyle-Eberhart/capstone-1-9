"""Main FastAPI application."""
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_
from datetime import datetime, timezone
from app.api.router import api_router
from app.db.base import Base, engine
from app.db.session import get_db
from app.db.models import User, Course, Exam, Student
from app.logging_config import setup_logging

# Import seeding function
from app.db.seed_users import seed_users

# Setup logging
setup_logging()

# Create database tables
Base.metadata.create_all(bind=engine)

# Seed users if they don’t already exist
seed_users()

# Create FastAPI app
app = FastAPI(
    title="AI Oral Exam Grader",
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
    """Student dashboard page with personalized welcome."""
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
    
    return render_template("student_dashboard.html", {
        "request": request,
        "first_name": first_name
    })

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
    
    return render_template("teacher_dashboard.html", {
        "request": request,
        "first_name": first_name,
        "courses": courses,
        "open_exams": open_exams,
        "closed_exams": closed_exams
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
        llm_prompt = form_data.get("llm_prompt", "").strip()
        
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
        if not llm_prompt:
            return RedirectResponse(url="/teacher/create-exam?error=LLM prompt is required", status_code=302)
        
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
            exam = Exam(
                exam_id=exam_id,
                course_number=course_number.upper(),
                section=section,
                exam_name=exam_name,
                quarter_year=quarter_year,
                instructor_name=instructor_name,
                instructor_id=user.id,
                status="not_started",  # Not yet published
                # Store LLM prompt in final_explanation field for now (or create a separate field later)
                # For now, we'll store it in final_explanation temporarily
                final_explanation=llm_prompt,
                # Timed exam fields
                is_timed=is_timed,
                duration_hours=duration_hours if is_timed else None,
                duration_minutes=duration_minutes if is_timed else None
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
    
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
    
    return render_template("exam_review.html", {
        "request": request,
        "exam": exam,
        "related_exams": related_exams,
        "combined_exam_id": combined_exam_id,
        "sections_list": sections_list,
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
    
    return render_template("exam_details.html", {
        "request": request,
        "exam": exam
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
        return RedirectResponse(url=f"/teacher/exam/{exam_id}?error=Error terminating exam: {str(e)}", status_code=302)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root page - login form."""
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


@app.get("/question/{question_id}", response_class=HTMLResponse)
async def question_page(request: Request, question_id: int):
    """Dummy question page for testing login."""
    # You can later render question.html template here
    return render_template("question.html", {"request": request, "question_id": question_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)