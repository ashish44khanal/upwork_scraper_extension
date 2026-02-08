# Upwork Scraper – Project Context

Use this document as reference for future work on the Upwork scraper (prompts, onboarding, or refactors).

---

## 1. Overview

- **Purpose**: Scrape job listings from Upwork search/product URLs: login, navigate to a search page, open each job tile, extract modal HTML, and run Gemini to get structured job data.
- **Stack**: Python (FastAPI), [Nodriver](https://github.com/ultrafunkamsterdam/nodriver) (CDP-based browser automation), Gemini for extraction.
- **Session**: **No cookie/session persistence**. Login is performed on every run using env credentials.

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
- **Steps**:
  1. Navigate to login URL.
  2. **Username**: Clear input with `clear_input()`, then type via `_human_type()` into `#login_username` (fallbacks: `input[name='login[username]']`, etc.).
  3. Click **Continue**: `#login_password_continue` (or `button[data-ev-label="Continue"][target-form="username"]`).
  4. **Password**: Clear input, then `_human_type()` into `#login_password`.
  5. Click **Log in**: `#login_control_continue`.
  6. Wait for redirect / login form to disappear.
- **Humanization**: `_human_delay()` between actions; `_human_type()` types at ~40–60 WPM (delays per key, longer for `@` and `.`). Inputs are cleared before typing.
- **Session**: Cookie-based persistence was removed by design; each run does a full login.

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

1. **Init browser**: `_init_browser()` – Nodriver `uc.start()` with `user_data_dir`, `browser_args`. Optional `sandbox=False` when `NODRIVER_SANDBOX` is not set and e.g. running as root (fixes “Failed to connect to browser”).
2. **Session**: `_ensure_session()` – always calls `_do_login()` (no cookie load/validate).
3. **Navigate**: Go to `product_url`; handle Cloudflare if needed (`_wait_for_cloudflare()`).
4. **Total pages**: Try GraphQL paging (`_get_total_pages_after_navigate` + handler); on failure use `_get_pagination_from_dom()`. Compute `pages_to_scrape = min(no_of_pages_to_scrape, total_pages)` or all pages if `no_of_pages_to_scrape` is `None`. If `no_of_pages_to_scrape <= 0`, return `[]`.
5. **Per page** (1 to `pages_to_scrape`):
   - If page > 1: navigate to `_build_next_page_url(product_url, page_num)`.
   - Wait for tiles: `article.job-tile[data-test="JobTile"]` via `_wait_for_tiles()`.
   - For each tile: click → wait for slider `div.air3-slider-content[data-test="UpCSliderBody"]` → `_extract_job_modal()` (full page DOM) → `_clean_html_server_side()` → append to list.
   - Close modal and continue to next tile.
6. **Extract**: Run Gemini extractor on collected HTML list; return `List[Dict]` → API returns `List[ExtractedData]`.

---

## 6. Key Files

| Path | Role |
|------|------|
| `src/schemas/extraction.py` | `UpworkScrapeRequest`, `ExtractedData`, etc. |
| `src/api/v1/endpoints/scrape.py` | `POST /upwork`, `POST /extract`, download; calls `scraper.scrape_jobs(product_url, no_of_pages_to_scrape)`. |
| `src/services/upwork_scraper.py` | `UpworkScraper`: browser init, login, pagination (API + DOM), page loop, tile loop, modal extraction, Gemini. |
| `src/services/gemini_extractor.py` | Gemini-based HTML → structured job data. |
| `test_upwork_scraper.py` | E2E test: load `.env`, `scrape_jobs(product_url, no_of_pages_to_scrape=1)`. |

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

- **No `num_jobs`**: Replaced by `no_of_pages_to_scrape` (page-based).
- **No cookie/session persistence**: Removed; login every run.
- **Inputs cleared before typing**: `clear_input()` then human-like typing.
- **Pagination**: Prefer GraphQL `userJobSearch` paging; fallback DOM “X of Y” + next link/URL.
- **Browser sandbox**: Disabled when needed (e.g. root/Docker) unless `NODRIVER_SANDBOX` is set.

---

*Last updated to reflect current codebase and multi-page scraping with no cookie persistence.*
