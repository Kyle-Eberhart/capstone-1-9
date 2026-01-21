"""Database initialization script."""
import logging
from app.db.base import Base, engine
from app.logging_config import setup_logging
# Import all models to ensure they're registered with Base.metadata
from app.db.models import Student, Exam, Question, Teacher, ExamTemplate, CustomQuestion, ExamAccess

setup_logging()
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Dropping existing tables...")
    # Drop all existing tables to ensure clean schema
    Base.metadata.drop_all(bind=engine)
    
    logger.info("Creating database tables...")
    # Create all tables with current schema
    Base.metadata.create_all(bind=engine)
    
    logger.info("Database tables created successfully!")

