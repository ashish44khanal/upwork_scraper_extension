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
from src.core.config import settings

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
    
    def __init__(self, browser_manager: BrowserManager):
        self.browser_manager = browser_manager
        # Use the session_id from browser_manager for consistency in logs/isolation
        self.session_id = browser_manager.session_id
        self._last_pagination_data = None
        self._pagination_event = asyncio.Event()

    async def scrape_jobs(
        self, 
        product_url: str, 
        no_of_pages_to_scrape: Optional[int] = None, 
        on_card_data_async: Optional[Callable] = None
    ):
        """Main entry point for scraping jobs from a search URL."""
        tab = await self.browser_manager.create_tab()
        
        try:
            # 2. Initial Navigation
            # Enable Network domain and add handler for GraphQL interception
            await tab.send(cdp.network.enable())
            
            # Use a lambda or closure to pass the tab to the handler
            async def handler(event):
                await self._on_response_received(tab, event)
                
            tab.add_handler(cdp.network.ResponseReceived, handler)
            
            # Trigger initial navigation to check session
            await tab.get("https://www.upwork.com/nx/find-work/best-matches")
            await self.wait_for_cloudflare(tab)
            
            # Check if redirected to login
            if "login" in tab.url or await self._is_login_page(tab):
                await self._perform_login(tab)
                # Verify if we actually got past login
                if "login" in tab.url or await self._is_login_page(tab):
                    logger.error("❌ Still on login page after authentication attempt. Aborting.")
                    raise ScraperException("Authentication failed or 2FA required.")
            
            # Now navigate to the real target
            await tab.get(product_url)
            await self.wait_for_cloudflare(tab)
            
            # 3. Determine extent of scraping
            total_pages = await self._determine_total_pages(tab)
            logger.info(f"📊 Final Total Pages Found: {total_pages}")

            if no_of_pages_to_scrape:
                pages_to_process = min(no_of_pages_to_scrape, total_pages)
                logger.info(f"🔢 User requested {no_of_pages_to_scrape} pages. Processing {pages_to_process}.")
            else:
                pages_to_process = total_pages
                logger.info(f"🔢 No page limit set. Processing all {pages_to_process} detected pages.")
            
            logger.info(f"[Session: {self.session_id}] Final plan: Scraping {pages_to_process} pages from {product_url}")

            for page_num in range(1, pages_to_process + 1):
                logger.info(f"🚀 [Page {page_num}/{pages_to_process}] Starting scrape...")
                
                if page_num > 1:
                    next_url = self._build_next_page_url(product_url, page_num)
                    logger.info(f"⏭️ Navigating to Page {page_num}: {next_url}")
                    await tab.get(next_url)
                    await self.wait_for_cloudflare(tab)
                    # Reset pagination event for each new page if we want fresh interception
                    self._pagination_event.clear()

                await self._scrape_page(tab, page_num, on_card_data_async)
                logger.info(f"✅ [Page {page_num}/{pages_to_process}] Finished.")

        finally:
            await tab.close()

    async def _scrape_page(self, tab: uc.Tab, page_num: int, callback: Optional[Callable]):
        """Processes all job tiles on a single search result page."""
        # 1. Wait for tiles to load initially
        initial_tiles = await self._wait_for_tiles(tab)
        count = len(initial_tiles)
        logger.info(f"Page {page_num} loaded with {count} tiles. Starting processing...")
        
        for i in range(count):
            card_index = i + 1
            logger.info(f"Processing Page {page_num}, Tile {card_index}/{count}")
            
            try:
                # 2. Re-select tiles to avoid StaleElementReferenceError
                # The DOM might update after closing modals, so always fetch fresh
                current_tiles = await tab.select_all(self.TILE_SELECTOR)
                
                if i >= len(current_tiles):
                    logger.warning(f"Tile index {i} out of range (found {len(current_tiles)}). Stopping page.")
                    break
                    
                tile = current_tiles[i]
                
                # 3. Scrape the tile
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
                
                # 4. Small delay between tiles to be human-like and let UI settle
                await asyncio.sleep(random.uniform(1.0, 2.0))
                
            except Exception as e:
                logger.error(f"Error scraping tile {card_index} on page {page_num}: {e}")
                # Try to recover by closing any open modal
                await self._close_modal(tab, tab)

    async def _scrape_tile(self, tab: uc.Tab, tile: uc.Element) -> Optional[str]:
        """Clicks a single job tile and extracts the content from the modal."""
        await tile.scroll_into_view()
        await tile.click()
        
        # Wait for modal content
        slider_appeared = await self._wait_for_element(tab, self.MODAL_SELECTOR, timeout=5.0)
        if not slider_appeared:
            return None
        
        # Wait for "Save job" text to ensure modal is loaded
        save_job_visible = await self._wait_for_text(tab, "Save job", timeout=5.0)
        if not save_job_visible:
            logger.warning(f"  - 'Save job' button not found for tile {card_index}, but proceeding...")
            
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

    async def _determine_total_pages(self, tab: uc.Tab) -> int:
        """
        Calculates total pages using API interception (preferred) or DOM fallback.
        """
        logger.info("🔍 Starting pagination detection...")
        
        # STRATEGY 0: API Interception (GraphQL body)
        logger.info("📡 Strategy 0: Checking API Interception data...")
        try:
            # Wait a bit for the handler to fire if it hasn't already
            try:
                await asyncio.wait_for(self._pagination_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.debug("API pagination event timed out, falling back to DOM.")

            if self._last_pagination_data:
                total_pages = self._last_pagination_data.get('total_pages', 1)
                logger.info(f"✅ SUCCESS via API: {total_pages} pages found!")
                return total_pages
            else:
                logger.info("   ❌ No API pagination data intercepted yet.")
        except Exception as e:
            logger.error(f"   ❌ Strategy 0 (API) failed: {e}")

        try:
            # Scroll to bottom to ensure pagination footer is loaded
            await tab.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3.0)
            
            # Capture debug screenshot
            try:
                debug_path = f"storage/debug_pagination_{self.session_id}.jpg"
                await tab.save_screenshot(filename=debug_path)
                logger.info(f"📸 Debug screenshot saved: {debug_path}")
            except Exception as e:
                logger.warning(f"Screenshot failed: {e}")

            # STRATEGY 1: .sr-only elements
            logger.info("📋 Strategy 1: Scanning .sr-only elements...")
            try:
                sr_elements = await tab.select_all('.sr-only')
                logger.info(f"   Found {len(sr_elements)} .sr-only elements")
                
                for i, el in enumerate(sr_elements):
                    try:
                        text = el.text_all
                        logger.info(f"   Element {i+1}: '{text[:50] if text else 'EMPTY'}'")
                        
                        if text:
                            match = re.search(r"of\s+(\d+)", text, re.IGNORECASE)
                            if match:
                                logger.info(f"✅ SUCCESS via .sr-only: {total_pages} pages found!")
                                return total_pages
                    except Exception as e:
                        logger.warning(f"   Error reading element {i+1}: {e}")
                        
                logger.info("   ❌ No 'of X' pattern found in .sr-only elements")
            except Exception as e:
                logger.error(f"   ❌ Strategy 1 failed: {e}")

            # STRATEGY 2: Mobile pagination
            logger.info("📱 Strategy 2: Mobile pagination...")
            try:
                element = await tab.select('li[data-test="pagination-mobile"]', timeout=0.5)
                if element:
                    text = element.text_all
                    logger.info(f"   Mobile element text: '{text}'")
                    
                    match = re.search(r"(\d+)\s+of\s+(\d+)", text, re.IGNORECASE)
                    if match:
                        total_pages = int(match.group(2))
                        logger.info(f"✅ SUCCESS via mobile: {total_pages} pages!")
                        return total_pages
                    
                    match = re.search(r"of\s+(\d+)", text, re.IGNORECASE)
                    if match:
                        total_pages = int(match.group(1))
                        logger.info(f"✅ SUCCESS via mobile (fallback): {total_pages} pages!")
                        return total_pages
                else:
                    logger.info("   ❌ Mobile pagination element not found")
            except Exception as e:
                logger.error(f"   ❌ Strategy 2 failed: {e}")

            # STRATEGY 3: Max page number from visible buttons
            logger.info("🔢 Strategy 3: Max page number from pagination buttons...")
            try:
                nr_elements = await tab.select_all('li[data-test="pagination-nr"]')
                logger.info(f"   Found {len(nr_elements)} pagination-nr elements")
                
                page_nums = []
                for i, el in enumerate(nr_elements):
                    try:
                        text = el.text_all
                        logger.info(f"   Button {i+1} text: '{text.strip()}'")
                        nums = re.findall(r"\d+", text)
                        if nums:
                            page_nums.append(int(nums[-1]))
                            logger.info(f"      Extracted number: {nums[-1]}")
                    except Exception as e:
                        logger.warning(f"   Error reading button {i+1}: {e}")
                
                if page_nums:
                    max_page = max(page_nums)
                    logger.info(f"✅ SUCCESS via max number: {max_page} pages (from {page_nums})!")
                    return max_page
                else:
                    logger.info("   ❌ No numbers extracted from pagination buttons")
            except Exception as e:
                logger.error(f"   ❌ Strategy 3 failed: {e}")

            logger.warning("⚠️ All strategies failed, defaulting to 1 page")
            
        except Exception as e:
            logger.error(f"❌ Critical error in _determine_total_pages: {e}", exc_info=True)
            
        return 1

    async def _wait_for_tiles(self, tab: uc.Tab, timeout: float = 15.0) -> List[uc.Element]:
        """
        Polls for job tiles to appear and handles lazy loading via incremental scrolling.
        """
        logger.debug("Waiting for jobs to load (scrolling to trigger lazy-load)...")
        
        last_count = 0
        stable_polls = 0
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            tiles = await tab.select_all(self.TILE_SELECTOR)
            count = len(tiles)
            
            if count > 0:
                if count > last_count:
                    logger.debug(f"Job count increased: {count}. Scrolling to last tile...")
                    await tiles[-1].scroll_into_view()
                    last_count = count
                    stable_polls = 0
                else:
                    stable_polls += 1
                    # If count is stable for 3 polls (~2.4s), assume page is fully loaded
                    if stable_polls >= 3:
                        logger.info(f"Page settled with {count} job tiles.")
                        return tiles
            else:
                # If nothing found yet, scroll a bit to kick off loading
                await tab.scroll_down(300)

            await asyncio.sleep(0.8)
            
        # Final fallback check
        final_tiles = await tab.select_all(self.TILE_SELECTOR)
        logger.info(f"Finished waiting. Captured {len(final_tiles)} tiles.")
        return final_tiles

    async def _wait_for_element(self, tab: uc.Tab, selector: str, timeout: float = 5.0) -> bool:
        """Polls for a generic element."""
        try:
            el = await tab.select(selector, timeout=timeout)
            return bool(el)
        except:
            return False

    async def _wait_for_text(self, tab: uc.Tab, text: str, timeout: float = 5.0) -> bool:
        """Polls for specific text on the page."""
        try:
            # nodriver's find method is great for text
            el = await tab.find(text, timeout=timeout)
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

    async def wait_for_cloudflare(self, tab: uc.Tab):
        """Helper to wait for Cloudflare challenges."""
        challenge_text = ["Verify you are human", "cf-turnstile", "Cloudflare", "Checking your browser"]
        try:
            content = await tab.evaluate("document.body.innerText")
            if any(term in content for term in challenge_text):
                logger.warning("Cloudflare / Bot-check detected. Waiting up to 120s...")
                start = datetime.now()
                while (datetime.now() - start).total_seconds() < 120:
                    await asyncio.sleep(4)
                    try:
                        content = await tab.evaluate("document.body.innerText")
                        if not any(term in content for term in challenge_text):
                            logger.info("Challenge cleared.")
                            break
                    except:
                        break
        except: pass

    async def _on_response_received(self, tab: uc.Tab, event: cdp.network.ResponseReceived):
        """Callback to intercept GraphQL responses containing pagination data."""
        url = event.response.url
        # Target specific signatures in URL or intercept any GraphQL for body inspection
        if "userJobSearch" in url or "graphql" in url.lower():
            try:
                # Spawn an async task to get the body without blocking
                asyncio.create_task(self._parse_graphql_pagination(tab, event.request_id, url))
            except Exception as e:
                logger.error(f"Failed to trigger GraphQL parsing: {e}")

    async def _parse_graphql_pagination(self, tab: uc.Tab, request_id: str, url: str):
        """Helper to get response body and parse JSON pagination."""
        try:
            # Short wait for body availability
            await asyncio.sleep(0.5)
            
            result = await tab.send(cdp.network.get_response_body(request_id=request_id))
            
            if isinstance(result, tuple):
                body_dict = next((x for x in result if isinstance(x, dict)), {})
            else:
                body_dict = result if isinstance(result, dict) else {}

            body = body_dict.get('body')
            if not body: return
            
            if body_dict.get('base64Encoded'):
                body = base64.b64decode(body).decode('utf-8')
            
            # Check signatures for relevant search data
            signatures = ["userJobSearch", "jobSearch", "searchNuxt", "paging"]
            if any(sig in body for sig in signatures) or any(sig in url for sig in signatures):
                data = json.loads(body)
                
                def find_paging(obj):
                    if isinstance(obj, dict):
                        if "paging" in obj and isinstance(obj["paging"], dict):
                            return obj["paging"]
                        for k, v in obj.items():
                            found = find_paging(v)
                            if found: return found
                    elif isinstance(obj, list):
                        for item in obj:
                            found = find_paging(item)
                            if found: return found
                    return None

                paging = find_paging(data)
                
                if paging:
                    total = paging.get('total')
                    count = paging.get('count')
                    offset = paging.get('offset', 0)
                    
                    if total and count:
                        total_pages = math.ceil(total / count)
                        current_page = (offset // count) + 1
                        self._last_pagination_data = {
                            'total_pages': total_pages,
                            'current_page': current_page,
                            'total_results': total,
                            'timestamp': datetime.now().isoformat()
                        }
                        logger.info(f"📉 Intercepted API Pagination: Page {current_page} of {total_pages} (Total: {total})")
                        self._pagination_event.set()
        except Exception as e:
            # Silent fail for non-matching or malformed payloads
            pass
    async def _is_login_page(self, tab: uc.Tab) -> bool:
        """Heuristic to check if we are on the login page."""
        try:
            content = await tab.evaluate("document.body.innerText")
            return "Log in to Upwork" in content or "login" in tab.url
        except:
            return False

    async def _perform_login(self, tab: uc.Tab):
        """Executes the multi-step login flow."""
        logger.info("🔐 Starting automated login flow...")
        
        if not settings.UPWORK_USERNAME or not settings.UPWORK_PASSWORD:
            logger.error("❌ UPWORK_USERNAME or UPWORK_PASSWORD not set in environment.")
            return

        try:
            # 1. Username
            logger.info("  - Entering username...")
            username_field = await tab.select('input[id="login_username"]', timeout=15)
            if username_field:
                await self._type_humanly(username_field, settings.UPWORK_USERNAME)
                await asyncio.sleep(random.uniform(1.0, 2.0))
                
                continue_btn = await tab.select('button[id="login_password_continue"]', timeout=10)
                if continue_btn:
                    await continue_btn.click()
                    await asyncio.sleep(random.uniform(2.0, 4.0)) # Longer wait after username
                else:
                    logger.error("❌ 'Continue' button not found after username.")
                    return
            else:
                logger.error("❌ Username field not found.")
                return
            
            # 2. Password
            logger.info("  - Entering password...")
            password_field = await tab.select('input[id="login_password"]', timeout=15)
            if password_field:
                await self._type_humanly(password_field, settings.UPWORK_PASSWORD)
                await asyncio.sleep(random.uniform(1.0, 2.0))
                
                login_btn = await tab.select('button[id="login_control_continue"]', timeout=10)
                if login_btn:
                    await asyncio.sleep(random.uniform(0.5, 1.5)) # Hesitate before final click
                    await login_btn.click()
                else:
                    logger.error("❌ 'Login' button not found after password.")
                    return
            else:
                logger.error("❌ Password field not found.")
                return
                
            # 3. Wait for dashboard or 2FA
            logger.info("⏳ Waiting for login completion or 2FA prompt...")
            start = datetime.now()
            while (datetime.now() - start).total_seconds() < 60:
                if "login" not in tab.url:
                    # Double check if we are actually logged in (e.g. redirected to home or find-work)
                    if "upwork.com" in tab.url and "login" not in tab.url:
                        logger.info("✅ Login successful (redirected away from login page).")
                        return
                
                # Check for 2FA screen text
                try:
                    content = await tab.evaluate("document.body.innerText")
                    if "Two-step verification" in content or "Enter the code" in content:
                        logger.warning("⚠️ 2FA REQUIRED. Please check your secondary device or browser profile.")
                        # We can't automate 2FA, so we wait and hope for manual/profile intervention
                        await asyncio.sleep(10)
                except:
                    pass
                
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"❌ Login failed: {e}")
            await tab.save_screenshot("storage/login_fail.jpg")

    async def _type_humanly(self, element: uc.Element, text: str):
        """Simulates character-by-character typing with VERY slow random delays."""
        try:
            for char in text:
                await element.send_keys(char)
                # Much slower: random delay between 0.3s and 0.8s
                await asyncio.sleep(random.uniform(0.3, 0.8))
                # Higher chance of longer "thinking" pauses
                if random.random() < 0.2:
                    await asyncio.sleep(random.uniform(1.5, 3.5))
        except Exception as e:
            logger.warning(f"Error during human typing: {e}")
            # Fallback to instant send_keys if character-by-character fails
            await element.send_keys(text)
