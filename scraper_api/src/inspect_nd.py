import nodriver as uc
import asyncio
import json

async def inspect():
    browser = await uc.start()
    page = await browser.get("https://www.google.com")
    print("Methods of page (Tab):")
    print([m for m in dir(page) if not m.startswith('_')])
    
    # Try to find frames
    if hasattr(page, 'targets'):
        print("Targets:", page.targets)
    
    await browser.stop()

if __name__ == "__main__":
    asyncio.run(inspect())
