"""
Yahoo Finance HTML scraper.
Fallback data source when yfinance fails.
Uses httpx for HTTP requests and BeautifulSoup for parsing.
"""

import time
from datetime import datetime
from typing import Optional
import json

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.core.config import settings
from src.core.models import Quote


class HTMLScraperError(Exception):
    """Custom exception for HTML scraping errors."""
    pass


class SelectorConfig:
    """
    CSS selectors for Yahoo Finance quote page.
    These may need to be updated if Yahoo changes their markup.
    """
    
    # Price selectors (in order of preference)
    PRICE_SELECTORS = [
        "fin-streamer[data-field='regularMarketPrice']",
        "[data-testid='qsp-price']",
        ".livePrice span",
    ]
    
    # Currency/change selectors
    CHANGE_SELECTORS = [
        "fin-streamer[data-field='regularMarketChange']",
        "[data-testid='qsp-price-change']",
    ]
    
    CHANGE_PERCENT_SELECTORS = [
        "fin-streamer[data-field='regularMarketChangePercent']",
        "[data-testid='qsp-price-change-percent']",
    ]


class YahooHTMLScraper:
    """
    Yahoo Finance HTML scraper for quote data.
    Uses BeautifulSoup for parsing and supports selector repair via Gemini.
    """
    
    BASE_URL = "https://finance.yahoo.com/quote"
    
    def __init__(self):
        self.rate_limit = settings.rate_limit_requests_per_second
        self._last_request_time: Optional[float] = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        # Track current selectors (can be updated by Gemini)
        self.price_selectors = list(SelectorConfig.PRICE_SELECTORS)
        self.change_selectors = list(SelectorConfig.CHANGE_SELECTORS)
        self.change_percent_selectors = list(SelectorConfig.CHANGE_PERCENT_SELECTORS)

    def _rate_limit_wait(self) -> None:
        """Enforce rate limiting between requests."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            min_interval = 1.0 / self.rate_limit
            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def fetch_html(self, url: str, timeout: float = 15.0) -> str:
        """
        Fetch HTML content from a URL.
        
        Args:
            url: URL to fetch
            timeout: Request timeout in seconds
        
        Returns:
            HTML content as string
        
        Raises:
            HTMLScraperError: If request fails
        """
        self._rate_limit_wait()
        
        try:
            with httpx.Client(timeout=timeout, headers=self.headers, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for {url}")
            raise HTMLScraperError(f"HTTP {e.response.status_code}: {url}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error for {url}: {e}")
            raise HTMLScraperError(f"Request failed: {url}") from e

    def _find_element_with_selectors(
        self,
        soup: BeautifulSoup,
        selectors: list,
        field_name: str
    ) -> Optional[str]:
        """
        Try multiple selectors to find an element's text.
        
        Args:
            soup: BeautifulSoup object
            selectors: List of CSS selectors to try
            field_name: Field name for logging
        
        Returns:
            Element text if found, None otherwise
        """
        for selector in selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    # Try to get value from data-value attribute first
                    value = element.get("data-value") or element.get("value")
                    if value:
                        return str(value)
                    # Fall back to text content
                    text = element.get_text(strip=True)
                    if text:
                        return text
            except Exception as e:
                logger.debug(f"Selector '{selector}' failed for {field_name}: {e}")
        
        return None

    def parse_quote_from_html(self, html: str, ticker: str) -> Quote:
        """
        Parse quote data from Yahoo Finance HTML.
        
        Args:
            html: HTML content
            ticker: Stock ticker symbol
        
        Returns:
            Quote object
        
        Raises:
            HTMLScraperError: If parsing fails
        """
        soup = BeautifulSoup(html, "lxml")
        
        # Find price
        price_str = self._find_element_with_selectors(
            soup, self.price_selectors, "price"
        )
        
        if not price_str:
            # Try to extract from JSON-LD or script data
            price_str = self._extract_price_from_scripts(soup)
        
        if not price_str:
            raise HTMLScraperError(f"Could not find price for {ticker}")
        
        # Clean and parse price
        try:
            price = float(price_str.replace(",", "").replace("$", ""))
        except ValueError:
            raise HTMLScraperError(f"Invalid price format: {price_str}")
        
        # Find change (optional)
        change = None
        change_str = self._find_element_with_selectors(
            soup, self.change_selectors, "change"
        )
        if change_str:
            try:
                change = float(change_str.replace(",", "").replace("+", ""))
            except ValueError:
                pass
        
        # Find change percent (optional)
        change_percent = None
        change_pct_str = self._find_element_with_selectors(
            soup, self.change_percent_selectors, "change_percent"
        )
        if change_pct_str:
            try:
                # Remove parentheses and percent sign
                cleaned = change_pct_str.replace("(", "").replace(")", "").replace("%", "").replace("+", "")
                change_percent = float(cleaned)
            except ValueError:
                pass
        
        # Determine currency (default to USD)
        currency = self._extract_currency(soup) or "USD"
        
        quote = Quote(
            ticker=ticker.upper(),
            price=price,
            currency=currency,
            timestamp=datetime.utcnow(),
            source="yahoo_html",
            change=change,
            change_percent=change_percent,
        )
        
        logger.info(f"Parsed HTML quote for {ticker}: ${quote.price:.2f}")
        return quote

    def _extract_price_from_scripts(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Try to extract price from embedded JSON/script data.
        
        Args:
            soup: BeautifulSoup object
        
        Returns:
            Price string if found, None otherwise
        """
        # Look for rootAppData or similar JSON structures
        for script in soup.find_all("script"):
            text = script.string
            if not text:
                continue
            
            # Look for regularMarketPrice in JSON
            if "regularMarketPrice" in text:
                try:
                    # Find JSON-like structure
                    start = text.find("{")
                    end = text.rfind("}") + 1
                    if start != -1 and end > start:
                        # Try to find price pattern
                        import re
                        match = re.search(r'"regularMarketPrice":\s*\{[^}]*"raw":\s*([\d.]+)', text)
                        if match:
                            return match.group(1)
                except Exception:
                    pass
        
        return None

    def _extract_currency(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Try to extract currency from the page.
        
        Args:
            soup: BeautifulSoup object
        
        Returns:
            Currency code if found, None otherwise
        """
        # Look for currency indicator in the page
        currency_indicators = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF"]
        
        # Check meta tags
        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            for curr in currency_indicators:
                if curr in content:
                    return curr
        
        return None

    def get_quote(self, ticker: str) -> Quote:
        """
        Get quote for a ticker via HTML scraping.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            Quote object
        
        Raises:
            HTMLScraperError: If scraping fails
        """
        url = f"{self.BASE_URL}/{ticker.upper()}"
        
        try:
            html = self.fetch_html(url)
            return self.parse_quote_from_html(html, ticker)
        except Exception as e:
            logger.error(f"HTML scraping failed for {ticker}: {e}")
            raise HTMLScraperError(f"Failed to scrape {ticker}: {e}") from e

    def get_html_snippet(self, ticker: str, max_length: int = 5000) -> str:
        """
        Get a snippet of HTML for the ticker page.
        Useful for Gemini selector analysis.
        
        Args:
            ticker: Stock ticker symbol
            max_length: Maximum snippet length
        
        Returns:
            HTML snippet
        """
        url = f"{self.BASE_URL}/{ticker.upper()}"
        html = self.fetch_html(url)
        
        # Try to extract relevant section
        soup = BeautifulSoup(html, "lxml")
        
        # Find the quote section
        quote_section = soup.find("section", {"data-testid": "quote-price"})
        if quote_section:
            return str(quote_section)[:max_length]
        
        # Fall back to body truncated
        body = soup.find("body")
        if body:
            return str(body)[:max_length]
        
        return html[:max_length]

    def update_selectors(self, new_price_selector: Optional[str] = None):
        """
        Update selectors (e.g., from Gemini repair).
        
        Args:
            new_price_selector: New CSS selector for price
        """
        if new_price_selector:
            # Add to the front of the list
            if new_price_selector not in self.price_selectors:
                self.price_selectors.insert(0, new_price_selector)
                logger.info(f"Added new price selector: {new_price_selector}")


# Module-level instance
html_scraper = YahooHTMLScraper()


def get_quote_html(ticker: str) -> Quote:
    """Convenience function to get quote via HTML scraping."""
    return html_scraper.get_quote(ticker)


def get_html_snippet(ticker: str) -> str:
    """Convenience function to get HTML snippet."""
    return html_scraper.get_html_snippet(ticker)
