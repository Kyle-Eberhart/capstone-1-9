"""Test script to verify password hashing functionality."""
from app.db.session import SessionLocal
from app.db.models import User
from app.services.auth_service import authenticate_user, create_user, is_hashed

def test_password_hashing():
    """Test password hashing and authentication."""
    db = SessionLocal()
    
    print("=" * 60)
    print("Testing Password Hashing Implementation")
    print("=" * 60)
    
    # Test 1: Check existing users have hashed passwords
    print("\n[Test 1] Checking existing users have hashed passwords...")
    existing_users = db.query(User).all()
    for user in existing_users:
        if is_hashed(user.password_hash):
            print(f"  [OK] {user.email}: Password is hashed")
        else:
            print(f"  [FAIL] {user.email}: Password is NOT hashed (plain text)")
    
    # Test 2: Authenticate with existing user (should work)
    print("\n[Test 2] Testing authentication with existing user...")
    test_email = existing_users[0].email if existing_users else None
    if test_email:
        # Try to authenticate (we don't know the password, but we can check the structure)
        user = db.query(User).filter(User.email == test_email).first()
        if user and is_hashed(user.password_hash):
            print(f"  [OK] {test_email}: Password is hashed (ready for authentication)")
        else:
            print(f"  [FAIL] {test_email}: Password not properly hashed")
    
    # Test 3: Create a new user and verify password is hashed
    print("\n[Test 3] Creating new test user...")
    test_user_email = "test_hash_user@example.com"
    test_password = "testpass123"
    
    # Delete if exists
    existing = db.query(User).filter(User.email == test_user_email).first()
    if existing:
        db.delete(existing)
        db.commit()
        print(f"  (Deleted existing test user)")
    
    # Create new user
    new_user = create_user(
        db=db,
        email=test_user_email,
        password=test_password,
        role="student",
        first_name="Test",
        last_name="User"
    )
    
    if new_user:
        if is_hashed(new_user.password_hash):
            print(f"  [OK] New user created with hashed password")
        else:
            print(f"  [FAIL] New user password is NOT hashed!")
        
        # Test 4: Authenticate with new user
        print("\n[Test 4] Testing authentication with new user...")
        authenticated = authenticate_user(db, test_user_email, test_password)
        if authenticated:
            print(f"  [OK] Authentication successful with correct password")
        else:
            print(f"  [FAIL] Authentication failed with correct password")
        
        # Test 5: Try wrong password
        print("\n[Test 5] Testing authentication with wrong password...")
        authenticated_wrong = authenticate_user(db, test_user_email, "wrongpassword")
        if not authenticated_wrong:
            print(f"  [OK] Correctly rejected wrong password")
        else:
            print(f"  [FAIL] Incorrectly accepted wrong password!")
        
        # Cleanup
        db.delete(new_user)
        db.commit()
        print(f"\n  (Cleaned up test user)")
    else:
        print(f"  [FAIL] Failed to create test user")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)
    
    db.close()

if __name__ == "__main__":
    test_password_hashing()
