"""Web utility functions for handling common web elements and scenarios."""

import asyncio
from typing import Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from ttuex_bot.config import app_config
from ttuex_bot.utils.logging import get_logger


class WebErrorHandler:
    """Handles common web page issues like pop-ups, cookie banners, etc."""
    
    def __init__(self, page: Page, logger=None):
        self.page = page
        self.logger = logger or get_logger("WebErrorHandler")
    
    async def handle_common_popups(self) -> bool:
        """
        Handle common pop-ups, cookie banners, and unexpected elements.
        Fast version - only checks most common popups.
        """
        # Quick check for most common popups only
        try:
            # Check for cookie banner with short timeout
            cookie_button = self.page.locator('button:has-text("Accept"), button:has-text("OK")').first
            if await cookie_button.is_visible(timeout=1000):
                await cookie_button.click(timeout=1000)
                return True
        except:
            pass
        return False
    
    async def _handle_cookie_banner(self) -> bool:
        """Handle cookie acceptance banners."""
        try:
            # Common selectors for cookie banners
            cookie_selectors = [
                'button:has-text("Accept")',
                'button:has-text("OK")', 
                'button:has-text("I agree")',
                'button:has-text("Consent")',
                'button:has-text("Accept all")',
                '#onetrust-accept-btn-handler',
                '#cookie-accept',
                '[data-testid="accept-cookies"]',
                '.cookie-banner button',
                '.gdpr-cookie button',
            ]
            
            for selector in cookie_selectors:
                try:
                    element = self.page.locator(selector)
                    if await element.count() > 0 and await element.is_visible():
                        await element.click(timeout=5000)
                        self.logger.info(f"Handled cookie banner with selector: {selector}")
                        return True
                except PlaywrightTimeoutError:
                    continue  # Try the next selector
        except Exception as e:
            self.logger.debug(f"Error handling cookie banner: {e}")
        
        return False
    
    async def _handle_modal_dialogs(self) -> bool:
        """Handle common modal dialog boxes."""
        try:
            # Common selectors for modal close buttons
            modal_selectors = [
                'button:has-text("Close")',
                'button[aria-label="Close"]',
                'button.close',
                '.modal .close',
                '[data-dismiss="modal"]',
                '.modal-header button.close',
                '.popup-close',
                '.overlay-close',
                'svg:has-text("×")',  # Close X symbols
            ]
            
            for selector in modal_selectors:
                try:
                    element = self.page.locator(selector)
                    if await element.count() > 0 and await element.is_visible():
                        await element.click(timeout=5000)
                        self.logger.info(f"Handled modal dialog with selector: {selector}")
                        return True
                except PlaywrightTimeoutError:
                    continue
        except Exception as e:
            self.logger.debug(f"Error handling modal dialogs: {e}")
        
        return False
    
    async def _handle_overlays(self) -> bool:
        """Handle overlay elements that might block interactions."""
        try:
            # Common overlay selectors
            overlay_selectors = [
                '.overlay',
                '.modal-backdrop',
                '.backdrop',
                '.popup-overlay',
            ]
            
            for selector in overlay_selectors:
                try:
                    element = self.page.locator(selector)
                    if await element.count() > 0 and await element.is_visible():
                        # Try to click on the overlay to dismiss it, or wait for it to disappear
                        await element.wait_for(state="hidden", timeout=5000)
                        self.logger.info(f"Overlay disappeared: {selector}")
                        return True
                except PlaywrightTimeoutError:
                    # If timeout waiting for overlay to disappear, try to click on it
                    try:
                        await self.page.mouse.click(100, 100)  # Click top-left corner
                        await asyncio.sleep(0.5)  # Small delay
                        return True
                    except:
                        continue
        except Exception as e:
            self.logger.debug(f"Error handling overlays: {e}")
        
        return False
    
    async def wait_for_element_safe(self, selector: str, timeout: Optional[int] = None) -> bool:
        """
        Safely wait for an element, handling popups that might interfere.
        Returns True if element is found, False otherwise.
        """
        if timeout is None:
            timeout = app_config.default_timeout
            
        try:
            # Quick popup check only on first attempt
            await self.handle_common_popups()
            element = self.page.locator(selector)
            await element.wait_for(state="visible", timeout=timeout)
            return True
        except (PlaywrightTimeoutError, Exception):
            return False
    
    async def click_element_safe(self, selector: str, timeout: Optional[int] = None) -> bool:
        """
        Safely click an element, handling popups that might interfere.
        Returns True if click was successful, False otherwise.
        """
        if timeout is None:
            timeout = app_config.default_timeout
            
        try:
            await self.handle_common_popups()
            element = self.page.locator(selector)
            await element.wait_for(state="visible", timeout=timeout)
            await element.click(timeout=timeout)
            return True
        except (PlaywrightTimeoutError, Exception):
            return False


async def handle_page_errors(page: Page, logger=None) -> bool:
    """
    Convenience function to handle common page errors and popups.
    Returns True if any error was handled, False otherwise.
    """
    handler = WebErrorHandler(page, logger)
    return await handler.handle_common_popups()