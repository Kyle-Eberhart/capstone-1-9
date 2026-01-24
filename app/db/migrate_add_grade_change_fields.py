"""Migration script to add grade_change_reason and grade_changed_by columns to exams table."""
from app.db.session import SessionLocal
from sqlalchemy import text


def migrate():
    """Add grade_change_reason and grade_changed_by columns to exams table."""
    db = SessionLocal()
    
    try:
        print("=" * 80)
        print("MIGRATING EXAMS TABLE - Adding Grade Change Fields")
        print("=" * 80)
        print("\nAdding new columns to exams table...")
        
        migrations = [
            ("grade_change_reason", "TEXT"),
            ("grade_changed_by", "INTEGER")
        ]
        
        for column_name, column_def in migrations:
            try:
                # Check if column exists first
                result = db.execute(text(
                    f"SELECT COUNT(*) as count FROM pragma_table_info('exams') WHERE name='{column_name}'"
                ))
                exists = result.fetchone()[0] > 0
                
                if not exists:
                    print(f"  [+] Adding column: {column_name}")
                    db.execute(text(f"ALTER TABLE exams ADD COLUMN {column_name} {column_def}"))
                    db.commit()
                else:
                    print(f"  [-] Column {column_name} already exists, skipping")
            except Exception as e:
                print(f"  [X] Error adding column {column_name}: {e}")
                db.rollback()
        
        print("\n[SUCCESS] Migration complete!")
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"\n[ERROR] Error during migration: {e}")
        db.rollback()
        print("\nYou may need to manually add the columns using SQL:")
        print("  ALTER TABLE exams ADD COLUMN grade_change_reason TEXT;")
        print("  ALTER TABLE exams ADD COLUMN grade_changed_by INTEGER;")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
