"""
This module contains the core actions that can be triggered by different interfaces
(CLI, Webhook, etc.). It decouples the action logic from the interface itself.
"""

import os
from typing import Optional
from playwright.async_api import Browser, BrowserContext
from telethon import TelegramClient # For type hinting

from ttuex_bot.config import app_config, load_accounts_from_json, AccountCredentials
from ttuex_bot.core.workflow import TtuexWorkflow
from ttuex_bot.utils.logging import get_logger

logger = get_logger("Actions")


def get_accounts_to_process(accounts_file: str = "accounts.json") -> list[AccountCredentials]:
    """Load accounts from JSON file or fall back to .env credentials."""
    accounts_config = load_accounts_from_json(accounts_file)
    if accounts_config.accounts:
        return accounts_config.accounts

    if app_config.ttuex_username and app_config.ttuex_password:
        return [
            AccountCredentials(
                account_name="default_account",
                username=app_config.ttuex_username,
                password=app_config.ttuex_password,
            )
        ]
    return []


async def run_login_for_account(account: AccountCredentials, browser: Browser, adapter, context: BrowserContext, **kwargs):
    logger.info(f"Attempting to run login for account: {account.account_name}")
    performant = kwargs.get("performant", False)

    # Prepare storage state path per account if enabled
    storage_state_path = None
    if app_config.storage_state_enabled:
        storage_dir = os.path.join(os.getcwd(), app_config.storage_state_dir)
        os.makedirs(storage_dir, exist_ok=True)
        storage_state_path = os.path.join(storage_dir, f"{account.account_name}.json")

    try:
        page = await context.new_page()
        workflow = TtuexWorkflow(
            username=account.username,
            password=account.password,
            browser_context=context,
            storage_state_path=storage_state_path,
            page=page, # Pass the created page to the workflow
        )
        return await workflow.execute_login(dry_run=kwargs.get("dry_run", True))
    finally:
        # Context is managed by the orchestrator, not closed here
        if page and not page.is_closed():
            await page.close()


async def run_copy_trade_for_account(
    account: AccountCredentials, 
    browser: Browser, 
    adapter, 
    context: BrowserContext, # Added context parameter
    telethon_client: Optional[TelegramClient] = None, 
    chat_id: Optional[int] = None, 
    **kwargs
):
    """Worker function to perform copy trade for a single account."""
    logger.info(f"Attempting to run copy trade for account: {account.account_name}")
    performant = kwargs.get("performant", False)

    # Prepare storage state path per account if enabled
    storage_state_path = None
    if app_config.storage_state_enabled:
        storage_dir = os.path.join(os.getcwd(), app_config.storage_state_dir)
        os.makedirs(storage_dir, exist_ok=True)
        storage_state_path = os.path.join(storage_dir, f"{account.account_name}.json")

    try:
        page = await context.new_page()
        workflow = TtuexWorkflow(
            username=account.username,
            password=account.password,
            browser_context=context,
            storage_state_path=storage_state_path,
            page=page, # Pass the created page to the workflow
        )
        report = await workflow.execute_copy_trade(**kwargs)
        if not report.get("success"):
            # If the workflow itself reported a failure, notify the user.
            error_message = report.get("error", "Unknown error during workflow execution.")
            logger.warning(f"Workflow failed for {account.account_name}: {error_message}")
            if telethon_client and chat_id:
                await telethon_client.send_message(chat_id, f"🔴 ÉCHEC pour le compte {account.account_name}: {error_message}")
        return report
    except Exception as e:
        # Catch unexpected errors that might crash the workflow
        logger.error(f"Critical error in workflow for account {account.account_name}: {e}", exc_info=True)
        if telethon_client and chat_id:
            await telethon_client.send_message(chat_id, f"🔴 ERREUR CRITIQUE pour le compte {account.account_name}: {e}")
        # Return a consistent failure report
        return {
            "account_name": account.account_name,
            "success": False,
            "error": str(e),
            "steps": [],
            "screenshots_taken": [],
        }
    finally:
        if page and not page.is_closed():
            await page.close()
