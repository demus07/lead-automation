"""Open a page in a real (headless) browser at phone size, so JavaScript sites can be read and the
mobile layout can be measured rather than guessed. Fails soft: no browser just means fewer checks."""
import time

from .fetch import USER_AGENT

MEASURE = """() => {
  const vw = window.innerWidth;
  const inFold = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.top < window.innerHeight && r.bottom > 0; };
  const actions = [...document.querySelectorAll('a, button')].filter(inFold).map(e => (e.innerText || '').trim().toLowerCase());
  return {
    overflow: document.documentElement.scrollWidth - vw,
    fold_actions: actions.filter(Boolean).slice(0, 40),
    small_text: [...document.querySelectorAll('p')].filter(p => (p.innerText || '').length > 40)
      .filter(p => parseFloat(getComputedStyle(p).fontSize) < 12).length,
  };
}"""


def render(url: str, timeout_ms: int = 25000) -> dict | None:
    """Returns {html, ms, overflow, fold_actions, small_text}, or None if it couldn't be rendered."""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, user_agent=USER_AGENT, is_mobile=True)
            page = ctx.new_page()
            start = time.monotonic()
            page.goto(url, wait_until="load", timeout=timeout_ms)
            ms = round((time.monotonic() - start) * 1000)
            page.wait_for_timeout(1200)  # let client-side content arrive
            out = {"html": page.content(), "final_url": page.url, "ms": ms, **page.evaluate(MEASURE)}
            browser.close()
            return out
    except Error:
        return None
