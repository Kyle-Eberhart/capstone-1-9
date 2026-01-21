"""Application settings and configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Together.ai API Configuration
    together_api_key: str = ""
    llm_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"  # Serverless model (no dedicated endpoint needed)
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2000
    
    # Database Configuration
    database_url: str = "sqlite:///./exam_grader.db"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Convert relative path to absolute if it's a relative SQLite path
        if self.database_url.startswith("sqlite:///./"):
            from pathlib import Path
            db_name = self.database_url.replace("sqlite:///./", "")
            project_root = Path(__file__).parent.parent
            db_path = project_root / db_name
            self.database_url = f"sqlite:///{db_path.absolute()}"
    
    # Application Settings
    secret_key: str = "change-this-in-production"
    environment: str = "development"
    
    # Exam Configuration
    exam_question_count: int = 3
    exam_time_limit_minutes: int = 60
    
    class Config:
        # Use absolute path to .env file relative to this file's location
        # __file__ is app/settings.py, so parent.parent is project root
        env_file = str(Path(__file__).parent.parent / ".env")
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

