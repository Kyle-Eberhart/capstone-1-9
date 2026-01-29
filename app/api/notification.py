"""Notification routes."""
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, Notification
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("/notification/{notification_id}/read")
async def mark_notification_read(
    request: Request,
    notification_id: int,
    redirect: str = "/student/dashboard",
    db: Session = Depends(get_db)
):
    """Mark a notification as read."""
    from app.db.models import Exam
    
    # Get user from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    notification_service = NotificationService()
    
    # Get notification to check its type and related exam
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user.id
    ).first()
    
    if not notification:
        return RedirectResponse(url=f"{redirect}?error=Notification not found", status_code=302)
    
    # Mark as read
    notification_service.mark_as_read(db, notification_id, user.id)
    
    # If it's a grade dispute notification and has a related exam, redirect to exam details
    if notification.notification_type == "grade_disputed" and notification.related_exam_id:
        exam = db.query(Exam).filter(Exam.id == notification.related_exam_id).first()
        if exam:
            # Redirect to exam details page using exam_id string
            if user.role == "teacher":
                return RedirectResponse(url=f"/teacher/exam/{exam.exam_id}", status_code=302)
            else:
                return RedirectResponse(url=f"/student/exam/{exam.exam_id}", status_code=302)
    
    # Default redirect
    return RedirectResponse(url=redirect, status_code=302)


@router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(
    request: Request,
    db: Session = Depends(get_db)
):
    """Mark all notifications as read for the current user."""
    # Get user from cookie
    email = request.cookies.get("username")
    if not email:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return RedirectResponse(url="/?error=login_required", status_code=302)
    
    notification_service = NotificationService()
    count = notification_service.mark_all_as_read(db, user.id)
    
    # Determine redirect based on user role
    if user.role == "teacher":
        redirect_url = "/api/teacher/dashboard"
    else:
        redirect_url = "/student/dashboard"
    
    return RedirectResponse(url=f"{redirect_url}?success={count} notifications marked as read", status_code=302)


@router.delete("/notification/{notification_id}")
async def delete_notification(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db)
):
    """Delete a notification."""
    from fastapi.responses import JSONResponse
    
    # Get user from cookie
    email = request.cookies.get("username")
    if not email:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Login required"}
        )
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Login required"}
        )
    
    notification_service = NotificationService()
    success = notification_service.delete_notification(db, notification_id, user.id)
    
    if success:
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Notification deleted"}
        )
    else:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Notification not found"}
        )
