import asyncio
import os
import logging
import nodriver as uc
from nodriver import cdp
from typing import Optional, List

logger = logging.getLogger(__name__)
class BrowserManager:
    """
    Instance-based Browser Manager for Nodriver.
    Handles startup, cleanup, and life-cycle of a single browser instance.
    """

    def __init__(self, headless: bool = False, session_id: Optional[str] = None):
        self.headless = headless
        # Create a unique profile path for this session to ensure isolation
        self.session_id = session_id or "default"
        self.profile_path = os.path.abspath(f"upwork_profile_{self.session_id}")
        self._browser: Optional[uc.Browser] = None
        self._lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

    async def get_browser(self) -> uc.Browser:
        """Get or initialize the browser instance."""
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.connection.send(cdp.browser.get_version())
                    return self._browser
                except:
                    logger.warning(f"Browser connection {self.session_id} lost. Re-initializing...")
                    self._browser = None
            
            self._browser = await self._start_browser()
            return self._browser

    async def _start_browser(self) -> uc.Browser:
        """Launches the browser with targeted cleanup."""
        logger.info(f"Initializing Browser instance for session {self.session_id}...")
        
        browser_args = [
            "--start-maximized",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-session-crashed-bubble",
            "--remote-allow-origins=*",
            "--disable-blink-features=AutomationControlled",
        ]

        # Only cleanup stale locks for THIS specific profile
        self._cleanup_stale_locks()

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                browser = await uc.start(
                    headless=self.headless,
                    user_data_dir=self.profile_path,
                    browser_args=browser_args,
                    sandbox=False,
                )
                logger.info(f"Browser session {self.session_id} launched successfully.")
                self._shutdown_event.clear()
                return browser
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Browser launch attempt {attempt+1} failed: {e}. Retrying cleanup...")
                    self._cleanup_stale_locks()
                    await asyncio.sleep(2)
                else:
                    logger.error(f"Critical failure launching browser {self.session_id}: {e}")
                    raise

    def _cleanup_stale_locks(self):
        """Removes the SingletonLock for this instance's profile."""
        if not os.path.exists(self.profile_path):
            return
            
        lock_file = os.path.join(self.profile_path, 'SingletonLock')
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                logger.debug(f"Removed stale SingletonLock for {self.session_id}.")
            except Exception as e:
                logger.warning(f"Could not remove lock file for {self.session_id}: {e}")

    async def close(self):
        """Shutdown the browser instance managed by this manager."""
        async with self._lock:
            if self._browser:
                try:
                    logger.info(f"Closing browser session {self.session_id} gracefully...")
                    self._shutdown_event.set()
                    if self._browser:
                        # Safely try to stop the browser
                        stop_method = getattr(self._browser, 'stop', None)
                        if stop_method:
                            try:
                                # Start the stop call
                                stop_call = stop_method()
                                # Only await if it's actually a coroutine
                                if asyncio.iscoroutine(stop_call) or hasattr(stop_call, '__await__'):
                                    await stop_call
                            except Exception as stop_err:
                                logger.debug(f"Inner stop error for {self.session_id}: {stop_err}")
                except Exception as e:
                    logger.warning(f"Error during browser shutdown for {self.session_id}: {e}")
                finally:
                    self._browser = None

    async def create_tab(self) -> uc.Tab:
        """Create a new tab in this browser."""
        browser = await self.get_browser()
        try:
            return await browser.get("about:blank")
        except Exception as e:
            logger.warning(f"Failed to create tab for {self.session_id}: {e}. Attempting restart...")
            async with self._lock:
                self._browser = None
            browser = await self.get_browser()
            return await browser.get("about:blank")
