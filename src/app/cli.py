"""
Command-line interface for the Yahoo Finance Stock Scraper.
Provides commands for fetching quotes, history, and batch processing.
"""

import argparse
import json
import sys
from datetime import datetime

from loguru import logger

# Configure loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
)


def setup_logging(verbose: bool = False):
    """Configure logging based on verbosity."""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=level,
    )


def cmd_quote(args):
    """Handle quote command."""
    from src.app.data_fetcher import get_quote
    from src.core.storage import save_quote

    ticker = args.ticker.upper()

    try:
        quote, metadata = get_quote(ticker)

        # Display result
        print(f"\n{'='*50}")
        print(f"  {quote.ticker} Quote")
        print(f"{'='*50}")
        print(f"  Price:    ${quote.price:,.2f} {quote.currency}")

        if quote.change is not None:
            change_sign = "+" if quote.change >= 0 else ""
            print(f"  Change:   {change_sign}{quote.change:,.2f}")

        if quote.change_percent is not None:
            pct_sign = "+" if quote.change_percent >= 0 else ""
            print(f"  Change %: {pct_sign}{quote.change_percent:.2f}%")

        if quote.volume:
            print(f"  Volume:   {quote.volume:,}")

        print(f"  Source:   {quote.source}")
        print(f"  Time:     {quote.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"{'='*50}\n")

        # Save if requested
        if args.save:
            filepath = save_quote(quote)
            print(f"Saved to: {filepath}")

        # JSON output if requested
        if args.json:
            print(json.dumps(quote.model_dump(), default=str, indent=2))

    except Exception as e:
        logger.error(f"Failed to get quote for {ticker}: {e}")
        sys.exit(1)


def cmd_history(args):
    """Handle history command."""

    from src.app.data_fetcher import get_history
    from src.core.storage import save_history

    ticker = args.ticker.upper()

    # Parse dates if provided
    start = None
    end = None

    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d").date()

    try:
        bars = get_history(ticker, start=start, end=end, period=args.period)

        if not bars:
            print(f"No history data found for {ticker}")
            return

        # Display summary
        print(f"\n{'='*60}")
        print(f"  {ticker} Historical Data ({len(bars)} bars)")
        print(f"{'='*60}")
        print(f"  Period: {bars[0].date.strftime('%Y-%m-%d')} to {bars[-1].date.strftime('%Y-%m-%d')}")

        # Show last 5 bars
        print("\n  Latest bars:")
        print(f"  {'Date':<12} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}")
        print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*12}")

        for bar in bars[-5:]:
            print(f"  {bar.date.strftime('%Y-%m-%d'):<12} {bar.open:>10.2f} {bar.high:>10.2f} {bar.low:>10.2f} {bar.close:>10.2f} {bar.volume:>12,}")

        print(f"{'='*60}\n")

        # Save if requested
        if args.save:
            filepath = save_history(bars, ticker, format=args.format)
            print(f"Saved to: {filepath}")

        # JSON output if requested
        if args.json:
            data = [bar.model_dump() for bar in bars]
            print(json.dumps(data, default=str, indent=2))

    except Exception as e:
        logger.error(f"Failed to get history for {ticker}: {e}")
        sys.exit(1)


def cmd_batch(args):
    """Handle batch command."""
    from src.app.data_fetcher import data_fetcher
    from src.core.storage import save_quotes

    tickers = [t.strip().upper() for t in args.tickers.split(",")]

    print(f"\nFetching quotes for {len(tickers)} tickers...")
    print(f"{'='*60}")

    results = data_fetcher.get_multiple_quotes(tickers)

    quotes = []
    for quote, _metadata in results:
        quotes.append(quote)
        change_str = ""
        if quote.change_percent is not None:
            sign = "+" if quote.change_percent >= 0 else ""
            change_str = f" ({sign}{quote.change_percent:.2f}%)"

        print(f"  {quote.ticker:<6} ${quote.price:>10,.2f} {quote.currency}{change_str}")

    print(f"{'='*60}")
    print(f"Successfully fetched {len(quotes)}/{len(tickers)} quotes\n")

    # Save if requested
    if args.save and quotes:
        filepath = save_quotes(quotes)
        print(f"Saved to: {filepath}")

    # JSON output if requested
    if args.json:
        data = [q.model_dump() for q in quotes]
        print(json.dumps(data, default=str, indent=2))


def cmd_test(args):
    """Test connection and configuration."""
    from src.core.config import settings

    print(f"\n{'='*50}")
    print("  Configuration Test")
    print(f"{'='*50}")

    print("\n  Settings:")
    print(f"    USE_YFINANCE:         {settings.use_yfinance}")
    print(f"    USE_HTML_FALLBACK:    {settings.use_html_fallback}")
    print(f"    USE_GEMINI_ASSISTANT: {settings.use_gemini_assistant}")
    print(f"    GEMINI_API_KEY:       {'[SET]' if settings.gemini_api_key else '[NOT SET]'}")
    print(f"    RATE_LIMIT:           {settings.rate_limit_requests_per_second} req/s")

    # Test yfinance
    print("\n  Testing yfinance...")
    try:
        from src.data_sources.yahoo_yfinance import get_latest_quote
        quote = get_latest_quote("AAPL")
        print(f"    ✓ yfinance working - AAPL: ${quote.price:.2f}")
    except Exception as e:
        print(f"    ✗ yfinance error: {e}")

    # Test Gemini if configured
    if settings.gemini_api_key:
        print("\n  Testing Gemini...")
        try:
            from src.llm.gemini_client import gemini_client
            if gemini_client.is_available():
                print("    ✓ Gemini available")
            else:
                print("    ✗ Gemini not available")
        except Exception as e:
            print(f"    ✗ Gemini error: {e}")

    print(f"\n{'='*50}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Yahoo Finance Stock Scraper with Gemini Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.app.cli quote AAPL
  python -m src.app.cli quote MSFT --save --json
  python -m src.app.cli history AAPL --period 1mo
  python -m src.app.cli history TSLA --start 2024-01-01 --end 2024-06-01 --save
  python -m src.app.cli batch --tickers AAPL,MSFT,GOOGL,AMZN
  python -m src.app.cli test
        """
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Quote command
    quote_parser = subparsers.add_parser("quote", help="Get latest quote for a ticker")
    quote_parser.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL)")
    quote_parser.add_argument("--save", action="store_true", help="Save quote to file")
    quote_parser.add_argument("--json", action="store_true", help="Output as JSON")
    quote_parser.set_defaults(func=cmd_quote)

    # History command
    history_parser = subparsers.add_parser("history", help="Get historical data for a ticker")
    history_parser.add_argument("ticker", help="Stock ticker symbol")
    history_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    history_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    history_parser.add_argument("--period", default="1mo",
                                help="Period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max)")
    history_parser.add_argument("--format", choices=["csv", "parquet"], default="csv",
                                help="Output format")
    history_parser.add_argument("--save", action="store_true", help="Save to file")
    history_parser.add_argument("--json", action="store_true", help="Output as JSON")
    history_parser.set_defaults(func=cmd_history)

    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Get quotes for multiple tickers")
    batch_parser.add_argument("--tickers", required=True,
                              help="Comma-separated list of tickers (e.g., AAPL,MSFT,GOOGL)")
    batch_parser.add_argument("--save", action="store_true", help="Save quotes to file")
    batch_parser.add_argument("--json", action="store_true", help="Output as JSON")
    batch_parser.set_defaults(func=cmd_batch)

    # Test command
    test_parser = subparsers.add_parser("test", help="Test configuration and connections")
    test_parser.set_defaults(func=cmd_test)

    args = parser.parse_args()

    if args.verbose:
        setup_logging(verbose=True)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
