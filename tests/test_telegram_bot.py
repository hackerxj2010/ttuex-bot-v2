import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ttuex_bot.telegram_bot import run_trade_task


@pytest.mark.asyncio
async def test_run_trade_task_success():
    """Tests the run_trade_task function with a successful trade."""
    # Create a mock event
    event = AsyncMock()
    event.respond = AsyncMock()

    # Create a mock orchestrate_accounts function
    mock_orchestrate_accounts = AsyncMock(return_value=[
        {"account_name": "account1", "success": True, "toast_message": "Successfully followed"},
        {"account_name": "account2", "success": True, "toast_message": "Successfully followed"},
    ])

    # Patch the orchestrate_accounts function
    from ttuex_bot import telegram_bot
    telegram_bot.orchestrate_accounts = mock_orchestrate_accounts

    # Call the run_trade_task function
    await run_trade_task("12345", event)

    # Check the response
    event.respond.assert_any_call("🚀 **Lancement du copy trading pour l'ordre `12345`...**\n\nVeuillez patienter pendant que je traite les comptes.")
    
    # Get the last call to event.respond
    last_call = event.respond.call_args_list[-1]
    # The message is the first positional argument
    message = last_call.args[0]
    
    assert "Rapport d'exécution pour l'ordre `12345`" in message
    assert "Succès:** 2" in message
    assert "Échecs:** 0" in message
    assert "✅ **account1:** SUCCÈS" in message
    assert "- _Message: Successfully followed_" in message
    assert "✅ **account2:** SUCCÈS" in message


@pytest.mark.asyncio
async def test_run_trade_task_failure():
    """Tests the run_trade_task function with a failed trade."""
    # Create a mock event
    event = AsyncMock()
    event.respond = AsyncMock()

    # Create a mock orchestrate_accounts function
    mock_orchestrate_accounts = AsyncMock(return_value=[
        {"account_name": "account1", "success": False, "error": "Duplicate order"},
        {"account_name": "account2", "success": True, "toast_message": "Successfully followed"},
    ])

    # Patch the orchestrate_accounts function
    from ttuex_bot import telegram_bot
    telegram_bot.orchestrate_accounts = mock_orchestrate_accounts

    # Call the run_trade_task function
    await run_trade_task("12345", event)

    # Check the response
    event.respond.assert_any_call("🚀 **Lancement du copy trading pour l'ordre `12345`...**\n\nVeuillez patienter pendant que je traite les comptes.")
    
    # Get the last call to event.respond
    last_call = event.respond.call_args_list[-1]
    # The message is the first positional argument
    message = last_call.args[0]

    assert "Rapport d'exécution pour l'ordre `12345`" in message
    assert "Succès:** 1" in message
    assert "Échecs:** 1" in message
    assert "❌ **account1:** ÉCHEC" in message
    assert "- _Raison: Duplicate order_" in message
    assert "✅ **account2:** SUCCÈS" in message
    assert "- _Message: Successfully followed_" in message
