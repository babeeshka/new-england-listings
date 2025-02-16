# src/new_england_listings/cli.py
import argparse
import json
import logging
import sys
from typing import List, Optional
from .main import process_listing
from . import __version__


def setup_logging(verbose: bool = False):
    """Configure logging with focused debug output."""
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )

    # Remove existing handlers
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Console handler - keep it minimal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(simple_formatter)
    console_handler.setLevel(logging.INFO)

    # Debug file handler - focus on extraction process
    file_handler = logging.FileHandler('extraction_debug.log', mode='w')
    file_handler.setFormatter(detailed_formatter)
    file_handler.setLevel(logging.DEBUG)

    # Configure root logger
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Silence noisy modules
    for logger_name in ['urllib3', 'selenium', 'WDM', 'websockets']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Ensure our extractors log at appropriate level
    extractor_logger = logging.getLogger('new_england_listings.extractors')
    extractor_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Add specific handler for HTML content
    html_handler = logging.FileHandler('html_content.log', mode='w')
    html_handler.setFormatter(logging.Formatter('%(message)s'))
    html_handler.addFilter(lambda record: 'HTML Content' in record.msg)
    extractor_logger.addHandler(html_handler)

def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
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
        "--debug-file",
        help="Write detailed debug logs to specified file"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None):
    """Main entry point for the CLI."""
    try:
        parsed_args = parse_args(args)
        setup_logging(parsed_args.verbose)
        logger = logging.getLogger(__name__)

        results = []
        errors = []

        for i, url in enumerate(parsed_args.urls, 1):
            logger.info(f"Processing URL {i}/{len(parsed_args.urls)}: {url}")
            try:
                data = process_listing(
                    url, use_notion=not parsed_args.no_notion)
                results.append(data)
                logger.info(f"Successfully processed {url}")
                if parsed_args.verbose:
                    logger.info(
                        f"Extracted data: {json.dumps(data, indent=2)}")
            except Exception as e:
                error_msg = f"Error processing {url}: {str(e)}"
                logger.error(error_msg)
                errors.append({"url": url, "error": error_msg})
                continue

        output = {
            "results": results,
            "errors": errors,
            "total": len(parsed_args.urls),
            "successful": len(results),
            "failed": len(errors)
        }

        # Only output the JSON results once
        if parsed_args.output:
            with open(parsed_args.output, 'w') as f:
                json.dump(output, f, indent=2)
            logger.info(f"Results written to {parsed_args.output}")
        else:
            print(json.dumps(output, indent=2))

        if errors:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
