from app.db.session import SessionLocal
from app.db.models import User

def seed_users():
    db = SessionLocal()
    
    # List of test users
    test_users = [
        {"email": "student@test.com", "password_hash": "password123", "role": "student"},
        {"email": "teacher@test.com", "password_hash": "password123", "role": "teacher"},
    ]
    
    for u in test_users:
        exists = db.query(User).filter(User.email == u["email"]).first()
        if not exists:
            user = User(**u)
            db.add(user)
    
    db.commit()
    db.close()
    print("Seeded test users successfully (or they already exist).")