import asyncio
import os
import logging
import sys
from typing import Optional
import nodriver as uc
from nodriver import cdp

logger = logging.getLogger(__name__)

# Singleton state
_browser_instance: Optional[uc.Browser] = None
_browser_lock = asyncio.Lock()

# Detection of OS
IS_MAC = sys.platform == "darwin"

def find_browser_binary() -> Optional[str]:
    """
    Search for Brave or Chrome binaries.
    """
    if IS_MAC:
        return "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    
    # Common Linux paths for Brave and Chrome
    search_paths = [
        "/usr/bin/brave-browser",
        "/usr/bin/brave-browser-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            return path
            
    # Fallback to 'which' command
    import shutil
    for cmd in ["brave-browser", "brave-browser-stable", "google-chrome", "google-chrome-stable", "chromium"]:
        found = shutil.which(cmd)
        if found:
            return found
            
    return None

BROWSER_USER_PROFILE = "./brave_data"
BRAVE_EXECUTABLE_PATH = os.getenv("CHROME_PATH") or find_browser_binary()

async def review_browser() -> uc.Browser:
    """
    Helper function to manage a singleton browser instance.
    """
    global _browser_instance
    async with _browser_lock:
        if _browser_instance is None:
            from src.core.config import settings
            
            try:
                if settings.CHROME_REMOTE_HOST and settings.CHROME_REMOTE_PORT:
                    logger.info(f"🔗 Connecting to remote browser at {settings.CHROME_REMOTE_HOST}:{settings.CHROME_REMOTE_PORT}...")
                    _browser_instance = await asyncio.wait_for(
                        uc.start(
                            host=settings.CHROME_REMOTE_HOST,
                            port=settings.CHROME_REMOTE_PORT,
                        ),
                        timeout=30.0
                    )
                    logger.info("✅ Connected to remote browser successfully.")
                else:
                    logger.info(f"🚀 Starting new browser instance (Brave, Path={BRAVE_EXECUTABLE_PATH})...")
                    logger.debug(f"🔍 Using browser path: {BRAVE_EXECUTABLE_PATH}")
                    
                    # Disable Brave-specific features that cause unknown CDP events (like Adblock)
                    # to prevent 'KeyError: Network.requestAdblockInfoReceived' in nodriver.
                    browser_args = [
                        "--disable-features=BraveAdblock,BraveRewards,BraveSpeedreader,BraveP3A",
                        "--disable-brave-extension",
                    ]
                    
                    _browser_instance = await asyncio.wait_for(
                        uc.start(
                            browser_executable_path=BRAVE_EXECUTABLE_PATH,
                            user_data_dir=BROWSER_USER_PROFILE,
                            headless=False,
                            browser_args=browser_args,
                        ),
                        timeout=60.0
                    )
                
                # Ensure we have at least one "anchor" tab to keep the browser alive
                if _browser_instance and not _browser_instance.tabs:
                    await _browser_instance.get("about:blank", new_tab=True)
                
                logger.info("✅ Browser instance started successfully.")
            except asyncio.TimeoutError:
                logger.error("❌ review_browser: Browser start TIMEOUT reached.")
                raise
            except Exception as e:
                logger.error(f"❌ review_browser: Browser start failed: {e}")
                raise
        
        # Verify connection is still alive
        try:
            await _browser_instance.connection.send(cdp.browser.get_version())
        except Exception:
            logger.warning("⚠️ Browser connection lost. Re-initializing...")
            _browser_instance = None
            # Recursive call will re-init under the lock
            return await review_browser()
            
        return _browser_instance

async def get_tab() -> uc.Tab:
    """
    Utility to get a fresh tab from the singleton browser.
    """
    browser = await review_browser()
    return await browser.get("about:blank", new_tab=True)

async def verify_cf(tab: uc.Tab):
    """
    Triggers nodriver's Cloudflare verification on the given tab.
    """
    logger.info("🛡️ Triggering Cloudflare verification (verify_cf)...")
    try:
        await tab.verify_cf()
        logger.info("✅ Cloudflare verification completed.")
    except Exception as e:
        logger.warning(f"⚠️ Cloudflare verification failed or not needed: {e}")

async def close_browser():
    """
    Gracefully closes the singleton browser instance.
    """
    global _browser_instance
    async with _browser_lock:
        if _browser_instance:
            logger.info("🛑 Closing singleton browser instance...")
            try:
                await _browser_instance.stop()
            except Exception as e:
                logger.error(f"❌ Error closing browser: {e}")
            finally:
                _browser_instance = None
