import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from pydantic import SecretStr
from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from ttuex_bot.config import app_config
from ttuex_bot.utils.logging import get_logger
from ttuex_bot.utils.retry import async_retry, PermanentError, TemporaryError, should_retry_exception
from ttuex_bot.utils.web_utils import WebErrorHandler
from ttuex_bot.utils.error_classifier import (
    ErrorClassifier, 
    classify_and_raise, 
    is_login_error, 
    is_network_error, 
    is_timeout_error,
    is_element_not_found_error
)


class TtuexWorkflow:
    """Manages and executes the TTUEX copy trading workflow."""

    def __init__(
        self,
        username: str,
        password: SecretStr,
        browser_context: Optional[BrowserContext] = None,
        storage_state_path: Optional[str] = None,
        page: Optional[Page] = None, # Added page parameter
    ):
        self.username = username
        self.password = password
        self.logger = get_logger("TtuexWorkflow", account_name=self.username)
        self.browser_context = browser_context
        self.storage_state_path = storage_state_path
        self.page = page # Store the page object

    async def execute_login(self, dry_run: bool = True) -> Dict[str, Any]:
        """Executes the login workflow for a single account."""
        self.logger.info("Starting login workflow", dry_run=dry_run)

        start_time = datetime.utcnow()
        report = {
            "account_name": self.username,
            "dry_run": dry_run,
            "start_time_utc": start_time.isoformat(),
            "steps": [],
            "success": False,
        }

        try:
            if not self.browser_context:
                raise PermanentError("BrowserContext not provided to workflow.")

            if not self.page:
                self.page = await self.browser_context.new_page()

            login_result = await self._step_login(self.page, dry_run)
            report["steps"].append(login_result)
            if not login_result.get("success", False):
                # Don't raise exception here since we want to return the proper report
                self.logger.warning(f"Login step failed: {login_result.get('error')}")
                return report  # Return early if login failed

            report["success"] = True
            self.logger.info("Login workflow completed successfully.")

        except PermanentError as e:
            report["error"] = f"Permanent error: {str(e)}"
            self.logger.error("Login workflow failed with permanent error", error=str(e))
        except Exception as e:
            # For any other unexpected exceptions
            report["error"] = f"Unexpected error: {str(e)}"
            self.logger.error("Login workflow failed with unexpected error", error=str(e), exc_info=True)

        finally:
            # The page should not be closed here if the workflow continues
            pass

        end_time = datetime.utcnow()
        elapsed = (end_time - start_time).total_seconds()

        # Enforce minimum run duration per account if configured (non-blocking sleep)
        if app_config.enforce_min_run_per_account:
            remaining = max(0.0, float(app_config.min_run_seconds) - float(elapsed))
            if remaining > 0:
                await asyncio.sleep(remaining)
                end_time = datetime.utcnow()
                elapsed = (end_time - start_time).total_seconds()

        report["end_time_utc"] = end_time.isoformat()
        report["duration_seconds"] = elapsed

        return report

    async def execute_copy_trade(
        self,
        order_number: str,
        dry_run: bool = True,
        headless: bool = True,
        performant: bool = False,
        skip_history_verification: bool = False,

    ) -> Dict[str, Any]:
        """Executes the full copy trading workflow for a single account using the provided browser context."""
        self.logger.info(
            "Starting copy trade workflow",
            order_number=order_number,
            dry_run=dry_run,
            performant=performant,
            skip_history_verification=skip_history_verification,
        )
        self.logger.debug(f"execute_copy_trade received dry_run: {dry_run}")

        start_time = datetime.utcnow()
        report = {
            "account_name": self.username,
            "order_number": order_number,
            "dry_run": dry_run,
            "start_time_utc": start_time.isoformat(),
            "steps": [],
            "success": False,
        }

        page: Optional[Page] = None
        try:
            # --- Dry Run Simulation ---
            if dry_run:
                self.logger.info("Executing dry run for copy trade.")
                # Simulate the sequence of operations without actual browser interaction
                simulated_steps = [
                    {"step": "login", "success": True, "simulated": True},
                    {"step": "navigate_to_contract", "success": True, "simulated": True},
                    {"step": "navigate_to_copy_trading", "success": True, "simulated": True},
                    {"step": "enter_order_number", "success": True, "simulated": True, "order_number": order_number},
                    {"step": "execute_follow_up", "success": True, "simulated": True},
                ]
                if not skip_history_verification:
                    simulated_steps.append({"step": "execute_follow_up", "success": True, "simulated": True})
                
                report["steps"] = simulated_steps
                report["success"] = True
                self.logger.info("Dry run completed successfully.")
                
            # --- Live Run Execution ---
            else:
                if not self.browser_context:
                    raise PermanentError("BrowserContext not provided for live run.")

                if not self.page:
                    self.page = await self.browser_context.new_page()

                # Define the sequence of steps for the live run
                steps_to_execute = [
                    self._step_login,
                    self._step_navigate_to_contract,
                    self._step_navigate_to_copy_trading,
                    lambda p, dr: self._step_enter_order_number(p, order_number, dr),
                    self._step_execute_follow_up,
                ]

                # Execute each step
                for step_func in steps_to_execute:
                    result = await step_func(self.page, dry_run)
                    report["steps"].append(result)
                    if not result.get("success", False):
                        # Log the failure but continue to return the full report
                        self.logger.warning(f"Step {result.get('step')} failed: {result.get('error')}")
                        return report  # Return early if any step failed

                report["success"] = True
                self.logger.info("Live run workflow completed successfully.")

        except PermanentError as e:
            report["error"] = f"Permanent error: {str(e)}"
            self.logger.error("Copy trade workflow failed with permanent error", error=str(e))
        except Exception as e:
            # For any other unexpected exceptions
            report["error"] = f"Unexpected error: {str(e)}"
            self.logger.error("Copy trade workflow failed with unexpected error", error=str(e), exc_info=True)

        finally:
            # The page should not be closed here; it's managed by the orchestrator
            pass

            end_time = datetime.utcnow()
            elapsed = (end_time - start_time).total_seconds()

            # Enforce minimum run duration per account if configured (non-blocking sleep)
            if app_config.enforce_min_run_per_account:
                remaining = max(0.0, float(app_config.min_run_seconds) - float(elapsed))
                if remaining > 0:
                    await asyncio.sleep(remaining)
                    end_time = datetime.utcnow()
                    elapsed = (end_time - start_time).total_seconds()

            report["end_time_utc"] = end_time.isoformat()
            report["duration_seconds"] = elapsed
            self.logger.info(f"Final report from execute_copy_trade: {report}")
        return report

    # --- Workflow steps ---

    @async_retry(max_attempts=3)  # Increased to 3 attempts for better resilience
    async def _step_login(self, page: Page, dry_run: bool) -> Dict[str, Any]:
        self.logger.info("Executing step: Standard Login")
        if dry_run:
            return {"step": "login", "success": True, "simulated": True}

        try:
            # Create web error handler for this step
            web_handler = WebErrorHandler(page, self.logger)
            
            # If storage state exists, assume login, and verify
            if self.storage_state_path and Path(self.storage_state_path).exists():
                self.logger.info("Existing session found. Verifying session status.")
                try:
                    # Navigate to a page that requires login
                    await page.goto(
                        app_config.ttuex_base_url,
                        timeout=app_config.default_timeout,
                        wait_until="domcontentloaded",
                    )
                    
                    # Handle any popups first
                    await web_handler.handle_common_popups()
                    
                    # Check if we are still logged in by looking for a post-login element
                    if await web_handler.wait_for_element_safe(app_config.selector_nav_contract_link, app_config.default_timeout):
                        self.logger.info("Session is still active. Skipping login.")
                        return {"step": "login", "success": True, "cached": True}
                    else:
                        self.logger.info("Session expired or invalid. Proceeding with full login.")
                except PlaywrightTimeoutError as e:
                    self.logger.info("Session expired or invalid. Proceeding with full login.")
                    if is_timeout_error(e):
                        classify_and_raise(f"Timeout validating existing session: {e}")
                    else:
                        classify_and_raise(f"Error validating existing session: {e}")
                except Exception as e:
                    error_str = str(e).lower()
                    # Check if this is a permanent login error
                    if is_login_error(e):
                        # This is likely a permanent error (e.g., account issue)
                        classify_and_raise(f"Permanent error validating existing session: {e}")
                    else:
                        # This might be a temporary network issue
                        self.logger.warning(f"An error occurred during session validation: {e}. Proceeding with full login.")
                        # Don't re-raise here, continue with full login

            self.logger.info(f"Navigating directly to login page: {app_config.ttuex_login_url}")
            await page.goto(
                app_config.ttuex_login_url,
                timeout=app_config.default_timeout,
                wait_until="domcontentloaded",
            )
            self.logger.info(f"Current URL after initial login page navigation: {page.url}")

            # Handle any popups on the login page
            await web_handler.handle_common_popups()

            # Wait for a known element on the login page to ensure it's loaded
            self.logger.info("Waiting for login form to be visible...")
            if not await web_handler.wait_for_element_safe(app_config.selector_login_username_input, app_config.default_timeout):
                # Check if this is due to incorrect credentials vs timeout
                if "/login" in page.url.lower() or "login" in page.title().lower():
                    # We are on login page but can't find the form - might be an error page
                    page_content = await page.content()
                    if any(error_word in page_content.lower() for error_word in ["invalid", "error", "incorrect"]):
                        raise PermanentError("Login page shows error - likely incorrect credentials")
                    else:
                        # This might be a temporary loading issue
                        raise TemporaryError("Login form not visible - possible temporary page loading issue")
                else:
                    # Not on login page - might be a navigation issue
                    raise TemporaryError(f"Did not reach login page as expected. Current URL: {page.url}")
            self.logger.info("Login form is visible.")

            self.logger.info("Filling username...")
            await page.locator(app_config.selector_login_username_input).fill(
                self.username, timeout=app_config.default_timeout
            )

            self.logger.info("Filling password...")
            await page.locator(app_config.selector_login_password_input).fill(
                self.password.get_secret_value(), timeout=app_config.default_timeout
            )

            self.logger.info("Clicking submit button and waiting for authenticated UI...")
            await page.locator(app_config.selector_login_submit_button).click(timeout=app_config.default_timeout)

            # Handle any post-login popups
            await web_handler.handle_common_popups()
            
            # Add explicit wait for URL to change away from login page
            self.logger.info("Waiting for redirection after login...")
            try:
                await page.wait_for_url(
                    lambda url: "/login" not in url.lower() and "login" not in url.lower(),
                    timeout=app_config.default_timeout
                )
            except PlaywrightTimeoutError:
                # Check if we're still on login page (wrong credentials) or just slow redirect
                current_url = page.url
                page_content = await page.content()
                
                # Check for common error indicators on login page
                if any(error_indicator in page_content.lower() for error_indicator in 
                      ["incorrect", "invalid", "error", "wrong password", "wrong credentials"]):
                    raise PermanentError(f"Login failed - likely incorrect credentials. Current URL: {current_url}")
                
                # If still on login page but no error message, it might be a temporary issue
                if "/login" in current_url.lower() or "login" in page.title().lower():
                    raise TemporaryError(f"Still on login page after submission - possible temporary issue. URL: {current_url}")
                else:
                    # We might be on the right page but URL didn't change as expected
                    # Let's check for post-login elements
                    pass

            self.logger.info(f"Current URL after redirection from login page: {page.url}")

            # Wait for a specific post-login element instead of full 'load'
            if not await web_handler.wait_for_element_safe(app_config.selector_nav_contract_link, app_config.default_timeout):
                # Check if this indicates wrong credentials vs loading issue
                current_url = page.url
                page_content = await page.content()
                
                if any(error_indicator in page_content.lower() for error_indicator in 
                      ["incorrect", "invalid", "error", "wrong password", "wrong credentials"]):
                    raise PermanentError(f"Login appeared successful but post-login elements missing - likely incorrect credentials. Current URL: {current_url}")
                else:
                    raise TemporaryError(f"Post-login elements not found. Current URL: {current_url}")

            self.logger.info(f"Found post-login element: {app_config.selector_nav_contract_link}")

            # Save storage state after successful login if configured
            if self.browser_context and self.storage_state_path:
                try:
                    await self.browser_context.storage_state(path=self.storage_state_path)
                    self.logger.info(f"Storage state saved to {self.storage_state_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to save storage state: {e}")

            self.logger.info("Login successful.")
            return {"step": "login", "success": True}

        except PermanentError as e:
            # This is already classified as permanent, so re-raise as is
            error_msg = f"Permanent error during login: {e}"
            self.logger.error(error_msg, exc_info=True)
            if page:
                self.logger.error(f"Current URL at login failure: {page.url}")
            return {
                "step": "login",
                "success": False,
                "error": error_msg,
            }
        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout during login step: {e}"
            self.logger.error(error_msg)
            if page:
                self.logger.error(f"Current URL at login timeout: {page.url}")
            # Classify timeout errors appropriately
            if is_login_error(str(e)):
                classify_and_raise(error_msg)
            else:
                # Network/timeout related - temporary error
                raise TemporaryError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during login: {e}"
            self.logger.error(error_msg, exc_info=True)
            
            # Classify the error as permanent or temporary
            if is_login_error(e):
                # Check if it's a clear login credential issue
                if any(cred_word in str(e).lower() for cred_word in ["password", "credential", "auth"]):
                    classify_and_raise(error_msg)
                else:
                    # Some login errors might be temporary (e.g., network issues during login)
                    if is_network_error(e) or is_timeout_error(e):
                        raise TemporaryError(error_msg)
                    else:
                        # Default to permanent if it's clearly a login issue
                        classify_and_raise(error_msg)
            elif is_network_error(e) or is_timeout_error(e):
                # Network or timeout issues are temporary
                raise TemporaryError(error_msg)
            elif is_element_not_found_error(e):
                # If we can't find expected elements, check if it might be a permanent UI change
                current_url = page.url if page else "unknown"
                self.logger.warning(f"Element not found during login, checking if permanent issue. Current URL: {current_url}")
                # For now, treat as temporary but in real implementation, you might want more sophisticated logic
                raise TemporaryError(error_msg)
            else:
                # Default classification
                if ErrorClassifier.is_permanent_error(e):
                    classify_and_raise(error_msg)
                else:
                    raise TemporaryError(error_msg)

    @async_retry(max_attempts=3)  # Increased to 3 attempts for better resilience
    async def _step_navigate_to_contract(
        self, page: Page, dry_run: bool
    ) -> Dict[str, Any]:
        self.logger.info("Executing step: Navigate to Contract")
        if dry_run:
            await asyncio.sleep(0.1)
            return {"step": "navigate_to_contract", "success": True, "simulated": True}

        try:
            web_handler = WebErrorHandler(page, self.logger)
            
            contract_url = app_config.ttuex_base_url.rstrip('/') + "/trade/btc"
            self.logger.info(f"Navigating directly to contract page: {contract_url}")
            await page.goto(
                contract_url,
                timeout=app_config.default_timeout,
                wait_until="domcontentloaded",
            )
            self.logger.info(f"Current URL after navigating to contract page: {page.url}")

            # Handle any popups that might appear on the contract page
            await web_handler.handle_common_popups()
            
            # Confirm we are on the contract page by waiting for a chart element
            if not await web_handler.wait_for_element_safe('span:has-text("Liste de commandes")', app_config.default_timeout):
                current_url = page.url
                page_content = await page.content()
                
                # Check if we're not logged in (redirected back to login)
                if any(login_word in current_url.lower() for login_word in ["/login", "login-page"]):
                    raise PermanentError(f"Not logged in when navigating to contract. Redirected to: {current_url}")
                
                # Check if page structure has changed
                if "error" in page_content.lower() or "not found" in page_content.lower():
                    raise PermanentError(f"Contract page returned error: {current_url}")
                
                # Otherwise, might be a temporary loading issue
                raise TemporaryError(f"Contract page elements not found. Current URL: {current_url}")
                
            self.logger.info("Successfully navigated to contract page and found chart.")
            return {"step": "navigate_to_contract", "success": True}
        except PermanentError as e:
            error_msg = f"Permanent error navigating to contract page: {e}"
            self.logger.error(error_msg, exc_info=True)
            if app_config.save_debug_html:
                html_path = f"debug_{self.username}_navigate_to_contract_error.html"
                try:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(await page.content())
                    self.logger.error(f"Saved page HTML to {html_path}")
                except Exception as html_e:
                    self.logger.error(f"Failed to save page HTML: {html_e}")
            return {
                "step": "navigate_to_contract",
                "success": False,
                "error": error_msg,
            }
        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout navigating to contract page: {e}"
            self.logger.error(error_msg)
            if is_timeout_error(e):
                raise TemporaryError(error_msg)
            else:
                classify_and_raise(error_msg)
        except Exception as e:
            error_msg = f"Error navigating to contract page: {e}"
            self.logger.error(error_msg, exc_info=True)
            
            if is_network_error(e) or is_timeout_error(e):
                raise TemporaryError(error_msg)
            elif "login" in page.url.lower() or "/login" in page.url.lower():
                # If we got redirected to login, that's a permanent error (not logged in)
                raise PermanentError(error_msg)
            elif ErrorClassifier.is_permanent_error(e):
                classify_and_raise(error_msg)
            else:
                # Default to temporary error for navigation issues
                raise TemporaryError(error_msg)
                
            if app_config.save_debug_html:
                html_path = f"debug_{self.username}_navigate_to_contract_error.html"
                try:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(await page.content())
                    self.logger.error(f"Saved page HTML to {html_path}")
                except Exception as html_e:
                    self.logger.error(f"Failed to save page HTML: {html_e}")
            return {
                "step": "navigate_to_contract",
                "success": False,
                "error": error_msg,
            }

    @async_retry(max_attempts=3)  # Increased to 3 attempts for better resilience
    async def _step_navigate_to_copy_trading(
        self, page: Page, dry_run: bool
    ) -> Dict[str, Any]:
        self.logger.info("Executing step: Navigate to Copy Trading")
        if dry_run:
            await asyncio.sleep(0.1)
            return {
                "step": "navigate_to_copy_trading",
                "success": True,
                "simulated": True,
            }

        try:
            web_handler = WebErrorHandler(page, self.logger)
            
            # Handle any popups first
            await web_handler.handle_common_popups()
            
            # Wait for and click the copy trading button
            if not await web_handler.click_element_safe(app_config.selector_contract_copy_trading_button, app_config.default_timeout):
                current_url = page.url
                page_content = await page.content()
                
                # Check if we've been logged out
                if any(login_word in current_url.lower() for login_word in ["/login", "login-page"]):
                    raise PermanentError(f"Logged out when navigating to copy trading. Redirected to: {current_url}")
                
                # Check if the element exists but is not visible/clickable
                element = page.locator(app_config.selector_contract_copy_trading_button)
                if await element.count() > 0:
                    # Element exists but couldn't be clicked - might be temporary loading issue
                    raise TemporaryError(f"Copy trading button exists but couldn't be clicked. Current URL: {current_url}")
                else:
                    # Element doesn't exist - UI might have changed permanently
                    raise PermanentError(f"Copy trading button not found. UI might have changed. Current URL: {current_url}")
            
            self.logger.info("Successfully clicked copy trading button.")
            return {"step": "navigate_to_copy_trading", "success": True}
            
        except PermanentError as e:
            error_msg = f"Permanent error in navigate to copy trading: {e}"
            self.logger.error(error_msg, exc_info=True)
            if app_config.save_debug_html:
                html_path = f"debug_{self.username}_navigate_to_copy_trading_error.html"
                try:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(await page.content())
                    self.logger.error(f"Saved page HTML to {html_path}")
                except Exception as html_e:
                    self.logger.error(f"Failed to save page HTML: {html_e}")
            
            return {
                "step": "navigate_to_copy_trading",
                "success": False,
                "error": error_msg,
            }
        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout in navigate to copy trading: {e}"
            self.logger.error(error_msg)
            if is_timeout_error(e):
                raise TemporaryError(error_msg)
            else:
                classify_and_raise(error_msg)
        except Exception as e:
            error_msg = f"Error in navigate to copy trading: {e}"
            self.logger.error(error_msg, exc_info=True)
            
            if is_network_error(e) or is_timeout_error(e):
                raise TemporaryError(error_msg)
            elif "login" in page.url.lower() or "/login" in page.url.lower():
                # If we got redirected to login, that's a permanent error (not logged in)
                raise PermanentError(error_msg)
            elif ErrorClassifier.is_permanent_error(e):
                classify_and_raise(error_msg)
            else:
                # Default to temporary error
                raise TemporaryError(error_msg)
                
            if app_config.save_debug_html:
                html_path = f"debug_{self.username}_navigate_to_copy_trading_error.html"
                try:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(await page.content())
                    self.logger.error(f"Saved page HTML to {html_path}")
                except Exception as html_e:
                    self.logger.error(f"Failed to save page HTML: {html_e}")
            return {
                "step": "navigate_to_copy_trading",
                "success": False,
                "error": error_msg,
            }

    async def _step_enter_order_number(
        self, page: Page, order_number: str, dry_run: bool
    ) -> Dict[str, Any]:
        self.logger.info(f"Executing step: Enter Order Number ('{order_number}')")
        if dry_run:
            await asyncio.sleep(0.1)
            return {
                "step": "enter_order_number",
                "success": True,
                "simulated": True,
                "order_number": order_number,
            }

        try:
            web_handler = WebErrorHandler(page, self.logger)
            
            # Handle any popups before entering the order number
            await web_handler.handle_common_popups()
            
            # Fill the order number input
            order_input = page.locator(app_config.selector_contract_order_number_input)
            
            # Wait for the element to be visible first
            if not await web_handler.wait_for_element_safe(app_config.selector_contract_order_number_input, app_config.default_timeout):
                current_url = page.url
                page_content = await page.content()
                
                # Check if we've been logged out
                if any(login_word in current_url.lower() for login_word in ["/login", "login-page"]):
                    raise PermanentError(f"Logged out when entering order number. Redirected to: {current_url}")
                
                # Check if the element exists but is not visible
                if await order_input.count() > 0:
                    raise TemporaryError(f"Order number input exists but couldn't be found. Current URL: {current_url}")
                else:
                    raise PermanentError(f"Order number input not found. UI might have changed. Current URL: {current_url}")
            
            await order_input.fill(order_number, timeout=app_config.default_timeout)
            self.logger.info(f"Successfully entered order number: {order_number}")
            return {
                "step": "enter_order_number",
                "success": True,
                "order_number": order_number,
            }
        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout entering order number: {e}"
            self.logger.error(error_msg)
            if is_timeout_error(e):
                raise TemporaryError(error_msg)
            else:
                classify_and_raise(error_msg)
        except Exception as e:
            error_msg = f"Error entering order number: {e}"
            self.logger.error(error_msg, exc_info=True)
            
            if is_network_error(e) or is_timeout_error(e):
                raise TemporaryError(error_msg)
            elif "login" in page.url.lower() or "/login" in page.url.lower():
                # If we got redirected to login, that's a permanent error
                raise PermanentError(error_msg)
            elif ErrorClassifier.is_permanent_error(e):
                classify_and_raise(error_msg)
            else:
                # Default to temporary error
                raise TemporaryError(error_msg)

    @async_retry(max_attempts=3)  # Increased to 3 attempts for better resilience
    async def _step_execute_follow_up(
        self, page: Page, dry_run: bool
    ) -> Dict[str, Any]:
        self.logger.info("Executing step: Execute Follow-up and Verify")
        if dry_run:
            await asyncio.sleep(0.1)
            return {"step": "execute_follow_up", "success": True, "simulated": True}

        try:
            web_handler = WebErrorHandler(page, self.logger)
            
            # Handle any popups before clicking the follow button
            await web_handler.handle_common_popups()
            
            # Click the follow order button
            follow_button = page.locator(app_config.selector_contract_follow_order_button)
            
            # Wait for the button to be available
            try:
                await follow_button.wait_for(state="visible", timeout=1000)
                self.logger.info("Follow order button is visible")
            except:
                current_url = page.url
                raise TemporaryError(f"Follow order button not visible. Current URL: {current_url}")

            # Click the follow order button with immediate success tracking
            click_success = False
            attempts = max(1, int(getattr(app_config, "follow_order_click_attempts", 1)))
            for i in range(attempts):
                try:
                    await follow_button.click(timeout=1000)
                    self.logger.info(f"Clicked follow order button (attempt {i+1}/{attempts})")
                    click_success = True
                    if i < attempts - 1:
                        await asyncio.sleep(0.2)
                except Exception as e:
                    current_url = page.url
                    self.logger.warning(f"Attempt {i+1}/{attempts} failed to click follow order button: {e}")
                    # Continue attempting or proceed to modal check regardless
                    click_success = True

            # Immediate proceed to check for modal since we know click was attempted
            if click_success:
                self.logger.info("Click registered, proceeding immediately to check for alert modal...")
            else:
                raise TemporaryError(f"Follow order button exists but couldn't be clicked. Current URL: {current_url}")

            # RADICAL-FAST SIMPLIFIED WORKFLOW - immediate action with minimal steps
            self.logger.info("RADICAL-FAST: Starting radically simplified follow order workflow...")
            
            # ULTRA-FAST modal detection and handling - immediate action
            self.logger.info("RADICAL-FAST: Detecting alert modal immediately after follow order click...")
            
            # Ultra-fast modal detection with minimal timeout
            modal_element = page.locator(app_config.selector_order_alert_modal)
            
            try:
                # Ultra-fast wait for modal (should appear instantly)
                await modal_element.wait_for(state="visible", timeout=2000)
                self.logger.info("RADICAL-FAST: Order alert modal detected instantly")
                
                # Ultra-fast message reading
                modal_text = await modal_element.text_content()
                self.logger.info(f"RADICAL-FAST: Modal message: {modal_text.strip()[:150]}...")
                
                # INSTANT DECISION MAKING BASED ON MESSAGE TEXT ONLY - CORRECT INTERPRETATION
                modal_text_lower = modal_text.lower()
                
                # FAILURE CASES - treat as permanent errors
                if "not exist" in modal_text_lower or "completed" in modal_text_lower or "not found" in modal_text_lower:
                    self.logger.warning(f"RADICAL-FAST: Order failed - {modal_text.strip()}")
                    raise PermanentError(f"Order failed - does not exist or completed: {modal_text.strip()}")
                elif "duplicate" in modal_text_lower:
                    self.logger.warning(f"RADICAL-FAST: Duplicate order detected - {modal_text.strip()}")
                    # THIS IS NOW CORRECTLY TREATED AS A FAILURE
                    raise PermanentError(f"Order failed - duplicate (already followed): {modal_text.strip()}")
                
                # CLEAR SUCCESS CASES
                elif "success" in modal_text_lower or "suivi" in modal_text_lower or "réussi" in modal_text_lower or "followed" in modal_text_lower:
                    self.logger.info(f"RADICAL-FAST: Success confirmed: {modal_text.strip()}")
                    # NO CLICK ON "DÉTERMINER" BUTTON NEEDED - JUST READ AND EXIT
                    return {"step": "execute_follow_up", "success": True, "toast_message": f"Success: {modal_text.strip()}"}
                
                # UNKNOWN MESSAGE - conservative treatment
                else:
                    self.logger.warning(f"RADICAL-FAST: Unknown message type - treating as failure: {modal_text.strip()}")
                    # For safety, treat unknown messages as failures
                    raise PermanentError(f"Unknown modal message - treating as failure: {modal_text.strip()}")
                        
            except Exception as e:
                self.logger.info(f"RADICAL-FAST: No modal detected or error reading message: {e}")
                # No modal - this might be normal, continue with toast checking
            
            # Immediate completion - no button clicking, no additional waiting
            self.logger.info("RADICAL-FAST: Message reading completed - proceeding to toast check")
            
            # Continue with the rest of the process after handling the alert
            
            # Wait for potential toast notification after handling the alert
            toast_locator = page.locator("div.adm-toast-main").first
            toast_timeout = 0
            
            # Wait for toast with a timeout
            try:
                await page.wait_for_selector("div.adm-toast-main", timeout=5000)
                toast_text = (await toast_locator.text_content() or "").strip()
                self.logger.info(f"Confirmation toast appeared with text: '{toast_text}'")

                # Check for explicit success message
                if "succesfully followed" in toast_text.lower() or "suivi réussi" in toast_text.lower() or "success" in toast_text.lower() or "suivi" in toast_text.lower():
                    self.logger.info("Follow-up appears successful.")
                    return {"step": "execute_follow_up", "success": True, "toast_message": toast_text}

                # Handle failure messages
                elif "completed" in toast_text.lower() or "not exist" in toast_text.lower() or "failed" in toast_text.lower() or "duplicate" in toast_text.lower():
                    self.logger.warning(f"Follow-up failed with toast: {toast_text}")
                    # This might be a permanent error (order doesn't exist) or temporary (system issue)
                    if "not exist" in toast_text.lower() or "duplicate" in toast_text.lower():
                        raise PermanentError(f"Follow-up failed - order may not exist or is duplicate: {toast_text}")
                    else:
                        raise TemporaryError(f"Follow-up failed: {toast_text}")
                else:
                    # Unclear result - might need to retry
                    self.logger.info(f"Unclear result from toast message: {toast_text}. Treating as temporary issue to retry.")
                    raise TemporaryError(f"Unclear result: {toast_text}")
            except:
                # Toast didn't appear, check if the alert itself had the status info
                toast_timeout = 1
                self.logger.info("Toast not found, but checking page for status information...")
                
                # Check if the alert content is directly visible on the page (not in toast)
                page_content = await page.content()
                
                if "duplicate" in page_content.lower():
                    self.logger.warning("Found 'duplicate' status in page content")
                    raise PermanentError(f"Follow-up failed - order is duplicate: {page_content[page_content.find('duplicate')-50:page_content.find('duplicate')+50]}")
                elif any(success_ind in page_content.lower() for success_ind in ["suivi", "réussi", "success", "suivi réussi"]):
                    self.logger.info("Success status found in page content")
                    return {"step": "execute_follow_up", "success": True, "toast_message": "Success found in page content"}
                else:
                    # Save page content for debugging
                    if app_config.save_debug_html:
                        html_path = f"debug_{self.username}_after_follow_up_new_ui.html"
                        try:
                            with open(html_path, "w", encoding="utf-8") as f:
                                f.write(await page.content())
                            self.logger.info(f"Saved page HTML to {html_path} - check for new UI elements")
                        except Exception as html_e:
                            self.logger.error(f"Failed to save page HTML: {html_e}")
                    
                    error_msg = "Status message not found in toast or page content"
                    self.logger.warning(error_msg)
                    return {"step": "execute_follow_up", "success": True, "toast_message": "Status message not found, but action may have succeeded"}

            # If we only had timeout but no exception (toast appeared after initial timeout check)
            if toast_timeout == 0:
                toast_text = (await toast_locator.text_content() or "").strip()
                self.logger.info(f"Confirmation toast appeared with text: '{toast_text}'")

                # Check for explicit success message
                if "succesfully followed" in toast_text.lower() or "suivi réussi" in toast_text.lower() or "success" in toast_text.lower() or "suivi" in toast_text.lower():
                    self.logger.info("Follow-up appears successful.")
                    return {"step": "execute_follow_up", "success": True, "toast_message": toast_text}

                # Handle failure messages
                elif "completed" in toast_text.lower() or "not exist" in toast_text.lower() or "failed" in toast_text.lower() or "duplicate" in toast_text.lower():
                    self.logger.warning(f"Follow-up failed with toast: {toast_text}")
                    # This might be a permanent error (order doesn't exist) or temporary (system issue)
                    if "not exist" in toast_text.lower() or "duplicate" in toast_text.lower():
                        raise PermanentError(f"Follow-up failed - order may not exist or is duplicate: {toast_text}")
                    else:
                        raise TemporaryError(f"Follow-up failed: {toast_text}")
                else:
                    # Unclear result - might need to retry
                    self.logger.info(f"Unclear result from toast message: {toast_text}. Treating as temporary issue to retry.")
                    raise TemporaryError(f"Unclear result: {toast_text}")

        except PermanentError as e:
            error_msg = f"Permanent error during follow-up: {e}"
            self.logger.error(error_msg, exc_info=True)
            return {"step": "execute_follow_up", "success": False, "error": error_msg}
        except PlaywrightTimeoutError as e:
            error_msg = "Timeout waiting for confirmation toast after clicking follow-up."
            self.logger.error(error_msg)
            if is_timeout_error(e):
                raise TemporaryError(error_msg)
            else:
                classify_and_raise(error_msg)
        except Exception as e:
            error_msg = f"An unexpected error occurred during follow-up: {e}"
            self.logger.error(error_msg, exc_info=True)
            
            if is_network_error(e) or is_timeout_error(e):
                raise TemporaryError(error_msg)
            elif "login" in page.url.lower() or "/login" in page.url.lower():
                # If we got redirected to login, that's permanent
                raise PermanentError(error_msg)
            elif ErrorClassifier.is_permanent_error(e):
                classify_and_raise(error_msg)
            else:
                # Default to temporary error for follow-up issues
                raise TemporaryError(error_msg)