"""Teacher dashboard routes."""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from jinja2 import Environment, FileSystemLoader
from app.db.session import get_db
from app.db.models import Teacher, ExamTemplate, CustomQuestion, ExamAccess, Student
from app.db.repo import StudentRepository

router = APIRouter()

# Templates
env = Environment(loader=FileSystemLoader("app/templates"))

# Add custom filter for JSON parsing
import json
def from_json(value):
    """Parse JSON string."""
    if not value:
        return None
    try:
        return json.loads(value)
    except:
        return None

env.filters['from_json'] = from_json


def render_template(template_name: str, context: dict) -> HTMLResponse:
    """Render a Jinja2 template."""
    template = env.get_template(template_name)
    html_content = template.render(**context)
    return HTMLResponse(content=html_content)


def get_current_teacher(request: Request, db: Session) -> Optional[Teacher]:
    """Get current teacher from session/cookie."""
    # For POC, we'll use a simple cookie-based approach
    teacher_username = request.cookies.get("teacher_username")
    if not teacher_username:
        return None
    return db.query(Teacher).filter(Teacher.username == teacher_username).first()


@router.get("/teacher/login", response_class=HTMLResponse)
async def teacher_login_page(request: Request):
    """Teacher login page."""
    error = request.query_params.get("error", "")
    return render_template("teacher_login.html", {"request": request, "error": error})


@router.post("/teacher/login")
async def teacher_login(request: Request, username: str = Form(...), db: Session = Depends(get_db)):
    """Teacher login - simple username-based for POC."""
    if not username:
        return RedirectResponse(url="/api/teacher/login?error=username_required", status_code=302)
    
    # Get or create teacher
    teacher = db.query(Teacher).filter(Teacher.username == username).first()
    if not teacher:
        teacher = Teacher(username=username)
        db.add(teacher)
        db.commit()
        db.refresh(teacher)
    
    response = RedirectResponse(url="/api/teacher/dashboard", status_code=302)
    response.set_cookie(key="teacher_username", value=username)
    return response


@router.get("/teacher/dashboard", response_class=HTMLResponse)
async def teacher_dashboard(request: Request, db: Session = Depends(get_db)):
    """Teacher dashboard."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    # Get all exam templates for this teacher
    # Add error handling in case of database issues
    try:
        exam_templates = db.query(ExamTemplate).filter(
            ExamTemplate.teacher_id == teacher.id
        ).order_by(ExamTemplate.created_at.desc()).all()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error loading exam templates: {e}")
        exam_templates = []
        # Try to refresh the teacher object
        db.refresh(teacher)
        # Try query again
        try:
            exam_templates = db.query(ExamTemplate).filter(
                ExamTemplate.teacher_id == teacher.id
            ).order_by(ExamTemplate.created_at.desc()).all()
        except Exception as e2:
            logger.error(f"Retry also failed: {e2}")
            exam_templates = []
    
    return render_template("teacher_dashboard.html", {
        "request": request,
        "teacher": teacher,
        "exam_templates": exam_templates
    })


@router.get("/teacher/exam/create", response_class=HTMLResponse)
async def create_exam_page(request: Request, db: Session = Depends(get_db)):
    """Page to create a new exam template."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    return render_template("teacher_create_exam.html", {
        "request": request,
        "teacher": teacher
    })


@router.post("/teacher/exam/create")
async def create_exam(
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    time_limit_type: str = Form(default="none"),
    time_limit_minutes: str = Form(default=""),
    grading_type: str = Form(default="per_question"),
    exam_rubric_type: str = Form(default=""),
    exam_rubric_percentage: str = Form(default=""),
    exam_rubric_letter: str = Form(default=""),
    db: Session = Depends(get_db)
):
    """Create a new exam template."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    # Parse time limit
    time_limit = None
    if time_limit_type in ["per_question", "total"] and time_limit_minutes:
        try:
            time_limit = int(time_limit_minutes)
            if time_limit <= 0:
                time_limit = None
        except ValueError:
            time_limit = None
    
    # Parse exam rubric if overall grading
    exam_rubric = None
    exam_rubric_type_final = None
    if grading_type == "overall":
        if exam_rubric_percentage and exam_rubric_percentage.strip():
            exam_rubric = exam_rubric_percentage
            exam_rubric_type_final = "percentage"
        elif exam_rubric_letter and exam_rubric_letter.strip():
            exam_rubric = exam_rubric_letter
            exam_rubric_type_final = "letter"
    
    exam_template = ExamTemplate(
        teacher_id=teacher.id,
        title=title,
        description=description,
        is_active=True,
        time_limit_type=time_limit_type,
        time_limit_minutes=time_limit,
        grading_type=grading_type,
        exam_rubric_type=exam_rubric_type_final,
        exam_rubric=exam_rubric
    )
    db.add(exam_template)
    db.commit()
    db.refresh(exam_template)
    
    db.refresh(exam_template)
    
    return RedirectResponse(url=f"/api/teacher/exam/{exam_template.id}/questions", status_code=302)


@router.post("/teacher/exam/edit")
async def edit_exam(
    request: Request,
    exam_template_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(default=""),
    time_limit_type: str = Form(default="none"),
    time_limit_minutes: str = Form(default=""),
    grading_type: str = Form(default="per_question"),
    exam_rubric_type: str = Form(default=""),
    exam_rubric_percentage: str = Form(default=""),
    exam_rubric_letter: str = Form(default=""),
    db: Session = Depends(get_db)
):
    """Edit an exam template."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    # Parse time limit
    time_limit = None
    if time_limit_type in ["per_question", "total"] and time_limit_minutes:
        try:
            time_limit = int(time_limit_minutes)
            if time_limit <= 0:
                time_limit = None
        except ValueError:
            time_limit = None
    
    # Parse exam rubric if overall grading
    exam_rubric = None
    exam_rubric_type_final = None
    if grading_type == "overall":
        if exam_rubric_percentage and exam_rubric_percentage.strip():
            exam_rubric = exam_rubric_percentage
            exam_rubric_type_final = "percentage"
        elif exam_rubric_letter and exam_rubric_letter.strip():
            exam_rubric = exam_rubric_letter
            exam_rubric_type_final = "letter"
    else:
        # Clear exam rubric if switching to per-question grading
        exam_rubric = None
        exam_rubric_type_final = None
    
    exam_template.title = title
    exam_template.description = description
    exam_template.time_limit_type = time_limit_type
    exam_template.time_limit_minutes = time_limit
    exam_template.grading_type = grading_type
    exam_template.exam_rubric_type = exam_rubric_type_final
    exam_template.exam_rubric = exam_rubric
    db.commit()
    db.refresh(exam_template)
    
    return RedirectResponse(url="/api/teacher/dashboard", status_code=302)


@router.post("/teacher/exam/toggle-status")
async def toggle_exam_status(
    request: Request,
    exam_template_id: int = Form(...),
    is_active: str = Form(...),
    db: Session = Depends(get_db)
):
    """Toggle exam active/inactive status."""
    from fastapi.responses import JSONResponse
    
    teacher = get_current_teacher(request, db)
    if not teacher:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        return JSONResponse({"error": "Exam template not found"}, status_code=404)
    
    exam_template.is_active = is_active.lower() == 'true'
    db.commit()
    db.refresh(exam_template)
    
    return JSONResponse({"success": True, "is_active": exam_template.is_active})


@router.post("/teacher/exam/{exam_template_id}/delete")
async def delete_exam(
    request: Request,
    exam_template_id: int,
    db: Session = Depends(get_db)
):
    """Delete an exam template."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    # Delete the exam template (cascade will delete questions and access)
    db.delete(exam_template)
    db.commit()
    
    return RedirectResponse(url="/api/teacher/dashboard", status_code=302)


@router.get("/teacher/exam/{exam_template_id}/questions", response_class=HTMLResponse)
async def manage_questions_page(
    request: Request,
    exam_template_id: int,
    db: Session = Depends(get_db)
):
    """Page to add/manage questions for an exam template."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    # Get all questions for this template
    questions = db.query(CustomQuestion).filter(
        CustomQuestion.exam_template_id == exam_template_id
    ).order_by(CustomQuestion.question_number).all()
    
    # Parse rubrics for display
    import json
    parsed_questions = []
    for q in questions:
        parsed_q = {
            "id": q.id,
            "question_number": q.question_number,
            "question_text": q.question_text,
            "context": q.context,
            "rubric": q.rubric,
            "rubric_parsed": None
        }
        try:
            rubric_data = json.loads(q.rubric) if q.rubric else None
            if isinstance(rubric_data, dict) and "type" in rubric_data and "criteria" in rubric_data:
                parsed_q["rubric_parsed"] = rubric_data
        except:
            pass
        parsed_questions.append(parsed_q)
    
    return render_template("teacher_manage_questions.html", {
        "request": request,
        "teacher": teacher,
        "exam_template": exam_template,
        "questions": questions,
        "parsed_questions": parsed_questions
    })


@router.post("/teacher/exam/{exam_template_id}/questions/add")
async def add_question(
    request: Request,
    exam_template_id: int,
    question_number: int = Form(...),
    question_text: str = Form(...),
    context: str = Form(default=""),
    rubric: str = Form(default=""),
    rubric_percentage: str = Form(default=""),
    rubric_letter: str = Form(default=""),
    db: Session = Depends(get_db)
):
    """Add a question to an exam template."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    # Check if question number already exists
    existing = db.query(CustomQuestion).filter(
        CustomQuestion.exam_template_id == exam_template_id,
        CustomQuestion.question_number == question_number
    ).first()
    
    # Determine which rubric to use (new format takes precedence)
    final_rubric = None
    if rubric_percentage and rubric_percentage.strip():
        final_rubric = rubric_percentage
    elif rubric_letter and rubric_letter.strip():
        final_rubric = rubric_letter
    elif rubric and rubric.strip():
        final_rubric = rubric
    
    if not final_rubric:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"No rubric provided. rubric_percentage: '{rubric_percentage}', rubric_letter: '{rubric_letter}', rubric: '{rubric}'")
        return RedirectResponse(url=f"/api/teacher/exam/{exam_template_id}/questions?error=Rubric_is_required_Please_add_at_least_one_grading_criterion", status_code=302)
    
    try:
        if existing:
            # Update existing question
            existing.question_text = question_text
            existing.context = context
            existing.rubric = final_rubric
        else:
            # Create new question
            question = CustomQuestion(
                exam_template_id=exam_template_id,
                question_number=question_number,
                question_text=question_text,
                context=context,
                rubric=final_rubric
            )
            db.add(question)
        
        db.commit()
        db.refresh(exam_template)  # Refresh to ensure it's up to date
    except Exception as e:
        db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error saving question: {e}")
        # Redirect with error message
        error_msg = str(e).replace(' ', '_')
        return RedirectResponse(url=f"/api/teacher/exam/{exam_template_id}/questions?error={error_msg}", status_code=302)
    
    return RedirectResponse(url=f"/api/teacher/exam/{exam_template_id}/questions", status_code=302)


@router.post("/teacher/exam/{exam_template_id}/questions/{question_id}/delete")
async def delete_question(
    request: Request,
    exam_template_id: int,
    question_id: int,
    db: Session = Depends(get_db)
):
    """Delete a question from an exam template."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    question = db.query(CustomQuestion).filter(
        CustomQuestion.id == question_id,
        CustomQuestion.exam_template_id == exam_template_id
    ).first()
    
    if question:
        db.delete(question)
        db.commit()
    
    return RedirectResponse(url=f"/api/teacher/exam/{exam_template_id}/questions", status_code=302)


@router.get("/teacher/exam/{exam_template_id}/access", response_class=HTMLResponse)
async def manage_access_page(
    request: Request,
    exam_template_id: int,
    db: Session = Depends(get_db)
):
    """Page to manage who can access an exam."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    # Get all access records for this template
    accesses = db.query(ExamAccess).filter(
        ExamAccess.exam_template_id == exam_template_id
    ).order_by(ExamAccess.created_at.desc()).all()
    
    return render_template("teacher_manage_access.html", {
        "request": request,
        "teacher": teacher,
        "exam_template": exam_template,
        "accesses": accesses
    })


@router.post("/teacher/exam/{exam_template_id}/access/add")
async def add_access(
    request: Request,
    exam_template_id: int,
    student_username: str = Form(...),
    db: Session = Depends(get_db)
):
    """Add access for a student to an exam template."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    # Check if access already exists
    existing = db.query(ExamAccess).filter(
        ExamAccess.exam_template_id == exam_template_id,
        ExamAccess.student_username == student_username
    ).first()
    
    if existing:
        # Reactivate if it was deactivated
        existing.is_active = True
    else:
        # Create new access
        access = ExamAccess(
            exam_template_id=exam_template_id,
            student_username=student_username,
            is_active=True
        )
        db.add(access)
    
    db.commit()
    return RedirectResponse(url=f"/api/teacher/exam/{exam_template_id}/access", status_code=302)


@router.post("/teacher/exam/{exam_template_id}/access/{access_id}/toggle")
async def toggle_access(
    request: Request,
    exam_template_id: int,
    access_id: int,
    db: Session = Depends(get_db)
):
    """Toggle access active/inactive."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    access = db.query(ExamAccess).filter(
        ExamAccess.id == access_id,
        ExamAccess.exam_template_id == exam_template_id
    ).first()
    
    if access:
        access.is_active = not access.is_active
        db.commit()
    
    return RedirectResponse(url=f"/api/teacher/exam/{exam_template_id}/access", status_code=302)


@router.post("/teacher/exam/{exam_template_id}/access/{access_id}/delete")
async def delete_access(
    request: Request,
    exam_template_id: int,
    access_id: int,
    db: Session = Depends(get_db)
):
    """Delete access for a student."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    access = db.query(ExamAccess).filter(
        ExamAccess.id == access_id,
        ExamAccess.exam_template_id == exam_template_id
    ).first()
    
    if access:
        db.delete(access)
        db.commit()
    
    return RedirectResponse(url=f"/api/teacher/exam/{exam_template_id}/access", status_code=302)


@router.get("/teacher/students", response_class=HTMLResponse)
async def manage_students_page(request: Request, db: Session = Depends(get_db)):
    """Page to manage all students."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    # Get all exam templates for this teacher
    exam_templates = db.query(ExamTemplate).filter(
        ExamTemplate.teacher_id == teacher.id
    ).all()
    
    exam_template_ids = [et.id for et in exam_templates]
    
    # Get all students who have access to any of this teacher's exams
    students_data = {}
    if exam_template_ids:
        accesses = db.query(ExamAccess).filter(
            ExamAccess.exam_template_id.in_(exam_template_ids)
        ).all()
        
        # Group by student username
        for access in accesses:
            if access.student_username not in students_data:
                students_data[access.student_username] = {
                    "username": access.student_username,
                    "exams": [],
                    "total_exams": 0,
                    "active_exams": 0
                }
            
            # Get exam template info
            exam_template = next((et for et in exam_templates if et.id == access.exam_template_id), None)
            if exam_template:
                students_data[access.student_username]["exams"].append({
                    "exam_id": exam_template.id,
                    "exam_title": exam_template.title,
                    "is_active": access.is_active
                })
                students_data[access.student_username]["total_exams"] += 1
                if access.is_active:
                    students_data[access.student_username]["active_exams"] += 1
    
    students_list = list(students_data.values())
    students_list.sort(key=lambda x: x["username"].lower())
    
    return render_template("teacher_manage_students.html", {
        "request": request,
        "teacher": teacher,
        "students": students_list,
        "exam_templates": exam_templates
    })


@router.post("/teacher/students/add")
async def add_student_to_exam(
    request: Request,
    student_username: str = Form(...),
    exam_template_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Add a student to an exam."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    # Check if access already exists
    existing = db.query(ExamAccess).filter(
        ExamAccess.exam_template_id == exam_template_id,
        ExamAccess.student_username == student_username
    ).first()
    
    if existing:
        # Reactivate if it was deactivated
        existing.is_active = True
    else:
        # Create new access
        access = ExamAccess(
            exam_template_id=exam_template_id,
            student_username=student_username,
            is_active=True
        )
        db.add(access)
    
    db.commit()
    return RedirectResponse(url="/api/teacher/students", status_code=302)


@router.post("/teacher/students/remove")
async def remove_student_from_exam(
    request: Request,
    student_username: str = Form(...),
    exam_template_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Remove a student from an exam."""
    teacher = get_current_teacher(request, db)
    if not teacher:
        return RedirectResponse(url="/api/teacher/login", status_code=302)
    
    exam_template = db.query(ExamTemplate).filter(
        ExamTemplate.id == exam_template_id,
        ExamTemplate.teacher_id == teacher.id
    ).first()
    
    if not exam_template:
        raise HTTPException(status_code=404, detail="Exam template not found")
    
    access = db.query(ExamAccess).filter(
        ExamAccess.exam_template_id == exam_template_id,
        ExamAccess.student_username == student_username
    ).first()
    
    if access:
        db.delete(access)
        db.commit()
    
    return RedirectResponse(url="/api/teacher/students", status_code=302)


@router.get("/teacher/logout")
async def teacher_logout(request: Request):
    """Teacher logout."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="teacher_username")
    return response
