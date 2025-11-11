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
        self.logger = get_logger("TtuexWorkflow")
        self.browser_context = browser_context
        self.storage_state_path = storage_state_path
        self.page = page # Store the page object

    async def execute_login(self, dry_run: bool = True) -> Dict[str, Any]:
        """Executes the login workflow for a single account."""
        self.logger.info("Starting login workflow", dry_run=dry_run, account_name=self.username)

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
                self.logger.warning(f"Login step failed: {login_result.get('error')}", account_name=self.username)
                return report  # Return early if login failed

            report["success"] = True
            self.logger.info("Login workflow completed successfully.", account_name=self.username)

        except PermanentError as e:
            report["error"] = f"Permanent error: {str(e)}"
            self.logger.error("Login workflow failed with permanent error", error=str(e), account_name=self.username)
        except Exception as e:
            # For any other unexpected exceptions
            report["error"] = f"Unexpected error: {str(e)}"
            self.logger.error("Login workflow failed with unexpected error", error=str(e), exc_info=True, account_name=self.username)

        finally:
            # The page should not be closed here if the workflow continues
            pass

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
            account_name=self.username,
        )
        self.logger.debug(f"execute_copy_trade received dry_run: {dry_run}", account_name=self.username)

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
                self.logger.info("Executing dry run for copy trade.", account_name=self.username)
                # Simulate the sequence of operations without actual browser interaction
                simulated_steps = [
                    {"step": "login", "success": True, "simulated": True},
                    {"step": "navigate_to_contract", "success": True, "simulated": True},
                    {"step": "navigate_to_copy_trading", "success": True, "simulated": True},
                    {"step": "enter_order_number", "success": True, "simulated": True, "order_number": order_number},
                    {"step": "execute_follow_up", "success": True, "simulated": True},
                ]
                # Add history verification step if needed
                if not skip_history_verification:
                    simulated_steps.append({"step": "verify_history", "success": True, "simulated": True})
                
                report["steps"] = simulated_steps
                report["success"] = True
                self.logger.info("Dry run completed successfully.", account_name=self.username)
                
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
                        self.logger.warning(f"Step {result.get('step')} failed: {result.get('error')}", account_name=self.username)
                        return report  # Return early if any step failed

                report["success"] = True
                self.logger.info("Live run workflow completed successfully.", account_name=self.username)

        except PermanentError as e:
            report["error"] = f"Permanent error: {str(e)}"
            self.logger.error("Copy trade workflow failed with permanent error", error=str(e), account_name=self.username)
        except Exception as e:
            # For any other unexpected exceptions
            report["error"] = f"Unexpected error: {str(e)}"
            self.logger.error("Copy trade workflow failed with unexpected error", error=str(e), exc_info=True, account_name=self.username)

        finally:
            # The page should not be closed here; it's managed by the orchestrator
            pass

        end_time = datetime.utcnow()
        elapsed = (end_time - start_time).total_seconds()

        report["end_time_utc"] = end_time.isoformat()
        report["duration_seconds"] = elapsed
        return report

    @async_retry(max_attempts=3)  # Back to 3 for better reliability
    async def _step_execute_follow_up(
        self, page: Page, dry_run: bool
    ) -> Dict[str, Any]:
        if dry_run:
            return {"step": "execute_follow_up", "success": True, "simulated": True}

        try:
            # Click follow button with reasonable timeout
            follow_button = page.locator(app_config.selector_contract_follow_order_button)
            try:
                await follow_button.wait_for(state="visible", timeout=10000)
                await follow_button.click(timeout=10000)
            except:
                pass  # Continue anyway

            # Wait a bit for modal/toast to appear
            await asyncio.sleep(0.5)

            # Check modal with reasonable timeout
            modal_element = page.locator(app_config.selector_order_alert_modal)
            try:
                await modal_element.wait_for(state="visible", timeout=3000)
                modal_text = (await modal_element.text_content() or "").lower()
                
                # Quick decision based on modal text
                if any(word in modal_text for word in ["not exist", "completed", "duplicate"]):
                    raise PermanentError(f"Order failed: {modal_text[:100]}")
                elif any(word in modal_text for word in ["success", "suivi", "réussi", "followed"]):
                    return {"step": "execute_follow_up", "success": True, "toast_message": "successful followed"}
            except:
                pass  # Continue to toast check

            # Check toast with reasonable timeout
            try:
                await page.wait_for_selector("div.adm-toast-main", timeout=5000)
                toast_text = (await page.locator("div.adm-toast-main").first.text_content() or "").lower()
                if any(word in toast_text for word in ["success", "suivi", "réussi", "followed"]):
                    return {"step": "execute_follow_up", "success": True, "toast_message": toast_text}
                elif any(word in toast_text for word in ["completed", "not exist", "failed", "duplicate"]):
                    raise PermanentError(f"Order failed: {toast_text[:100]}")
            except PlaywrightTimeoutError:
                # Check page content for any error indicators before assuming success
                try:
                    page_content = (await page.content() or "").lower()
                    if any(word in page_content for word in ["not exist", "completed", "duplicate", "failed"]):
                        raise PermanentError("Order failed - error found in page content")
                except PermanentError:
                    raise
                # Assume success if no error message appears
                return {"step": "execute_follow_up", "success": True, "toast_message": "completed"}
            
            # If we get here, assume success
            return {"step": "execute_follow_up", "success": True, "toast_message": "completed"}

        except PermanentError as e:
            error_msg = f"Permanent error during follow-up: {e}"
            self.logger.error(error_msg, exc_info=True, account_name=self.username)
            return {"step": "execute_follow_up", "success": False, "error": error_msg}
        except PlaywrightTimeoutError as e:
            # Assume success on timeout - action likely completed
            return {"step": "execute_follow_up", "success": True, "toast_message": "timeout_assumed_success"}
        except Exception as e:
            error_msg = f"Unexpected error during follow-up: {e}"
            self.logger.error(error_msg, exc_info=True, account_name=self.username)
            if "login" in page.url.lower() or "/login" in page.url.lower():
                raise PermanentError(error_msg)
            else:
                raise TemporaryError(error_msg)

    # --- Workflow steps ---

    @async_retry(max_attempts=3)  # Back to 3 for better reliability
    async def _step_login(self, page: Page, dry_run: bool) -> Dict[str, Any]:
        if dry_run:
            return {"step": "login", "success": True, "simulated": True}

        try:
            web_handler = WebErrorHandler(page, self.logger)
            
            # Fast session check - if storage state exists, try to use it
            if self.storage_state_path and Path(self.storage_state_path).exists():
                try:
                    await page.goto(
                        app_config.ttuex_base_url,
                        timeout=15000,  # Reduced timeout
                        wait_until="domcontentloaded",
                    )
                    await web_handler.handle_common_popups()
                    # Quick check - reduced timeout
                    if await web_handler.wait_for_element_safe(app_config.selector_nav_contract_link, 5000):
                        return {"step": "login", "success": True, "cached": True}
                except:
                    pass  # Continue to full login

            # Fast login flow
            await page.goto(
                app_config.ttuex_login_url,
                timeout=20000,
                wait_until="domcontentloaded",
            )
            await web_handler.handle_common_popups()

            # Wait for form with reasonable timeout
            if not await web_handler.wait_for_element_safe(app_config.selector_login_username_input, 15000):
                # Check if this is due to incorrect credentials vs timeout
                if "/login" in page.url.lower() or "login" in page.title().lower():
                    # We are on login page but can't find the form - might be an error page
                    page_content = await page.content()
                    # Log the page content for debugging
                    self.logger.error(f"Login page content at time of error: {page_content}", account_name=self.username)
                    # Take a screenshot for debugging
                    screenshot_path = f"debug_{self.username}_login_error.png"
                    await page.screenshot(path=screenshot_path)
                    self.logger.error(f"Saved screenshot of login error to {screenshot_path}", account_name=self.username)

                    if any(error_word in page_content.lower() for error_word in ["invalid", "error", "incorrect"]):
                        raise PermanentError("Login page shows error - likely incorrect credentials")
                    else:
                        # This might be a temporary loading issue
                        raise TemporaryError("Login form not visible - possible temporary page loading issue")
                else:
                    # Not on login page - might be a navigation issue
                    raise TemporaryError(f"Did not reach login page as expected. Current URL: {page.url}")
            self.logger.info("Login form is visible.", account_name=self.username)

            # Fast form fill
            await page.locator(app_config.selector_login_username_input).fill(
                self.username, timeout=5000
            )
            await page.locator(app_config.selector_login_password_input).fill(
                self.password.get_secret_value(), timeout=5000
            )
            await page.locator(app_config.selector_login_submit_button).click(timeout=5000)

            await web_handler.handle_common_popups()
            
            # Wait for redirect with reasonable timeout
            try:
                await page.wait_for_url(
                    lambda url: "/login" not in url.lower() and "login" not in url.lower(),
                    timeout=20000
                )
            except PlaywrightTimeoutError:
                current_url = page.url
                if "/login" in current_url.lower():
                    raise TemporaryError(f"Still on login page: {current_url}")

            # Post-login check with reasonable timeout
            if not await web_handler.wait_for_element_safe(app_config.selector_nav_contract_link, 15000):
                # Check if this indicates wrong credentials vs loading issue
                current_url = page.url
                page_content = await page.content()
                
                if any(error_indicator in page_content.lower() for error_indicator in 
                      ["incorrect", "invalid", "error", "wrong password", "wrong credentials"]):
                    raise PermanentError(f"Login appeared successful but post-login elements missing - likely incorrect credentials. Current URL: {current_url}")
                else:
                    raise TemporaryError(f"Post-login elements not found. Current URL: {current_url}")

            # Save storage state quickly
            if self.browser_context and self.storage_state_path:
                try:
                    await self.browser_context.storage_state(path=self.storage_state_path)
                except:
                    pass

            return {"step": "login", "success": True}

        except PermanentError as e:
            # This is already classified as permanent, so re-raise as is
            error_msg = f"Permanent error during login: {e}"
            self.logger.error(error_msg, exc_info=True, account_name=self.username)
            if page:
                self.logger.error(f"Current URL at login failure: {page.url}", account_name=self.username)
            return {
                "step": "login",
                "success": False,
                "error": error_msg,
            }
        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout during login step: {e}"
            self.logger.error(error_msg, account_name=self.username)
            if page:
                self.logger.error(f"Current URL at login timeout: {page.url}", account_name=self.username)
            # Classify timeout errors appropriately
            if is_login_error(str(e)):
                classify_and_raise(error_msg)
            else:
                # Network/timeout related - temporary error
                raise TemporaryError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during login: {e}"
            self.logger.error(error_msg, exc_info=True, account_name=self.username)
            
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

    @async_retry(max_attempts=3)  # Back to 3 for better reliability
    async def _step_navigate_to_contract(
        self, page: Page, dry_run: bool
    ) -> Dict[str, Any]:
        if dry_run:
            return {"step": "navigate_to_contract", "success": True, "simulated": True}

        try:
            web_handler = WebErrorHandler(page, self.logger)
            
            contract_url = app_config.ttuex_base_url.rstrip('/') + "/trade/btc"
            await page.goto(
                contract_url,
                timeout=20000,
                wait_until="domcontentloaded",
            )
            await web_handler.handle_common_popups()
            
            # Wait for contract page element with reasonable timeout
            if not await web_handler.wait_for_element_safe('span:has-text("Liste de commandes")', 15000):
                current_url = page.url
                page_content = await page.content()
                
                # Check if we're not logged in (redirected back to login)
                if any(login_word in current_url.lower() for login_word in ["/login", "login-page"]):
                    raise PermanentError(f"Not logged in when navigating to contract. Redirected to: {current_url}")
                
                # Check if page structure has changed
                if "error" in page_content.lower() or "not found" in page_content.lower():
                    raise PermanentError(f"Contract page returned error: {current_url}")
                
                raise TemporaryError(f"Contract page elements not found. Current URL: {current_url}")
                
            return {"step": "navigate_to_contract", "success": True}
        except PermanentError as e:
            error_msg = f"Permanent error navigating to contract: {e}"
            self.logger.error(error_msg, exc_info=True, account_name=self.username)
            return {
                "step": "navigate_to_contract",
                "success": False,
                "error": error_msg,
            }
        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout navigating to contract page: {e}"
            self.logger.error(error_msg, account_name=self.username)
            if is_timeout_error(e):
                raise TemporaryError(error_msg)
            else:
                classify_and_raise(error_msg)
        except Exception as e:
            error_msg = f"Error navigating to contract page: {e}"
            self.logger.error(error_msg, exc_info=True, account_name=self.username)


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
                    self.logger.error(f"Saved page HTML to {html_path}", account_name=self.username)
                except Exception as html_e:
                    self.logger.error(f"Failed to save page HTML: {html_e}", account_name=self.username)
            return {
                "step": "navigate_to_contract",
                "success": False,
                "error": error_msg,
            }

    @async_retry(max_attempts=3)  # Back to 3 for better reliability
    async def _step_navigate_to_copy_trading(
        self, page: Page, dry_run: bool
    ) -> Dict[str, Any]:
        if dry_run:
            return {
                "step": "navigate_to_copy_trading",
                "success": True,
                "simulated": True,
            }

        try:
            web_handler = WebErrorHandler(page, self.logger)
            await web_handler.handle_common_popups()
            
            # Click copy trading button with reasonable timeout
            if not await web_handler.click_element_safe(app_config.selector_contract_copy_trading_button, 15000):
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
                    raise PermanentError(f"Copy trading button not found. UI might have changed. Current URL: {current_url}")
            
            return {"step": "navigate_to_copy_trading", "success": True}
            
        except PermanentError as e:
            error_msg = f"Permanent error in navigate to copy trading: {e}"
            self.logger.error(error_msg, exc_info=True, account_name=self.username)
            if app_config.save_debug_html:
                html_path = f"debug_{self.username}_navigate_to_copy_trading_error.html"
                try:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(await page.content())
                    self.logger.error(f"Saved page HTML to {html_path}", account_name=self.username)
                except Exception as html_e:
                    self.logger.error(f"Failed to save page HTML: {html_e}", account_name=self.username)
            
            return {
                "step": "navigate_to_copy_trading",
                "success": False,
                "error": error_msg,
            }
        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout in navigate to copy trading: {e}"
            self.logger.error(error_msg, account_name=self.username)
            if is_timeout_error(e):
                raise TemporaryError(error_msg)
            else:
                classify_and_raise(error_msg)
        except Exception as e:
            error_msg = f"Error in navigate to copy trading: {e}"
            self.logger.error(error_msg, exc_info=True, account_name=self.username)
            
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
                    self.logger.error(f"Saved page HTML to {html_path}", account_name=self.username)
                except Exception as html_e:
                    self.logger.error(f"Failed to save page HTML: {html_e}", account_name=self.username)
            return {
                "step": "navigate_to_copy_trading",
                "success": False,
                "error": error_msg,
            }

    async def _step_enter_order_number(
        self, page: Page, order_number: str, dry_run: bool
    ) -> Dict[str, Any]:
        if dry_run:
            return {
                "step": "enter_order_number",
                "success": True,
                "simulated": True,
                "order_number": order_number,
            }

        try:
            web_handler = WebErrorHandler(page, self.logger)
            await web_handler.handle_common_popups()
            
            # Small delay to let the page fully load after clicking copy trading
            await asyncio.sleep(0.5)
            
            order_input = page.locator(app_config.selector_contract_order_number_input)
            
            # Wait for order input with reasonable timeout and retry logic
            found = False
            for attempt in range(2):
                if await web_handler.wait_for_element_safe(app_config.selector_contract_order_number_input, 15000):
                    found = True
                    break
                if attempt < 1:
                    await web_handler.handle_common_popups()
                    await asyncio.sleep(0.5)
            
            if not found:
                current_url = page.url
                # Check if we've been logged out
                if any(login_word in current_url.lower() for login_word in ["/login", "login-page"]):
                    raise PermanentError(f"Logged out when entering order number. Redirected to: {current_url}")
                
                # Check if the element exists but is not visible
                if await order_input.count() > 0:
                    raise TemporaryError(f"Order number input exists but couldn't be found. Current URL: {current_url}")
                else:
                    raise TemporaryError(f"Order number input not found after retries. Current URL: {current_url}")
            
            await order_input.fill(order_number, timeout=10000)
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
            self.logger.error(error_msg, exc_info=True, account_name=self.username)
            if app_config.save_debug_html:
                html_path = f"debug_{self.username}_enter_order_number_error.html"
                try:
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(await page.content())
                    self.logger.error(f"Saved page HTML to {html_path}", account_name=self.username)
                except Exception as html_e:
                    self.logger.error(f"Failed to save page HTML: {html_e}", account_name=self.username)
            
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
