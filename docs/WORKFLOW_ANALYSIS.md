# TTUEX Copy Trading - Video Workflow Analysis

This document breaks down the manual copy trading workflow as observed in the `TTUEX交易视频.mp4` video and maps each step to a corresponding Python function for automation.

## Workflow Summary

The user performs the following sequence of actions:
1.  Navigates from the homepage to the "Contract" trading section.
2.  (Optional) Selects a specific time frame for the chart.
3.  Navigates to the "Copy Trading" sub-section.
4.  Enters a specific order number.
5.  Executes the copy trade by clicking "Follow-up".
6.  Visually confirms the trade was successful by checking the trade history.

---

## Step-by-Step Mapping to Code

### **Step 1: Navigate to Contract Section**

*   **Video Action (00:02):** User clicks the "Contract" icon in the main navigation bar at the bottom of the screen.
*   **Input:** None.
*   **Action:** Click UI element.
*   **Output:** The application transitions to the contract trading interface.
*   **Python Function Mapping:**
    ```python
    async def navigate_to_contract(page: Page):
        """Navigates to the main 'Contract' trading page."""
        # Selector for the 'Contract' tab
        contract_selector = "a[href='/contract']" # Example selector
        await page.click(contract_selector)
        # Wait for a unique element on the contract page to ensure it has loaded
        await page.wait_for_selector(".chart-container") # Example selector
    ```

### **Step 2: Navigate to Copy Trading Interface**

*   **Video Action (00:14):** After scrolling down, the user clicks the "Copy Trading" tab from a secondary menu.
*   **Input:** None.
*   **Action:** Click UI element.
*   **Output:** The UI reveals the input field for the order number.
*   **Python Function Mapping:**
    ```python
    async def navigate_to_copy_trading(page: Page):
        """Navigates to the 'Copy Trading' input section."""
        # Selector for the 'Copy Trading' tab
        copy_trade_selector = "div.tab:has-text('Copy Trading')" # Example selector
        await page.click(copy_trade_selector)
        # Wait for the input field to be visible
        await page.wait_for_selector("input[placeholder='Please enter order num']")
    ```

### **Step 3: Enter Order Number**

*   **Video Action (00:18):** User types the order number `DK20250701NO01` into the input field.
*   **Input:** `order_number` (string).
*   **Action:** Type text into a form field.
*   **Output:** The input field contains the provided order number.
*   **Python Function Mapping:**
    ```python
    async def enter_order_number(page: Page, order_number: str):
        """Fills the order number into the copy trading input field."""
        order_input_selector = "input[placeholder='Please enter order num']"
        await page.fill(order_input_selector, order_number)
    ```

### **Step 4: Execute Copy Trade**

*   **Video Action (00:21):** User clicks the "Follow-up" button.
*   **Input:** None.
*   **Action:** Click a button to submit the form/action.
*   **Output:** A temporary success message ("Successfully Followed") appears.
*   **Python Function Mapping:**
    ```python
    async def execute_follow_up(page: Page):
        """Clicks the 'Follow-up' button and waits for the success toast."""
        follow_up_button_selector = "button:has-text('Follow-up')"
        await page.click(follow_up_button_selector)
        # Wait for the success message to appear
        await page.wait_for_selector("text=Successfully Followed")
    ```

### **Step 5: Verify Trade in History**

*   **Video Action (00:25):** User scrolls down to the "Following History" list and visually confirms the new trade appears.
*   **Input:** `order_number` (string, to verify against).
*   **Action:** Locate and read text from a list of elements.
*   **Output:** A dictionary containing the details of the newly found trade, or `None` if not found.
*   **Python Function Mapping:**
    ```python
    async def verify_order_in_history(page: Page, order_number: str) -> dict | None:
        """
        Waits for the history to update and verifies the new trade is present.
        Returns the trade data if found, otherwise None.
        """
        # The video shows the order ID is truncated in the history view
        partial_order_id = order_number.split('NO')[0] # e.g., "DK20250701"

        # A robust selector for the history row containing the partial ID
        history_row_selector = f"div.history-item:has-text('{partial_order_id}')" # Example

        try:
            # Wait for the new row to appear in the DOM
            new_row = await page.wait_for_selector(history_row_selector, timeout=15000)

            # Extract data from the row
            trade_data = {
                "id": await new_row.locator(".trade-id").inner_text(),
                "product": await new_row.locator(".product").inner_text(),
                "direction": await new_row.locator(".direction").inner_text(),
                "quantity": await new_row.locator(".quantity").inner_text(),
                "timestamp": await new_row.locator(".timestamp").inner_text(),
            }
            return trade_data
        except TimeoutError:
            return None
    ```

---

## Performance Optimizations

To improve the bot's execution speed, especially when handling multiple accounts, several optimizations have been implemented:

### **1. Reusing the Browser Instance**

-   **Problem:** The original implementation launched a new, separate browser instance for every single account being processed. The overhead of starting a browser (launching the process, creating a profile, etc.) is significant and was a major performance bottleneck.
-   **Solution:** The code has been refactored to launch the browser only **once**. For each account, a new `BrowserContext` is created. This is a lightweight, isolated session within the main browser instance. It maintains its own cookies and local storage, ensuring accounts do not interfere with each other, but avoids the costly process of launching a new browser.

### **2. Resource Blocking (`--performant` mode)**

-   **Problem:** Web pages often load many non-essential resources like images, fonts, and tracking scripts, which can slow down page navigation.
-   **Solution:** A `--performant` flag has been added to the `copy_trade` command. When enabled, it instructs Playwright to intercept network requests and **abort** any requests for resources like images, fonts, and media files. This can significantly speed up page load times, allowing the bot to navigate and interact with elements more quickly.

### **3. Optional History Verification (`--skip-history-verification`)**

-   **Problem:** The step to verify if a trade appears in the history involves waiting for the UI to update, which can take several seconds. While crucial for confirming a trade, this might not always be necessary for every run.
-   **Solution:** A `--skip-history-verification` flag has been added to the `copy_trade` command. This allows the user to bypass this final verification step, saving time when they are confident that the trades are being executed successfully.

These changes make the bot significantly faster and more efficient, especially in multi-account scenarios.
