import json
import os
import asyncio
import random
import logging
import time
from datetime import datetime
from typing import List, Dict, Any
import nodriver as uc
from bs4 import BeautifulSoup
from src.services.gemini_extractor import GeminiExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('upwork_scraper.log')
    ]
)
logger = logging.getLogger(__name__)

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
        self.debug_save = True # Optional: Save local HTML files

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

    async def _find_job_frame(self):
        """
        Helper to detect the frame containing the job slider ('air3-slider-content').
        Scans all tab targets in the browser.
        """
        try:
            # Check main page
            main_found = await self.page.select('div.air3-slider-content[data-test="UpCSliderBody"]', timeout=2)
            if main_found:
                print("DEBUG: Found slider in main page context.")
                return self.page

            # Scan all targets
            print(f"DEBUG: Scanning {len(self.browser.targets)} targets for slider...")
            for target in self.browser.targets:
                try:
                    if hasattr(target, 'select'):
                        found = await target.select('div.air3-slider-content[data-test="UpCSliderBody"]', timeout=1)
                        if found:
                            print(f"DEBUG: FOUND slider in specialization target: {getattr(target, 'url', 'Unknown')}")
                            return target
                except:
                    continue
        except Exception as e:
            print(f"DEBUG: Iframe scan error: {e}")
        
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

                # 2. Wait for content hydration (title present)
                start_wait = time.time()
                hydrated = False
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
                            print(f"✅ Hydration SUCCESS for Card.")
                            hydrated = True
                            break
                        
                        print(f"DEBUG: Syncing panel contents... (Text: {diag_data.get('text_len', 0) if diag_data else 0})")
                    except Exception as eval_err:
                        print(f"DEBUG: Eval error during wait: {eval_err}")
                    
                    await asyncio.sleep(1.2)
                
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
            print("DEBUG: Waiting 8s for tiles to load...")
            await asyncio.sleep(8)
            
            tiles = await self.page.select_all(tile_selector)
            logger.info(f"Page scan complete. Total tiles discovered: {len(tiles)}")
            print(f"\n[CONSOLE] FOUND {len(tiles)} JOB CARDS ON PAGE")
            
            if not tiles:
                print("[CONSOLE] NO TILES FOUND.")
                await self.page.save_screenshot("no_tiles.png")
                return []

            # Iterate through discovered tiles
            limit = min(len(tiles), num_jobs) if num_jobs > 0 else len(tiles)
            
            for i in range(limit):
                try:
                    # Re-acquire tiles
                    cur_tiles = await self.page.select_all(tile_selector)
                    if i >= len(cur_tiles): break
                    tile = cur_tiles[i]
                    
                    print(f"\n[CONSOLE] PROCESSING CARD {i+1} of {limit}")
                    print(f"DEBUG: CLICKING CARD {i+1}...")
                    
                    await tile.scroll_into_view()
                    await tile.click()
                    
                    # Wait for animation
                    wait_time = random.uniform(2.5, 4.0)
                    print(f"DEBUG: Waiting {wait_time:.1f}s for detail hydration...")
                    await asyncio.sleep(wait_time)
                    
                    # Detect frame/context
                    context = await self._find_job_frame()
                    
                    # Extract WHOLE PAGE HTML
                    full_page_dom = await self._extract_job_modal(context=context)
                    
                    if full_page_dom:
                        # Clean and Filter HTML on the SERVER side
                        print(f"DEBUG: Filtering slider content from full DOM on server for Card {i+1}...")
                        filtered_html = self._clean_html_server_side(full_page_dom)
                        
                        if filtered_html:
                            # Store in requested list format
                            temp_html_list.append({f"card_{i+1}": filtered_html})
                            print(f"✅ Card {i+1} stored (Filtered Size: {len(filtered_html)} chars)")
                        else:
                            print(f"❌ Server-side filter failed to find slider in Card {i+1} DOM.")
                    else:
                        print(f"❌ Failed to capture full DOM for Card {i+1}")

                    # Close the panel
                    print(f"DEBUG: Closing Modal for Card {i+1}...")
                    try:
                        back_btn = await context.select('button.air3-slider-prev-btn', timeout=3)
                        if back_btn:
                            await back_btn.click()
                        else:
                            await self.page.send_keys("\uE00C")
                    except:
                        try: await self.page.send_keys("\uE00C")
                        except: pass
                    
                    await asyncio.sleep(random.uniform(1.2, 2.5))
                        
                except Exception as e:
                    logger.error(f"Card {i+1} interaction error: {e}")
                    print(f"[CONSOLE] ERROR ON CARD {i+1}: {e}")
                    try: await self.page.send_keys("\uE00C")
                    except: pass
                    
        except Exception as e:
            logger.error(f"Global extraction failure: {e}")
            print(f"[CONSOLE] CRITICAL FAILURE: {e}")

        # 3. Post-Process with Gemini AI Extraction
        print("\n" + "="*50)
        print("DEBUG: Starting AI Extraction phase...")
        response_content = []
        
        for item in temp_html_list:
            # item is {"card_N": "html_content"}
            card_key = list(item.keys())[0]
            html_content = item[card_key]
            
            if not html_content:
                continue
                
            print(f"DEBUG: Extracting data for {card_key}...")
            try:
                # Use the existing GeminiExtractor
                data = self.extractor.extract_from_html(html_content)
                if data:
                    print(f"✅ AI Extraction SUCCESS for {card_key}")
                    response_content.append(data)
                else:
                    print(f"⚠️ AI returned empty data for {card_key}")
            except Exception as e:
                print(f"❌ AI Extraction FAILED for {card_key}: {e}")

        # Final print as explicitly requested
        print("\n" + "="*50)
        print("[CONSOLE] SCRAPING & EXTRACTION COMPLETE. FINAL DATA:")
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

