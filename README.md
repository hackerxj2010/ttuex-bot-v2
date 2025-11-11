# TTUEX Copy Trading Bot

This project is a sophisticated automation tool designed to perform copy trading on the TTUEX platform. It offers multiple interfaces for operation, including a command-line interface (CLI) and a Telegram bot, allowing for flexible and automated trading workflows.

## ✨ Features

*   **Multi-Account Support:** Process trades for multiple TTUEX accounts concurrently.
*   **Multiple Interfaces:**
    *   **CLI:** A powerful command-line interface for manual control and scripting.
    *   **Telegram Bot:** Control the bot and receive real-time notifications on your phone.
*   **Resilient & Performant:**
    *   Built-in retry logic for failed actions.
    *   Performance optimizations to minimize resource usage (CPU, RAM, network).
    *   Session caching to avoid frequent logins.
*   **Configurable:** Highly configurable through environment variables and JSON files.
*   **Extensible:** The modular architecture makes it easy to add new features and interfaces.

## 🏗️ Architecture

The bot is built with Python and leverages several key libraries:

*   **[Playwright](https://playwright.dev/python/)**: For robust browser automation to interact with the TTUEX website.
*   **[Click](https://click.palletsprojects.com/)**: To create a user-friendly and powerful command-line interface.
*   **[Telethon](https://docs.telethon.dev/)**: To integrate with the Telegram API for bot functionality.
*   **[FastAPI](https://fastapi.tiangolo.com/)**: For the optional web server component (e.g., for webhooks).
*   **Pydantic**: For robust configuration and data validation.

The project is structured into several key components:

*   **`actions.py`**: Contains the core logic for performing actions like logging in and copy trading.
*   **`orchestrator.py`**: Manages the concurrent execution of actions across multiple accounts.
*   **`playwright_adapter.py`**: A wrapper around Playwright for browser interactions.
*   **`cli.py`**: Defines the CLI commands and their options.
*   **`telegram_bot.py`**: Contains the logic for the Telegram bot.
*   **`config.py`**: Manages all application settings.

## 🚀 Getting Started

### Prerequisites

*   Python 3.10+
*   [Poetry](https://python-poetry.org/) (recommended for dependency management)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd ttuex-bot
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    or with Poetry:
    ```bash
    poetry install
    ```

3.  **Install Playwright browsers:**
    ```bash
    playwright install
    ```

### Configuration

1.  **`.env` file:**
    Create a `.env` file in the root of the project. This file is used for general configuration. You can copy the example below:

    ```env
    # .env

    # -- General Settings --
    LOG_LEVEL="INFO"
    LOG_FORMAT="console" # "json" or "console"

    # -- TTUEX Settings --
    TTUEX_LOGIN_URL="https://vip8-ttuex.com/login-page"
    TTUEX_BASE_URL="https://vip8-ttuex.com"

    # -- Automation Settings --
    DEFAULT_TIMEOUT=90000 # 90 seconds
    MAX_CONCURRENT_ACCOUNTS=1
    LOW_RESOURCE_MODE=true

    # -- Telegram Settings (if using the bot) --
    TELEGRAM_API_ID="your_api_id"
    TELEGRAM_API_HASH="your_api_hash"
    TELEGRAM_BOT_TOKEN="your_bot_token"
    ```

2.  **`accounts.json` file:**
    Create an `accounts.json` file in the root of the project to store the credentials for the TTUEX accounts you want to use.

    ```json
    {
      "accounts": [
        {
          "account_name": "main_account",
          "username": "user1@example.com",
          "password": "password123"
        },
        {
          "account_name": "secondary_account",
          "username": "user2@example.com",
          "password": "password456"
        }
      ]
    }
    ```

3.  **`authorized_users.json` (for Telegram bot):**
    If you are using the Telegram bot, create an `authorized_users.json` file to specify which Telegram user IDs are allowed to use the bot.

    ```json
    {
      "user_ids": [123456789, 987654321]
    }
    ```

## Usage

### Command-Line Interface (CLI)

The CLI is the primary way to interact with the bot.

*   **Login to all accounts:**
    This command will log in to all accounts specified in `accounts.json` and save the session cookies to speed up future operations.

    ```bash
    python -m ttuex_bot login
    ```

*   **Execute a copy trade:**
    This command will execute a copy trade for a given order number on all configured accounts.

    ```bash
    python -m ttuex_bot copy-trade <ORDER_NUMBER>
    ```

    **Important:** Add the `-y` or `--yes` flag to confirm that you want to execute live trades.

    ```bash
    python -m ttuex_bot copy-trade <ORDER_NUMBER> --yes
    ```

    **Options:**
    *   `--dry-run`: Simulate the trade without actually executing it.
    *   `--mode visible`: Run the browser in visible mode for debugging.
    *   `--accounts-file <path>`: Use a different accounts file.

### Telegram Bot

The Telegram bot allows you to control the copy trading process from anywhere.

1.  **Start the bot:**
    ```bash
    python -m ttuex_bot run-telegram
    ```

2.  **Interact with the bot on Telegram:**
    *   `/start` or `/help`: Get a welcome message with instructions.
    *   `/copy <ORDER_NUMBER>`: Execute a copy trade for the given order number.

## ⚙️ Configuration Details

The bot's behavior can be fine-tuned through the `.env` file:

*   `DEFAULT_TIMEOUT`: The default timeout for browser operations in milliseconds.
*   `MAX_CONCURRENT_ACCOUNTS`: The number of accounts to process in parallel.
*   `LOW_RESOURCE_MODE`: Enables optimizations for low-resource environments.
*   `STORAGE_STATE_ENABLED`: Set to `true` to cache browser sessions and avoid re-logins.
*   `FOLLOW_ORDER_CLICK_ATTEMPTS`: Number of times to click the "Suivi des commandes" button before checking success.

For a full list of configuration options, see the `AppConfig` class in `src/ttuex_bot/config.py`.

## Project Structure

```
├── src/ttuex_bot/
│   ├── __main__.py       # Main entry point for the package
│   ├── actions.py        # Core logic for bot actions
│   ├── cli.py            # CLI command definitions
│   ├── config.py         # Application configuration
│   ├── orchestrator.py   # Manages concurrent account processing
│   ├── playwright_adapter.py # Playwright wrapper
│   ├── telegram_bot.py   # Telegram bot logic
│   └── ...
├── .env                  # Environment variables
├── accounts.json         # Account credentials
├── requirements.txt      # Python dependencies
└── ...
```