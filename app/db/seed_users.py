from app.db.session import SessionLocal
from app.db.models import User
from app.services.auth_service import hash_password

def seed_users():
    db = SessionLocal()
    
    # List of test users with plain-text passwords (will be hashed)
    test_users = [
        {"email": "student@test.com", "password": "password123", "role": "student"},
        {"email": "teacher@test.com", "password": "password123", "role": "teacher"},
    ]
    
    for u in test_users:
        exists = db.query(User).filter(User.email == u["email"]).first()
        if not exists:
            # Hash the password before creating user
            hashed_password = hash_password(u["password"])
            user = User(
                email=u["email"],
                password_hash=hashed_password,
                role=u["role"]
            )
            db.add(user)
    
    db.commit()
    db.close()
    print("Seeded test users successfully (or they already exist).")