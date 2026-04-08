import asyncio
import os
import logging
import sys
import psutil
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

async def kill_zombie_browsers():
    """
    Forcefully terminate any orphaned Brave/Chrome processes using the 
    specified profile directory to release locks.
    """
    profile_abs_path = os.path.abspath(BROWSER_USER_PROFILE)
    logger.info(f"🧹 Checking for zombie browsers locking {profile_abs_path}...")
    
    current_pid = os.getpid()
    count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            
            # Look for browser processes with our data dir in their cmdline
            cmdline = " ".join(proc.info.get('cmdline') or [])
            if profile_abs_path in cmdline or BROWSER_USER_PROFILE in cmdline:
                logger.warning(f"  - Terminating orphaned browser {proc.info['name']} (PID: {proc.info['pid']})")
                proc.kill() # Be More aggressive
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    if count > 0:
        logger.info(f"✅ Terminated {count} orphaned browser processes.")
        await asyncio.sleep(1.0) # wait for OS release

async def review_browser() -> uc.Browser:
    """
    Helper function to manage a singleton browser instance.
    """
    global _browser_instance
    async with _browser_lock:
        if _browser_instance is not None:
            # Verify if browser is actually alive
            try:
                await _browser_instance.connection.send(cdp.browser.get_version())
                return _browser_instance
            except Exception:
                logger.warning("⚠️ Browser connection lost. Attempting re-initialization...")
                _browser_instance = None

        from src.core.config import settings
        
        # If we got here, we need to start/restart
        max_start_attempts = 2
        for attempt in range(max_start_attempts):
            try:
                if settings.CHROME_REMOTE_HOST and settings.CHROME_REMOTE_PORT:
                    logger.info(f"🔗 Connecting to remote browser at {settings.CHROME_REMOTE_HOST}:{settings.CHROME_REMOTE_PORT}...")
                    _browser_instance = await asyncio.wait_for(
                        uc.start(host=settings.CHROME_REMOTE_HOST, port=settings.CHROME_REMOTE_PORT),
                        timeout=30.0
                    )
                else:
                    logger.info(f"🚀 Starting singleton browser (Attempt {attempt+1})...")
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
                            sandbox=False, # Often avoids 'Failed to connect' in restricted environments
                        ),
                        timeout=60.0
                    )
                
                logger.info("✅ Browser instance started successfully.")
                return _browser_instance

            except Exception as e:
                logger.error(f"❌ review_browser: Attempt {attempt+1} failed: {e}")
                # Any failure to connect/start warrants a cleanup
                await kill_zombie_browsers()
                
                if attempt == max_start_attempts - 1:
                    raise
                await asyncio.sleep(2.0)
        
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

import gc

async def close_browser():
    """
    Gracefully and safely closes the singleton browser instance.
    """
    global _browser_instance
    async with _browser_lock:
        if _browser_instance:
            logger.info("🛑 Closing singleton browser instance...")
            try:
                # Use a separate ref to avoid race conditions during clear
                browser = _browser_instance
                _browser_instance = None
                
                # Close connection but shield it from current cancellation
                # to ensure it actually finishes.
                stop_task = browser.stop()
                if asyncio.iscoroutine(stop_task):
                    await asyncio.wait_for(asyncio.shield(stop_task), timeout=5.0)
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"Non-fatal browser shutdown error: {e}")
            finally:
                _browser_instance = None
                gc.collect()
