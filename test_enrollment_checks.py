"""Test script to verify enrollment checks are working."""
from app.db.session import SessionLocal
from app.db.models import User, Student, Course, Enrollment, Exam
from app.services.auth_service import create_user

def test_enrollment_checks():
    """Test that enrollment checks are working correctly."""
    db = SessionLocal()
    
    print("=" * 60)
    print("Testing Enrollment Checks")
    print("=" * 60)
    
    # Test 1: Check existing enrollments
    print("\n[Test 1] Checking existing enrollments...")
    enrollments = db.query(Enrollment).all()
    print(f"  Found {len(enrollments)} enrollments in database")
    
    for enrollment in enrollments:
        student = enrollment.student
        course = enrollment.course
        if student and course:
            print(f"  - Student: {student.username} enrolled in {course.course_number}-{course.section}")
    
    # Test 2: Check courses
    print("\n[Test 2] Checking courses...")
    courses = db.query(Course).all()
    print(f"  Found {len(courses)} courses in database")
    for course in courses:
        print(f"  - {course.course_number}-{course.section} ({course.quarter_year})")
    
    # Test 3: Check exams
    print("\n[Test 3] Checking published exams...")
    published_exams = db.query(Exam).filter(
        Exam.date_published.isnot(None),
        Exam.student_id.is_(None)  # Template exams
    ).all()
    print(f"  Found {len(published_exams)} published template exams")
    for exam in published_exams:
        print(f"  - {exam.exam_name} for {exam.course_number}-{exam.section} ({exam.quarter_year})")
    
    # Test 4: Verify enrollment-exam matching
    print("\n[Test 4] Verifying enrollment-exam matching logic...")
    students = db.query(Student).all()
    for student in students:
        enrollments = db.query(Enrollment).filter(
            Enrollment.student_id == student.id
        ).all()
        
        enrolled_courses = []
        for enrollment in enrollments:
            course = enrollment.course
            if course:
                enrolled_courses.append((
                    course.course_number.upper(),
                    course.section,
                    course.quarter_year
                ))
        
        # Find exams for enrolled courses
        matching_exams = []
        for exam in published_exams:
            exam_key = (exam.course_number.upper(), exam.section, exam.quarter_year)
            if exam_key in enrolled_courses:
                matching_exams.append(exam)
        
        print(f"  Student {student.username}:")
        print(f"    - Enrolled in {len(enrolled_courses)} course(s)")
        print(f"    - Can see {len(matching_exams)} exam(s)")
        for exam in matching_exams:
            print(f"      * {exam.exam_name} ({exam.course_number}-{exam.section})")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)
    print("\nNote: Enrollment checks should now:")
    print("  1. Filter dashboard exams to only show enrolled courses")
    print("  2. Block exam details page if not enrolled")
    print("  3. Block exam start if not enrolled")
    
    db.close()

if __name__ == "__main__":
    test_enrollment_checks()
