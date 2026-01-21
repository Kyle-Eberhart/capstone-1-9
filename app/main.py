"""Main FastAPI application."""
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session
from app.api.router import api_router
from app.db.base import Base, engine
from app.db.session import get_db
from app.db.models import ExamTemplate
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
async def student_dashboard(request: Request):
    """Blank student dashboard page."""
    return render_template("student_dashboard.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    """Root page - login form."""
    try:
        error = request.query_params.get("error", "")
        username = request.query_params.get("username", "")
        
        available_exams = []
        if username:
            # Get exams this student has access to
            from app.db.models import ExamTemplate, ExamAccess
            try:
                # Get all active exam templates that this student has access to
                accesses = db.query(ExamAccess).filter(
                    ExamAccess.student_username == username,
                    ExamAccess.is_active == True
                ).all()
                
                exam_template_ids = [access.exam_template_id for access in accesses]
                
                if exam_template_ids:
                    # Only show active exams that the student has access to
                    available_exams = db.query(ExamTemplate).filter(
                        ExamTemplate.id.in_(exam_template_ids),
                        ExamTemplate.is_active == True
                    ).all()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error loading accessible exams: {e}")
                available_exams = []
        
        return render_template("login.html", {
            "request": request, 
            "error": error,
            "available_exams": available_exams,
            "username": username
        })
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error rendering root page: {e}", exc_info=True)
        # Return a simple error page instead of white screen
        return HTMLResponse(
            content=f"""
            <html>
            <head><title>Error</title></head>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1>Application Error</h1>
                <p>An error occurred while loading the page.</p>
                <p style="color: #666; font-size: 0.9em;">Error: {str(e)}</p>
                <p><a href="/">Try Again</a></p>
            </body>
            </html>
            """,
            status_code=500
        )


@app.get("/question/{question_id}", response_class=HTMLResponse)
async def question_page(request: Request, question_id: int):
    """Dummy question page for testing login."""
    # You can later render question.html template here
    return render_template("question.html", {"request": request, "question_id": question_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)