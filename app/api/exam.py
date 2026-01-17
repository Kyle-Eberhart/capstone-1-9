"""Exam routes."""
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader
from app.db.session import get_db
from app.db.repo import ExamRepository, QuestionRepository
from app.services.exam_service import ExamService
from app.core.schemas.api_models import AnswerSubmission

router = APIRouter()

# Templates
env = Environment(loader=FileSystemLoader("app/templates"))


def render_template(template_name: str, context: dict) -> HTMLResponse:
    """Render a Jinja2 template."""
    template = env.get_template(template_name)
    html_content = template.render(**context)
    return HTMLResponse(content=html_content)


@router.get("/exam/{exam_id}", response_class=HTMLResponse)
async def get_exam(request: Request, exam_id: int, db: Session = Depends(get_db)):
    """Get current question for exam."""
    from app.db.models import Exam, ExamTemplate
    
    exam_service = ExamService()
    question = await exam_service.get_current_question(db, exam_id)
    
    if question is None:
        # All questions answered, redirect to completion
        return RedirectResponse(url=f"/api/exam/{exam_id}/complete", status_code=302)
    
    # Get exam status
    status = exam_service.get_exam_status(db, exam_id)
    
    # Get exam template to check time limits
    exam = ExamRepository.get(db, exam_id)
    time_limit_type = None
    time_limit_minutes = None
    if exam and exam.exam_template_id:
        exam_template = db.query(ExamTemplate).filter(ExamTemplate.id == exam.exam_template_id).first()
        if exam_template:
            time_limit_type = exam_template.time_limit_type
            time_limit_minutes = exam_template.time_limit_minutes
    
    # Parse rubric if it's JSON format
    rubric_parsed = None
    if question.rubric:
        import json
        try:
            rubric_data = json.loads(question.rubric)
            if isinstance(rubric_data, dict) and "type" in rubric_data and "criteria" in rubric_data:
                rubric_parsed = rubric_data
        except:
            pass
    
    return render_template("question.html", {
        "request": request,
        "question": question,
        "exam_id": exam_id,
        "question_number": status["questions_completed"] + 1,
        "total_questions": status["total_questions"],
        "rubric_parsed": rubric_parsed,
        "time_limit_type": time_limit_type,
        "time_limit_minutes": time_limit_minutes
    })


@router.post("/exam/{exam_id}/answer")
async def submit_answer(
    request: Request,
    exam_id: int,
    question_id: int = Form(...),
    answer: str = Form(...),
    db: Session = Depends(get_db)
):
    """Submit an answer for a question."""
    exam_service = ExamService()
    
    # Submit and grade answer
    question = await exam_service.submit_answer(db, question_id, answer)
    
    # Check if exam is complete
    status = exam_service.get_exam_status(db, exam_id)
    if status["questions_completed"] >= status["total_questions"]:
        # Complete the exam
        await exam_service.complete_exam(db, exam_id)
        return RedirectResponse(url=f"/api/exam/{exam_id}/complete", status_code=302)
    
    # Go to next question
    return RedirectResponse(url=f"/api/exam/{exam_id}", status_code=302)


@router.get("/exam/{exam_id}/exit")
async def exit_exam(request: Request, exam_id: int, db: Session = Depends(get_db)):
    """Exit exam early - mark as incomplete and return to home."""
    exam = ExamRepository.get(db, exam_id)
    if exam and exam.status == "in_progress":
        # Mark exam as incomplete (don't calculate final grade)
        ExamRepository.update_status(db, exam_id, "incomplete", None, "Exam exited early by student")
    
    # Clear cookies and redirect to home
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="exam_id")
    response.delete_cookie(key="username")
    return response


@router.get("/exam/{exam_id}/complete", response_class=HTMLResponse)
async def exam_complete(request: Request, exam_id: int, db: Session = Depends(get_db)):
    """Show exam completion page with final grade."""
    exam = ExamRepository.get(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    questions = QuestionRepository.get_by_exam(db, exam_id)
    
    return render_template("complete.html", {
        "request": request,
        "exam": exam,
        "questions": questions
    })

