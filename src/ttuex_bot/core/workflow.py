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
from ttuex_bot.utils.retry import async_retry


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
                raise Exception("BrowserContext not provided to workflow.")

            if not self.page:
                self.page = await self.browser_context.new_page()

            login_result = await self._step_login(self.page, dry_run)
            report["steps"].append(login_result)
            if not login_result.get("success", False):
                raise Exception(f"Step 'login' failed: {login_result.get('error')}")

            report["success"] = True
            self.logger.info("Login workflow completed successfully.")

        except Exception as e:
            report["error"] = str(e)
            self.logger.error("Login workflow failed", error=str(e))

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
                    raise Exception("BrowserContext not provided for live run.")

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
                        raise Exception(f"Step '{result.get('step')}' failed: {result.get('error')}")

                report["success"] = True
                self.logger.info("Live run workflow completed successfully.")

        except Exception as e:
            report["error"] = str(e)
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

    @async_retry(max_attempts=2)
    async def _step_login(self, page: Page, dry_run: bool) -> Dict[str, Any]:
        self.logger.info("Executing step: Standard Login")
        if dry_run:
            return {"step": "login", "success": True, "simulated": True}

        try:
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
                    # Check if we are still logged in by looking for a post-login element
                    await page.locator(app_config.selector_nav_contract_link).first.wait_for(
                        state="visible", timeout=app_config.default_timeout
                    )
                    self.logger.info("Session is still active. Skipping login.")
                    return {"step": "login", "success": True, "cached": True}
                except PlaywrightTimeoutError:
                    self.logger.info("Session expired or invalid. Proceeding with full login.")
                except Exception as e:
                    self.logger.warning(f"An error occurred during session validation: {e}. Proceeding with full login.")

            self.logger.info(f"Navigating directly to login page: {app_config.ttuex_login_url}")
            await page.goto(
                app_config.ttuex_login_url,
                timeout=app_config.default_timeout,
                wait_until="domcontentloaded",
            )
            self.logger.info(f"Current URL after initial login page navigation: {page.url}")

            # Wait for a known element on the login page to ensure it's loaded
            self.logger.info("Waiting for login form to be visible...")
            await page.locator(app_config.selector_login_username_input).wait_for(
                timeout=app_config.default_timeout
            )
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

            # Add explicit wait for URL to change away from login page
            self.logger.info("Waiting for redirection after login...")
            await page.wait_for_url(
                lambda url: "/login-page" not in url,
                timeout=app_config.default_timeout
            )
            self.logger.info(f"Current URL after redirection from login page: {page.url}")

            # Wait for a specific post-login element instead of full 'load'
            await page.locator(app_config.selector_nav_contract_link).first.wait_for(
                state="visible", timeout=app_config.default_timeout
            )
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

        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout during login step: {e}"
            self.logger.error(error_msg)
            if page:
                self.logger.error(f"Current URL at login timeout: {page.url}")
            return {
                "step": "login",
                "success": False,
                "error": error_msg,
            }
        except Exception as e:
            error_msg = f"Unexpected error during login: {e}"
            self.logger.error(error_msg, exc_info=True)
            if page:
                self.logger.error(f"Current URL at unexpected login error: {page.url}")
            return {
                "step": "login",
                "success": False,
                "error": error_msg,
            }

    @async_retry(max_attempts=2)
    async def _step_navigate_to_contract(
        self, page: Page, dry_run: bool
    ) -> Dict[str, Any]:
        self.logger.info("Executing step: Navigate to Contract")
        if dry_run:
            await asyncio.sleep(0.1)
            return {"step": "navigate_to_contract", "success": True, "simulated": True}

        try:
            contract_url = app_config.ttuex_base_url.rstrip('/') + "/trade/btc"
            self.logger.info(f"Navigating directly to contract page: {contract_url}")
            await page.goto(
                contract_url,
                timeout=app_config.default_timeout,
                wait_until="domcontentloaded",
            )
            self.logger.info(f"Current URL after navigating to contract page: {page.url}")

            # Confirm we are on the contract page by waiting for a chart element
            await page.locator('span:has-text("Liste de commandes")').first.wait_for(
                state="visible", timeout=app_config.default_timeout
            )
            self.logger.info("Successfully navigated to contract page and found chart.")
            return {"step": "navigate_to_contract", "success": True}
        except Exception as e:
            error_msg = f"Error navigating to contract page: {e}"
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

    @async_retry(max_attempts=2)
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
            copy_trade_locator = page.locator(
                app_config.selector_contract_copy_trading_button
            )
            await copy_trade_locator.wait_for(state="visible", timeout=app_config.default_timeout)
            await copy_trade_locator.scroll_into_view_if_needed(timeout=app_config.default_timeout)
            await copy_trade_locator.click(timeout=app_config.default_timeout)
            return {"step": "navigate_to_copy_trading", "success": True}
        except Exception as e:
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
                "error": str(e),
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
            await page.locator(app_config.selector_contract_order_number_input).fill(
                order_number, timeout=app_config.default_timeout
            )
            return {
                "step": "enter_order_number",
                "success": True,
                "order_number": order_number,
            }
        except Exception as e:
            return {"step": "enter_order_number", "success": False, "error": str(e)}

    @async_retry(max_attempts=2)
    async def _step_execute_follow_up(
        self, page: Page, dry_run: bool
    ) -> Dict[str, Any]:
        self.logger.info("Executing step: Execute Follow-up and Verify")
        if dry_run:
            await asyncio.sleep(0.1)
            return {"step": "execute_follow_up", "success": True, "simulated": True}

        try:
            await page.locator(app_config.selector_contract_follow_order_button).click(
                timeout=app_config.follow_button_timeout
            )

            # Wait for the toast container to appear
            toast_locator = page.locator("div.adm-toast-main").first
            await toast_locator.wait_for(state="visible", timeout=app_config.default_timeout)
            toast_text = (await toast_locator.text_content() or "").strip()
            self.logger.info(f"Confirmation toast appeared with text: '{toast_text}'")

            # Check for explicit success message
            if "succesfully followed" in toast_text.lower() or "suivi réussi" in toast_text.lower():
                self.logger.info("Follow-up appears successful.")
                return {"step": "execute_follow_up", "success": True, "toast_message": toast_text}

            # Handle failure messages
            else:
                self.logger.warning(f"Follow-up failed with toast: {toast_text}")
                return {"step": "execute_follow_up", "success": False, "error": f"Follow-up failed with message: {toast_text}"}

        except PlaywrightTimeoutError:
            error_msg = "Timeout waiting for confirmation toast after clicking follow-up."
            self.logger.error(error_msg)
            return {"step": "execute_follow_up", "success": False, "error": error_msg}
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during follow-up: {e}", exc_info=True)
            return {"step": "execute_follow_up", "success": False, "error": str(e)}