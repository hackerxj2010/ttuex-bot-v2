"""
Configuration management for the TTUEX Bot using Pydantic."""

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Main application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # -- General Settings --
    log_level: str = Field(
        default="INFO", description="Logging level (e.g., DEBUG, INFO, WARNING)"
    )
    log_format: str = Field(
        default="json", description="Log format: 'json' or 'console'"
    )

    # -- TTUEX Settings --
    ttuex_login_url: str = Field(default="https://ttuex.club/login-page?redirect=/pc-home")
    ttuex_base_url: str = Field(default="https://ttuex.club")

    # -- TTUEX Credentials (for single account mode, if used) --
    ttuex_username: Optional[str] = Field(
        default=None, description="Username (email) for the TTUEX account."
    )
    ttuex_password: Optional[SecretStr] = Field(
        default=None, description="Password for the TTUEX account."
    )

    # -- Automation Settings --
    default_timeout: int = Field(
        default=20000,
        description="Default timeout for Playwright operations in milliseconds",
    )
    follow_button_timeout: int = Field(
        default=35000,
        description="Timeout for clicking the follow order button in milliseconds",
    )
    max_concurrent_accounts: int = Field(
        default=1, description="Maximum number of accounts to process concurrently"
    )
    confirm_live_trades: bool = Field(
        default=True,
        description="Require explicit confirmation for live (non-dry-run) trades",
    )

    save_debug_html: bool = Field(
        default=True, description="Whether to save HTML content for debugging on failure."
    )

    # -- Follow Order Click Behavior --
    follow_order_click_attempts: int = Field(
        default=1,
        description=(
            "Number of times to attempt clicking the 'Suivi des commandes' (Follow Order) button "
            "before checking for success. Useful if the site requires multiple clicks."
        ),
    )

    # -- Execution Duration Control --
    enforce_min_run_per_execution: bool = Field(
        default=True,
        description="Ensure each CLI execution lasts at least 'min_run_seconds' before returning.",
    )
    enforce_min_run_per_account: bool = Field(
        default=False,
        description="Ensure each account workflow lasts at least 'min_run_seconds'. Usually keep False.",
    )
    min_run_seconds: int = Field(
        default=120,
        description=(
            "Minimum total duration in seconds for an execution or per-account workflow, depending on the flag."
        ),
    )

    # -- Low resource mode for Playwright/Chromium --
    low_resource_mode: bool = Field(
        default=True,
        description="Enable Chromium launch flags optimized for low RAM/CPU environments.",
    )
    chromium_launch_args: list[str] = Field(
        default_factory=lambda: [
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--no-default-browser-check",
            "--no-first-run",
            "--no-zygote",
            "--disable-extensions",
            "--mute-audio",
            "--blink-settings=imagesEnabled=false",
        ],
        description="Chromium flags used when low_resource_mode is enabled.",
    )

    # -- Storage State Settings --
    storage_state_enabled: bool = Field(
        default=True,
        description="Enable Playwright storage state to avoid re-login on each run.",
    )
    storage_state_dir: str = Field(
        default="storage_states",
        description="Directory where per-account storage state JSON files are stored.",
    )

    # -- Selectors --
    # Login Page
    selector_login_username_input: str = Field(
        default='input[placeholder="Veuillez saisir votre compte"]',
        description="Selector for the username input on the login page.",
    )
    selector_login_password_input: str = Field(
        default='input[placeholder="S\'il vous plaît entrer le mot de passe"]',
        description="Selector for the password input on the login page.",
    )
    selector_login_submit_button: str = Field(
        default='button[type="submit"]',
        description="Selector for the login submit button.",
    )

    # Main Navigation
    selector_nav_contract_link: str = Field(
        default='span:has-text("Copy trading")',
        description="Selector for the main navigation link to the 'Contract' or 'Trade' page.",
    )

    # Contract/Trade Page
    selector_contract_copy_trading_button: str = Field(
        default='span:has-text("Copy trading")',
        description="Selector for the 'Copy trading' button on the contract page.",
    )
    selector_contract_order_number_input: str = Field(
        default='#root > div > div > div.max-w-full.mx-auto.px-2.md\\:px-4.pb-16 > div > div > div.col-span-9.space-y-4 > div:nth-child(3) > div.border-t.border-bitfinex-border > div > div.overflow-x-hidden.mb-8.bg-bitfinex-background.px-4.py-3 > div > div:nth-child(1) > div > div.tradelistruning-8 > div > div > input',
        description="Selector for the order number input field in copy trading.",
    )


    selector_contract_follow_order_button: str = Field(
        default='button:has-text("Suivi des commandes")',
        description="Selector for the 'Follow Order' or 'Copy' button.",
    )

    selector_follow_up_status_message: str = Field(
        default='#root > div > div > div.max-w-full.mx-auto.px-2.md\\:px-4.pb-16 > div > div > div.col-span-9.space-y-4 > div:nth-child(3) > div.border-t.border-bitfinex-border > div > div.fixed.inset-0.bg-black\\/50.flex.items-center.justify-center.z-50 > div > p:has-text("suivi réussi"), #root > div > div > div.max-w-full.mx-auto.px-2.md\\:px-4.pb-16 > div > div > div.col-span-9.space-y-4 > div:nth-child(3) > div.border-t.border-bitfinex-border > div > div.fixed.inset-0.bg-black\\/50.flex.items-center.justify-center.z-50 > div > p:has-text("successful followed")',
        description="Selector for the success message that appears after following an order.",
    )


    # History Page
    selector_history_item: str = Field(
        default="//div[contains(@class, 'history-item') and contains(., '{partial_order_id}')]",
        description="Selector for a specific item in the trade history, formatted with 'partial_order_id'.",
    )
    selector_order_status_toast: str = Field(
        default='div[class*="toast"], div[class*="notification"], div[class*="alert"]',
        description="Selector for the toast message indicating order status (completed or not exist).",
    )
    
    # Order Alert Modal
    selector_order_alert_modal: str = Field(
        default='#root > div > div > div.max-w-full.mx-auto.px-2.md\\:px-4.pb-16 > div > div > div.col-span-9.space-y-4 > div:nth-child(3) > div.border-t.border-bitfinex-border > div > div.fixed.inset-0.bg-black\\/50.flex.items-center.justify-center.z-50 > div',
        description="Selector for the order alert modal container that appears after clicking follow order.",
    )
    
    selector_order_alert_button: str = Field(
        default='button:has-text("déterminer"), button:has-text("OK"), button:has-text("Confirmer")',
        description="Selector for the specific 'déterminer' button in the order alert modal.",
    )
    
    selector_order_alert_message: str = Field(
        default='div[class*="alert-content"], div[class*="modal-content"], div[class*="popup-content"], div[role="dialog"] p, div[role="dialog"] span',
        description="Selector for the order alert message content within the modal.",
    )

    # -- Webhook Server Settings --
    webhook_host: str = Field(default="127.0.0.1")
    webhook_port: int = Field(default=8000)

    # -- Twilio Settings (for WhatsApp Business API) --
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[SecretStr] = None
    twilio_phone_number: Optional[str] = None  # e.g., 'whatsapp:+14155238886'

    # -- Telegram Settings --
    telegram_api_id: Optional[int] = None
    telegram_api_hash: Optional[str] = None
    telegram_bot_token: Optional[SecretStr] = None


# Instantiate a single config object for the application to use
app_config = AppConfig()


# --- Multi-Account Configuration ---
class AccountCredentials(BaseModel):
    """Represents the credentials for a single TTUEX account."""

    account_name: str = Field(
        ...,
        description="A unique, friendly name for the account (e.g., 'main_account')",
    )
    username: str
    password: SecretStr  # Use SecretStr to keep password redacted in logs


class AccountsConfig(BaseModel):
    """Container for a list of all TTUEX accounts."""

    accounts: List[AccountCredentials]

def load_accounts_from_json(path: str = "accounts.json") -> AccountsConfig:
    """Loads TTUEX account credentials from a JSON file."""
    config_path = Path(path)
    if not config_path.exists():
        print(f"Warning: Accounts file not found at '{path}'. No accounts loaded.")
        return AccountsConfig(accounts=[])

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AccountsConfig(**data)
    except (json.JSONDecodeError, TypeError, KeyError, FileNotFoundError) as e:
        raise ValueError(f"Error parsing accounts file at '{config_path}': {e}")