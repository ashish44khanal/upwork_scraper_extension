"""
Custom exceptions for the Upwork scraper.
Provides a clear hierarchy for different failure modes.
"""

class ScraperException(Exception):
    """Base exception for all scraper-related errors"""
    pass


class CloudflareBlockException(ScraperException):
    """Raised when Cloudflare challenge is not solved within timeout"""
    pass


class ModalExtractionException(ScraperException):
    """Raised when job modal HTML extraction fails after all retries"""
    pass


class AIExtractionException(ScraperException):
    """Raised when Gemini API fails to extract structured data"""
    pass


class BrowserInitException(ScraperException):
    """Raised when browser initialization fails"""
    pass


class SessionResetException(ScraperException):
    """Raised when session needs to be reset due to consecutive failures"""
    pass
