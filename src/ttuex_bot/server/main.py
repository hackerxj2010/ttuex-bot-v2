"""FastAPI server for handling WhatsApp webhooks."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request, BackgroundTasks, Response
from twilio.twiml.messaging_response import MessagingResponse

from ttuex_bot.actions import get_accounts_to_process, run_copy_trade_for_account
from ttuex_bot.config import app_config
from ttuex_bot.orchestrator import orchestrate_accounts
from ttuex_bot.playwright_adapter import PlaywrightAdapter
from ttuex_bot.utils.logging import get_logger

logger = get_logger("WebhookServer")


async def run_trade_task(order_number: str, dry_run: bool = False):
    """
    The actual long-running task that is executed in the background.
    """
    logger.info(f"Background task started for order: {order_number}")
    accounts_to_process = get_accounts_to_process()
    if not accounts_to_process:
        logger.warning("No accounts found for background task.")
        return

    try:
        async with PlaywrightAdapter() as adapter:
            browser = await adapter.launch_browser(headless=True)
            results = await orchestrate_accounts(
                accounts=accounts_to_process,
                run_for_account=run_copy_trade_for_account,
                max_concurrency=app_config.max_concurrent_accounts,
                browser=browser,
                adapter=adapter,
                order_number=order_number,
                dry_run=dry_run,
                headless=True,
                performant=True,
                skip_history_verification=False,
            )
            await browser.close()
        logger.info(f"Background task finished for order: {order_number}", results=results)
        # Here you could add logic to send a completion message via Twilio
    except Exception as e:
        logger.error(f"Error during background task for order {order_number}: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the application's lifespan events (startup and shutdown)."""
    logger.info(
        "Starting FastAPI server",
        host=app_config.webhook_host,
        port=app_config.webhook_port,
    )
    yield


app = FastAPI(
    title="TTUEX Trading Bot Webhook Server",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/whatsapp")
async def handle_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    From: Optional[str] = Form(None),
    Body: Optional[str] = Form(None),
):
    """
    Handles incoming WhatsApp messages from a Twilio webhook.
    It expects a POST request with a 'From' and 'Body' field.
    """
    client_host = request.client.host
    logger.info(
        "Received incoming message", source_ip=client_host, sender=From, body=Body
    )
    response = MessagingResponse()

    if not From or not Body:
        logger.warning("Received a request with missing From or Body fields.")
        raise HTTPException(status_code=400, detail="Missing 'From' or 'Body' fields")

    # Simple command parsing: "copy <order_number>"
    parts = Body.strip().lower().split()
    if len(parts) == 2 and parts[0] == "copy":
        order_number = parts[1]
        # TODO: Add validation for order_number format

        logger.info(f"Valid command received. Starting background task for order {order_number}.")

        # Add the long-running task to the background
        background_tasks.add_task(run_trade_task, order_number=order_number, dry_run=False)

        # Immediately send a confirmation message back to the user
        response.message(f"✅ Commande reçue ! Démarrage du copy trading pour l'ordre : {order_number}. Vous recevrez une notification à la fin.")
    else:
        logger.warning(f"Invalid command format received: '{Body}'")
        response.message("❌ Commande non valide. Veuillez utiliser le format : copy <numéro_ordre>")

    return Response(content=str(response), media_type="application/xml")


@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


# To run this server:
# uvicorn ttuex_bot.server.main:app --reload
