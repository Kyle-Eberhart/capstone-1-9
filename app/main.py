"""Main FastAPI application."""
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.api.router import api_router
from app.db.base import Base, engine
from app.db.session import get_db
from app.db.models import User, Course
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
    
    # TODO: Query open exams for this instructor from database
    # For now, using empty list as placeholder
    open_exams = []  # Will be populated when Exam model is extended with course info
    
    return render_template("teacher_dashboard.html", {
        "request": request,
        "first_name": first_name,
        "courses": courses,
        "open_exams": open_exams
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