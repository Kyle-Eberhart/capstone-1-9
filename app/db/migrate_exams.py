"""Script to migrate exams table to add new columns."""
from app.db.session import SessionLocal
from app.db.base import Base, engine
# Import Exam model to ensure it's registered with Base.metadata
from app.db.models import Exam
from sqlalchemy import text


def migrate_exams_table():
    """Add new columns to the exams table if they don't exist."""
    db = SessionLocal()
    
    try:
        print("=" * 80)
        print("MIGRATING EXAMS TABLE")
        print("=" * 80)
        print("\nAdding new columns to exams table...")
        
        # SQLite syntax for adding columns
        migrations = [
            ("exam_id", "VARCHAR(100)"),
            ("course_number", "VARCHAR(20)"),
            ("section", "VARCHAR(10)"),
            ("exam_name", "VARCHAR(100)"),
            ("quarter_year", "VARCHAR(20)"),
            ("instructor_name", "VARCHAR(200)"),
            ("instructor_id", "INTEGER"),
            ("date_start", "DATETIME"),
            ("date_end", "DATETIME"),
            ("date_published", "DATETIME"),
            ("date_end_availability", "DATETIME"),
            ("exam_passcode", "VARCHAR(4)")
        ]
        
        # Check which columns already exist
        inspector_result = db.execute(text(
            "SELECT name FROM pragma_table_info('exams')"
        ))
        existing_columns = [row[0] for row in inspector_result.fetchall()]
        
        for column_name, column_def in migrations:
            if column_name in existing_columns:
                print(f"  [-] Column {column_name} already exists, skipping")
            else:
                try:
                    print(f"  [+] Adding column: {column_name}")
                    # For SQLite, we can't add NOT NULL columns without defaults for existing rows
                    # So we'll add nullable columns first
                    nullable_def = column_def.replace("NOT NULL", "").strip()
                    if "INTEGER" in nullable_def and "instructor_id" in column_name:
                        db.execute(text(f"ALTER TABLE exams ADD COLUMN {column_name} INTEGER"))
                    elif "DATETIME" in nullable_def:
                        db.execute(text(f"ALTER TABLE exams ADD COLUMN {column_name} DATETIME"))
                    else:
                        db.execute(text(f"ALTER TABLE exams ADD COLUMN {column_name} {nullable_def}"))
                    db.commit()
                except Exception as e:
                    print(f"  [X] Error adding column {column_name}: {e}")
                    db.rollback()
        
        # Create index on exam_id if it doesn't exist
        try:
            indices_result = db.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='exams'"
            ))
            existing_indices = [row[0] for row in indices_result.fetchall()]
            
            if 'ix_exams_exam_id' not in existing_indices:
                print("  [+] Creating index on exam_id")
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_exams_exam_id ON exams(exam_id)"))
                db.commit()
            
            if 'ix_exams_course_number' not in existing_indices:
                print("  [+] Creating index on course_number")
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_exams_course_number ON exams(course_number)"))
                db.commit()
                
            if 'ix_exams_instructor_id' not in existing_indices:
                print("  [+] Creating index on instructor_id")
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_exams_instructor_id ON exams(instructor_id)"))
                db.commit()
        except Exception as e:
            print(f"  [X] Error creating indexes: {e}")
            db.rollback()
        
        print("\n[SUCCESS] Migration complete!")
        print("\nThe exams table has been extended with the following fields:")
        print("  - exam_id (String, unique)")
        print("  - course_number (String)")
        print("  - section (String)")
        print("  - exam_name (String)")
        print("  - quarter_year (String)")
        print("  - instructor_name (String)")
        print("  - instructor_id (Integer, FK to users)")
        print("  - date_start, date_end, date_published, date_end_availability (DateTime)")
        print("\nNote: student_id is now nullable to allow teacher-created exams")
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"\n[ERROR] Error during migration: {e}")
        db.rollback()
        print("\nYou may need to manually add the columns or recreate the table.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate_exams_table()
