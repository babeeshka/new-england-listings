# tests/test_performance/test_benchmarks.py
import pytest
import time
import json
import os
import statistics
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import asyncio

from new_england_listings import process_listing, process_listings
from new_england_listings.extractors import get_extractor_for_url
from new_england_listings.utils.browser import get_page_content_async


# ------------------- Configuration -------------------

# Define benchmark thresholds
THRESHOLDS = {
    "extract_listing_name": 0.01,  # 10ms
    "extract_location": 0.01,      # 10ms
    "extract_price": 0.01,         # 10ms
    "extract_acreage_info": 0.01,  # 10ms
    "extract_all": 0.05,           # 50ms
    "process_listing": 0.2,        # 200ms
    "process_listings_1": 0.3,     # 300ms for 1 listing
    "process_listings_3": 0.6,     # 600ms for 3 listings
}

# Configure benchmark data storage
BENCHMARK_DIR = Path(__file__).parent.parent / "fixtures" / "benchmarks"
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
BENCHMARK_FILE = BENCHMARK_DIR / "performance_history.json"


# ------------------- Fixtures -------------------

@pytest.fixture
def cached_pages():
    """Return a dictionary of cached HTML pages for testing."""
    cache_dir = Path(__file__).parent.parent / "fixtures" / "cached_pages"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Load cached pages if available
    pages = {}
    for html_file in cache_dir.glob("*.html"):
        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()
            pages[html_file.stem] = html

    return pages


@pytest.fixture
def mock_get_page_content(cached_pages):
    """Mock get_page_content_async to use cached pages."""
    async def mock_get_page(url, **kwargs):
        from bs4 import BeautifulSoup

        # Generate a key from the URL
        import hashlib
        key = hashlib.md5(url.encode()).hexdigest()

        if key in cached_pages:
            return BeautifulSoup(cached_pages[key], "html.parser")
        else:
            # If no cached page, return a minimal page
            return BeautifulSoup("<html><body>Test</body></html>", "html.parser")

    with patch("new_england_listings.main.get_page_content_async", side_effect=mock_get_page):
        yield


@pytest.fixture
def sample_urls():
    """Return a list of sample URLs for testing."""
    return [
        "https://www.realtor.com/realestateandhomes-detail/123-Main-St_Portland_ME_04101_M12345-67890",
        "https://www.landandfarm.com/property/10_Acres_in_Brunswick-12345",
        "https://www.zillow.com/homedetails/123-Main-St-Portland-ME-04101/12345_zpid/"
    ]


@pytest.fixture
def performance_tracker():
    """Create a performance tracker for collecting benchmark data."""
    class PerformanceTracker:
        def __init__(self):
            self.results = {}

        def add_result(self, name, duration, threshold=None):
            """Add a benchmark result."""
            self.results[name] = {
                "duration": duration,
                "threshold": threshold,
                "passed": threshold is None or duration <= threshold
            }

        def save_history(self):
            """Save benchmark results to history file."""
            # Load existing history
            history = []
            if BENCHMARK_FILE.exists():
                try:
                    with open(BENCHMARK_FILE, "r") as f:
                        history = json.load(f)
                except json.JSONDecodeError:
                    # If file is corrupted, start fresh
                    history = []

            # Add new results
            entry = {
                "timestamp": datetime.now().isoformat(),
                "results": self.results,
                "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
                "platform": os.name,
                "python_version": ".".join(map(str, tuple(__import__("sys").version_info[:3]))),
            }
            history.append(entry)

            # Save updated history
            with open(BENCHMARK_FILE, "w") as f:
                json.dump(history, f, indent=2)

            # Generate report
            self._generate_report(history)

        def _generate_report(self, history):
            """Generate a performance report based on history."""
            report_file = BENCHMARK_DIR / "performance_report.md"

            with open(report_file, "w") as f:
                f.write("# Performance Benchmark Report\n\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n\n")

                f.write("## Latest Results\n\n")
                f.write("| Benchmark | Duration (ms) | Threshold (ms) | Status |\n")
                f.write("|-----------|--------------|----------------|--------|\n")

                for name, data in self.results.items():
                    duration_ms = data["duration"] * 1000
                    threshold_ms = data["threshold"] * \
                        1000 if data["threshold"] else "N/A"
                    status = "✅" if data["passed"] else "❌"

                    f.write(
                        f"| {name} | {duration_ms:.2f} | {threshold_ms} | {status} |\n")

                f.write("\n## Historical Trends\n\n")

                # Calculate trends for each benchmark
                benchmarks = set()
                for entry in history:
                    for name in entry["results"].keys():
                        benchmarks.add(name)

                for benchmark in sorted(benchmarks):
                    values = []
                    for entry in history:
                        if benchmark in entry["results"]:
                            # Convert to ms
                            values.append(entry["results"]
                                          [benchmark]["duration"] * 1000)

                    if len(values) > 1:
                        trend = values[-1] - values[0]
                        trend_pct = (trend / values[0]) * \
                            100 if values[0] > 0 else 0

                        trend_str = "improving" if trend < 0 else "worsening" if trend > 0 else "stable"

                        f.write(f"### {benchmark}\n\n")
                        f.write(f"- Current: {values[-1]:.2f} ms\n")
                        f.write(f"- First: {values[0]:.2f} ms\n")
                        f.write(
                            f"- Change: {trend:+.2f} ms ({trend_pct:+.2f}%)\n")
                        f.write(f"- Trend: {trend_str}\n")

                        if len(values) >= 3:
                            f.write(
                                f"- Mean: {statistics.mean(values):.2f} ms\n")
                            f.write(
                                f"- Median: {statistics.median(values):.2f} ms\n")
                            f.write(
                                f"- Std Dev: {statistics.stdev(values):.2f} ms\n")

                        f.write("\n")

    return PerformanceTracker()


# ------------------- Test Classes -------------------

@pytest.mark.performance
class TestExtractorPerformance:
    """Performance tests for extractors."""

    def test_extractor_initialization(self, sample_urls, performance_tracker):
        """Measure extractor initialization time."""
        url = sample_urls[0]

        # Time extractor initialization
        start_time = time.time()
        for _ in range(100):  # Run multiple times for more accurate measurement
            extractor_class = get_extractor_for_url(url)
            extractor = extractor_class(url)
        end_time = time.time()

        # Calculate average time
        avg_time = (end_time - start_time) / 100

        # Log result
        performance_tracker.add_result(
            "extractor_init", avg_time, threshold=0.001)
        print(f"\nExtractor initialization: {avg_time*1000:.2f} ms")

    @pytest.mark.parametrize("platform", ["realtor.com", "landandfarm.com", "zillow.com"])
    def test_extraction_methods(self, platform, sample_urls, cached_pages, performance_tracker):
        """Measure performance of individual extraction methods."""
        # Find URL for the platform
        url = next((u for u in sample_urls if platform in u), None)
        if not url:
            pytest.skip(f"No test URL found for platform: {platform}")

        # Get the appropriate extractor
        extractor_class = get_extractor_for_url(url)
        if not extractor_class:
            pytest.skip(f"No extractor available for platform: {platform}")

        # Initialize the extractor
        extractor = extractor_class(url)

        # Generate a key from the URL
        import hashlib
        key = hashlib.md5(url.encode()).hexdigest()

        # Create soup from cached page
        from bs4 import BeautifulSoup
        if key in cached_pages:
            soup = BeautifulSoup(cached_pages[key], "html.parser")
        else:
            # If no cached page, use a minimal page
            soup = BeautifulSoup(
                "<html><body>Test</body></html>", "html.parser")

        extractor.soup = soup

        # Test individual extraction methods
        methods = [
            "extract_listing_name",
            "extract_location",
            "extract_price",
            "extract_acreage_info"
        ]

        for method_name in methods:
            if hasattr(extractor, method_name):
                method = getattr(extractor, method_name)

                # Measure method execution time
                start_time = time.time()
                for _ in range(10):  # Run multiple times for more accurate measurement
                    try:
                        method()
                    except Exception:
                        # Ignore errors in performance testing
                        pass
                end_time = time.time()

                # Calculate average time
                avg_time = (end_time - start_time) / 10

                # Log result
                performance_tracker.add_result(
                    f"{platform}_{method_name}",
                    avg_time,
                    threshold=THRESHOLDS.get(method_name)
                )
                print(f"{platform} {method_name}: {avg_time*1000:.2f} ms")

        # Test extract method (full extraction)
        start_time = time.time()
        try:
            extractor.extract(soup)
        except Exception:
            # Ignore errors in performance testing
            pass
        end_time = time.time()

        # Log result
        performance_tracker.add_result(
            f"{platform}_extract_all",
            end_time - start_time,
            threshold=THRESHOLDS.get("extract_all")
        )
        print(f"{platform} extract_all: {(end_time - start_time)*1000:.2f} ms")


@pytest.mark.asyncio
@pytest.mark.performance
class TestProcessingPerformance:
    """Performance tests for processing functions."""

    async def test_process_listing_performance(self, sample_urls, mock_get_page_content, performance_tracker):
        """Measure performance of process_listing function."""
        # Use first URL
        url = sample_urls[0]

        # Mock notion
        with patch("new_england_listings.main.create_notion_entry"):
            # Warm up
            await process_listing(url, use_notion=False)

            # Measure performance
            start_time = time.time()
            await process_listing(url, use_notion=False)
            end_time = time.time()

            # Log result
            performance_tracker.add_result(
                "process_listing",
                end_time - start_time,
                threshold=THRESHOLDS.get("process_listing")
            )
            print(f"\nprocess_listing: {(end_time - start_time)*1000:.2f} ms")

    @pytest.mark.parametrize("concurrency,count", [(1, 1), (3, 3)])
    async def test_process_listings_performance(self, concurrency, count, sample_urls,
                                                mock_get_page_content, performance_tracker):
        """Measure performance of process_listings with different concurrency."""
        # Use subset of URLs
        urls = sample_urls[:count]

        # Mock notion
        with patch("new_england_listings.main.create_notion_entry"):
            # Warm up
            await process_listings(urls, use_notion=False, concurrency=concurrency)

            # Measure performance
            start_time = time.time()
            await process_listings(urls, use_notion=False, concurrency=concurrency)
            end_time = time.time()

            # Log result
            performance_tracker.add_result(
                f"process_listings_{count}_concurrency_{concurrency}",
                end_time - start_time,
                threshold=THRESHOLDS.get(f"process_listings_{count}")
            )
            print(
                f"process_listings ({count} URLs, concurrency={concurrency}): {(end_time - start_time)*1000:.2f} ms")


@pytest.mark.performance
class TestMemoryUsage:
    """Tests for memory usage."""

    def test_memory_profile(self, sample_urls, mock_get_page_content, performance_tracker):
        """Measure memory usage during extraction."""
        try:
            import memory_profiler
        except ImportError:
            pytest.skip("memory_profiler not installed")

        url = sample_urls[0]

        # Define the function to profile
        def run_extraction():
            # Get the appropriate extractor
            extractor_class = get_extractor_for_url(url)
            extractor = extractor_class(url)

            # Create soup
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(
                "<html><body>Test</body></html>", "html.parser")

            # Run extraction
            extractor.extract(soup)

        # Profile memory usage
        memory_usage = memory_profiler.memory_usage(
            (run_extraction,), interval=0.1)

        # Calculate memory metrics
        baseline = memory_usage[0]
        peak = max(memory_usage)
        increase = peak - baseline

        # Log results
        print(f"\nMemory baseline: {baseline:.2f} MiB")
        print(f"Memory peak: {peak:.2f} MiB")
        print(f"Memory increase: {increase:.2f} MiB")

        # Add to performance tracker
        performance_tracker.add_result("memory_increase", increase)


@pytest.mark.performance
def test_save_benchmark_history(performance_tracker):
    """Save benchmark results to history."""
    performance_tracker.save_history()

    assert BENCHMARK_FILE.exists()

    # Verify the report was generated
    report_file = BENCHMARK_DIR / "performance_report.md"
    assert report_file.exists()

    # Print path to report for easy access
    print(f"\nPerformance report generated at: {report_file}")


# Use this conditional to enable running the tests directly
if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
