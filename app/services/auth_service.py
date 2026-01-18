from sqlalchemy.orm import Session
from app.db.models import User

def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None

    # Plain-text comparison (NO hashing)
    if user.password_hash != password:
        return None

    return user