import asyncio
import logging
import random
import os
import nodriver as uc
from datetime import datetime
from nodriver import cdp

logger = logging.getLogger(__name__)

class UpworkSessionManager:
    """
    Handles Upwork login and session verification logic.
    Decoupled from scraping logic.
    """
    LOGIN_URL = "https://www.upwork.com/ab/account-security/login"
    
    def __init__(self, browser_manager):
        self.browser_manager = browser_manager
        self._login_lock = asyncio.Lock()

    async def verify_or_login(self, tab: uc.Tab) -> bool:
        """Ensures an active session exists on the provided tab."""
        async with self._login_lock:
            # 1. Passive check (Cookies)
            if await self._has_session_cookies(tab):
                logger.debug("Active session cookies detected.")
                return True
            
            # 2. Active check (Dashboard)
            if await self._verify_via_ui(tab):
                return True
            
            # 3. Perform login if all else fails
            logger.info("No valid session found. Initiating login flow...")
            return await self.login(tab)

    async def _has_session_cookies(self, tab: uc.Tab) -> bool:
        """Queries CDP for existence of session tokens."""
        try:
            cookies = await tab.send(cdp.network.get_cookies())
            return any(c.name in ["oauth_token", "login_remember_me"] for c in cookies)
        except Exception:
            return False

    async def _verify_via_ui(self, tab: uc.Tab) -> bool:
        """Navigates and checks for authenticated UI elements."""
        try:
            await tab.get("https://www.upwork.com/nx/find-work/")
            await self.wait_for_cloudflare(tab)
            await asyncio.sleep(3) # Hydration wait
            
            current_url = tab.url
            if "login" in current_url:
                return False
                
            indicators = [
                'button[data-test="nav-user-menu"]',
                '.air3-avatar',
                'a[href="/nx/find-work/"]'
            ]
            
            for selector in indicators:
                try:
                    if await tab.select(selector, timeout=3):
                        logger.info(f"Verified session via indicator: {selector}")
                        return True
                except: continue
                
            return any(path in current_url for path in ["nx/find-work", "nx/search/jobs", "freelancers/settings"])
        except Exception as e:
            logger.warning(f"UI verification failed: {e}")
            return False

    async def login(self, tab: uc.Tab) -> bool:
        """Executes the full login flow with human-like interaction."""
        username = os.getenv("UPWORK_USERNAME")
        password = os.getenv("UPWORK_PASSWORD")
        
        if not username or not password:
            logger.error("UPWORK_USERNAME or UPWORK_PASSWORD missing in environment.")
            return False

        try:
            await tab.get(self.LOGIN_URL)
            await self.wait_for_cloudflare(tab)
            
            # 1. Username
            user_input = await tab.select("#login_username", timeout=10)
            if not user_input: return False
            await self._human_type(user_input, username)
            
            continue_btn = await tab.select("#login_password_continue", timeout=5)
            if continue_btn: await continue_btn.click()
            
            # 2. Password
            pass_input = await tab.select("#login_password", timeout=10)
            if not pass_input: return False
            await self._human_type(pass_input, password)
            
            # 3. Remember Me (Crucial for persistence)
            try:
                remember_me = await tab.select('label[for="login_remember_me"]', timeout=3)
                if remember_me: await remember_me.click()
            except: pass
            
            # 4. Submit
            submit_btn = await tab.select("#login_control_continue", timeout=5)
            if submit_btn: await submit_btn.click()
            
            # Wait for success
            await asyncio.sleep(5) # Cookie flush wait
            return await self._verify_via_ui(tab)
            
        except Exception as e:
            logger.error(f"Login process failed: {e}")
            return False

    async def wait_for_cloudflare(self, tab: uc.Tab):
        """Helper to wait for Cloudflare challenges."""
        challenge_text = ["Verify you are human", "cf-turnstile", "Cloudflare"]
        try:
            content = await tab.evaluate("document.body.innerText")
            if any(term in content for term in challenge_text):
                logger.warning("Cloudflare detected. Please solve if required.")
                start = datetime.now()
                while (datetime.now() - start).total_seconds() < 120:
                    await asyncio.sleep(4)
                    content = await tab.evaluate("document.body.innerText")
                    if not any(term in content for term in challenge_text):
                        logger.info("Challenge cleared.")
                        break
        except: pass

    async def _human_type(self, element, text: str):
        """Type with natural delays."""
        await element.focus()
        for char in text:
            await element.send_keys(char)
            delay = 0.3 if char in "@." else random.uniform(0.05, 0.15)
            await asyncio.sleep(delay)
