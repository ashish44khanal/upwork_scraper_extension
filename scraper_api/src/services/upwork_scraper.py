import json
import os
import re
import math
import asyncio
import random
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from logging.handlers import RotatingFileHandler
# Nodriver: https://github.com/ultrafunkamsterdam/nodriver
# Docs: https://ultrafunkamsterdam.github.io/nodriver/
import nodriver as uc
from nodriver import cdp
from dotenv import load_dotenv

# Scraper root (scraper_api/) for .env path
_scraper_root = Path(__file__).resolve().parent.parent.parent
_load_dotenv_path = _scraper_root / ".env"
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

# Upwork login
LOGIN_URL = "https://www.upwork.com/ab/account-security/login"

class UpworkScraper:
    """
    Elite Stealth Scraper using Nodriver (CDP-based).
    Supports persistent singleton browser and tab-based concurrency.
    """
    # Shared singleton browser and locks for concurrency
    _browser = None
    _browser_lock = asyncio.Lock()
    _login_lock = asyncio.Lock()
    
    def __init__(self, headless: bool = False, page=None):
        self.headless = headless
        self.page = page
        self.browser = None
        self.extractor = GeminiExtractor()
        self.output_file = "upwork.json"
        self.profile_path = os.path.abspath(os.path.join(os.getcwd(), 'upwork_profile_nd'))
        self.login_url = LOGIN_URL
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
        """
        Singleton browser manager: ensures only one browser instance runs with the user profile.
        """
        async with UpworkScraper._browser_lock:
            # Check if browser exists and is still responsive
            is_alive = False
            if UpworkScraper._browser:
                try:
                    # Simple health check: ping the browser
                    await UpworkScraper._browser.connection.send(cdp.browser.get_version())
                    is_alive = True
                except Exception:
                    logger.warning("Singleton browser appears dead. Resetting...")
                    UpworkScraper._browser = None

            if not UpworkScraper._browser:
                logger.info("Initializing Singleton Elite Nodriver Browser...")
                browser_args = ["--start-maximized", "--no-sandbox", "--disable-setuid-sandbox"]
                
                max_retries = 2
                for attempt in range(max_retries + 1):
                    try:
                        UpworkScraper._browser = await uc.start(
                            headless=self.headless,
                            user_data_dir=self.profile_path,
                            browser_args=browser_args,
                            sandbox=False,
                        )
                        is_alive = True
                        break
                    except Exception as e:
                        if attempt < max_retries:
                            logger.warning(f"Browser launch attempt {attempt+1} failed: {e}. Cleaning and retrying...")
                            # Aggressively kill processes and remove locks
                            if os.name == 'posix':
                                os.system('pkill -f "Google Chrome" || true')
                                os.system('pkill -f "chrome" || true')
                                # CRITICAL: Remove the singleton lock file which prevents re-entry
                                lock_file = os.path.join(self.profile_path, 'SingletonLock')
                                if os.path.exists(lock_file):
                                    try: os.remove(lock_file)
                                    except: pass
                            await asyncio.sleep(2)
                        else:
                            logger.error(f"Failed to launch singleton browser after {max_retries+1} attempts.")
                            raise e
            
            self.browser = UpworkScraper._browser
            
            # If this task instance doesn't have a page or it's closed, use a new tab
            if not self.page:
                logger.debug(f"[Session: {self.session_id}] Creating new tab for task")
                self.page = await self.browser.get("about:blank", new_tab=True)
                # Small wait for tab stability
                await asyncio.sleep(1)

    async def scrape_and_save_raw(self, url: str, filename_base: str, storage_dir: str) -> Dict[str, str]:
        """
        Elite navigation and capture: Saves HTML and Screenshot for downstream extraction.
        """
        await self._init_browser()
        await self._ensure_session()
        
        logger.info(f"Navigating to for raw capture: {url}")
        await self.page.get(url)
        await self._wait_for_cloudflare()
        
        # Wait for hydration/rendering
        await asyncio.sleep(random.uniform(3.0, 5.0))
        
        os.makedirs(storage_dir, exist_ok=True)
        
        html_path = os.path.abspath(os.path.join(storage_dir, f"{filename_base}.html"))
        
        # 1. Capture and Save HTML
        content = await self.page.get_content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        logger.info(f"✅ Raw capture complete for {filename_base}")
        logger.info(f"HTML: {html_path}")
        
        return {
            "html_path": html_path,
            "url": url,
            "timestamp": datetime.now().isoformat()
        }

    async def _human_delay(self, min_sec: float = 0.3, max_sec: float = 0.8):
        """Random delay to mimic human; reduces antibot detection."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def _human_type(self, element, text: str):
        """Type at normal human speed (~40–60 WPM): ~150–280ms per key, longer pause after @ and ."""
        await element.focus()
        await self._human_delay(0.2, 0.45)
        for i, char in enumerate(text):
            await element.send_keys(char)
            # Human-like delay: 150–280ms typical; 250–450ms after @ or . (natural hesitation)
            if char in "@.":
                await asyncio.sleep(random.uniform(0.25, 0.5))
            else:
                await asyncio.sleep(random.uniform(0.12, 0.28))

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
            try:
                await un.clear_input()
            except Exception:
                pass
            await self._human_delay(0.15, 0.35)
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
            try:
                await pw.clear_input()
            except Exception:
                pass
            await self._human_delay(0.15, 0.35)
            await self._human_type(pw, password)
            await self._human_delay(0.4, 0.9)

            # 3.5 Remember Me checkbox
            try:
                # Upwork usually has 'Remember me' on the password step
                remember_sel = ['#login_rememberme', 'input[name="login[remember_me]"]', 'label[for="login_rememberme"]']
                for rsel in remember_sel:
                    try:
                        rem = await self.page.select(rsel, timeout=1)
                        if rem:
                            await rem.click()
                            logger.info("Login: Selected 'Remember me'")
                            break
                    except: continue
            except: pass

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
            # Mandatory wait to ensure cookies are flushed to disk
            logger.info("✨ Login successful. Syncing session to disk...")
            await asyncio.sleep(5)
            
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
        return False

    async def verify_session(self) -> bool:
        """
        Elite Multi-Layer Session Verification.
        Strategy:
        1. Query CDP for active session cookies (oauth/token).
        2. Navigate to dashboard and check for private UI components.
        3. Logic fallbacks for different account states (Freelancer/Client).
        """
        await self._init_browser()
        
        # Layer 1: Passive Cookie Check (No navigation required)
        try:
            cookies = await self.page.send(cdp.network.get_cookies())
            authorized = any(c.name in ["oauth_token", "login_remember_me"] for c in cookies)
            if authorized:
                logger.debug("� CDP: Found cryptographic session tokens in local storage.")
        except Exception:
            authorized = False

        # Layer 2: Active Navigation Check
        try:
            logger.info("🔍 Conducting deep-layer session verification...")
            await self.page.get("https://www.upwork.com/nx/find-work/")
            await self._wait_for_cloudflare()
            await asyncio.sleep(4) # Allow JS hydration
            
            current_url = self.page.url
            
            # Absolute failure case: Redirected to login
            if "upwork.com/ab/account-security/login" in current_url:
                logger.info("� Secure session expired or missing. Initializing recovery flow...")
                success = await self._do_login()
                if success:
                    logger.info("✨ Recovery successful. New session context synced to profile.")
                    await asyncio.sleep(5)
                    return True
                return False

            # Success indicators (Freelancer or Client variants)
            logged_in_indicators = [
                'button[data-test="nav-user-menu"]',      # Avatar Menu
                '.air3-avatar',                           # User Avatar
                'a[href="/nx/find-work/"]',              # Find Work link
                '.up-n-nav-job-search'                    # Search input
            ]
            
            for selector in logged_in_indicators:
                try:
                    el = await self.page.select(selector, timeout=3)
                    if el:
                        logger.info(f"✨ Session verified via component: {selector}")
                        return True
                except: continue

            # Fallback URL logic
            if any(path in current_url for path in ["nx/find-work", "nx/search/jobs", "freelancers/settings"]):
                logger.info("✨ Professional session confirmed via target URL presence.")
                return True
                
            logger.warning(f"⚠️ Session identity ambiguous (URL: {current_url}). Attempting deep re-login...")
            return False
            
        except Exception as e:
            logger.warning(f"Session verification interrupted: {e}")
            return False

    async def _ensure_session(self) -> None:
        """Log in with UPWORK_USERNAME / UPWORK_PASSWORD from .env."""
        ok = await self._do_login()
        if not ok:
            raise ScraperException("Login failed; check credentials or solve captcha")

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

    def _build_next_page_url(self, base_url: str, page_num: int) -> str:
        """Add or replace page=N in product_url for pagination."""
        parsed = urlparse(base_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs["page"] = [str(page_num)]
        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    async def _get_pagination_from_dom(self) -> Optional[Dict[str, Any]]:
        """
        Parse pagination from DOM: ul[data-test="pagination"], li[data-test="pagination-mobile"] "X of Y".
        Returns {"total_pages": int, "current_page": int, "has_next": bool} or None.
        """
        try:
            mobile_el = await self.page.select('li[data-test="pagination-mobile"]', timeout=3)
            if not mobile_el:
                return {"total_pages": 1, "current_page": 1, "has_next": False}
            text = getattr(mobile_el, "text_all", None) or getattr(mobile_el, "text", "") or ""
            text = str(text).strip()
            match = re.search(r"(\d+)\s+of\s+(\d+)", text.strip())
            if not match:
                return {"total_pages": 1, "current_page": 1, "has_next": False}
            current_page = int(match.group(1))
            total_pages = int(match.group(2))
            next_el = await self.page.select('a[data-test="next-page"]:not(.is-disabled)', timeout=1)
            has_next = bool(next_el) and total_pages > 1 and current_page < total_pages
            return {"total_pages": total_pages, "current_page": current_page, "has_next": has_next}
        except Exception as e:
            logger.debug(f"DOM pagination parse failed: {e}")
        return {"total_pages": 1, "current_page": 1, "has_next": False}

    def _parse_paging_from_response_body(self, body_str: str) -> Optional[Dict[str, Any]]:
        """
        Parse data.data.search.universalSearchNuxt.userJobSearchV1.paging from GraphQL response.
        Returns {"total_pages": int, "current_page": int} or None.
        """
        try:
            data = json.loads(body_str)
            paging = (data.get("data") or {}).get("search") or {}
            paging = (paging.get("universalSearchNuxt") or {}).get("userJobSearchV1") or {}
            paging = paging.get("paging")
            if not paging:
                return None
            total = int(paging.get("total") or 0)
            offset = int(paging.get("offset") or 0)
            count = int(paging.get("count") or 10)
            if count <= 0:
                return None
            total_pages = math.ceil(total / count) if total else 1
            current_page = (offset // count) + 1 if offset is not None else 1
            return {"total_pages": total_pages, "current_page": current_page}
        except Exception as e:
            logger.debug(f"API paging parse failed: {e}")
        return None

    async def _get_total_pages_after_navigate(self, graphql_request_id_queue: asyncio.Queue) -> Optional[Dict[str, Any]]:
        """
        After navigate: wait for userJobSearch response request_id from queue, get body, parse paging.
        Returns {"total_pages": int, "current_page": int} or None (then use DOM fallback).
        """
        try:
            request_id = await asyncio.wait_for(graphql_request_id_queue.get(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.debug("No userJobSearch response within 15s; will use DOM pagination")
            return None
        try:
            body, base64_encoded = await self.page.send(cdp.network.get_response_body(request_id), True)
            if base64_encoded:
                import base64
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            return self._parse_paging_from_response_body(body)
        except Exception as e:
            logger.debug(f"getResponseBody or parse failed: {e}")
        return None

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


    async def scrape_jobs(self, product_url: str, no_of_pages_to_scrape: Optional[int] = None, on_card_data_async=None) -> List[Dict[str, Any]]:
        """Scrape jobs from the given product URL across one or more pages. no_of_pages_to_scrape: None = all pages; 1,2,3... = up to that many pages."""
        try:
            try:
                loop = asyncio.get_running_loop()
                return await self._scrape_jobs_from_url(product_url, no_of_pages_to_scrape, on_card_data_async)
            except RuntimeError:
                return asyncio.run(self._scrape_jobs_from_url(product_url, no_of_pages_to_scrape, on_card_data_async))
        except Exception as e:
            import traceback
            logger.error(f"Scrape failed: {e}")
            traceback.print_exc()
            return []

    async def search_jobs(self, query: str, no_of_pages_to_scrape: Optional[int] = None) -> List[Dict[str, Any]]:
        """Backward-compat: build search URL from query and scrape."""
        search_url = f"https://www.upwork.com/nx/search/jobs/?q={query.replace(' ', '%20')}"
        return await self.scrape_jobs(search_url, no_of_pages_to_scrape=no_of_pages_to_scrape)

    async def _scrape_jobs_from_url(self, product_url: str, no_of_pages_to_scrape: Optional[int] = None, on_card_data_async=None) -> List[Dict[str, Any]]:
        await self._init_browser()
        
        # Premium Session Logic: Check if we need to login
        # We check specific URL first
        await self.page.get(product_url)
        await self._wait_for_cloudflare()
        
        if "upwork.com/ab/account-security/login" in self.page.url:
            logger.info("🔒 Navigation intercepted by login wall. Recovering session...")
            async with UpworkScraper._login_lock:
                # Double check inside lock
                if "upwork.com/ab/account-security/login" in self.page.url:
                    success = await self._do_login()
                    if not success:
                        raise ScraperException("Unable to breach the login wall. Check credentials/CAPTCHA.")
                    # Re-navigate to the target
                    await self.page.get(product_url)
                    await self._wait_for_cloudflare()
        else:
            logger.debug("🚀 Session active. Rocketing to target URL...")

        # Queue for GraphQL userJobSearch response request_id (handler runs in same tab)
        graphql_queue: asyncio.Queue = asyncio.Queue()

        def on_response_received(event):
            try:
                if "userJobSearch" in (getattr(event.response, "url", None) or ""):
                    graphql_queue.put_nowait(event.request_id)
            except Exception:
                pass

        self.page.add_handler(cdp.network.ResponseReceived, on_response_received)
        try:
            await self.page.send(cdp.network.enable(), True)
        except Exception as e:
            logger.debug(f"Network.enable failed: {e}")
        logger.info(f"Navigating to product URL: {product_url}")
        await self.page.get(product_url)
        await self._wait_for_cloudflare()

        # Get total pages: try GraphQL response first, then DOM fallback
        paging = await self._get_total_pages_after_navigate(graphql_queue)
        self.page.remove_handler(cdp.network.ResponseReceived, on_response_received)
        try:
            await self.page.send(cdp.network.disable(), True)
        except Exception:
            pass
        if paging is None:
            paging = await self._get_pagination_from_dom()
        total_pages = paging.get("total_pages", 1) or 1
        if no_of_pages_to_scrape is not None and no_of_pages_to_scrape <= 0:
            return []
        pages_to_scrape = total_pages if no_of_pages_to_scrape is None else min(no_of_pages_to_scrape, total_pages)
        logger.info(f"[Session: {self.session_id}] Scraping {pages_to_scrape} page(s) (total available: {total_pages})")

        temp_html_list = []
        tile_selector = 'article.job-tile[data-test="JobTile"]'
        try:
            for page_num in range(1, pages_to_scrape + 1):
                if page_num > 1:
                    next_url = self._build_next_page_url(product_url, page_num)
                    logger.info(f"[Session: {self.session_id}] Navigating to page {page_num}: {next_url[:80]}...")
                    await self.page.get(next_url)
                    await self._wait_for_cloudflare()
                    await asyncio.sleep(random.uniform(1.0, 2.0))

                logger.info(f"[Session: {self.session_id}] Waiting for tiles on page {page_num}...")
                tiles = await self._wait_for_tiles(tile_selector, max_wait=10.0)
                if not tiles:
                    logger.warning(f"[Session: {self.session_id}] No tiles on page {page_num}")
                    if page_num == 1:
                        await self.page.save_screenshot("no_tiles.png")
                    continue

                limit = len(tiles)
                logger.info(f"[Session: {self.session_id}] Processing {limit} job cards on page {page_num}/{pages_to_scrape}")

                card_base = len(temp_html_list)
                for i in range(limit):
                    card_start_time = time.time()
                    try:
                        # Re-acquire tiles
                        cur_tiles = await self.page.select_all(tile_selector)
                        if i >= len(cur_tiles): break
                        tile = cur_tiles[i]
                        card_index = card_base + i + 1
                        logger.info(f"[Session: {self.session_id}] Processing card {card_index} (page {page_num}: {i+1}/{limit})")
                        
                        await tile.scroll_into_view()
                        await tile.click()
                        
                        # OPTIMIZATION: Wait for slider to appear (was fixed 2.5-4s)
                        slider_appeared = await self._wait_for_element('.air3-slider-content', timeout=5.0)
                        if not slider_appeared:
                            logger.warning(f"[Session: {self.session_id}] Slider didn't appear for card {card_index}")
                            continue
                        
                        # Small jitter for human-like behavior
                        await asyncio.sleep(random.uniform(0.3, 0.7))
                        
                        # Detect frame/context
                        context = await self._find_job_frame()
                        
                        # 1. Capture WHOLE PAGE HTML
                        full_page_dom = await self._extract_job_modal(context=context)

                        if full_page_dom:
                            # Clean and Filter HTML on the SERVER side
                            logger.debug(f"[Session: {self.session_id}] Filtering HTML for card {card_index}")
                            filtered_html = self._clean_html_server_side(full_page_dom)
                            
                            if on_card_data_async:
                                await on_card_data_async(
                                    card_index=card_index,
                                    page_num=page_num,
                                    raw_html=full_page_dom,
                                    filtered_html=filtered_html,
                                    url=self.page.url
                                )
                            
                            if filtered_html:
                                temp_html_list.append({f"card_{card_index}": filtered_html})
                                logger.info(f"[Session: {self.session_id}] ✅ Card {card_index} processed")
                            else:
                                logger.warning(f"[Session: {self.session_id}] Server-side filter failed for card {card_index}")
                        else:
                            logger.warning(f"[Session: {self.session_id}] Failed to capture DOM for card {card_index}")

                        # Close the panel
                        logger.debug(f"[Session: {self.session_id}] Closing modal for card {card_index}")
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
                        logger.debug(f"[Session: {self.session_id}] Card {card_index} processed in {card_time:.2f}s")
                            
                    except Exception as e:
                        logger.error(f"Card {card_base + i + 1} interaction error: {e}")
                        print(f"[CONSOLE] ERROR ON CARD {card_base + i + 1}: {e}")
                        try: await self.page.send_keys("\uE00C")
                        except: pass
                    
        except Exception as e:
            logger.error(f"Global extraction failure: {e}")
            print(f"[CONSOLE] CRITICAL FAILURE: {e}")

        return []
        
        
        
        
        
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
        
        print("="*50 + "\n")
        
        return response_content

    async def close(self):
        """
        Cleanup the specific tab/page. The singleton browser remains open.
        """
        try:
            if self.page:
                logger.info(f"[Session: {self.session_id}] Closing tab...")
                await self.page.close()
        except Exception as e:
            logger.debug(f"Error closing tab: {e}")
        finally:
            self.page = None

    @classmethod
    async def shutdown(cls):
        """
        Final shutdown of the singleton browser instance.
        """
        async with cls._browser_lock:
            if cls._browser:
                logger.info("Shutting down Singleton Browser...")
                try:
                    await cls._browser.stop()
                except: pass
                cls._browser = None

if __name__ == "__main__":
    scraper = UpworkScraper(headless=False)
    try:
        if os.getenv("GEMINI_API_KEY"):
            product_url = "https://www.upwork.com/nx/search/jobs/?q=React%20Developer"
            asyncio.run(scraper.scrape_jobs(product_url, no_of_pages_to_scrape=1))
        else:
            print("Set GEMINI_API_KEY")
    finally:
        asyncio.run(scraper.close())

