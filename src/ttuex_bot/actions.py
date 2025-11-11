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
from ttuex_bot.utils.translators import translate_error

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
    logger.info(f"run_login_for_account called for account: {account.account_name}")
    logger.info(f"Function parameters: kwargs={list(kwargs.keys())}")
    performant = kwargs.get("performant", False)

    # Prepare storage state path per account if enabled
    storage_state_path = None
    if app_config.storage_state_enabled:
        storage_dir = os.path.join(os.getcwd(), app_config.storage_state_dir)
        os.makedirs(storage_dir, exist_ok=True)
        storage_state_path = os.path.join(storage_dir, f"{account.account_name}.json")

    try:
        logger.debug(f"Creating new page for account: {account.account_name}")
        page = await context.new_page()
        logger.debug(f"Page created for account: {account.account_name}")
        
        workflow = TtuexWorkflow(
            username=account.username,
            password=account.password,
            browser_context=context,
            storage_state_path=storage_state_path,
            page=page, # Pass the created page to the workflow
        )
        logger.debug(f"Workflow created for account: {account.account_name}, calling execute_login")
        result = await workflow.execute_login(dry_run=kwargs.get("dry_run", True))
        logger.info(f"execute_login completed for account: {account.account_name}, result: {type(result)}")
        return result
    finally:
        # Context is managed by the orchestrator, not closed here
        if 'page' in locals() and page and not page.is_closed():
            await page.close()
            logger.debug(f"Page closed for account: {account.account_name}")


async def run_copy_trade_for_account(
    account: AccountCredentials, 
    browser: Browser, 
    adapter, 
    context: BrowserContext,
    telethon_client: Optional[TelegramClient] = None, 
    chat_id: Optional[int] = None, 
    **kwargs
):
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
            page=page,
        )
        report = await workflow.execute_copy_trade(**kwargs)
        return report
    except Exception as e:
        logger.error(f"Critical error in workflow for account {account.account_name}: {e}")
        return {
            "account_name": account.account_name,
            "success": False,
            "error": str(e),
            "steps": [],
        }
    finally:
        if 'page' in locals() and page and not page.is_closed():
            await page.close()
