"""Notification service for creating and managing notifications."""
from sqlalchemy.orm import Session
from app.db.models import Notification
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notifications."""
    
    def create_notification(
        self,
        db: Session,
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        related_exam_id: int = None,
        related_course_id: int = None
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            related_exam_id=related_exam_id,
            related_course_id=related_course_id,
            is_read=False
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        logger.info(f"Created notification {notification.id} for user {user_id}: {notification_type}")
        return notification
    
    def get_user_notifications(
        self,
        db: Session,
        user_id: int,
        unread_only: bool = False,
        limit: int = None
    ) -> list:
        """Get notifications for a user."""
        query = db.query(Notification).filter(Notification.user_id == user_id)
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        query = query.order_by(Notification.created_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def mark_as_read(self, db: Session, notification_id: int, user_id: int) -> bool:
        """Mark a notification as read."""
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id
        ).first()
        
        if notification:
            notification.is_read = True
            db.commit()
            return True
        return False
    
    def mark_all_as_read(self, db: Session, user_id: int) -> int:
        """Mark all notifications as read for a user."""
        count = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({"is_read": True})
        db.commit()
        return count
    
    def get_unread_count(self, db: Session, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        return db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).count()
    
    def delete_notification(self, db: Session, notification_id: int, user_id: int) -> bool:
        """Delete a notification."""
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id
        ).first()
        
        if notification:
            db.delete(notification)
            db.commit()
            logger.info(f"Deleted notification {notification_id} for user {user_id}")
            return True
        return False
