import json
import os
import asyncio
import random
import logging
import time
from datetime import datetime
from typing import List, Dict, Any
import nodriver as uc
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

    async def _init_browser(self):
        if not self.browser:
            logger.info("Launching Elite Nodriver Browser...")
            # nodriver automatically handles most stealth requirements
            self.browser = await uc.start(
                headless=self.headless,
                user_data_dir=self.profile_path,
                browser_args=["--start-maximized"]
            )
            # Entry point: Use a search engine referrer maturation first
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

    async def search_jobs(self, query: str, num_jobs: int = 5) -> List[Dict[str, Any]]:
        """Main search entry point (Wrapped for sync/async compatibility)."""
        try:
            # Check if we are in an event loop
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
        
        # 2. Extract - Targeted Job Tile & Slider
        results = []
        try:
            tile_selector = 'article.job-tile[data-test="JobTile"]'
            print("DEBUG: Waiting 8s for tiles to populate...")
            await asyncio.sleep(8)
            
            tiles = await self.page.select_all(tile_selector)
            logger.info(f"Page scan complete. Tiles found: {len(tiles)}")
            print(f"DEBUG: FOUND {len(tiles)} TILES")
            
            if not tiles:
                print("DEBUG: NO TILES FOUND. Capturing state...")
                await self.page.save_screenshot("empty_results.png")
                return []

            limit = min(len(tiles), num_jobs)
            
            for i in range(limit):
                try:
                    # Re-acquire to avoid stale pointers
                    cur_tiles = await self.page.select_all(tile_selector)
                    tile = cur_tiles[i]
                    
                    logger.info(f"[{i+1}/{limit}] Clicking tile...")
                    print(f"DEBUG: CLICKING TILE {i+1}...")
                    
                    # Ensure element is visible
                    await tile.scroll_into_view()
                    await tile.click()
                    
                    # Human wait for hydration
                    print("DEBUG: Waiting 1.5s for DOM hydration...")
                    await asyncio.sleep(1.5)
                    
                    # Correctly capture the whole page content for debugging and extraction
                    page_html_full = await self.page.get_content()
                    print(f"DEBUG: FULL PAGE HTML CAPTURED ({len(page_html_full)} chars)")
                    
                    if len(page_html_full) > 1000:
                        logger.info(f"Sending full page HTML to Gemini for parsing...")
                        print(f"DEBUG: SENDING FULL PAGE TO GEMINI")
                        
                        data = self.extractor.extract_from_html(page_html_full)
                        if data:
                            print(f"DEBUG: EXTRACTION SUCCESSFUL for Tile {i+1}")
                            results.append(data)
                        else:
                            print(f"DEBUG: GEMINI RETURNED NULL for Tile {i+1}")
                        
                        # Close panel via ESC (to be safe for the next tile click)
                        await self.page.send_keys("\uE00C")
                        await asyncio.sleep(1.5)
                    else:
                        print(f"DEBUG: PAGE HTML TOO SMALL for Tile {i+1}")
                        
                except Exception as e:
                    logger.error(f"Tile {i+1} interaction error: {e}")
                    print(f"DEBUG ERROR: Tile {i+1} -> {e}")
                    
        except Exception as e:
            logger.error(f"Extraction block failure: {e}")
            print(f"DEBUG CRITICAL EXTRACTION FAILURE: {e}")

        logger.info(f"Collected total of {len(results)} jobs.")
        print(f"DEBUG: RETURNING {len(results)} JOBS TO API")
        return results

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
