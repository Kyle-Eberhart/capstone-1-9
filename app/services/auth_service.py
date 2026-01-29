from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.models import User
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def is_hashed(password_hash: str) -> bool:
    """Check if a password is already hashed (bcrypt hashes start with $2b$)."""
    return password_hash.startswith('$2b$') or password_hash.startswith('$2a$')

def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None

    # Check if password is already hashed (new format) or plain text (old format)
    # Try hashed first, then fall back to plain text for backward compatibility
    if is_hashed(user.password_hash):
        # Password is hashed, verify using bcrypt
        if verify_password(password, user.password_hash):
            return user
    else:
        # Password is plain text (old format) - check plain text match
        if user.password_hash == password:
            # Auto-upgrade: hash the plain-text password and save it
            user.password_hash = hash_password(password)
            db.commit()
            return user

    return None

def create_user(db: Session, email: str, password: str, role: str = "student", 
                first_name: str = "", last_name: str = "", 
                student_id: str = None, instructor_id: str = None):
    """Create a new user account.
    
    Args:
        db: Database session
        email: User email (must be unique)
        password: User password (will be hashed before storing)
        role: User role (default: "student")
        first_name: User's first name
        last_name: User's last name
        student_id: Student ID (for students only)
        instructor_id: Instructor ID (for teachers only)
    
    Returns:
        User object if created successfully, None if email already exists
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return None
    
    # Hash the password before storing
    hashed_password = hash_password(password)
    
    # Create new user with hashed password
    user = User(
        email=email,
        password_hash=hashed_password,
        role=role,
        first_name=first_name,
        last_name=last_name,
        student_id=student_id if role == "student" else None,
        instructor_id=instructor_id if role == "teacher" else None
    )
    
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        return None