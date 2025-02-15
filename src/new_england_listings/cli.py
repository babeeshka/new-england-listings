# src/new_england_listings/cli.py
import argparse
import json
import logging
import sys
import traceback
from typing import List, Optional
from .main import process_listing
from . import __version__


def setup_logging(verbose: bool = False):
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO

    # Remove any existing handlers
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout,  # Explicitly log to stdout
        force=True
    )

    # Create a file handler for debug.log
    file_handler = logging.FileHandler('debug.log', mode='w')
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    # Add file handler to root logger
    root.addHandler(file_handler)

    # Set level for key loggers
    for logger_name in ['new_england_listings', 'selenium', 'urllib3']:
        logging.getLogger(logger_name).setLevel(level)


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
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    return parser.parse_args(args)


def check_dependencies():
    """Check if required dependencies are installed."""
    logger = logging.getLogger(__name__)
    logger.debug("Checking dependencies...")

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        logger.debug("Installing ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        logger.debug("ChromeDriver installed successfully")

        logger.debug("Configuring Chrome options...")
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        logger.debug("Initializing Chrome driver...")
        driver = webdriver.Chrome(service=service, options=options)
        driver.quit()

        logger.info("Chrome and ChromeDriver are properly configured")
        return True
    except Exception as e:
        logger.error(f"Dependency check failed: {str(e)}")
        logger.debug("Stack trace:", exc_info=True)
        return False


def main(args: Optional[List[str]] = None):
    """Main entry point for the CLI."""
    logger = logging.getLogger(__name__)
    logger.debug("Starting main function...")

    try:
        parsed_args = parse_args(args)
        setup_logging(parsed_args.verbose)

        logger.info("Starting extraction process...")
        logger.debug(f"Arguments: {parsed_args}")

        if not check_dependencies():
            logger.error("Required dependencies are not properly configured")
            sys.exit(1)

        results = []
        errors = []

        for i, url in enumerate(parsed_args.urls, 1):
            logger.info(f"[{i}/{len(parsed_args.urls)}] Processing URL: {url}")
            try:
                logger.debug(f"Calling process_listing for URL: {url}")
                data = process_listing(
                    url, use_notion=not parsed_args.no_notion)
                logger.info("Successfully extracted data")
                logger.debug(f"Extracted data: {json.dumps(data, indent=2)}")
                results.append(data)
            except Exception as e:
                error_msg = f"Error processing {url}: {str(e)}"
                logger.error(error_msg)
                logger.debug("Stack trace:", exc_info=True)
                errors.append({"url": url, "error": error_msg,
                              "traceback": traceback.format_exc()})
                continue

        output = {
            "results": results,
            "errors": errors,
            "total": len(parsed_args.urls),
            "successful": len(results),
            "failed": len(errors)
        }

        if parsed_args.output:
            logger.debug(f"Writing output to file: {parsed_args.output}")
            with open(parsed_args.output, 'w') as f:
                json.dump(output, f, indent=2)
        else:
            print(json.dumps(output, indent=2))

        if errors:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.debug("Stack trace:", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
