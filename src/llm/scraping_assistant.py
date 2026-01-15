"""
Scraping assistant using Gemini LLM.
Provides utilities for selector discovery, repair, and validation.
"""

import json

from loguru import logger

from .gemini_client import GeminiError, gemini_client


class ScrapingAssistant:
    """
    LLM-powered assistant for web scraping tasks.
    Uses Gemini to analyze HTML and suggest/repair CSS selectors.
    """

    def __init__(self):
        self.client = gemini_client

    def suggest_selectors(
        self,
        html_snippet: str,
        field_description: str
    ) -> dict[str, str | None]:
        """
        Suggest CSS selectors for extracting data from HTML.

        Args:
            html_snippet: HTML content to analyze
            field_description: Description of the data to extract
                              (e.g., "stock price and currency")

        Returns:
            Dict with suggested selectors (e.g., {"price_selector": "...", "currency_selector": "..."})

        Raises:
            GeminiError: If Gemini fails to respond properly
        """
        system_prompt = """You are an expert web scraping assistant.
Given HTML, you propose robust CSS selectors.
Always prefer selectors that use data attributes or unique identifiers.
Avoid class-based selectors that look auto-generated or likely to change.
Return ONLY valid JSON without any markdown formatting or explanation."""

        user_prompt = f'''Analyze this HTML and identify CSS selectors for: {field_description}

HTML:
```html
{html_snippet[:3000]}
```

Return a JSON object with selectors. Example format:
{{"price_selector": "fin-streamer[data-field='regularMarketPrice']", "currency_selector": null}}

If a selector cannot be determined, set its value to null.
Return ONLY the JSON object, no other text.'''

        try:
            response = self.client.generate_text(user_prompt, system_prompt)

            # Extract JSON from response
            result = self._parse_json_response(response)
            logger.info(f"Gemini suggested selectors: {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to get selector suggestions: {e}")
            raise GeminiError(f"Selector suggestion failed: {e}")

    def repair_selector(
        self,
        html_snippet: str,
        old_selector: str,
        field_description: str
    ) -> str:
        """
        Suggest a repaired selector when the old one stops working.

        Args:
            html_snippet: Current HTML content
            old_selector: The selector that stopped working
            field_description: What the selector should target

        Returns:
            New CSS selector string

        Raises:
            GeminiError: If repair fails
        """
        system_prompt = """You are a web scraping assistant helping maintain CSS selectors.
When a selector breaks, you analyze the new HTML and propose a replacement.
Return ONLY the new CSS selector, nothing else."""

        user_prompt = f'''The CSS selector for "{field_description}" stopped working.

Old selector: {old_selector}

Current HTML snippet:
```html
{html_snippet[:3000]}
```

Propose a new CSS selector that targets the same data.
Return ONLY the selector string, no explanation or quotes.'''

        try:
            response = self.client.generate_text(user_prompt, system_prompt)
            new_selector = response.strip().strip('"\'`')

            logger.info(f"Gemini repaired selector: '{old_selector}' -> '{new_selector}'")
            return new_selector

        except Exception as e:
            logger.error(f"Failed to repair selector: {e}")
            raise GeminiError(f"Selector repair failed: {e}")

    def validate_quote(
        self,
        quote_data: dict,
        html_context: str
    ) -> dict[str, any]:
        """
        Validate scraped quote data for plausibility.

        Args:
            quote_data: Scraped quote as dict
            html_context: Surrounding HTML for context

        Returns:
            Dict with 'valid' boolean and 'reason' string
        """
        system_prompt = """You are a financial data validation assistant.
Check if scraped stock prices look plausible.
Consider: reasonable price ranges, proper currency, data consistency."""

        user_prompt = f'''Validate this scraped stock quote:

Quote data:
```json
{json.dumps(quote_data, indent=2, default=str)}
```

HTML context (truncated):
```html
{html_context[:1500]}
```

Does this data look valid and plausible?
Return JSON: {{"valid": true/false, "reason": "brief explanation"}}'''

        try:
            response = self.client.generate_text(user_prompt, system_prompt)
            result = self._parse_json_response(response)

            if 'valid' not in result:
                result = {'valid': True, 'reason': 'Unable to fully validate'}

            logger.debug(f"Quote validation result: {result}")
            return result

        except Exception as e:
            logger.warning(f"Quote validation failed: {e}")
            # Return valid by default if validation fails
            return {'valid': True, 'reason': f'Validation error: {e}'}

    def explain_error(
        self,
        error_message: str,
        html_snippet: str,
        selector: str
    ) -> str:
        """
        Get an explanation for a scraping error.

        Args:
            error_message: The error that occurred
            html_snippet: HTML that was being parsed
            selector: Selector that was used

        Returns:
            Human-readable explanation
        """
        system_prompt = """You are a web scraping debugging assistant.
Explain scraping errors clearly and suggest fixes."""

        user_prompt = f'''A scraping error occurred:

Error: {error_message}
Selector used: {selector}

HTML snippet:
```html
{html_snippet[:2000]}
```

Explain what likely went wrong and suggest how to fix it.
Be concise (2-3 sentences max).'''

        try:
            response = self.client.generate_text(user_prompt, system_prompt)
            return response.strip()
        except Exception as e:
            return f"Unable to explain error: {e}"

    def _parse_json_response(self, response: str) -> dict:
        """
        Extract and parse JSON from Gemini response.

        Args:
            response: Raw response text

        Returns:
            Parsed JSON as dict

        Raises:
            ValueError: If JSON cannot be extracted
        """
        # Remove markdown code blocks if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        # Find JSON object
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:
            raise ValueError(f"No JSON found in response: {response[:200]}")

        json_str = text[start:end + 1]
        return json.loads(json_str)

    def is_available(self) -> bool:
        """Check if the scraping assistant is available."""
        return self.client.is_available()


# Module-level instance
scraping_assistant = ScrapingAssistant()


def suggest_selectors(html_snippet: str, field_description: str) -> dict[str, str | None]:
    """Convenience function for selector suggestion."""
    return scraping_assistant.suggest_selectors(html_snippet, field_description)


def repair_selector(html_snippet: str, old_selector: str, field_description: str) -> str:
    """Convenience function for selector repair."""
    return scraping_assistant.repair_selector(html_snippet, old_selector, field_description)


def validate_quote(quote_data: dict, html_context: str) -> dict[str, any]:
    """Convenience function for quote validation."""
    return scraping_assistant.validate_quote(quote_data, html_context)
