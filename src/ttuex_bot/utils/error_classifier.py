"""Error classification utilities for the TTUEX bot."""

from typing import Dict, List, Type, Union
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from ttuex_bot.utils.retry import PermanentError, TemporaryError


class ErrorClassifier:
    """Classifies errors as permanent or temporary based on their nature."""
    
    # Permanent errors - these should not be retried
    PERMANENT_ERROR_PATTERNS = [
        # Authentication errors
        "invalid.*credentials",
        "incorrect.*password",
        "wrong.*password",
        "authentication.*failed",
        "login.*failed",
        "access.*denied",
        "forbidden",
        "unauthorized",
        "401",
        "403",
        
        # Invalid input or configuration errors
        "invalid.*input",
        "malformed.*url",
        "invalid.*selector",
        "element.*not.*found",  # When the element should definitely exist
        
        # Account-specific errors
        "account.*disabled",
        "account.*suspended",
        "account.*banned",
        "account.*locked",
        
        # Page structure changes
        "selector.*not.*found",  # When looking for expected elements
    ]
    
    # Temporary errors - these can be retried
    TEMPORARY_ERROR_PATTERNS = [
        # Network errors
        "net::ERR_",
        "timeout",
        "load.*failed",
        "navigation.*failed",
        "page.*crashed",
        "connection.*refused",
        "connection.*reset",
        "host.*unreachable",
        "was.*closed",
        "failed.*fetch",
        "network.*error",
        "502",
        "503",
        "504",
        "slow.*down",
        
        # Browser-specific temporary errors
        "target.*closed",
        "browser.*disconnected",
        "context.*disposed",
        "execution.*context.*was.*destroyed",
        
        # Page load issues
        "page.*load.*timeout",
        "document.*load.*timeout",
        "resource.*load.*failed",
    ]
    
    @classmethod
    def classify_error(cls, error: Union[Exception, str]) -> Type[Union[PermanentError, TemporaryError]]:
        """
        Classify an error as permanent or temporary.
        
        Returns:
            PermanentError if the error is permanent (should not be retried)
            TemporaryError if the error is temporary (should be retried)
        """
        error_str = str(error).lower()
        
        # Check for permanent patterns first
        for pattern in cls.PERMANENT_ERROR_PATTERNS:
            if pattern.lower() in error_str:
                return PermanentError
        
        # Check for temporary patterns
        for pattern in cls.TEMPORARY_ERROR_PATTERNS:
            if pattern.lower() in error_str:
                return TemporaryError
        
        # Default to temporary error (safer to retry than not)
        return TemporaryError

    @classmethod
    def is_permanent_error(cls, error: Union[Exception, str]) -> bool:
        """Check if an error is permanent."""
        return cls.classify_error(error) == PermanentError

    @classmethod
    def is_temporary_error(cls, error: Union[Exception, str]) -> bool:
        """Check if an error is temporary."""
        return cls.classify_error(error) == TemporaryError


def classify_and_raise(error: Union[Exception, str]):
    """
    Classify an error and raise it appropriately.
    If it's a permanent error, wrap it in PermanentError.
    If it's a temporary error, wrap it in TemporaryError.
    """
    error_type = ErrorClassifier.classify_error(error)
    if error_type == PermanentError:
        if isinstance(error, Exception):
            raise PermanentError(f"Permanent error: {str(error)}") from error
        else:
            raise PermanentError(f"Permanent error: {error}")
    else:
        if isinstance(error, Exception):
            raise TemporaryError(f"Temporary error: {str(error)}") from error
        else:
            raise TemporaryError(f"Temporary error: {error}")


def is_login_error(error: Union[Exception, str]) -> bool:
    """Check if an error is related to login problems."""
    error_str = str(error).lower()
    login_related_patterns = [
        "password",
        "credential",
        "login",
        "auth",
        "incorrect",
        "invalid.*user",
        "invalid.*account",
    ]
    return any(pattern in error_str for pattern in login_related_patterns)


def is_network_error(error: Union[Exception, str]) -> bool:
    """Check if an error is related to network problems."""
    error_str = str(error).lower()
    network_patterns = [
        "timeout",
        "net::err_",
        "connection.*refused",
        "connection.*reset",
        "host.*unreachable",
        "502",
        "503",
        "504",
        "network.*error",
    ]
    return any(pattern in error_str for pattern in network_patterns)


def is_timeout_error(error: Union[Exception, str]) -> bool:
    """Check if an error is specifically a timeout error."""
    if isinstance(error, PlaywrightTimeoutError):
        return True
    error_str = str(error).lower()
    return "timeout" in error_str


def is_element_not_found_error(error: Union[Exception, str]) -> bool:
    """Check if an error is related to missing elements."""
    error_str = str(error).lower()
    element_patterns = [
        "element.*not.*found",
        "locator.*not.*found",
        "selector.*not.*found",
        "could.*not.*find",
        "does.*not.*exist",
    ]
    return any(pattern in error_str for pattern in element_patterns)