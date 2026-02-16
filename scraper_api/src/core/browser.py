import asyncio
import os
import logging
import nodriver as uc
from nodriver import cdp
from typing import Optional, List

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Singleton Browser Manager for Nodriver.
    Handles startup, cleanup, and life-cycle of a single persistent browser instance.
    """
    _instance: Optional['BrowserManager'] = None
    _browser: Optional[uc.Browser] = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(BrowserManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, headless: bool = False, profile_path: Optional[str] = None):
        # We only init once due to Singleton pattern
        if not hasattr(self, 'initialized'):
            self.headless = headless
            self.profile_path = profile_path or os.path.abspath("upwork_profile_nd")
            self._shutdown_event = asyncio.Event()
            self.initialized = True

    async def get_browser(self) -> uc.Browser:
        """Get or initialize the singleton browser instance."""
        async with self._lock:
            if self._browser:
                try:
                    # Quick check if connection is active
                    await self._browser.connection.send(cdp.browser.get_version())
                    return self._browser
                except:
                    logger.warning("Browser connection lost. Re-initializing...")
                    self._browser = None
            
            self._browser = await self._start_browser()
            return self._browser

    def _is_alive(self) -> bool:
        """Check if browser process is still responding."""
        try:
            # Check if underlying process exists and connection is active
            return self._browser and self._browser.process and self._browser.connection
        except:
            return False

    async def _start_browser(self) -> uc.Browser:
        """Launches the browser with proactive cleanup and arguments."""
        logger.info("Initializing Singleton Nodriver Browser...")
        
        browser_args = [
            "--start-maximized",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-session-crashed-bubble",
            "--remote-allow-origins=*",
            "--disable-blink-features=AutomationControlled", # Stealth
        ]

        # PROACTIVE CLEANUP: Kill any hanging instances BEFORE the first attempt
        self._aggressive_cleanup()
        await asyncio.sleep(1.5) # Allow OS to release port/profile resources

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                # Extra lock check right before launch
                self._cleanup_stale_locks()
                
                browser = await uc.start(
                    headless=self.headless,
                    user_data_dir=self.profile_path,
                    browser_args=browser_args,
                    sandbox=False,
                )
                logger.info("Browser launched successfully.")
                self._shutdown_event.clear()
                return browser
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Browser launch attempt {attempt+1} failed: {e}. Retrying cleanup...")
                    self._aggressive_cleanup()
                    await asyncio.sleep(2)
                else:
                    logger.error(f"Critical failure launching browser: {e}")
                    raise

    def _cleanup_stale_locks(self):
        """Removes Chrome's SingletonLock if it exists."""
        lock_file = os.path.join(self.profile_path, 'SingletonLock')
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                logger.debug("Removed stale SingletonLock.")
            except Exception as e:
                logger.warning(f"Could not remove lock file: {e}")

    def _aggressive_cleanup(self):
        """Kills zombie chrome processes using pkill -9 for reliability."""
        logger.info("Executing aggressive process cleanup...")
        if os.name == 'posix':
            # Force kill all Chrome related processes
            os.system('pkill -9 -f "Google Chrome" || true')
            os.system('pkill -9 -f "chrome" || true')
            os.system('pkill -9 -f "nodriver" || true')
        
        self._cleanup_stale_locks()

    async def close_all(self):
        """Shutdown the browser and all tabs gracefully."""
        async with self._lock:
            if self._browser:
                try:
                    logger.info("Closing browser gracefully...")
                    self._shutdown_event.set()
                    if self._browser.connection:
                        await self._browser.stop()
                    else:
                        if self._browser.process:
                            self._browser.process.kill()
                except Exception as e:
                    logger.warning(f"Error during browser shutdown: {e}")
                    self._aggressive_cleanup()
                finally:
                    self._browser = None
                    logger.info("Singleton Browser shut down.")

    async def create_tab(self) -> uc.Tab:
        """Create a new tab in the singleton browser."""
        browser = await self.get_browser()
        try:
            return await browser.get("about:blank")
        except Exception as e:
            logger.warning(f"Failed to create tab: {e}. Attempting browser restart...")
            async with self._lock:
                self._browser = None
            browser = await self.get_browser()
            return await browser.get("about:blank")
