"""Authentication routes."""
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.auth_service import authenticate_user
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
        # Invalid login → stay on login page with error
        return RedirectResponse(url="/?error=invalid_login", status_code=302)
    
    # Successful login → start exam
    exam_service = ExamService()
    exam = await exam_service.start_exam(db, email)  # email used as placeholder username
    
    # Redirect to the normal exam route (like original code)
    response = RedirectResponse(url=f"/api/exam/{exam.id}", status_code=302)
    response.set_cookie(key="exam_id", value=str(exam.id))
    response.set_cookie(key="username", value=email)
    
    return response