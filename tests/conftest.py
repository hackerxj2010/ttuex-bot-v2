import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


from typing import Optional


class FakeLocator:
    def __init__(self, text_content=""):
        self._text_content = text_content

    async def wait_for(self, **kwargs): pass
    async def fill(self, value, **kwargs): pass
    async def click(self, **kwargs): pass
    async def scroll_into_view_if_needed(self, **kwargs): pass
    async def text_content(self): return self._text_content

    @property
    def first(self):
        return self

class FakePage:
    def __init__(self):
        self.url = "http://fake.com"

    async def goto(self, url, **kwargs): pass
    async def screenshot(self, path, **kwargs): pass
    async def locator(self, selector):
        if "div.adm-toast-main" in selector:
            return FakeLocator(text_content="not exist")
        return FakeLocator()
    async def wait_for_url(self, url, **kwargs): pass


class FakeContext:
    async def new_page(self): return FakePage()
    async def close(self): pass
    async def storage_state(self, path):
        pass


class FakeBrowser:
    async def new_context(self, **kwargs): return FakeContext()
    async def close(self): pass


class FakeAdapter:
    def __init__(self):
        self._pw = SimpleNamespace(devices={"iPhone 13": {}})
        self.browser = FakeBrowser()

    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def launch_browser(self, headless=True, performant=False): return self.browser
    async def new_context(self, browser, device: Optional[dict] = None, performant=False, storage_state_path=None):
        return await self.browser.new_context(**device) if device else await self.browser.new_context()
    def get_device(self, device_name: str) -> dict:
        return self._pw.devices.get(device_name, {})


@pytest.fixture(autouse=False)
def fake_playwright_adapter(monkeypatch):
    import ttuex_bot.cli as cli_mod
    import ttuex_bot.orchestrator as orchestrator_mod
    monkeypatch.setattr(cli_mod, "PlaywrightAdapter", FakeAdapter)
    monkeypatch.setattr(orchestrator_mod, "PlaywrightAdapter", FakeAdapter)
    yield FakeAdapter