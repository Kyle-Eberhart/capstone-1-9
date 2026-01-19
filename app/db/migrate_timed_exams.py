"""Script to migrate exams table to add timed exam columns."""
from app.db.session import SessionLocal
from app.db.base import Base, engine
# Import Exam model to ensure it's registered with Base.metadata
from app.db.models import Exam
from sqlalchemy import text


def migrate_timed_exam_fields():
    """Add timed exam columns to the exams table if they don't exist."""
    db = SessionLocal()
    
    try:
        print("=" * 80)
        print("MIGRATING EXAMS TABLE - ADDING TIMED EXAM FIELDS")
        print("=" * 80)
        print("\nAdding timed exam columns to exams table...")
        
        # SQLite syntax for adding columns
        migrations = [
            ("is_timed", "BOOLEAN DEFAULT 0"),
            ("duration_hours", "INTEGER"),
            ("duration_minutes", "INTEGER"),
            ("student_exam_start_time", "DATETIME")
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
                    if "BOOLEAN" in nullable_def:
                        # SQLite doesn't have native BOOLEAN, use INTEGER (0 or 1)
                        db.execute(text(f"ALTER TABLE exams ADD COLUMN {column_name} INTEGER DEFAULT 0"))
                    elif "INTEGER" in nullable_def:
                        db.execute(text(f"ALTER TABLE exams ADD COLUMN {column_name} INTEGER"))
                    elif "DATETIME" in nullable_def:
                        db.execute(text(f"ALTER TABLE exams ADD COLUMN {column_name} DATETIME"))
                    else:
                        db.execute(text(f"ALTER TABLE exams ADD COLUMN {column_name} {nullable_def}"))
                    db.commit()
                except Exception as e:
                    print(f"  [X] Error adding column {column_name}: {e}")
                    db.rollback()
        
        print("\n[SUCCESS] Migration complete!")
        print("\nThe exams table has been extended with the following fields:")
        print("  - is_timed (Boolean, default False)")
        print("  - duration_hours (Integer, nullable)")
        print("  - duration_minutes (Integer, nullable)")
        print("  - student_exam_start_time (DateTime, nullable)")
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"\n[ERROR] Error during migration: {e}")
        db.rollback()
        print("\nYou may need to manually add the columns or recreate the table.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate_timed_exam_fields()
