# Upwork Scraper – Project Context

Use this document as reference for future work on the Upwork scraper (prompts, onboarding, or refactors).

---

## 1. Overview

- **Purpose**: Scrape job listings from Upwork search/product URLs: login (once), navigate to search pages, open job tiles, extract modal HTML, and run Gemini for structured data.
- **Stack**: Python (FastAPI), [Nodriver](https://github.com/ultrafunkamsterdam/nodriver) (CDP-based automation), Redis (Streams) for async processing, Gemini.
- **Session**: **Persistent Chromium Profile**. Sessions are stored in `upwork_profile_nd/` and reused across restarts. Includes "Remember Me" checkbox support.
- **Concurrency**: **Multi-tab Processing**. A singleton browser instance handles up to 8 concurrent scraping tabs using `asyncio.Semaphore`.

---

## 2. API and Schema

- **Endpoint**: `POST /api/v1/scrape/upwork`
- **Request model**: `UpworkScrapeRequest` in `src/schemas/extraction.py`
  - `product_url: str` – Full Upwork search URL (e.g. `https://www.upwork.com/nx/search/jobs/?q=python&sort=relevance`)
  - `no_of_pages_to_scrape: Optional[int] = None` – `None` = scrape all pages; `1, 2, 3, ...` = scrape up to that many pages.
  - `headless: Optional[bool] = False`
- **Credentials**: Never in request body. Read from server env only: `UPWORK_USERNAME`, `UPWORK_PASSWORD` (see `.env`).
- **Response**: `List[ExtractedData]` (Pydantic models; job title, summary, client info, skills, etc.).

---

## 3. Login Flow (No Cookies)

- **URL**: `https://www.upwork.com/ab/account-security/login`
- **Persistence Strategy**:
  1. **Singleton Browser**: Only one browser instance runs, initialized with an absolute `user_data_dir`.
  2. **Verify Session**: Before any task, `verify_session()` checks CDP cookies and UI indicators (e.g., user avatar).
  3. **Auto-Recovery**: If no session is found, `_do_login()` is triggered over the persistent profile.
- **Login Steps**:
  1. Username entered into `#login_username` via `_human_type()`.
  2. Click **Continue**.
  3. Password entered into `#login_password`.
  4. **Remember Me**: The scraper explicitly clicks the "Remember Me" checkbox to ensure long-term persistence.
  5. Click **Log in**.
  6. **Persistence Sync**: Wait 5 seconds after login to ensure Chromium flushes all cookies/tokens to disk.
- **Humanization**: `_human_delay()` between actions; typing at ~40–60 WPM.

---

## 4. Pagination (Multi-Page Scraping)

- **Preferred**: Intercept GraphQL response for `userJobSearch`:
  - Enable CDP Network, add `ResponseReceived` handler for URLs containing `userJobSearch`.
  - After loading the search page, wait for the response (e.g. 15s timeout), get body via `cdp.network.get_response_body(request_id)`.
  - Parse `data.search.universalSearchNuxt.userJobSearchV1.paging` → `total`, `offset`, `count` → `total_pages = ceil(total/count)`, `current_page = offset//count + 1`.
- **Fallback**: DOM pagination:
  - Container: `ul[data-test="pagination"]`.
  - Text: `li[data-test="pagination-mobile"]` e.g. `"5 of 95"` → regex `(\d+)\s+of\s+(\d+)` → current_page, total_pages.
  - Next: `a[data-test="next-page"]` (if not `.is-disabled`); or build URL with `page=N`.
- **Next page URL**: `_build_next_page_url(base_url, page_num)` using `urllib.parse` to set `page=N` in query.

---

## 5. Scraper Flow (High Level)

1. **Init Browser**: `_init_browser()` – Manages a Singleton browser. If the instance is dead, it cleans up `SingletonLock` and zombie processes before restarting.
2. **Session Warmup**: `verify_session()` – Passive cookie check via CDP followed by active navigation check for authenticated components.
3. **Navigate**: Go to `product_url`. If a login wall is hit, it automatically triggers `_do_login()` and resumes.
4. **Multi-Tab Execution**: `RedisStreamReader` dispatches messages to isolated scraper instances (tabs), limited by a concurrency semaphore of 8.
5. **Per Page**:
   - Navigate to current page.
   - Wait for tiles: `article.job-tile[data-test="JobTile"]`.
   - For each tile: click → wait for slider `.air3-slider-content` → `_extract_job_modal()` (full page DOM) → `_clean_html_server_side()`.
6. **Efficiency**: **No Screenshots**. Screenshot logic was removed to optimize processing time and reduce storage costs.
7. **Callback**: Card data is passed back to `RedisStreamReader` for publishing to the extraction stream and saving HTML to `storage/`.

---

## 6. Key Files

| Path | Role |
|------|------|
| `app.py` | Main root-level entry point for the application. |
| `src/services/upwork_scraper.py` | Singleton browser manager, multi-layered session verification, and job scraping logic (Modal/DOM). |
| `src/services/redis_stream_reader.py` | Concurrent stream consumer with Semaphore-based tab isolation. |
| `src/services/gemini_extractor.py` | LLM-based HTML to structured job data extraction. |
| `test_redis_push.py` | Local utility to push tasks into the Redis stream for testing. |

---

## 7. Environment Variables

- **Required for scrape**: `UPWORK_USERNAME`, `UPWORK_PASSWORD` (from `.env`; not in request).
- **Required for extraction**: `GEMINI_API_KEY`.
- **Optional**: `NODRIVER_SANDBOX=1` (or `true`/`yes`) to keep browser sandbox enabled; if unset and e.g. root, sandbox is disabled so the browser can connect.

`.env` is loaded from `scraper_api/.env` (e.g. via `load_dotenv` in scraper and test).

---

## 8. Nodriver References

- **Repo**: https://github.com/ultrafunkamsterdam/nodriver  
- **Docs**: https://ultrafunkamsterdam.github.io/nodriver  

Use these for browser start options, CDP (e.g. `cdp.network`), Tab/Element APIs, and cookie/session APIs if reintroducing persistence later.

---

## 9. Design Decisions (Summary)

- **Persistent Browser Profile**: Used for single-login lifecycle.
- **Concurrency**: Tab-based isolation capped at 8 tabs per browser instance.
- **Resource Cleanup**: Automated killing of zombie Chrome processes and removal of `SingletonLock` files.
- **No Screenshots**: Removed to maximize scraping speed and reduce storage footprint.
- **Root Entry Point**: `app.py` at root for simplified deployment and execution.
- **Verification Fallbacks**: Multi-path login detection (Avatar, URL, Search bar).

---

*Last updated to reflect current codebase and multi-page scraping with no cookie persistence.*
