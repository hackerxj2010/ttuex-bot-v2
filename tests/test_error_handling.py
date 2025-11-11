"""Tests for the enhanced error handling system."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ttuex_bot.utils.retry import async_retry, PermanentError, TemporaryError, should_retry_exception
from ttuex_bot.utils.error_classifier import ErrorClassifier, classify_and_raise, is_login_error, is_network_error
from ttuex_bot.utils.web_utils import WebErrorHandler


class TestRetryMechanism:
    """Test the enhanced retry mechanism."""
    
    @pytest.mark.asyncio
    async def test_temporary_error_retry(self):
        """Test that temporary errors are retried."""
        call_count = 0
        
        @async_retry(max_attempts=3)
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TemporaryError("Temporary network issue")
            return "success"
        
        result = await flaky_function()
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_permanent_error_no_retry(self):
        """Test that permanent errors are not retried."""
        call_count = 0
        
        @async_retry(max_attempts=3)
        async def bad_function():
            nonlocal call_count
            call_count += 1
            raise PermanentError("Bad credentials")
        
        with pytest.raises(PermanentError):
            await bad_function()
        
        assert call_count == 1  # Should only be called once
    
    @pytest.mark.asyncio
    async def test_timeout_error_retry(self):
        """Test that timeout errors are treated as temporary and retried."""
        call_count = 0
        
        @async_retry(max_attempts=3)
        async def timeout_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise PlaywrightTimeoutError("Timeout error")
            return "success"
        
        result = await timeout_function()
        assert result == "success"
        assert call_count == 2
    
    def test_should_retry_exception_classification(self):
        """Test that the should_retry_exception function works correctly."""
        # Temporary errors should return True
        assert should_retry_exception(PlaywrightTimeoutError("Timeout"))
        assert should_retry_exception(TemporaryError("Network issue"))
        assert should_retry_exception(Exception("net::ERR_CONNECTION_REFUSED"))
        
        # Permanent errors should return False after classification
        try:
            classify_and_raise(PermanentError("Bad credentials"))
        except PermanentError:
            # This confirms the error was classified as permanent
            pass
        
        # After classification, should_retry_exception should return False for permanent errors
        assert not should_retry_exception(PermanentError("Bad credentials"))


class TestErrorClassifier:
    """Test the error classification system."""
    
    def test_permanent_error_classification(self):
        """Test that permanent errors are correctly identified."""
        permanent_errors = [
            "invalid credentials",
            "incorrect password", 
            "authentication failed",
            "access denied",
            "401 unauthorized",
            "account disabled",
            "account suspended",
        ]
        
        for error in permanent_errors:
            assert ErrorClassifier.is_permanent_error(error)
            assert not ErrorClassifier.is_temporary_error(error)
            assert ErrorClassifier.classify_error(error) == PermanentError
    
    def test_temporary_error_classification(self):
        """Test that temporary errors are correctly identified."""
        temporary_errors = [
            "timeout",
            "net::ERR_CONNECTION_REFUSED",
            "connection reset",
            "host unreachable",
            "502 bad gateway",
            "503 service unavailable",
            "page load timeout",
        ]
        
        for error in temporary_errors:
            assert ErrorClassifier.is_temporary_error(error)
            assert not ErrorClassifier.is_permanent_error(error)
            assert ErrorClassifier.classify_error(error) == TemporaryError
    
    def test_generic_error_classification(self):
        """Test that generic errors default to temporary."""
        generic_errors = [
            "some unknown error",
            "element click intercepted",
            "other issue",
        ]
        
        for error in generic_errors:
            assert ErrorClassifier.is_temporary_error(error)
            assert not ErrorClassifier.is_permanent_error(error)
            assert ErrorClassifier.classify_error(error) == TemporaryError


class TestErrorUtilityFunctions:
    """Test the error utility functions."""
    
    def test_login_error_detection(self):
        """Test that login-related errors are detected."""
        login_errors = [
            "incorrect password",
            "invalid credentials",
            "authentication failed",
            "bad login info",
        ]
        
        for error in login_errors:
            assert is_login_error(error)
    
    def test_network_error_detection(self):
        """Test that network-related errors are detected."""
        network_errors = [
            "timeout",
            "net::ERR_CONNECTION_REFUSED",
            "connection reset",
            "network error",
        ]
        
        for error in network_errors:
            assert is_network_error(error)
    
    def test_error_classification_and_raising(self):
        """Test the classify_and_raise function."""
        # Test permanent error classification
        with pytest.raises(PermanentError):
            classify_and_raise("invalid credentials")
        
        # Test temporary error classification
        with pytest.raises(TemporaryError):
            classify_and_raise("timeout occurred")


class TestWebErrorHandler:
    """Test the web error handler utility."""
    
    @pytest.mark.asyncio
    async def test_handle_common_popups(self):
        """Test that the web error handler can handle common popups."""
        # Mock page object
        page = AsyncMock()
        page.locator = MagicMock()
        element = AsyncMock()
        element.count = AsyncMock(return_value=1)
        element.is_visible = AsyncMock(return_value=True)
        element.click = AsyncMock()
        page.locator.return_value = element
        
        handler = WebErrorHandler(page)
        
        # Test that cookie banner handling works
        result = await handler._handle_cookie_banner()
        assert result is True
        element.click.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_wait_for_element_safe(self):
        """Test safe element waiting with popup handling."""
        # Mock page object
        page = AsyncMock()
        page.locator = MagicMock()
        element = AsyncMock()
        element.wait_for = AsyncMock()
        page.locator.return_value = element
        
        handler = WebErrorHandler(page)
        
        # Test successful element wait
        result = await handler.wait_for_element_safe("button#test")
        assert result is True
        element.wait_for.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_click_element_safe(self):
        """Test safe element clicking with popup handling."""
        # Mock page object
        page = AsyncMock()
        page.locator = MagicMock()
        element = AsyncMock()
        element.wait_for = AsyncMock()
        element.scroll_into_view_if_needed = AsyncMock()
        element.click = AsyncMock()
        page.locator.return_value = element
        
        handler = WebErrorHandler(page)
        
        # Test successful element click
        result = await handler.click_element_safe("button#test")
        assert result is True
        element.click.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])