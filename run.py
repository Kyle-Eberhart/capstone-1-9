"""Simple script to run the application."""
import uvicorn
from pathlib import Path

from app.settings import get_settings


def prompt_for_api_key():
    """Interactively prompt user for API key if not set."""
    get_settings.cache_clear()
    settings = get_settings()
    
    # Check if API key is already set
    if settings.together_api_key:
        return settings
    
    # Prompt user
    print("\n" + "="*60)
    print("🔑 API Key Setup")
    print("="*60)
    print("\nThe app can run in two modes:")
    print("  1. Demo Mode (no API key) - Uses pre-written questions and basic grading")
    print("  2. AI Mode (with API key) - Uses AI-generated questions and AI grading")
    print("\nTo enable AI features, you'll need a Together.ai API key.")
    print("Get one for free at: https://together.ai/")
    print("\n" + "-"*60)
    
    response = input("\nDo you want to enter an API key now? (y/n, or press Enter to skip): ").strip().lower()
    
    if response in ['y', 'yes']:
        api_key = input("\nEnter your Together.ai API key: ").strip()
        
        if api_key:
            # Save to .env file
            env_path = Path(__file__).parent / ".env"
            
            # Read existing .env file if it exists
            env_content = ""
            if env_path.exists():
                env_content = env_path.read_text(encoding='utf-8')
            
            # Update or add TOGETHER_API_KEY
            lines = env_content.split('\n') if env_content else []
            updated = False
            for i, line in enumerate(lines):
                if line.startswith('TOGETHER_API_KEY='):
                    lines[i] = f'TOGETHER_API_KEY={api_key}'
                    updated = True
                    break
            
            if not updated:
                # Add new line if doesn't exist
                if lines and lines[-1]:  # Add newline separator if there's existing content
                    lines.append('')
                lines.append(f'TOGETHER_API_KEY={api_key}')
            
            # Ensure DATABASE_URL exists
            has_db_url = any(line.startswith('DATABASE_URL=') for line in lines)
            if not has_db_url:
                lines.append('DATABASE_URL=sqlite:///./exam_grader.db')
            
            # Write back to .env
            env_path.write_text('\n'.join(lines), encoding='utf-8')
            
            print("\n✅ API key saved to .env file!")
            print("   The app will now use AI features when you restart.\n")
            
            # Clear cache and reload settings
            get_settings.cache_clear()
            settings = get_settings()
        else:
            print("\n⚠️  No API key entered. Running in demo mode.\n")
    else:
        print("\n⏭️  Skipping API key setup. Running in demo mode.")
        print("   (You can add an API key later by editing the .env file or running this script again)\n")
    
    return settings


if __name__ == "__main__":
    settings = prompt_for_api_key()
    
    print("="*60)
    print("🚀 Starting AI Oral Exam Grader")
    print("="*60)
    print(f"LLM_MODEL = {settings.llm_model}")
    api_key_preview = settings.together_api_key[:5] + "…" if settings.together_api_key else "(not set - using demo mode)"
    print(f"TOGETHER_API_KEY = {api_key_preview}")
    print("="*60)
    print("\n📍 Server starting at http://localhost:8000")
    print("   Press CTRL+C to stop\n")
    
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

