import asyncio
import nodriver as uc
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_interaction():
    browser = await uc.start()
    page = await browser.get("https://www.upwork.com/nx/search/jobs/")
    await asyncio.sleep(5)
    
    try:
        # Check if we can find the element
        selector = 'input.air3-typeahead-input-fake'
        search_input = await page.select(selector, timeout=10)
        if search_input:
            logger.info(f"Found input: {search_input}")
            
            # Test get_position
            rect = await search_input.get_position()
            logger.info(f"Position: {rect}")
            
            # Test move and click
            logger.info("Moving mouse...")
            center_x = rect[0] + (rect[2] / 2)
            center_y = rect[1] + (rect[3] / 2)
            
            await page.mouse_move(center_x, center_y)
            await page.mouse_click()
            logger.info("Clicked.")
            
            await asyncio.sleep(2)
            await page.send_keys("React Developer\n")
            logger.info("Keys sent.")
            
        else:
            logger.error("Input NOT found!")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await asyncio.sleep(5)
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(test_interaction())
