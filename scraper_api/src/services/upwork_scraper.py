import json
import os
import asyncio
import random
import logging
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from logging.handlers import RotatingFileHandler
import nodriver as uc
from bs4 import BeautifulSoup
from src.services.gemini_extractor import GeminiExtractor
from src.services.exceptions import (
    ScraperException,
    CloudflareBlockException,
    ModalExtractionException,
    AIExtractionException,
    BrowserInitException,
    SessionResetException
)

# Configure professional logging with rotation
os.makedirs('logs', exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Rotating file handler (10MB max, 5 backups)
file_handler = RotatingFileHandler(
    'logs/upwork_scraper.log',
    maxBytes=10*1024*1024,
    backupCount=5
)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
)
file_handler.setFormatter(file_formatter)

# Console handler (INFO and above)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
console_handler.setFormatter(console_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

class UpworkScraper:
    """
    Elite Stealth Scraper using Nodriver (CDP-based).
    Inspired by Scrapfly 2026 recommendations.
    """
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.extractor = GeminiExtractor()
        self.browser = None
        self.page = None
        self.output_file = "upwork.json"
        self.profile_path = os.path.join(os.getcwd(), 'upwork_profile_nd')
        self.debug_save = True
        self.session_id = str(uuid.uuid4())[:8]  # Unique session identifier
        self.consecutive_failures = 0  # Track failures for auto-reset
        self.performance_metrics = {  # Track timing metrics
            'total_time': 0,
            'browser_init_time': 0,
            'scraping_time': 0,
            'ai_extraction_time': 0
        }

    async def _init_browser(self):
        if not self.browser:
            logger.info("Launching Elite Nodriver Browser...")
            self.browser = await uc.start(
                headless=self.headless,
                user_data_dir=self.profile_path,
                browser_args=["--start-maximized"]
            )
            # Entry point maturation
            self.page = await self.browser.get("https://www.google.com/search?q=upwork+jobs")
            await asyncio.sleep(3)

    async def _wait_for_cloudflare(self):
        """Wait for human to solve or for challenge to pass."""
        challenge_text = ["Verify you are human", "cf-turnstile", "Cloudflare"]
        try:
            content = await self.page.evaluate("document.body.innerText")
            if any(term in content for term in challenge_text):
                logger.warning("Cloudflare challenge detected. Please solve in browser.")
                print("\n" + "="*50)
                print("DEBUG: CLOUDFLARE BLOCK DETECTED!")
                print("ACTION: PLEASE SOLVE THE CHALLENGE IN THE BROWSER WINDOW.")
                print("="*50 + "\n")
                
                start = datetime.now()
                while True:
                    await asyncio.sleep(3)
                    content = await self.page.evaluate("document.body.innerText")
                    if not any(term in content for term in challenge_text):
                        print("DEBUG: CHALLENGE CLEARED - PROCEEDING...")
                        break
                    if (datetime.now() - start).total_seconds() > 180:
                        logger.error("Timed out waiting for solve.")
                        break
                logger.info("Challenge cleared.")
                await asyncio.sleep(4)
        except: pass

    async def _wait_for_element(self, selector: str, timeout: float = 10.0, context=None) -> bool:
        """
        Smart polling for element with exponential backoff.
        Returns True if element found, False if timeout.
        """
        if context is None:
            context = self.page
            
        start = time.time()
        poll_interval = 0.2  # Start fast (200ms)
        
        while time.time() - start < timeout:
            try:
                element = await context.select(selector, timeout=0.5)
                if element:
                    elapsed = time.time() - start
                    logger.debug(f"[Session: {self.session_id}] Element '{selector}' found in {elapsed:.2f}s")
                    return True
            except:
                pass
            
            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.3, 1.5)  # Exponential backoff, cap at 1.5s
        
        logger.warning(f"[Session: {self.session_id}] Element '{selector}' not found after {timeout}s")
        return False

    async def _wait_for_tiles(self, selector: str, max_wait: float = 10.0) -> list:
        """
        Intelligent tile loading with early exit.
        Much faster than fixed 8s wait.
        """
        start = time.time()
        poll_interval = 0.3
        
        while time.time() - start < max_wait:
            tiles = await self.page.select_all(selector)
            if tiles and len(tiles) > 0:
                elapsed = time.time() - start
                logger.info(f"[Session: {self.session_id}] {len(tiles)} tiles loaded in {elapsed:.2f}s")
                return tiles
            
            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 2.0)
        
        logger.warning(f"[Session: {self.session_id}] No tiles found after {max_wait}s")
        return []

    async def _find_job_frame(self):
        """
        Helper to detect the frame containing the job slider.
        """
        try:
            # Check main page
            main_found = await self.page.select('div.air3-slider-content[data-test="UpCSliderBody"]', timeout=2)
            if main_found:
                logger.debug(f"[Session: {self.session_id}] Found slider in main page context")
                return self.page

            # Scan all targets
            logger.debug(f"[Session: {self.session_id}] Scanning {len(self.browser.targets)} targets for slider")
            for target in self.browser.targets:
                try:
                    if hasattr(target, 'select'):
                        found = await target.select('div.air3-slider-content[data-test="UpCSliderBody"]', timeout=1)
                        if found:
                            logger.debug(f"[Session: {self.session_id}] Found slider in specialized target")
                            return target
                except:
                    continue
        except Exception as e:
            logger.error(f"[Session: {self.session_id}] Iframe scan error: {e}")
        
        return self.page

    def _clean_html_server_side(self, full_dom: str) -> str:
        """
        Server-side precision filtering.
        Takes full DOM, finds the specific slider container, and cleans it.
        """
        if not full_dom:
            return ""
        
        try:
            soup = BeautifulSoup(full_dom, 'html.parser')
            
            # 1. Target the specific slider container
            # Using the exact selectors previously discussed
            slider = soup.select_one('div.air3-slider-content[data-test="UpCSliderBody"]') or \
                     soup.select_one('.air3-slider-content') or \
                     soup.select_one('[data-test="UpCSliderBody"]')
            
            if not slider:
                print("DEBUG: [Server-Filter] Slider element NOT found in full DOM.")
                return ""

            # 2. Clean the slider element
            for tag in slider.find_all(['script', 'style', 'svg', 'path', 'link', 'meta', 'iframe', 'noscript']):
                tag.decompose()
                
            return str(slider)
        except Exception as e:
            print(f"DEBUG: [Server-Filter] Error during BeautifulSoup processing: {e}")
            return ""

    async def _extract_job_modal(self, context=None, max_retries: int = 3) -> str:
        """
        Ultra-robust extractor for Upwork job slider.
        Ensures hydration, then returns the WHOLE page DOM to the server.
        """
        if not context:
            context = self.page

        for attempt in range(max_retries):
            try:
                print(f"DEBUG: Ensuring slider hydration (Attempt {attempt+1}) in context: {getattr(context, 'url', 'Main')[:60]}...")

                # 1. Wait for container presence
                await context.select('div.air3-slider-content[data-test="UpCSliderBody"]', timeout=12)

                # 2. Optimized hydration polling with exponential backoff
                start_wait = time.time()
                hydrated = False
                poll_interval = 0.2  # Start fast
                
                while time.time() - start_wait < 10:
                    try:
                        diag_data = await context.evaluate("""
                            (() => {
                                const el = document.querySelector('div.air3-slider-content[data-test="UpCSliderBody"]') || 
                                           document.querySelector('.air3-slider-content');
                                if (!el) return { "found": false };
                                const title = el.querySelector('h1');
                                return {
                                    "found": true,
                                    "has_title": !!title && title.innerText.trim().length > 0,
                                    "text_len": el.innerText ? el.innerText.trim().length : 0
                                };
                            })()
                        """)
                        
                        if diag_data and diag_data.get('has_title'):
                            elapsed = time.time() - start_wait
                            logger.debug(f"[Session: {self.session_id}] Hydration SUCCESS in {elapsed:.2f}s")
                            hydrated = True
                            break
                        
                        logger.debug(f"[Session: {self.session_id}] Polling... (Text: {diag_data.get('text_len', 0) if diag_data else 0})")
                    except Exception as eval_err:
                        logger.debug(f"[Session: {self.session_id}] Eval error: {eval_err}")
                    
                    await asyncio.sleep(poll_interval)
                    poll_interval = min(poll_interval * 1.3, 1.5)  # Exponential backoff
                
                # 3. Capture WHOLE PAGE DOM as requested
                print("DEBUG: Hydration confirmed. Capturing FULL DOM...")
                full_dom = await context.get_content()

                if full_dom and len(full_dom) > 10000: # Whole page should be large
                    print(f"✅ Full DOM captured successfully ({len(full_dom)} chars).")
                    return full_dom
                else:
                    print(f"⚠️ Full DOM capture suspect length ({len(full_dom) if full_dom else 0}), retrying...")

            except Exception as e:
                print(f"⚠️ Hydration/Capture attempt {attempt+1} failed: {e}")
                await asyncio.sleep(1.2)

        print("❌ Failed to capture full DOM after retries.")
        return None

    async def search_jobs(self, query: str, num_jobs: int = 5) -> List[Dict[str, Any]]:
        """Main search entry point (Wrapped for sync/async compatibility)."""
        try:
            try:
                loop = asyncio.get_running_loop()
                return await self._search_jobs_async(query, num_jobs)
            except RuntimeError:
                return asyncio.run(self._search_jobs_async(query, num_jobs))
        except Exception as e:
            import traceback
            logger.error(f"Search failed: {e}")
            print(f"DEBUG CRITICAL ERROR: {e}")
            traceback.print_exc()
            return []

    async def _search_jobs_async(self, query: str, num_jobs: int = 5) -> List[Dict[str, Any]]:
        await self._init_browser()
        
        # 1. Direct Search Results Navigation
        search_url = f"https://www.upwork.com/nx/search/jobs/?q={query.replace(' ', '%20')}"
        logger.info(f"Navigating directly to search results: {search_url}")
        print(f"DEBUG: SEARCH URL -> {search_url}")
        await self.page.get(search_url)
        await self._wait_for_cloudflare()
        
        # 2. Extract - All Job Tiles & Page DOM
        temp_html_list = []
        try:
            tile_selector = 'article.job-tile[data-test="JobTile"]'
            
            # OPTIMIZATION: Intelligent tile loading (was fixed 8s)
            logger.info(f"[Session: {self.session_id}] Waiting for tiles to load...")
            tiles = await self._wait_for_tiles(tile_selector, max_wait=10.0)
            
            if not tiles:
                logger.warning(f"[Session: {self.session_id}] No tiles found")
                await self.page.save_screenshot("no_tiles.png")
                return []

            # Iterate through discovered tiles
            limit = min(len(tiles), num_jobs) if num_jobs > 0 else len(tiles)
            logger.info(f"[Session: {self.session_id}] Processing {limit} job cards")
            
            for i in range(limit):
                card_start_time = time.time()
                try:
                    # Re-acquire tiles
                    cur_tiles = await self.page.select_all(tile_selector)
                    if i >= len(cur_tiles): break
                    tile = cur_tiles[i]
                    
                    logger.info(f"[Session: {self.session_id}] Processing card {i+1}/{limit}")
                    
                    await tile.scroll_into_view()
                    await tile.click()
                    
                    # OPTIMIZATION: Wait for slider to appear (was fixed 2.5-4s)
                    slider_appeared = await self._wait_for_element('.air3-slider-content', timeout=5.0)
                    if not slider_appeared:
                        logger.warning(f"[Session: {self.session_id}] Slider didn't appear for card {i+1}")
                        continue
                    
                    # Small jitter for human-like behavior
                    await asyncio.sleep(random.uniform(0.3, 0.7))
                    
                    # Detect frame/context
                    context = await self._find_job_frame()
                    
                    # Extract WHOLE PAGE HTML
                    full_page_dom = await self._extract_job_modal(context=context)
                    
                    if full_page_dom:
                        # Clean and Filter HTML on the SERVER side
                        logger.debug(f"[Session: {self.session_id}] Filtering HTML for card {i+1}")
                        filtered_html = self._clean_html_server_side(full_page_dom)
                        
                        if filtered_html:
                            temp_html_list.append({f"card_{i+1}": filtered_html})
                            logger.info(f"[Session: {self.session_id}] ✅ Card {i+1} stored ({len(filtered_html)} chars)")
                        else:
                            logger.warning(f"[Session: {self.session_id}] Server-side filter failed for card {i+1}")
                    else:
                        logger.warning(f"[Session: {self.session_id}] Failed to capture DOM for card {i+1}")

                    # Close the panel
                    logger.debug(f"[Session: {self.session_id}] Closing modal for card {i+1}")
                    try:
                        back_btn = await context.select('button.air3-slider-prev-btn', timeout=2)
                        if back_btn:
                            await back_btn.click()
                        else:
                            await self.page.send_keys("\uE00C")
                    except:
                        try: await self.page.send_keys("\uE00C")
                        except: pass
                    
                    # OPTIMIZATION: Wait for slider to disappear (was fixed 1.2-2.5s)
                    close_start = time.time()
                    while time.time() - close_start < 3.0:
                        try:
                            slider = await self.page.select('.air3-slider-content', timeout=0.3)
                            if not slider:
                                break
                        except:
                            break
                        await asyncio.sleep(0.2)
                    
                    # Small random delay between cards
                    await asyncio.sleep(random.uniform(0.4, 0.8))
                    
                    card_time = time.time() - card_start_time
                    logger.debug(f"[Session: {self.session_id}] Card {i+1} processed in {card_time:.2f}s")
                        
                except Exception as e:
                    logger.error(f"Card {i+1} interaction error: {e}")
                    print(f"[CONSOLE] ERROR ON CARD {i+1}: {e}")
                    try: await self.page.send_keys("\uE00C")
                    except: pass
                    
        except Exception as e:
            logger.error(f"Global extraction failure: {e}")
            print(f"[CONSOLE] CRITICAL FAILURE: {e}")

        # 3. Post-Process with Concurrent Gemini AI Extraction
        print("\n" + "="*50)
        logger.info(f"[Session: {self.session_id}] Starting concurrent AI extraction for {len(temp_html_list)} cards")
        
        ai_start_time = time.time()
        response_content = []
        failed_extractions = []
        
        # Create concurrent extraction tasks
        async def extract_single_card(item: Dict[str, str], index: int) -> Optional[Dict[str, Any]]:
            """Extract data from a single card with error handling"""
            card_key = list(item.keys())[0]
            html_content = item[card_key]
            
            if not html_content:
                logger.warning(f"[Session: {self.session_id}] Empty HTML for {card_key}")
                return None
                
            try:
                logger.debug(f"[Session: {self.session_id}] Extracting data for {card_key}...")
                data = await self.extractor.extract_from_html_async(html_content)
                if data:
                    logger.info(f"[Session: {self.session_id}] ✅ AI Extraction SUCCESS for {card_key}")
                    self.consecutive_failures = 0  # Reset failure counter
                    return data
                else:
                    logger.warning(f"[Session: {self.session_id}] AI returned empty data for {card_key}")
                    return None
            except Exception as e:
                logger.error(f"[Session: {self.session_id}] ❌ AI Extraction FAILED for {card_key}: {e}")
                self.consecutive_failures += 1
                failed_extractions.append(index + 1)
                return None
        
        # Execute all extractions concurrently
        extraction_tasks = [
            extract_single_card(item, i) 
            for i, item in enumerate(temp_html_list)
        ]
        
        results = await asyncio.gather(*extraction_tasks, return_exceptions=True)
        
        # Filter out None and exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[Session: {self.session_id}] Exception in extraction {i+1}: {result}")
                failed_extractions.append(i + 1)
            elif result is not None:
                response_content.append(result)
        
        ai_extraction_time = time.time() - ai_start_time
        self.performance_metrics['ai_extraction_time'] = ai_extraction_time
        
        # Log performance metrics
        logger.info(f"[Session: {self.session_id}] AI Extraction completed in {ai_extraction_time:.2f}s")
        logger.info(f"[Session: {self.session_id}] Success: {len(response_content)}/{len(temp_html_list)} cards")
        if failed_extractions:
            logger.warning(f"[Session: {self.session_id}] Failed cards: {failed_extractions}")

        # Final print
        print("\n" + "="*50)
        print(f"[CONSOLE] SCRAPING & EXTRACTION COMPLETE")
        print(f"[CONSOLE] Session ID: {self.session_id}")
        print(f"[CONSOLE] Success Rate: {len(response_content)}/{len(temp_html_list)} cards")
        print(f"[CONSOLE] AI Extraction Time: {ai_extraction_time:.2f}s")
        print(f"[CONSOLE] FINAL DATA:")
        print(json.dumps(response_content, indent=2))
        print("="*50 + "\n")
        
        return response_content

    async def close(self):
        try:
            if self.browser:
                logger.info("Decommissioning browser...")
                await self.browser.stop()
        except: pass

if __name__ == "__main__":
    scraper = UpworkScraper(headless=False)
    try:
        if os.getenv("GEMINI_API_KEY"):
            asyncio.run(scraper._search_jobs_async("React Developer", num_jobs=1))
        else:
            print("Set GEMINI_API_KEY")
    finally:
        asyncio.run(scraper.close())

