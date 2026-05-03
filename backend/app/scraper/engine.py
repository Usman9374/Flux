import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from playwright.async_api import BrowserContext, async_playwright

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)

T = TypeVar("T")


@asynccontextmanager
async def browser_context(headless: bool = True) -> AsyncIterator[BrowserContext]:
    """Yield a configured Playwright browser context. Always cleans up."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = await browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        try:
            yield context
        finally:
            try:
                await context.close()
            finally:
                await browser.close()


async def polite_sleep(min_s: float = 0.5, max_s: float = 1.5) -> None:
    """Jittered sleep — keeps scraping pace human-like."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def with_retries(
    factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    label: str = "task",
) -> T:
    """Run an async factory with exponential backoff. Re-raises the last exception."""
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return await factory()
        except Exception as e:  # noqa: BLE001 — catch broad, retry, log
            last = e
            wait = base_delay * (2**i) + random.random()
            log.warning("%s failed (attempt %d/%d): %s — retrying in %.1fs", label, i + 1, attempts, e, wait)
            await asyncio.sleep(wait)
    assert last is not None
    raise last
