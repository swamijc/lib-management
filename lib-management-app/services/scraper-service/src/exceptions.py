"""
Scraper Service — custom exceptions.
"""


class ScraperException(Exception):
    """Base scraper error."""


class PackageNotFoundError(ScraperException):
    """Registry returned no results for this package."""


class CircuitOpenError(ScraperException):
    """Circuit breaker is open; fast-failing without making a network call."""


class ParseError(ScraperException):
    """Registry response could not be parsed into a ScrapedVersion."""


class RegistryNotSupportedError(ScraperException):
    """No strategy registered for the given registry key."""
