"""
Rate limiting utilities for New England Listings.
Provides domain-specific rate limiting to respect website policies.
"""

from typing import Dict, List, Optional
from datetime import datetime
import time
import asyncio
import logging
import json
import os
from urllib.parse import urlparse

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

    async def async_wait_if_needed(self):
        """Asynchronous version of wait_if_needed"""
        if not self.can_request():
            # Wait until oldest request is more than a minute old
            sleep_time = 60 - (time.time() - self.request_times[0])
            if sleep_time > 0:
                logger.debug(f"Rate limit reached, waiting {sleep_time:.1f}s")
                await asyncio.sleep(sleep_time)

    def record_request(self):
        """Record that a request was made"""
        self.request_times.append(time.time())
        self._clean_old_requests()


class RateLimiter:
    """Global rate limiter managing multiple domains"""

    def __init__(self,
                 default_rpm: int = 30,
                 persistence_path: Optional[str] = None):
        self.default_rpm = default_rpm
        self.domain_limits: Dict[str, int] = {
            "realtor.com": 10,  # Reduced as realtor.com is sensitive to scraping
            "zillow.com": 8,    # Very restrictive
            "landandfarm.com": 25,
            "landsearch.com": 30,
            "mainefarmlandtrust.org": 50,
            "newenglandfarmlandfinder.org": 40
        }
        self.limiters: Dict[str, DomainRateLimiter] = {}
        self.persistence_path = persistence_path
        self.stats = {
            "total_requests": 0,
            "rate_limited_requests": 0,
            "domains": {}
        }

        # Try to load persisted state
        if self.persistence_path and os.path.exists(self.persistence_path):
            self._load_state()

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        return urlparse(url).netloc.lower()

    def _get_limiter(self, domain: str) -> DomainRateLimiter:
        """Get or create rate limiter for domain"""
        if domain not in self.limiters:
            rpm = self.domain_limits.get(domain, self.default_rpm)
            self.limiters[domain] = DomainRateLimiter(rpm)
            # Initialize stats for new domain
            if domain not in self.stats["domains"]:
                self.stats["domains"][domain] = {
                    "requests": 0,
                    "rate_limited": 0,
                    "rpm_limit": rpm
                }
        return self.limiters[domain]

    def wait_if_needed(self, url: str):
        """Wait if necessary to respect rate limits"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)

        was_limited = not limiter.can_request()
        if was_limited:
            self.stats["rate_limited_requests"] += 1
            self.stats["domains"][domain]["rate_limited"] += 1

        limiter.wait_if_needed()

        # Record stats
        self.stats["total_requests"] += 1
        self.stats["domains"][domain]["requests"] += 1

    async def async_wait_if_needed(self, url: str):
        """Asynchronous version of wait_if_needed"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)

        was_limited = not limiter.can_request()
        if was_limited:
            self.stats["rate_limited_requests"] += 1
            self.stats["domains"][domain]["rate_limited"] += 1

        await limiter.async_wait_if_needed()

        # Record stats
        self.stats["total_requests"] += 1
        self.stats["domains"][domain]["requests"] += 1

    def record_request(self, url: str):
        """Record that a request was made"""
        domain = self._get_domain(url)
        limiter = self._get_limiter(domain)
        limiter.record_request()

    def get_stats(self, url: Optional[str] = None) -> Dict:
        """
        Get rate limiting stats.
        
        Args:
            url: Optional URL to get stats for a specific domain
            
        Returns:
            Dictionary of stats
        """
        if url:
            domain = self._get_domain(url)
            limiter = self._get_limiter(domain)

            return {
                "domain": domain,
                "requests_last_minute": len(limiter.request_times),
                "rpm_limit": self.domain_limits.get(domain, self.default_rpm),
                "total_requests": self.stats["domains"].get(domain, {}).get("requests", 0),
                "rate_limited_requests": self.stats["domains"].get(domain, {}).get("rate_limited", 0)
            }
        else:
            # Return global stats
            return {
                "total_requests": self.stats["total_requests"],
                "rate_limited_requests": self.stats["rate_limited_requests"],
                "domains": {
                    domain: {
                        "requests": stats["requests"],
                        "rate_limited": stats["rate_limited"],
                        "rpm_limit": stats["rpm_limit"],
                        "requests_last_minute": len(self.limiters.get(domain, DomainRateLimiter()).request_times)
                    }
                    for domain, stats in self.stats["domains"].items()
                }
            }

    def _save_state(self):
        """Save current state to disk for persistence"""
        if not self.persistence_path:
            return

        try:
            with open(self.persistence_path, 'w') as f:
                json.dump({
                    "stats": self.stats,
                    # We don't save request times since they're time-sensitive
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save rate limiter state: {e}")

    def _load_state(self):
        """Load state from disk"""
        if not self.persistence_path:
            return

        try:
            with open(self.persistence_path, 'r') as f:
                data = json.load(f)
                if "stats" in data:
                    self.stats = data["stats"]
        except Exception as e:
            logger.warning(f"Failed to load rate limiter state: {e}")


# Create singleton instance with optional persistence
rate_limiter = RateLimiter(
    persistence_path=os.environ.get('RATE_LIMITER_STATE_PATH')
)
