"""Authentication routes."""
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.auth_service import authenticate_user, create_user
from app.services.exam_service import ExamService

router = APIRouter()


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Login and start exam session."""
    
    # Check email/password
    user = authenticate_user(db, email, password)
    if not user:
        # Invalid login → redirect to selection page with error
        # Try to determine which login page they came from based on referer
        referer = request.headers.get("referer", "")
        if "/teacher/login" in referer:
            return RedirectResponse(url="/teacher/login?error=invalid_login", status_code=302)
        elif "/student/login" in referer:
            return RedirectResponse(url="/student/login?error=invalid_login", status_code=302)
        else:
            # Default to selection page
            return RedirectResponse(url="/?error=invalid_login", status_code=302)
    
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
    exam = await exam_service.start_exam(db, email)  # email used as placeholder username
    
    # Redirect to the normal exam route
    response = RedirectResponse(url=f"/api/exam/{exam.id}", status_code=302)
    response.set_cookie(key="exam_id", value=str(exam.id))
    response.set_cookie(key="username", value=email)
    
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
    
    # Account created successfully - redirect to appropriate login page with success message
    if role == "teacher":
        return RedirectResponse(url="/teacher/login?success=account_created", status_code=302)
    else:
        return RedirectResponse(url="/student/login?success=account_created", status_code=302)