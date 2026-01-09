"""Quick test to verify LLM is working."""
import asyncio
from app.core.llm.client import LLMClient
from app.settings import get_settings

async def test_llm():
    """Test if LLM client can make a call."""
    get_settings.cache_clear()
    settings = get_settings()
    
    print(f"API Key: {'SET (' + settings.together_api_key[:10] + '...)' if settings.together_api_key else 'NOT SET'}")
    print(f"Model: {settings.llm_model}")
    print()
    
    if not settings.together_api_key:
        print("❌ API key not set! Cannot test LLM.")
        return
    
    print("Testing LLM client...")
    client = LLMClient()
    
    try:
        test_prompt = '{"test": "hello"}'
        result = await client.generate_json(
            "Respond with this exact JSON: " + test_prompt,
            "You are a JSON formatter. Only return valid JSON."
        )
        print("✅ LLM is working! Got response:", result)
    except Exception as e:
        print(f"❌ LLM test failed: {e}")
        print("   This means the API key might be invalid or there's a connection issue.")

if __name__ == "__main__":
    asyncio.run(test_llm())

