import asyncio
import time

import click
import uvicorn

from ttuex_bot.actions import (
    get_accounts_to_process,
    run_copy_trade_for_account,
    run_login_for_account,
)
from ttuex_bot.config import app_config
from ttuex_bot.orchestrator import orchestrate_accounts
from ttuex_bot.playwright_adapter import PlaywrightAdapter
from ttuex_bot.server.main import app as fastapi_app
from ttuex_bot.telegram_bot import run_bot as run_telegram_bot


from ttuex_bot.utils.logging import get_logger

logger = get_logger("CLI")

def sanitize_for_console(text) -> str:
    """Sanitizes a string for safe console output."""
    return str(text).encode("cp1252", "replace").decode("cp1252")


@click.group()
def cli():
    """TTUEX Copy Trading Bot"""
    pass


@cli.command()
@click.option("--mode", type=click.Choice(["visible", "invisible"]), default="invisible")
@click.option("--accounts-file", default="accounts.json")
@click.option("--performant/--no-performant", default=True)
def login(mode: str, accounts_file: str, performant: bool):
    """Automate login for all configured accounts."""
    headless = mode == "invisible"
    accounts_to_process = get_accounts_to_process(accounts_file)
    if not accounts_to_process:
        click.echo(click.style("No accounts found. Please configure accounts.json or your .env file.", fg="red"))
        return

    click.echo(f"Attempting login for {len(accounts_to_process)} accounts in {mode} mode (performant={performant}) ...")

    start_wall = time.perf_counter()

    async def main():
        async with PlaywrightAdapter() as adapter:
            browser = await adapter.launch_browser(headless=headless)
            results = await orchestrate_accounts(
                accounts=accounts_to_process,
                run_for_account=run_login_for_account,
                max_concurrency=app_config.max_concurrent_accounts,
                browser=browser,
                adapter=adapter,
                dry_run=False,  # execute_login expects this
                performant=performant,
            )
            await browser.close()
            return results

    try:
        results = asyncio.run(main())
    except Exception as e:
        err = sanitize_for_console(str(e))
        click.echo(click.style(f"Fatal error during login execution: {err}", fg="red"))
        results = []
    
    for result in results:
        if isinstance(result, dict):
            account_name = result.get("account_name", "Unknown Account")
            if result.get("success"):
                click.echo(f"{account_name}: {click.style('Login SUCCESS', fg='green')}")
            else:
                error_msg = sanitize_for_console(result.get("error", "Unknown error"))
                click.echo(f"{account_name}: {click.style('Login FAILED', fg='red')} - {error_msg}")
        else:
            # An unexpected exception slipped through asyncio.gather(return_exceptions=True)
            err = sanitize_for_console(str(result))
            click.echo(f"{click.style('Login FAILED', fg='red')} - Unexpected error: {err}")

    # Enforce minimum total execution time for this CLI command
    if app_config.enforce_min_run_per_execution:
        elapsed = time.perf_counter() - start_wall
        remaining = float(app_config.min_run_seconds) - float(elapsed)
        if remaining > 0:
            time.sleep(remaining)

    click.echo("All login attempts finished.")


@cli.command()
@click.argument("order_number")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("-y", "--yes", is_flag=True)
@click.option("--mode", type=click.Choice(["visible", "invisible"]), default="invisible")
@click.option("--accounts-file", default="accounts.json")
@click.option("--performant/--no-performant", default=True)
@click.option("--skip-history-verification", is_flag=True, default=False)
@click.option("--max-retries", type=int, default=1)
def copy_trade(
    order_number: str,
    dry_run: bool,
    yes: bool,
    mode: str,
    accounts_file: str,
    performant: bool,
    skip_history_verification: bool,
    max_retries: int,
):
    """Executes the copy trading workflow for all configured accounts with retry logic."""
    if not dry_run and not yes:
        click.confirm(
            "WARNING: You are about to execute LIVE trades. Do you want to proceed?",
            abort=True,
        )

    headless = mode == "invisible"
    initial_accounts = get_accounts_to_process(accounts_file)
    if not initial_accounts:
        click.echo(
            click.style(
                "No accounts found. Please configure accounts.json or your .env file.",
                fg="red",
            )
        )
        return

    start_wall = time.perf_counter()

    async def main():
        async with PlaywrightAdapter() as adapter:
            browser = await adapter.launch_browser(headless=headless)
            try:
                results = await orchestrate_accounts(
                    accounts=initial_accounts,
                    run_for_account=run_copy_trade_for_account,
                    max_concurrency=app_config.max_concurrent_accounts,
                    browser=browser,
                    adapter=adapter,
                    order_number=order_number,
                    dry_run=dry_run,
                    headless=headless,
                    performant=performant,
                    skip_history_verification=skip_history_verification,
                )
                logger.info(f"Results from orchestrate_accounts: {results}")
                return results
            finally:
                await browser.close()

    try:
        final_reports = asyncio.run(main())
    except Exception as e:
        err = sanitize_for_console(str(e))
        click.echo(click.style(f"Fatal error during copy-trade execution: {err}", fg="red"))
        final_reports = []

    click.echo("\n--- Final Execution Summary ---")
    success_count = sum(1 for r in final_reports if isinstance(r, dict) and r.get("success"))
    for report in final_reports:
        if isinstance(report, dict):
            account_name = report.get("account_name", "Unknown Account")
            if report.get("success"):
                click.echo(f"{account_name}: {click.style('SUCCESS', fg='green')}")
            else:
                error_msg = sanitize_for_console(report.get("error", "Unknown error"))
                click.echo(
                    f"{account_name}: {click.style('FAILED', fg='red')} - {error_msg}"
                )
        else:
            err = sanitize_for_console(str(report))
            click.echo(f"{click.style('FAILED', fg='red')} - Unexpected error: {err}")

    # Enforce minimum total execution time for this CLI command
    if app_config.enforce_min_run_per_execution:
        elapsed = time.perf_counter() - start_wall
        remaining = float(app_config.min_run_seconds) - float(elapsed)
        if remaining > 0:
            time.sleep(remaining)

    click.echo(
        f"\n=========================\nAll workflows completed. {success_count}/{len(initial_accounts)} successful.\n========================="
    )



@cli.command()
def serve():
    """Starts the FastAPI webhook server."""
    uvicorn.run(
        fastapi_app,
        host=app_config.webhook_host,
        port=app_config.webhook_port,
        log_level=app_config.log_level.lower(),
    )


@cli.command()
def run_telegram():
    """Starts the Telegram bot."""
    run_telegram_bot()



if __name__ == "__main__":
    cli()
