"""
Gemini API client wrapper.
Provides a thin wrapper around the Google GenAI SDK for text generation.
"""

import time

from loguru import logger

from src.core.config import settings


class GeminiError(Exception):
    """Custom exception for Gemini-related errors."""
    pass


class GeminiClient:
    """
    Wrapper around Google GenAI SDK for Gemini API.
    Handles authentication, rate limiting, and error handling.
    """

    def __init__(self, model: str = "gemini-2.5-flash"):
        """
        Initialize Gemini client.

        Args:
            model: Model name to use (default: gemini-2.5-flash)
        """
        self.model = model
        self._client = None
        self._last_request_time: float | None = None
        self._min_request_interval = 1.0  # Minimum seconds between requests

    def _get_client(self):
        """Lazy initialization of the Gemini client."""
        if self._client is None:
            api_key = settings.gemini_api_key
            if not api_key:
                raise GeminiError(
                    "GEMINI_API_KEY not set. Please set it in your .env file."
                )

            try:
                from google import genai
                self._client = genai.Client(api_key=api_key)
                logger.debug("Gemini client initialized")
            except ImportError:
                raise GeminiError(
                    "google-genai package not installed. Run: pip install google-genai"
                )
            except Exception as e:
                raise GeminiError(f"Failed to initialize Gemini client: {e}")

        return self._client

    def _rate_limit_wait(self) -> None:
        """Enforce rate limiting between requests."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self._min_request_interval:
                sleep_time = self._min_request_interval - elapsed
                logger.debug(f"Rate limiting Gemini: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
        self._last_request_time = time.time()

    def generate_text(
        self,
        user_prompt: str,
        system_prompt: str | None = None,
        max_retries: int = 3
    ) -> str:
        """
        Generate text using Gemini.

        Args:
            user_prompt: The user's prompt/question
            system_prompt: Optional system instruction
            max_retries: Maximum number of retry attempts

        Returns:
            Generated text response

        Raises:
            GeminiError: If generation fails after retries
        """
        if not settings.use_gemini_assistant:
            raise GeminiError("Gemini assistant is disabled in settings")

        client = self._get_client()
        self._rate_limit_wait()

        last_error = None
        for attempt in range(max_retries):
            try:
                # Build the content
                contents = user_prompt

                # Generate response
                config = None
                if system_prompt:
                    from google.genai import types
                    config = types.GenerateContentConfig(
                        system_instruction=system_prompt
                    )

                response = client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config
                )

                # Extract text from response
                if hasattr(response, 'text'):
                    return response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    return response.candidates[0].content.parts[0].text
                else:
                    raise GeminiError("Unexpected response format from Gemini")

            except Exception as e:
                last_error = e
                logger.warning(f"Gemini attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        raise GeminiError(f"Gemini generation failed after {max_retries} attempts: {last_error}")

    def is_available(self) -> bool:
        """
        Check if Gemini is available and configured.

        Returns:
            True if Gemini can be used, False otherwise
        """
        if not settings.use_gemini_assistant:
            return False

        if not settings.gemini_api_key:
            return False

        try:
            self._get_client()
            return True
        except GeminiError:
            return False


# Module-level instance
gemini_client = GeminiClient()


def generate_text(user_prompt: str, system_prompt: str | None = None) -> str:
    """Convenience function for text generation."""
    return gemini_client.generate_text(user_prompt, system_prompt)


def is_gemini_available() -> bool:
    """Check if Gemini is available."""
    return gemini_client.is_available()
