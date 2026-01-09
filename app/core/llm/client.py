"""LLM client using Together.ai for JSON-based prompts."""
import json
import asyncio
import logging
from typing import Optional
from together import Together
from app.settings import get_settings

logger = logging.getLogger(__name__)

class LLMClient:
    """Client to interact with an LLM via Together.ai."""

    def __init__(self):
        """Initialize LLM client. Together client is created lazily only when needed."""
        self.model = None
        self._client: Optional[Together] = None
        self._client_api_key: Optional[str] = None  # Track which API key was used for client
    
    def _get_settings(self):
        """Get fresh settings (always reads from .env file, respecting cache clearing)."""
        # Clear cache to ensure we get latest from .env file
        get_settings.cache_clear()
        return get_settings()
    
    def _get_api_key(self) -> str:
        """Get API key dynamically from settings."""
        settings = self._get_settings()
        return settings.together_api_key or ""
    
    def _get_model(self) -> str:
        """Get model dynamically from settings."""
        if self.model is None:
            settings = self._get_settings()
            self.model = settings.llm_model
        return self.model
    
    def _get_client(self) -> Together:
        """Lazily initialize and return the Together client."""
        api_key = self._get_api_key()
        
        # Recreate client if API key changed
        if self._client is None or self._client_api_key != api_key:
            if not api_key:
                raise RuntimeError(
                    "TOGETHER_API_KEY is not set. "
                    "Set it as an environment variable or in .env file to use LLM features. "
                    "The app will use fallback questions/grading when the API key is missing."
                )
            self._client = Together(api_key=api_key)
            self._client_api_key = api_key
        return self._client

    async def generate_json(self, prompt: str, system_prompt: str = None) -> dict:
        """
        Generate a JSON response from the LLM.

        Args:
            prompt (str): The user prompt.
            system_prompt (str, optional): System-level instructions.

        Returns:
            dict: Parsed JSON response from the LLM.
            
        Raises:
            RuntimeError: If API key is missing or LLM request fails.
        """
        # Check if API key is available before attempting to use LLM
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError(
                "TOGETHER_API_KEY is not set. Cannot generate LLM response. "
                "Use fallback functionality instead."
            )
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Together SDK is synchronous, wrap in async
        loop = asyncio.get_event_loop()

        def call_llm_with_retry():
            # Simple retry for temporary server issues (503)
            client = self._get_client()
            model = self._get_model()
            for _ in range(3):
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    logger.warning(f"LLM call failed, retrying: {e}")
            # If all retries fail
            raise RuntimeError("LLM request failed after 3 attempts")

        result_text = await loop.run_in_executor(None, call_llm_with_retry)

        # Clean up response - remove markdown code fences if present
        cleaned_text = result_text.strip()
        if cleaned_text.startswith("```"):
            # Remove opening code fence (```json or ```)
            cleaned_text = cleaned_text.split("\n", 1)[1] if "\n" in cleaned_text else cleaned_text[3:]
            # Remove closing code fence
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()
        
        # Attempt to parse JSON
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            # Provide debugging info if JSON is invalid
            logger.error(f"Failed to parse LLM response as JSON. Original: {result_text[:200]}")
            raise e