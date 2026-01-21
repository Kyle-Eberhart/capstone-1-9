"""Authentication routes."""
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.services.auth_service import authenticate_user, create_user
from app.services.exam_service import ExamService

router = APIRouter()


@router.post("/login")
async def login(
    request: Request, 
    username: str = Form(...), 
    exam_template_id: str = Form(""),
    db: Session = Depends(get_db)
):
    """Login and start exam session."""
    
    # Parse exam_template_id (might be empty string from form)
    template_id = None
    if exam_template_id and exam_template_id.strip():
        try:
            template_id = int(exam_template_id)
        except ValueError:
            pass
    
    # If the user is a student, redirect to student dashboard
    if user.role == "student":
        response = RedirectResponse(url="/student/dashboard", status_code=302)
        response.set_cookie(key="username", value=email)
        return response
    
    # If the user is a teacher, redirect to teacher dashboard
    if user.role == "teacher":
        response = RedirectResponse(url="/teacher/dashboard", status_code=302)
        response.set_cookie(key="username", value=email)
        return response
    
    # Otherwise (other roles) → start exam as before
    exam_service = ExamService()
    try:
        exam = await exam_service.start_exam(db, username, template_id)
    except ValueError as e:
        # Handle access denied or other errors
        return RedirectResponse(url=f"/?error={str(e)}", status_code=302)
    
    # Redirect to the exam route
    response = RedirectResponse(url=f"/api/exam/{exam.id}", status_code=302)
    response.set_cookie(key="exam_id", value=str(exam.id))
    response.set_cookie(key="username", value=username)
    
    return response


@router.post("/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    role: str = Form("student"),
    student_id: str = Form(None),
    instructor_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new user account."""
    
    # Validate role
    if role not in ["student", "teacher"]:
        role = "student"
    
    # Create user account
    user = create_user(
        db, 
        email, 
        password, 
        role, 
        first_name=first_name, 
        last_name=last_name,
        student_id=student_id if student_id else None,
        instructor_id=instructor_id if instructor_id else None
    )
    if not user:
        # User already exists or creation failed
        return RedirectResponse(url="/signup?error=email_exists", status_code=302)
    
    # Account created successfully - redirect to login with success message
    return RedirectResponse(url="/?success=account_created", status_code=302)