import json
import os
import asyncio
import random
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from logging.handlers import RotatingFileHandler
# Nodriver: https://github.com/ultrafunkamsterdam/nodriver
# Docs: https://ultrafunkamsterdam.github.io/nodriver/
import nodriver as uc
from dotenv import load_dotenv

# Load .env from project root (scraper_api/.env) so UPWORK_* and GEMINI_* are available
_load_dotenv_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_load_dotenv_path)
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

# Upwork login and session persistence
LOGIN_URL = "https://www.upwork.com/ab/account-security/login"
PROFILE_URL = "https://www.upwork.com/ab/account-security/"

class UpworkScraper:
    """
    Elite Stealth Scraper using Nodriver (CDP-based).
    Uses persistent session (cookies.json); logs in only when needed.
    """
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.extractor = GeminiExtractor()
        self.browser = None
        self.page = None
        self.output_file = "upwork.json"
        self.profile_path = os.path.join(os.getcwd(), 'upwork_profile_nd')
        self.cookies_path = os.path.join(os.getcwd(), os.getenv("UPWORK_COOKIES_PATH", "cookies.json"))
        self.login_url = LOGIN_URL
        self.profile_url = os.getenv("UPWORK_PROFILE_URL", PROFILE_URL)
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
            # sandbox=False adds --no-sandbox so Chrome can connect (root / restricted envs).
            # Nodriver param is "sandbox" (True=default); we pass sandbox=False to disable.
            use_sandbox = os.getenv("NODRIVER_SANDBOX", "").lower() in ("1", "true", "yes")
            if not use_sandbox and getattr(os, "geteuid", lambda: -1)() == 0:
                logger.info("Running as root: disabling sandbox")
            self.browser = await uc.start(
                headless=self.headless,
                user_data_dir=self.profile_path,
                browser_args=["--start-maximized"],
                sandbox=use_sandbox,  # False => --no-sandbox (fixes "Failed to connect to browser")
            )
            # Entry point maturation
            self.page = await self.browser.get("https://www.google.com/search?q=upwork+jobs")
            await asyncio.sleep(3)

    def _get_cdp_connection(self):
        """Get CDP connection from page or browser for cookie get/set."""
        conn = getattr(self.page, "connection", None) if self.page else None
        if conn is None and self.browser:
            conn = getattr(self.browser, "connection", None)
        return conn

    async def _get_cookies_via_cdp(self) -> Optional[List[Dict[str, Any]]]:
        """Get cookies for Upwork domain via CDP. Returns None if CDP unavailable."""
        try:
            conn = self._get_cdp_connection()
            if conn is None:
                return None
            # CDP Network.getCookies
            result = await conn.send("Network.getCookies", {"urls": ["https://www.upwork.com"]})
            if result and isinstance(result, dict) and "cookies" in result:
                logger.info("Session: got cookies via CDP")
                return result["cookies"]
        except Exception as e:
            logger.debug(f"CDP getCookies failed: {e}")
        return None

    async def _set_cookies_via_cdp(self, cookies: List[Dict[str, Any]]) -> bool:
        """Set cookies via CDP. Must be on Upwork domain first. Returns True if applied."""
        if not cookies:
            return True
        try:
            conn = self._get_cdp_connection()
            if conn is None:
                return False
            for c in cookies:
                params = {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain", ".upwork.com"),
                    "path": c.get("path", "/"),
                }
                if c.get("secure"):
                    params["secure"] = True
                if c.get("httpOnly"):
                    params["httpOnly"] = True
                if c.get("expires") and c["expires"] != -1:
                    params["expires"] = c["expires"]
                await conn.send("Network.setCookie", params)
            logger.info("Session: applied cookies via CDP")
            return True
        except Exception as e:
            logger.debug(f"CDP setCookie failed: {e}")
        return False

    def _load_cookies(self, path: str) -> Optional[List[Dict[str, Any]]]:
        """Read cookies from JSON file. Do not log cookie values."""
        try:
            if not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                logger.info("Session loaded from file")
                return data
            return None
        except Exception as e:
            logger.warning(f"Session file load failed: {e}")
        return None

    async def _save_cookies(self, path: str) -> None:
        """Save cookies to JSON file with owner-only permissions. Do not log cookie values."""
        cookies = await self._get_cookies_via_cdp()
        if not cookies:
            logger.debug("Session: no cookies to save (CDP may be unavailable)")
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            logger.info("Session saved")
        except Exception as e:
            logger.warning(f"Session file save failed: {e}")

    async def _validate_session(self) -> bool:
        """Open Profile URL and check if logged in (no login form)."""
        try:
            await self.page.get(self.profile_url)
            await asyncio.sleep(2)
            await self._wait_for_cloudflare()
            # Logged in if login form is absent
            login_input = await self._select_login_username(timeout=3)
            if login_input:
                logger.info("Session invalid: login form present")
                return False
            logger.info("Session valid")
            return True
        except Exception as e:
            logger.warning(f"Session validation failed: {e}")
        return False

    async def _human_delay(self, min_sec: float = 0.3, max_sec: float = 0.8):
        """Random delay to mimic human; reduces antibot detection."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def _human_type(self, element, text: str):
        """Type into element with human-like pacing (nodriver Element has send_keys only)."""
        await element.focus()
        await self._human_delay(0.15, 0.35)
        # Send in small chunks with micro-delays to avoid instant paste detection
        chunk_size = random.randint(2, 5)
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            await element.send_keys(chunk)
            await asyncio.sleep(random.uniform(0.05, 0.15))

    async def _select_login_username(self, timeout: float = 10):
        """Try multiple selectors for Upwork username field; returns first found or None."""
        for sel in ("#login_username", "input[name='login[username]']", "input[type='email']", "input#login_username"):
            try:
                el = await self.page.select(sel, timeout=timeout if sel == "#login_username" else 2)
                if el:
                    logger.debug(f"Login: found username field with selector '{sel}'")
                    return el
            except Exception:
                continue
        return None

    async def _select_login_password(self, timeout: float = 10):
        """Try multiple selectors for Upwork password field."""
        for sel in ("#login_password", "input[name='login[password]']", "input[type='password']", "input#login_password"):
            try:
                el = await self.page.select(sel, timeout=timeout if sel == "#login_password" else 2)
                if el:
                    logger.debug(f"Login: found password field with selector '{sel}'")
                    return el
            except Exception:
                continue
        return None

    async def _select_continue_after_username(self, timeout: float = 8):
        """Continue button after entering username."""
        for sel in ("#login_password_continue", "button[type='submit']", "button[data-test='next']", "#login_password_continue"):
            try:
                el = await self.page.select(sel, timeout=timeout if sel == "#login_password_continue" else 2)
                if el:
                    logger.debug(f"Login: found continue (username) with '{sel}'")
                    return el
            except Exception:
                continue
        return None

    async def _select_login_submit(self, timeout: float = 8):
        """Final Log in button."""
        for sel in ("#login_control_continue", "button[type='submit']", "button[data-test='submit']", "#login_control_continue"):
            try:
                el = await self.page.select(sel, timeout=timeout if sel == "#login_control_continue" else 2)
                if el:
                    logger.debug(f"Login: found submit button with '{sel}'")
                    return el
            except Exception:
                continue
        return None

    async def _do_login(self) -> bool:
        """Perform Upwork login using env UPWORK_USERNAME and UPWORK_PASSWORD.
        Uses send_keys only (no .input()); human-like delays; multiple selector fallbacks.
        """
        # Read and strip credentials; .env is loaded at module level
        username = (os.getenv("UPWORK_USERNAME") or "").strip()
        password = (os.getenv("UPWORK_PASSWORD") or "").strip()
        if not username or not password:
            raise ValueError("UPWORK_USERNAME and UPWORK_PASSWORD are required for login (check .env)")
        logger.info("Login: credentials loaded (username set)")
        try:
            await self.page.get(self.login_url)
            await asyncio.sleep(random.uniform(2.0, 3.5))  # Human: wait for page
            await self._wait_for_cloudflare()
            await self._human_delay(0.5, 1.0)

            # 1. Username field — use send_keys only (nodriver Element has no .input())
            un = await self._select_login_username(timeout=12)
            if not un:
                logger.warning("Login: username input not found (tried multiple selectors)")
                return False
            try:
                await un.scroll_into_view()
            except Exception:
                pass
            await self._human_delay(0.2, 0.5)
            await self._human_type(un, username)
            await self._human_delay(0.4, 0.9)

            # 2. Continue (after username)
            cont = await self._select_continue_after_username(timeout=8)
            if not cont:
                logger.warning("Login: Continue button not found")
                return False
            try:
                await cont.scroll_into_view()
            except Exception:
                pass
            await self._human_delay(0.2, 0.5)
            await cont.click()
            await asyncio.sleep(random.uniform(2.0, 3.0))  # Wait for password step
            await self._human_delay(0.3, 0.7)

            # 3. Password field
            pw = await self._select_login_password(timeout=12)
            if not pw:
                logger.warning("Login: password input not found")
                return False
            try:
                await pw.scroll_into_view()
            except Exception:
                pass
            await self._human_delay(0.2, 0.5)
            await self._human_type(pw, password)
            await self._human_delay(0.4, 0.9)

            # 4. Log in button
            login_btn = await self._select_login_submit(timeout=8)
            if not login_btn:
                logger.warning("Login: Log in button not found")
                return False
            try:
                await login_btn.scroll_into_view()
            except Exception:
                pass
            await self._human_delay(0.2, 0.6)
            await login_btn.click()
            await asyncio.sleep(random.uniform(3.0, 4.5))
            await self._wait_for_cloudflare()

            # Check we left login page
            login_input_after = await self._select_login_username(timeout=2)
            if login_input_after:
                logger.warning("Login: still on login page (wrong credentials or captcha)")
                return False
            logger.info("Login succeeded")
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
        return False

    async def _ensure_session(self) -> None:
        """Ensure we have a valid logged-in session: load cookies and validate, or login and save."""
        # 1. Try load cookies and validate
        if os.path.exists(self.cookies_path):
            cookies = self._load_cookies(self.cookies_path)
            if cookies:
                await self.page.get("https://www.upwork.com/")
                await asyncio.sleep(1)
                applied = await self._set_cookies_via_cdp(cookies)
                if applied:
                    if await self._validate_session():
                        return
        # 2. No session or invalid: login
        ok = await self._do_login()
        if not ok:
            raise ScraperException("Login failed; check credentials or solve captcha")
        await self._save_cookies(self.cookies_path)

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

    async def scrape_jobs(self, product_url: str, num_jobs: int = 5) -> List[Dict[str, Any]]:
        """Scrape jobs from the given product URL. Uses persistent session; logs in when needed."""
        try:
            try:
                loop = asyncio.get_running_loop()
                return await self._scrape_jobs_from_url(product_url, num_jobs)
            except RuntimeError:
                return asyncio.run(self._scrape_jobs_from_url(product_url, num_jobs))
        except Exception as e:
            import traceback
            logger.error(f"Scrape failed: {e}")
            traceback.print_exc()
            return []

    async def search_jobs(self, query: str, num_jobs: int = 5) -> List[Dict[str, Any]]:
        """Backward-compat: build search URL from query and scrape."""
        search_url = f"https://www.upwork.com/nx/search/jobs/?q={query.replace(' ', '%20')}"
        return await self.scrape_jobs(search_url, num_jobs=num_jobs)

    async def _scrape_jobs_from_url(self, product_url: str, num_jobs: int = 5) -> List[Dict[str, Any]]:
        await self._init_browser()
        await self._ensure_session()
        logger.info(f"Navigating to product URL: {product_url}")
        await self.page.get(product_url)
        await self._wait_for_cloudflare()
        # Extract - All Job Tiles & Page DOM
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
            product_url = "https://www.upwork.com/nx/search/jobs/?q=React%20Developer"
            asyncio.run(scraper.scrape_jobs(product_url, num_jobs=1))
        else:
            print("Set GEMINI_API_KEY")
    finally:
        asyncio.run(scraper.close())

