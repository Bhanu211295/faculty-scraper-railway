"""
fetcher_advanced.py
-------------------
Enhanced fetcher that handles:
  - Dynamic content (scrolling)
  - Pagination (auto-detect and scrape all pages)
  - Individual profile pages (click to visit each one)
  - Better link discovery

Uses Playwright to render JavaScript, scroll, and click.
"""

import time
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

USER_AGENT = "FacultyDataResearchBot/2.0 (+contact: you@yourdomain.edu)"


class AdvancedFetcher:
    def __init__(self, headless=True, delay_seconds=1.5):
        self.delay_seconds = delay_seconds
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless)
        self.context = self.browser.new_context(user_agent=USER_AGENT)

    def close(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()

    def fetch_with_scrolling(self, url: str, scroll_pause_time: float = 2.0, max_scrolls: int = 10) -> dict:
        """
        Fetch a page with SCROLLING to load dynamic content.
        Useful for sites that load faculty on scroll (like SASTRA).
        """
        page = self.context.new_page()
        try:
            print(f"  [*] Navigating to {url}")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            
            print(f"  [*] Scrolling to load dynamic content (max {max_scrolls} scrolls)...")
            last_height = page.evaluate("document.body.scrollHeight")
            scroll_count = 0
            
            while scroll_count < max_scrolls:
                # Scroll to bottom
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(scroll_pause_time)
                
                # Check if new content loaded
                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    print(f"  [*] No more content after {scroll_count + 1} scrolls, stopping")
                    break
                last_height = new_height
                scroll_count += 1
                print(f"      Scroll {scroll_count}: Page height = {last_height}px")
            
            html = page.content()
        finally:
            page.close()
        
        time.sleep(self.delay_seconds)
        return self._clean(html, url)

    def discover_pagination(self, url: str) -> list[str]:
        """
        Detect pagination links on a page and return all page URLs.
        Returns list like [url, url?page=2, url?page=3, ...]
        """
        page = self.context.new_page()
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            html = page.content()
        finally:
            page.close()
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for pagination links (Page 1, 2, 3 or Next buttons)
        page_urls = [url]  # Start with the first page
        
        # Common pagination patterns
        pagination_selectors = [
            "a[href*='page']",
            "a[rel='next']",
            "li.pagination a",
            "nav.pagination a",
            "div.pager a",
        ]
        
        seen_urls = {url}
        for selector in pagination_selectors:
            for link in soup.select(selector):
                href = link.get("href")
                if href:
                    full_url = urljoin(url, href)
                    if full_url not in seen_urls and full_url.startswith("http"):
                        page_urls.append(full_url)
                        seen_urls.add(full_url)
        
        time.sleep(self.delay_seconds)
        return page_urls

    def discover_and_click_profiles(self, url: str, max_profiles: int = 200) -> list[dict]:
        """
        For listing pages that have individual profile cards:
        Click each one and collect the destination URLs.
        """
        page = self.context.new_page()
        results = []
        
        try:
            print(f"  [*] Navigating to {url}")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            
            # First, scroll to load all dynamic content
            print(f"  [*] Scrolling to load all profiles...")
            last_height = page.evaluate("document.body.scrollHeight")
            for scroll_attempt in range(15):  # Max 15 scrolls
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            # Find clickable profile elements
            selectors = [
                "[onclick*='profile']",
                "[onclick*='staff']",
                "[onclick*='faculty']",
                "a.faculty-profile",
                "a.staff-profile",
                ".faculty-card a",
                ".staff-card a",
                ".profile-link",
            ]
            
            clickable_elements = []
            for selector in selectors:
                clickable_elements.extend(page.query_selector_all(selector))
                if len(clickable_elements) >= max_profiles:
                    break
            
            clickable_elements = clickable_elements[:max_profiles]
            print(f"  [*] Found {len(clickable_elements)} clickable profile elements")
            
            for i, element in enumerate(clickable_elements, 1):
                try:
                    text = (element.inner_text() or "").strip()[:100]
                    
                    # Try to click
                    element.scroll_into_view_if_needed(timeout=2000)
                    
                    # Wait for navigation
                    try:
                        with page.expect_navigation(timeout=5000):
                            element.click(timeout=2000)
                        new_url = page.url
                        if new_url and new_url != url:
                            results.append({"text": text, "href": new_url})
                            print(f"    [{i}] Clicked -> {new_url}")
                    except:
                        # Click didn't navigate (maybe modal or no-op)
                        pass
                    
                    # Go back to listing page
                    try:
                        page.goto(url, timeout=10000, wait_until="domcontentloaded")
                        page.wait_for_timeout(500)
                    except:
                        pass
                
                except Exception as e:
                    print(f"    [{i}] Error: {e}")
                    pass
        
        finally:
            page.close()
        
        # De-dupe by URL
        seen, deduped = set(), []
        for r in results:
            if r["href"] not in seen:
                deduped.append(r)
                seen.add(r["href"])
        
        time.sleep(self.delay_seconds)
        return deduped

    def fetch(self, url: str, wait_ms: int = 1500) -> dict:
        """Standard fetch with minimal wait."""
        page = self.context.new_page()
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)
            html = page.content()
        finally:
            page.close()
        
        time.sleep(self.delay_seconds)
        return self._clean(html, url)

    @staticmethod
    def _clean(html: str, base_url: str) -> dict:
        """Clean HTML and extract text + links."""
        soup = BeautifulSoup(html, "html.parser")
        
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        
        links = []
        seen_hrefs = set()
        
        # Extract all links
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            text = a.get_text(strip=True)
            if href.startswith("http") and href not in seen_hrefs:
                links.append({"text": text, "href": href})
                seen_hrefs.add(href)
        
        # Extract text
        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.split("\n") if l.strip()]
        text = "\n".join(lines)
        
        return {"url": base_url, "text": text, "links": links}
