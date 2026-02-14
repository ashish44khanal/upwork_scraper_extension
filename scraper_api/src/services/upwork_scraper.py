import asyncio
import logging
import random
import re
import math
import json
import base64
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import nodriver as uc
from nodriver import cdp

from src.core.browser import BrowserManager
from src.services.session_manager import UpworkSessionManager

logger = logging.getLogger(__name__)

class ScraperException(Exception):
    """Base exception for scraper errors."""
    pass

class UpworkScraper:
    """
    Refactored Upwork Scraper following SOLID principles.
    Focuses purely on navigation and data extraction from Upwork search results.
    """
    
    TILE_SELECTOR = 'article.job-tile[data-test="JobTile"]'
    MODAL_SELECTOR = '.air3-slider-content'
    
    def __init__(self, browser_manager: BrowserManager, session_manager: UpworkSessionManager):
        self.browser_manager = browser_manager
        self.session_manager = session_manager
        self.session_id = str(random.randint(1000, 9999))

    async def scrape_jobs(
        self, 
        product_url: str, 
        no_of_pages_to_scrape: Optional[int] = None, 
        on_card_data_async: Optional[Callable] = None
    ):
        """Main entry point for scraping jobs from a search URL."""
        tab = await self.browser_manager.create_tab()
        try:
            # 1. Ensure Auth
            if not await self.session_manager.verify_or_login(tab):
                raise ScraperException("Authentication failed.")

            # 2. Initial Navigation
            await tab.get(product_url)
            await self.session_manager.wait_for_cloudflare(tab)
            
            # 3. Determine extent of scraping
            total_pages = await self._determine_total_pages(tab)
            pages_to_process = min(no_of_pages_to_scrape or total_pages, total_pages)
            
            logger.info(f"[Session: {self.session_id}] Scraping {pages_to_process} pages from {product_url}")

            for page_num in range(1, pages_to_process + 1):
                if page_num > 1:
                    next_url = self._build_next_page_url(product_url, page_num)
                    await tab.get(next_url)
                    await self.session_manager.wait_for_cloudflare(tab)

                await self._scrape_page(tab, page_num, on_card_data_async)

        finally:
            await tab.close()

    async def _scrape_page(self, tab: uc.Tab, page_num: int, callback: Optional[Callable]):
        """Processes all job tiles on a single search result page."""
        tiles = await self._wait_for_tiles(tab)
        for i, tile in enumerate(tiles):
            card_index = i + 1
            logger.info(f"Processing Page {page_num}, Tile {card_index}")
            
            try:
                job_html = await self._scrape_tile(tab, tile)
                if job_html and callback:
                    filtered_html = self._clean_html(job_html)
                    await callback(
                        card_index=card_index,
                        page_num=page_num,
                        raw_html=job_html,
                        filtered_html=filtered_html,
                        url=tab.url
                    )
            except Exception as e:
                logger.error(f"Error scraping tile {card_index} on page {page_num}: {e}")

    async def _scrape_tile(self, tab: uc.Tab, tile: uc.Element) -> Optional[str]:
        """Clicks a single job tile and extracts the content from the modal."""
        await tile.scroll_into_view()
        await tile.click()
        
        # Wait for modal content
        slider_appeared = await self._wait_for_element(tab, self.MODAL_SELECTOR, timeout=5.0)
        if not slider_appeared:
            return None
            
        await asyncio.sleep(random.uniform(0.5, 1.0)) # Jitter
        
        # Extract content
        try:
            # We often need to look in frames or the main tab depending on where the slider landed
            context = await self._find_job_context(tab)
            modal_content = await context.evaluate("document.body.innerHTML")
            
            # Close modal
            await self._close_modal(tab, context)
            return modal_content
        except Exception as e:
            logger.debug(f"Extraction from modal failed: {e}")
            return None

    # --- Helper Utilities ---

    async def _determine_total_pages(self, tab: uc.Tab) -> int:
        """
        Elite fast total page calculator.
        Uses JS evaluation for zero-latency extraction if DOM is ready.
        """
        try:
            # 1. Fast JS Attempt: Direct selector innerText
            js_query = r"""
            (() => {
                const el = document.querySelector('li[data-test="pagination-mobile"]');
                if (el) return el.innerText;
                // Fallback scan for common pagination patterns in text
                const bodyText = document.body.innerText;
                const match = bodyText.match(/(\d+)\s+of\s+(\d+)\s+jobs/i);
                if (match) return match[0];
                return null;
            })()
            """
            result = await tab.evaluate(js_query)
            if result:
                match = re.search(r"(\d+)\s+of\s+(\d+)", str(result))
                if match:
                    total = int(match.group(2))
                    logger.debug(f"Fast-calc: Identified {total} total pages.")
                    return total

            # 2. Fast DOM Attempt: Select with minimal timeout
            element = await tab.select('li[data-test="pagination-mobile"]', timeout=0.8)
            if element:
                text = element.text_all
                match = re.search(r"(\d+)\s+of\s+(\d+)", text)
                if match:
                    return int(match.group(2))
        except Exception as e:
            logger.debug(f"Pagination calc snag: {e}")
            
        return 1

    async def _wait_for_tiles(self, tab: uc.Tab, timeout: float = 10.0) -> List[uc.Element]:
        """Polls for job tiles to appear."""
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            tiles = await tab.select_all(self.TILE_SELECTOR)
            if tiles: return tiles
            await asyncio.sleep(0.5)
        return []

    async def _wait_for_element(self, tab: uc.Tab, selector: str, timeout: float = 5.0) -> bool:
        """Polls for a generic element."""
        try:
            el = await tab.select(selector, timeout=timeout)
            return bool(el)
        except:
            return False

    async def _find_job_context(self, tab: uc.Tab):
        """Upwork modals sometimes appear in different contexts; this helper finds it."""
        for target in tab.browser.targets:
            try:
                if await target.select(self.MODAL_SELECTOR, timeout=0.5):
                    return target
            except: continue
        return tab

    async def _close_modal(self, tab: uc.Tab, context):
        """Closes the job details slider."""
        try:
            close_btn = await context.select('button.air3-slider-prev-btn', timeout=1)
            if close_btn: await close_btn.click()
            else: await tab.send_keys("\uE00C") # Escape key
        except:
            await tab.send_keys("\uE00C")

    def _build_next_page_url(self, base_url: str, page_num: int) -> str:
        """Query string builder for pagination."""
        parsed = urlparse(base_url)
        qs = parse_qs(parsed.query)
        qs["page"] = [str(page_num)]
        return urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

    def _clean_html(self, html: str) -> str:
        """Simplified HTML cleaner focusing on relevant content."""
        if not html: return ""
        # Find the main job description part to keep it lean
        match = re.search(r'(<section[^>]*class="[^"]*job-details[^"]*"[^>]*>.*?</section>)', html, re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else html
