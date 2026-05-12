import asyncio
import logging
import os
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

# Render's $HOME differs between build and runtime, so the default
# ~/.cache/ms-playwright/ cache becomes invisible to the running app. Pin
# the cache inside the project src/ tree (which Render preserves across
# build → runtime) so `playwright install` (build) and chromium launch
# (runtime) agree on a path. setdefault preserves any explicit override.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/render/project/src/.playwright")

from playwright.async_api import BrowserContext, Route, async_playwright  # noqa: E402

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)

# Resource types we never need for scraping data. Blocking these cuts
# Google Maps page weight by ~80% and shaves seconds off every nav.
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

# Tracker / analytics hosts that load on every Maps page and slow it down
# without contributing anything to the data we extract.
BLOCKED_HOSTS = (
    "doubleclick.net",
    "googlesyndication.com",
    "googletagmanager.com",
    "google-analytics.com",
    "googleadservices.com",
    "facebook.net",
    "facebook.com/tr",
)

T = TypeVar("T")


async def _block_heavy_assets(route: Route) -> None:
    req = route.request
    if req.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return
    url = req.url
    if any(h in url for h in BLOCKED_HOSTS):
        await route.abort()
        return
    await route.continue_()


@asynccontextmanager
async def browser_context(
    headless: bool = True,
    *,
    block_assets: bool = True,
) -> AsyncIterator[BrowserContext]:
    """Yield a configured Playwright browser context. Always cleans up.

    `block_assets=True` aborts requests for images/fonts/css/media and known
    tracker hosts. Cuts page weight enormously and is the single biggest
    speedup for a scrape pass — leave it on unless you specifically need
    rendered visuals.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-shm-usage",
                "--no-sandbox",
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
        if block_assets:
            await context.route("**/*", _block_heavy_assets)
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
