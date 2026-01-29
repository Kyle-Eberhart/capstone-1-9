"""Migration script to hash existing plain-text passwords."""
from app.db.session import SessionLocal
from app.db.models import User
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def is_hashed(password_hash: str) -> bool:
    """Check if a password is already hashed (bcrypt hashes start with $2b$)."""
    return password_hash.startswith('$2b$') or password_hash.startswith('$2a$')

def migrate_passwords():
    """Hash all plain-text passwords in the database."""
    db = SessionLocal()
    
    try:
        # Get all users
        users = db.query(User).all()
        updated_count = 0
        
        for user in users:
            # Check if password is already hashed
            if not is_hashed(user.password_hash):
                print(f"Hashing password for user: {user.email}")
                # Hash the plain-text password
                user.password_hash = hash_password(user.password_hash)
                updated_count += 1
            else:
                print(f"Password already hashed for user: {user.email}")
        
        if updated_count > 0:
            db.commit()
            print(f"\n[+] Successfully hashed {updated_count} passwords")
        else:
            print("\n[+] All passwords are already hashed")
            
    except Exception as e:
        db.rollback()
        print(f"[X] Error hashing passwords: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_passwords()
