"""Authentication routes."""
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.db.models import ExamTemplate, ExamAccess
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
    if not username:
        return RedirectResponse(url="/?error=username_required", status_code=302)
    
    # Parse exam_template_id (might be empty string from form)
    template_id = None
    if exam_template_id and exam_template_id.strip():
        try:
            template_id = int(exam_template_id)
        except ValueError:
            pass
    
    # Start exam
    exam_service = ExamService()
    try:
        exam = await exam_service.start_exam(db, username, template_id)
    except ValueError as e:
        # Handle access denied or other errors
        return RedirectResponse(url=f"/?error={str(e)}", status_code=302)
    
    # Store exam_id in session (for POC, we'll use cookies)
    response = RedirectResponse(url=f"/api/exam/{exam.id}", status_code=302)
    response.set_cookie(key="exam_id", value=str(exam.id))
    response.set_cookie(key="username", value=username)
    
    return response

