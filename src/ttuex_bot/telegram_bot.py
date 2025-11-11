import asyncio
import os
import re
import sys
from pathlib import Path

from telethon import TelegramClient, events

from ttuex_bot.actions import get_accounts_to_process, run_copy_trade_for_account
from ttuex_bot.config import app_config
from ttuex_bot.orchestrator import orchestrate_accounts
from ttuex_bot.playwright_adapter import PlaywrightAdapter
from ttuex_bot.utils.logging import get_logger

logger = get_logger("TelethonBot")


async def run_trade_task(order_number: str, event: events.NewMessage.Event):
    """
    The actual long-running task that is executed in the background.
    Sends a message back to the user upon completion or failure.
    """
    logger.info(f"Telethon background task started for order: {order_number}")

    accounts_to_process = get_accounts_to_process()
    if not accounts_to_process:
        logger.warning("No accounts found for background task.")
        await event.respond("⚠️ **Aucun compte n'a été trouvé.**\n\nIl semble que la liste des comptes à traiter est vide. Veuillez vérifier la configuration ou contacter le support.")
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
                telethon_client=event.client,
                chat_id=event.chat_id,
                order_number=order_number,
                dry_run=False,
                headless=True,
                performant=True,
                skip_history_verification=True,
            )
            await browser.close()

        success_count = 0
        failure_count = 0
        account_summaries = []

        for report in results:
            if isinstance(report, dict):
                account_name = report.get("account_name", "Compte inconnu")
                if report.get("success"):
                    success_count += 1
                    toast_message = report.get("toast_message")
                    if toast_message:
                        account_summaries.append(f"✅ **{account_name}:** Ordre copié. Le site a retourné le message : '_{toast_message}_'")
                    else:
                        account_summaries.append(f"✅ **{account_name}:** Ordre copié avec succès.")
                else:
                    failure_count += 1
                    error_msg = report.get("error", "Erreur inconnue")
                    translated_error = translate_error(error_msg)
                    account_summaries.append(f"❌ **{account_name}:** Échec de la copie.\n   - _Raison : {translated_error}_")
            else:  # An unexpected exception was returned by gather
                failure_count += 1
                # Attempt to get account name from the exception string if possible
                account_name_match = re.search(r"account_name='([^']*)'", str(report))
                account_name = account_name_match.group(1) if account_name_match else "Compte inconnu"
                account_summaries.append(f"🚨 **{account_name}:** Une erreur système critique est survenue lors du traitement de ce compte.")

        summary_header = f"📋 **Rapport final pour l'ordre `{order_number}`**\n\n"
        summary_counts = f"**Résultat :** {success_count} copié(s) avec succès, {failure_count} en échec.\n\n---\n"
        final_summary = summary_header + summary_counts + "\n".join(account_summaries)

        logger.info(f"Background task finished for order: {order_number}", results=results)
        await event.respond(final_summary)

    except Exception as e:
        logger.error(f"Error during Telethon background task for order {order_number}: {e}", exc_info=True)
        await event.respond(f"🆘 **Une erreur critique est survenue lors de l'exécution de l'ordre `{order_number}`.**\n\nLe processus a dû être interrompu. Veuillez contacter le support technique.")


from ttuex_bot.utils.translators import translate_error




def run_bot():
    """Starts the Telegram bot using Telethon, ensuring only one instance runs at a time."""
    LOCK_FILE = Path("bot.lock")
    if LOCK_FILE.exists():
        logger.error("Another instance of the bot is already running. Exiting.")
        sys.exit(1)

    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))

        if not all([app_config.telegram_api_id, app_config.telegram_api_hash, app_config.telegram_bot_token]):
            raise ValueError("Telegram API ID, Hash, and Bot Token must be configured in .env file.")

        bot = TelegramClient(
            'bot',
            app_config.telegram_api_id,
            app_config.telegram_api_hash
        ).start(bot_token=app_config.telegram_bot_token.get_secret_value())

        @bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            sender = await event.get_sender()
            gif_url = "https://media.tenor.com/2hA5tZ9eAOMAAAAC/crypto-arbitrage-bot-trading-bot.gif"
            
            caption = f"""
**✨ Bienvenue, {sender.first_name} ! ✨**

Je suis votre **assistant de trading TTUEX personnel**, prêt à transformer votre expérience de copy trading. Considérez-moi comme votre co-pilote, exécutant vos ordres avec précision et rapidité.

---

### **🚀 Mes Super-pouvoirs :**
- **Exécution Ultra-Rapide :** Je place vos ordres en un clin d'œil.
- **Notifications en Temps Réel :** Restez informé à chaque étape du processus.
- **Fiabilité à Toute Épreuve :** Je suis conçu pour être robuste et sécurisé.

---

### **🛠️ Commandes Disponibles :**
- `/copy <numéro_ordre>` : Pour lancer la magie du copy trading.
- `/status` : _(Bientôt disponible)_ Pour suivre l'avancement de vos ordres.
- `/help` : Pour afficher ce message et redécouvrir mes capacités.

---

**Prêt à commencer ?**
Utilisez la commande `/copy` suivie de votre numéro d'ordre. Par exemple :
` /copy 12345 `

Pour toute question, n'hésitez pas à contacter le support.
"""
            
            await event.respond(file=gif_url, message=caption)

        @bot.on(events.NewMessage(pattern=re.compile(r'/copy(?:\s+)(\S+)')))
        async def copy_handler(event):
            try:
                order_number = event.pattern_match.group(1)
                logger.info(f"Received /copy command for order: {order_number} from user: {event.sender_id}")
                # Respond immediately without waiting
                await event.respond(f"✅ Commande reçue ! L'ordre {order_number} va être traité.")
                # Run the long task in the background immediately
                asyncio.create_task(run_trade_task(order_number, event))
            except (IndexError, ValueError):
                await event.respond("❌ Commande invalide. Utilisation : /copy <numéro_ordre>")

        logger.info("Telethon bot is starting...")
        bot.run_until_disconnected()

    finally:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
        logger.info("Telethon bot stopped and lock file removed.")


if __name__ == "__main__":
    run_bot()
