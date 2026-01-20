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
            settings = self._get_settings()
            temperature = settings.llm_temperature
            max_tokens = settings.llm_max_tokens
            logger.info(f"Calling LLM API - Model: {model}, Temperature: {temperature}, Max tokens: {max_tokens}, API Key present: {bool(api_key)}")
            last_error = None
            for attempt in range(3):
                try:
                    logger.debug(f"LLM API call attempt {attempt + 1}/3")
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    content = response.choices[0].message.content
                    logger.info(f"LLM API call successful. Response length: {len(content)} characters")
                    logger.debug(f"LLM response preview (first 500 chars): {content[:500]}")
                    return content
                except Exception as e:
                    last_error = e
                    error_type = type(e).__name__
                    error_msg = str(e)
                    logger.error(f"LLM API call failed on attempt {attempt + 1}/3 - Type: {error_type}, Error: {error_msg}")
                    if hasattr(e, 'status_code'):
                        logger.error(f"HTTP Status Code: {e.status_code}")
                    if hasattr(e, 'response'):
                        logger.error(f"Response details: {e.response}")
            # If all retries fail
            error_summary = f"LLM request failed after 3 attempts. Last error: {type(last_error).__name__}: {str(last_error)}"
            logger.error(error_summary)
            raise RuntimeError(error_summary) from last_error

        result_text = await loop.run_in_executor(None, call_llm_with_retry)

        # Clean up response - extract JSON even if there's text before/after
        cleaned_text = result_text.strip()
        
        # Remove markdown code fences if present
        if cleaned_text.startswith("```"):
            # Remove opening code fence (```json or ```)
            cleaned_text = cleaned_text.split("\n", 1)[1] if "\n" in cleaned_text else cleaned_text[3:]
            # Remove closing code fence
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()
        
        # Try to find JSON object in the response (in case there's explanatory text)
        # Look for the first { and last } to extract JSON
        first_brace = cleaned_text.find('{')
        if first_brace != -1:
            # Find the matching closing brace
            brace_count = 0
            last_brace = -1
            for i in range(first_brace, len(cleaned_text)):
                if cleaned_text[i] == '{':
                    brace_count += 1
                elif cleaned_text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        last_brace = i
                        break
            
            if last_brace != -1:
                # Extract the JSON portion
                cleaned_text = cleaned_text[first_brace:last_brace + 1]
        
        # Attempt to parse JSON
        try:
            parsed_json = json.loads(cleaned_text)
            logger.debug(f"Successfully parsed JSON. Keys: {list(parsed_json.keys()) if isinstance(parsed_json, dict) else 'N/A'}")
            return parsed_json
        except json.JSONDecodeError as e:
            # Provide comprehensive debugging info if JSON is invalid
            logger.error(f"Failed to parse LLM response as JSON")
            logger.error(f"JSONDecodeError: {str(e)}")
            logger.error(f"Cleaned text length: {len(cleaned_text)} characters")
            logger.error(f"Cleaned text preview (first 1000 chars): {cleaned_text[:1000]}")
            logger.error(f"Original response length: {len(result_text)} characters")
            logger.error(f"Original response preview (first 1000 chars): {result_text[:1000]}")
            logger.error(f"First brace position: {first_brace}, Last brace position: {last_brace if 'last_brace' in locals() else 'N/A'}")
            raise json.JSONDecodeError(
                f"Failed to parse LLM response as JSON: {str(e)}. Response preview: {result_text[:500]}",
                e.doc,
                e.pos
            ) from e