import pytest
from click.testing import CliRunner
from unittest.mock import patch, AsyncMock, MagicMock
from types import SimpleNamespace
import asyncio

from ttuex_bot.cli import cli, run_login_for_account, run_copy_trade_for_account
from ttuex_bot.config import AccountsConfig, AccountCredentials, SecretStr
from ttuex_bot.orchestrator import orchestrate_accounts


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_app_config(monkeypatch):
    """Mocks the app_config with valid credentials and default concurrency."""
    mock_config = MagicMock()
    mock_config.ttuex_username = "test@example.com"
    mock_password = MagicMock()
    mock_password.get_secret_value.return_value = "password123"
    mock_config.ttuex_password = mock_password
    mock_config.max_concurrent_accounts = 3
    mock_config.webhook_host = "127.0.0.1"
    mock_config.webhook_port = 8000
    mock_config.log_level = "INFO"

    monkeypatch.setattr("ttuex_bot.cli.app_config", mock_config)

    return mock_config


@pytest.fixture
def mock_app_config_no_creds(monkeypatch):
    """Mocks the app_config with missing credentials."""
    mock_config = MagicMock()
    mock_config.ttuex_username = None
    mock_config.ttuex_password = None
    mock_config.max_concurrent_accounts = 3
    mock_config.webhook_host = "127.0.0.1"
    mock_config.webhook_port = 8000
    mock_config.log_level = "INFO"

    monkeypatch.setattr("ttuex_bot.cli.app_config", mock_config)

    return mock_config


@pytest.fixture
def mock_load_accounts(monkeypatch):
    """Mocks load_accounts_from_json to return a predefined list of 3 accounts."""
    accounts = AccountsConfig(
        accounts=[
            AccountCredentials(account_name="test_account_1", username="user1@example.com", password=SecretStr("pass1")),
            AccountCredentials(account_name="test_account_2", username="user2@example.com", password=SecretStr("pass2")),
            AccountCredentials(account_name="test_account_3", username="user3@example.com", password=SecretStr("pass3")),
        ]
    )
    monkeypatch.setattr("ttuex_bot.actions.load_accounts_from_json", lambda *args, **kwargs: accounts)
    return accounts


@pytest.fixture
def mock_load_accounts_empty(monkeypatch):
    """Mocks load_accounts_from_json to return an empty list."""
    monkeypatch.setattr("ttuex_bot.actions.load_accounts_from_json", lambda *args, **kwargs: AccountsConfig(accounts=[]))



@patch("ttuex_bot.cli.run_login_for_account", new_callable=AsyncMock)
def test_login_command_success(mock_run_login_for_account, runner, mock_app_config, mock_load_accounts, fake_playwright_adapter):
    """Test the 'login' command with successful authentication for multiple accounts."""
    mock_run_login_for_account.return_value = {"success": True, "account_name": "mocked_account"}

    result = runner.invoke(cli, ["login"])

    assert result.exit_code == 0
    assert "Attempting login for 3 accounts in invisible mode (performant=True) ..." in result.output
    assert "Login SUCCESS" in result.output
    assert "All login attempts finished." in result.output
    assert mock_run_login_for_account.call_count == 3


@patch("ttuex_bot.cli.run_login_for_account", new_callable=AsyncMock)
def test_login_command_failure(mock_run_login_for_account, runner, mock_app_config, mock_load_accounts, fake_playwright_adapter):
    """Test the 'login' command with a failed authentication for multiple accounts."""
    mock_run_login_for_account.side_effect = [
        {"success": True, "account_name": "test_account_1"},
        {"success": False, "account_name": "test_account_2", "error": "Invalid credentials"},
        {"success": False, "account_name": "test_account_3", "error": "Another error"},
    ]

    result = runner.invoke(cli, ["login"])

    assert result.exit_code == 0
    assert "Attempting login for 3 accounts in invisible mode (performant=True) ..." in result.output
    assert "test_account_1: Login SUCCESS" in result.output
    assert "test_account_2: Login FAILED - Invalid credentials" in result.output
    assert "test_account_3: Login FAILED - Another error" in result.output
    assert "All login attempts finished." in result.output
    assert mock_run_login_for_account.call_count == 3


def test_login_command_no_credentials(runner, mock_app_config_no_creds, mock_load_accounts_empty):
    """Test the 'login' command when no credentials are set in .env and accounts.json is empty."""
    result = runner.invoke(cli, ["login"])

    assert result.exit_code == 0
    assert "No accounts found. Please configure accounts.json or your .env file." in result.output


@patch("ttuex_bot.cli.run_copy_trade_for_account", new_callable=AsyncMock)
def test_copy_trade_command_success(mock_run_copy_trade_for_account, runner, mock_app_config, mock_load_accounts, fake_playwright_adapter):
    """Test the 'copy-trade' command with successful execution for multiple accounts."""
    mock_run_copy_trade_for_account.side_effect = [
        {"success": True, "account_name": "test_account_1", "order_number": "ORDER123"},
        {"success": True, "account_name": "test_account_2", "order_number": "ORDER123"},
        {"success": True, "account_name": "test_account_3", "order_number": "ORDER123"},
    ]

    result = runner.invoke(cli, ["copy-trade", "ORDER123", "--yes"])

    assert result.exit_code == 0
    assert "All workflows completed. 3/3 successful." in result.output
    assert mock_run_copy_trade_for_account.call_count == 3