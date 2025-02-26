# src/new_england_listings/cli.py

from datetime import datetime, date
from enum import Enum
from typing import Any, Dict
from pydantic import BaseModel, HttpUrl
import argparse
import json
import logging
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import List, Optional, Dict
from .main import process_listing
from . import __version__


def serialize_result(result: Any) -> Dict:
    """Convert result to JSON serializable format."""
    if isinstance(result, BaseModel):
        # Use model_dump() for Pydantic V2 compatibility
        return {
            k: serialize_value(v)
            for k, v in result.model_dump().items()
        }
    elif hasattr(result, '__dict__'):
        return {
            k: serialize_value(v)
            for k, v in result.__dict__.items()
        }
    return serialize_value(result)

def serialize_value(value: Any) -> Any:
    """Serialize a single value."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    elif isinstance(value, HttpUrl):
        return str(value)
    elif isinstance(value, (datetime, date)):
        return value.isoformat()
    elif isinstance(value, Enum):
        return value.value
    elif isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple, set)):
        return [serialize_value(item) for item in value]
    elif hasattr(value, 'model_dump'):  # Pydantic model
        return serialize_value(value.model_dump())
    elif hasattr(value, '__dict__'):  # Custom class
        return serialize_value(value.__dict__)
    else:
        return str(value)

async def process_urls(urls: List[str], use_notion: bool = True, verbose: bool = False) -> Dict:
    """Process multiple URLs concurrently with enhanced logging."""
    logger = logging.getLogger(__name__)
    results = []
    errors = []

    tasks = []
    for url in urls:
        tasks.append(process_listing(url, use_notion=use_notion))

    completed = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(completed):
        url = urls[i]
        if isinstance(result, Exception):
            error_msg = f"Error processing {url}: {str(result)}"
            logger.error(error_msg, exc_info=True)
            errors.append({"url": url, "error": error_msg})
        else:
            # Serialize the result
            try:
                serialized_result = serialize_result(result)
                results.append(serialized_result)

                # Log success with serialized data
                logger.info(
                    f"Successfully processed {url}",
                    extra={
                        'extraction_success': True,
                        'data': json.dumps(serialized_result, indent=2)
                    }
                )

                if verbose:
                    logger.debug(
                        f"Extracted data: {json.dumps(serialized_result, indent=2)}")
            except Exception as e:
                logger.error(
                    f"Error serializing result for {url}: {str(e)}", exc_info=True)
                errors.append(
                    {"url": url, "error": f"Serialization error: {str(e)}"})

    return {
        "results": results,
        "errors": errors,
        "total": len(urls),
        "successful": len(results),
        "failed": len(errors)
    }

def setup_logging(verbose: bool = False, log_dir: str = "logs"):
    """Configure comprehensive logging with file organization."""
    from .utils.logging_config import configure_logging

    log_level = logging.DEBUG if verbose else logging.INFO

    return configure_logging(
        level=log_level,
        log_dir=log_dir,
        app_name="new_england_listings",
        context={
            "version": __version__,
            "cli_invocation": " ".join(sys.argv)
        },
        include_console=True
    )

def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments with logging options."""
    parser = argparse.ArgumentParser(
        description="Process New England property listings"
    )

    parser.add_argument(
        "urls",
        nargs="+",
        help="One or more listing URLs to process"
    )

    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="Don't create Notion entries"
    )

    parser.add_argument(
        "--output",
        "-o",
        help="Output file for JSON results (default: print to stdout)"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directory for log files (default: logs)"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    return parser.parse_args(args)

async def async_main(args: Optional[List[str]] = None):
    """Async main entry point for the CLI."""
    try:
        parsed_args = parse_args(args)
        setup_logging(parsed_args.verbose)
        logger = logging.getLogger(__name__)

        output = await process_urls(
            parsed_args.urls,
            use_notion=not parsed_args.no_notion,
            verbose=parsed_args.verbose
        )

        if parsed_args.output:
            with open(parsed_args.output, 'w') as f:
                json.dump(output, f, indent=2)
            logger.info(f"Results written to {parsed_args.output}")
        else:
            print(json.dumps(output, indent=2))

        if output["errors"]:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        sys.exit(1)

def main(args: Optional[List[str]] = None):
    """Main entry point that runs the async event loop."""
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(
                asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"Fatal error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
