"""Visit each Streamlit app in a real browser so it never idles into sleep.

A plain HTTP ping doesn't count as traffic: Streamlit only sees a browser
session. If an app is already asleep, click its wake button. Exits non-zero
if any app fails to render, so GitHub emails a failure notice.
"""

import sys

from playwright.sync_api import sync_playwright

APPS = [
    "https://hows-my-portfolio.streamlit.app",
    "https://iul-vs-direct-investing.streamlit.app",
]
WAKE_BUTTON = "button:has-text('get this app back up')"
APP_ROOT = "[data-testid='stApp']"


def app_rendered(page) -> bool:
    """The Streamlit app runs inside an iframe on *.streamlit.app; check every frame."""
    return any(frame.query_selector(APP_ROOT) for frame in page.frames)


def visit(page, url: str) -> bool:
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(10_000)
    wake = page.query_selector(WAKE_BUTTON)
    if wake:
        print(f"{url}: asleep, waking it")
        wake.click()
        page.wait_for_timeout(5_000)
    for _ in range(18):  # up to ~3 minutes for a cold start
        if app_rendered(page):
            print(f"{url}: awake")
            return True
        page.wait_for_timeout(10_000)
    print(f"{url}: did not render")
    return False


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        results = []
        for url in APPS:
            page = browser.new_page()
            try:
                results.append(visit(page, url))
            except Exception as exc:  # noqa: BLE001 - report and carry on to the next app
                print(f"{url}: error {exc}")
                results.append(False)
            finally:
                page.close()
        browser.close()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
