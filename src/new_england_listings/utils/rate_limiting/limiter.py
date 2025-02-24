# src/new_england_listings/utils/rate_limiting/limiter.py

from typing import Dict, List, Optional
from datetime import datetime
import time
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded"""
    pass


class DomainRateLimiter:
    """Rate limiter for a specific domain"""

    def __init__(self, requests_per_minute: int = 30):
        self.rpm = requests_per_minute
        self.request_times: List[float] = []

    def can_request(self) -> bool:
        """Check if a request can be made"""
        self._clean_old_requests()
        return len(self.request_times) < self.rpm

    def _clean_old_requests(self):
        """Remove requests older than one minute"""
        now = time.time()
        self.request_times = [t for t in self.request_times if now - t < 60]

    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        if not self.can_request():
            # Wait until oldest request is more than a minute old
            sleep_time = 60 - (time.time() - self.request_times[0])
            if sleep_time > 0:
                logger.debug(f"Rate limit reached, waiting {sleep_time:.1f}s")
                time.sleep(sleep_time)

    def record_request(self):
        """Record that a request was made"""
        self.request_times.append(time.time())
        self._clean_old_requests()


class RateLimiter:
    """Global rate limiter managing multiple domains"""

    def __init__(self, default_rpm: int = 30):
        self.default_rpm = default_rpm
        self.domain_limits: Dict[str, int] = {
            "realtor.com": 20,
            "zillow.com": 15,
            "landandfarm.com": 30,
            "landsearch.com": 40,
            "mainefarmlandtrust.org": 60
        }
        self.limiters: Dict[str, DomainRateLimiter] = {}

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        return urlparse(url).netloc.lower()

    def _get_limiter(self, domain: str) -> DomainRateLimiter:
        """Get or create rate limiter for domain"""
        if domain not in self.limiters:
            rpm = self.domain_limits.get(domain, self.default_rpm)
            self.limiters[domain] = DomainRateLimiter(rpm)
        return self.limiters[domain]

    def wait_if_needed(self, url: str):
        """Wait if necessary to respect rate limits"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)
        limiter.wait_if_needed()

    def record_request(self, url: str):
        """Record that a request was made"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)
        limiter.record_request()

    def get_stats(self, url: str) -> Dict:
        """Get rate limiting stats for a domain"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)

        return {
            "domain": domain,
            "requests_last_minute": len(limiter.request_times),
            "rpm_limit": self.domain_limits.get(domain, self.default_rpm)
        }


# Create singleton instance
rate_limiter = RateLimiter()
