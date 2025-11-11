import asyncio
import logging
import os
from typing import List, Dict, Callable, Coroutine, Any

from playwright.async_api import Browser

from ttuex_bot.config import app_config, AccountCredentials
from ttuex_bot.playwright_adapter import PlaywrightAdapter


logger = logging.getLogger(__name__)

async def orchestrate_accounts(
    accounts: List[AccountCredentials],
    run_for_account: Callable[..., Coroutine[Any, Any, Dict]],
    max_concurrency: int,
    browser: Browser,
    adapter: PlaywrightAdapter,
    **kwargs
) -> List[Dict]:
    """
    Orchestrates the execution of an asynchronous task for multiple accounts concurrently.

    Args:
        accounts: A list of account objects to process.
        run_for_account: An async callable that performs the work for a single account.
        max_concurrency: The maximum number of tasks to run in parallel.
        browser: The Playwright browser instance.
        adapter: The Playwright adapter instance.
        **kwargs: Additional keyword arguments to pass to the `run_for_account` function.

    Returns:
        A list of result dictionaries from each task.
    """
    if not accounts:
        return []
        
    limit = max(1, min(int(max_concurrency or 1), 10))
    semaphore = asyncio.Semaphore(limit)
    tasks = []

    async def worker(account: AccountCredentials):
        async with semaphore:
            context = None
            try:
                storage_state_path = None
                if app_config.storage_state_enabled:
                    storage_dir = os.path.join(os.getcwd(), app_config.storage_state_dir)
                    os.makedirs(storage_dir, exist_ok=True)
                    storage_state_path = os.path.join(storage_dir, f"{account.account_name}.json")

                context = await adapter.new_context(
                    browser,
                    device=None,
                    performant=kwargs.get("performant", False),
                    storage_state_path=storage_state_path,
                )
                
                result = await run_for_account(account, browser, adapter, context, **kwargs)
                return result
            except Exception as e:
                logger.error(f"Error in worker for account {account.account_name}: {e}")
                raise
            finally:
                if context:
                    await context.close()

    for account in accounts:
        task = asyncio.create_task(worker(account))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
