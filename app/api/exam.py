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
    from app.db.repo import ExamRepository, QuestionRepository
    
    exam_service = ExamService()
    
    # Get exam to check if it exists
    exam = ExamRepository.get(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    # Check if exam has any questions
    questions = QuestionRepository.get_by_exam(db, exam_id)
    
    if len(questions) == 0:
        # No questions yet - exam might not be ready
        # For now, show a message that exam is being prepared
        return render_template("exam_preparing.html", {
            "request": request,
            "exam": exam,
            "exam_id": exam_id
        })
    
    question = await exam_service.get_current_question(db, exam_id)
    
    if question is None:
        # All questions answered, redirect to completion
        return RedirectResponse(url=f"/api/exam/{exam_id}/complete", status_code=302)
    
    # Get exam status
    status = exam_service.get_exam_status(db, exam_id)
    
    # Pass exam timing information for timer display - simplified: just pass duration
    return render_template("question.html", {
        "request": request,
        "question": question,
        "exam_id": exam_id,
        "question_number": status["questions_completed"] + 1,
        "total_questions": status["total_questions"],
        "is_timed": exam.is_timed,
        "duration_hours": exam.duration_hours if exam.is_timed else None,
        "duration_minutes": exam.duration_minutes if exam.is_timed else None
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


@router.get("/exam/{exam_id}/dispute", response_class=HTMLResponse)
async def dispute_grade_page(request: Request, exam_id: int, db: Session = Depends(get_db)):
    """Show dispute grade form."""
    exam = ExamRepository.get(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    # Only allow dispute if exam is completed and has a grade
    if exam.status != "completed" or exam.final_grade is None:
        return RedirectResponse(url=f"/api/exam/{exam_id}/complete?error=Cannot dispute grade for this exam", status_code=302)
    
    # Check if already disputed
    if exam.status == "disputed":
        return RedirectResponse(url=f"/api/exam/{exam_id}/complete?error=This exam grade has already been disputed", status_code=302)
    
    error = request.query_params.get("error", "")
    
    return render_template("dispute_grade.html", {
        "request": request,
        "exam": exam,
        "error": error
    })


@router.post("/exam/{exam_id}/dispute")
async def submit_dispute(
    request: Request,
    exam_id: int,
    dispute_reason: str = Form(...),
    db: Session = Depends(get_db)
):
    """Submit a grade dispute."""
    from app.db.models import Exam, Notification, User
    from app.services.notification_service import NotificationService
    
    exam = ExamRepository.get(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    # Only allow dispute if exam is completed and has a grade
    if exam.status != "completed" or exam.final_grade is None:
        return RedirectResponse(url=f"/api/exam/{exam_id}/dispute?error=Cannot dispute grade for this exam", status_code=302)
    
    # Check if already disputed
    if exam.status == "disputed":
        return RedirectResponse(url=f"/api/exam/{exam_id}/dispute?error=This exam grade has already been disputed", status_code=302)
    
    # Update exam status and store dispute reason
    exam.status = "disputed"
    exam.dispute_reason = dispute_reason
    db.commit()
    db.refresh(exam)
    
    # Create notification for instructor
    if exam.instructor_id:
        notification_service = NotificationService()
        notification_service.create_notification(
            db=db,
            user_id=exam.instructor_id,
            notification_type="grade_disputed",
            title=f"Grade Dispute: {exam.course_number} - {exam.exam_name}",
            message=f"A student has disputed their grade for {exam.exam_name} in {exam.course_number} - {exam.section}. Reason: {dispute_reason[:200]}...",
            related_exam_id=exam.id,
            related_course_id=None  # Could link to course if we have that relationship
        )
        
        # Send email notification to instructor
        # Note: Instructor email is automatically retrieved from their User account (created via signup)
        from app.services.email_service import EmailService
        from app.db.models import Student, User as UserModel
        from app.db.repo import QuestionRepository
        
        # Get instructor email from their User account (email is stored during signup)
        instructor = db.query(UserModel).filter(UserModel.id == exam.instructor_id).first()
        if instructor and instructor.email:
            # Get student name
            student_name = "Student"
            if exam.student_id:
                student = db.query(Student).filter(Student.id == exam.student_id).first()
                if student:
                    student_user = db.query(UserModel).filter(UserModel.email == student.username).first()
                    if student_user:
                        student_name = f"{student_user.first_name} {student_user.last_name}".strip() or student.username
                    else:
                        student_name = student.username
            
            # Get questions for this exam
            questions = QuestionRepository.get_by_exam(db, exam.id)
            
            # Generate exam details HTML
            email_service = EmailService()
            exam_details_html = email_service.generate_exam_details_html(
                exam=exam,
                student_name=student_name,
                questions=questions,
                dispute_reason=dispute_reason
            )
            
            # Send email and verify it was sent successfully
            email_sent = email_service.send_dispute_notification(
                to_email=instructor.email,
                student_name=student_name,
                course_number=exam.course_number,
                exam_name=exam.exam_name,
                exam_details_html=exam_details_html
            )
            
            if email_sent:
                # Email sent successfully - show confirmation
                return RedirectResponse(
                    url=f"/api/exam/{exam_id}/complete?success=Dispute submitted successfully. A confirmation email has been sent to your instructor at {instructor.email}.",
                    status_code=302
                )
            else:
                # Email failed - show error but dispute was still recorded
                logger.warning(
                    f"Failed to send dispute email to instructor {instructor.email} for exam {exam.exam_id}. "
                    f"Check email configuration in .env file. In-app notification was still created."
                )
                return RedirectResponse(
                    url=f"/api/exam/{exam_id}/complete?error=Dispute submitted, but failed to send email notification to instructor. Please contact your instructor directly at {instructor.email}. Check application logs for email configuration issues.",
                    status_code=302
                )
        else:
            # No instructor email found
            logger.warning(f"No email address found for instructor (user_id: {exam.instructor_id})")
            return RedirectResponse(
                url=f"/api/exam/{exam_id}/complete?error=Dispute submitted, but instructor email address not found. Please contact your instructor directly.",
                status_code=302
            )
    else:
        # No instructor_id on exam
        logger.warning(f"No instructor_id found for exam {exam_id}")
        return RedirectResponse(
            url=f"/api/exam/{exam_id}/complete?error=Dispute submitted, but instructor information not found. Please contact your instructor directly.",
            status_code=302
        )
    
    # Fallback (shouldn't reach here, but just in case)
    return RedirectResponse(url=f"/api/exam/{exam_id}/complete?success=Dispute submitted successfully", status_code=302)

