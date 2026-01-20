"""Test script to diagnose LLM exam generation issues."""
import asyncio
import logging
import sys
from app.core.grading.generator import QuestionGenerator
from app.settings import get_settings

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_exam_generation():
    """Test exam generation with detailed logging."""
    settings = get_settings()
    print(f"\n{'='*60}")
    print("LLM Exam Generation Diagnostic Test")
    print(f"{'='*60}")
    print(f"Model: {settings.llm_model}")
    print(f"Temperature: {settings.llm_temperature}")
    print(f"Max Tokens: {settings.llm_max_tokens}")
    print(f"API Key present: {bool(settings.together_api_key)}")
    print(f"{'='*60}\n")
    
    if not settings.together_api_key:
        print("ERROR: TOGETHER_API_KEY is not set!")
        print("Please set it in your .env file or as an environment variable.")
        return
    
    generator = QuestionGenerator()
    
    try:
        num_questions = 8  # Test with 8 questions like the user reported
        print(f"Generating exam with {num_questions} questions on topic: 'Data Structures'...")
        print("-" * 60)
        
        generated_exam = await generator.generate_exam(
            topic="Data Structures",
            num_questions=num_questions,
            additional_details=""
        )
        
        print("\n" + "="*60)
        print("SUCCESS! Exam generated successfully!")
        print("="*60)
        print(f"Number of questions: {len(generated_exam.questions)}\n")
        
        for q in generated_exam.questions:
            print(f"Question {q.question_number}:")
            print(f"  Text: {q.question_text[:100]}...")
            print(f"  Context: {q.context[:80]}..." if q.context else "  Context: None")
            print(f"  Rubric: {q.rubric[:80]}..." if q.rubric else "  Rubric: None")
            print()
        
    except Exception as e:
        print("\n" + "="*60)
        print("ERROR: Exam generation failed!")
        print("="*60)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        print("\nFull traceback:")
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(test_exam_generation())
