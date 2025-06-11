import sys

if sys.platform.startswith("win"):
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
from fastapi import FastAPI, Query, HTTPException
from typing import List
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time

app = FastAPI()

def get_event_page(state: str, country: str) -> str:
    url_state = state.lower().replace(" ", "-")
    url_country = country.lower().replace(" ", "-")
    url = f"https://www.eventbrite.com/d/{url_country}--{url_state}/events--today/?page=1"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        ))
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector('[data-testid="search-event"]', timeout=20000)
        except Exception:
            pass  # Continue anyway

        for _ in range(5):
            page.mouse.wheel(0, 5000)
            time.sleep(1.5)

        html = page.content()
        browser.close()
        return html

def get_single_event_page(event_url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(event_url, timeout=60000)
        try:
            page.wait_for_selector("h2:has-text(\"Date and time\")", timeout=15000)
            page.wait_for_selector("h2:has-text(\"Location\")", timeout=15000)
        except:
            pass
        time.sleep(2)
        html = page.content()
        browser.close()
        return html

def extract_events_from_html(html_content: str) -> List[dict]:
    soup = BeautifulSoup(html_content, "lxml")
    event_list = soup.select_one("ul.SearchResultPanelContentEventCardList-module__eventList___2wk-D")
    if not event_list:
        raw_cards = soup.select('div[data-testid="search-event"]')
        cards_to_iterate = raw_cards
    else:
        cards_to_iterate = event_list.find_all("li", recursive=False)

    events = []
    seen_urls = set()

    for container in cards_to_iterate:
        card = container.select_one('div[data-testid="search-event"]')
        if not card:
            continue

        title_tag = card.select_one("h3")
        title = title_tag.get_text(strip=True) if title_tag else "N/A"

        date_time = "N/A"
        for p in card.select('p.Typography_body-md-bold__487rx'):
            text = p.get_text(strip=True)
            if "•" in text:
                date_time = text
                break

        venue_tag = card.select_one("p.Typography_body-md__487rx")
        venue = venue_tag.get_text(strip=True) if venue_tag else "N/A"

        price_tag = card.select_one("div.DiscoverVerticalEventCard-module__priceWrapper___usWo6 p") or \
                    card.select_one("div.DiscoverHorizontalEventCard-module__priceWrapper___3rOUY p")
        price = price_tag.get_text(strip=True) if price_tag else "N/A"

        url_tag = card.select_one("a.event-card-link")
        url = url_tag["href"] if url_tag and url_tag.has_attr("href") else "N/A"
        if url.startswith("/") and not url.startswith("http"):
            url = "https://www.eventbrite.com" + url

        if url in seen_urls:
            continue
        seen_urls.add(url)

        events.append({
            "title": title,
            "date_time": date_time,
            "venue": venue,
            "price": price,
            "url": url
        })

    return events

def parse_event_details(event_html: str) -> dict:
    soup = BeautifulSoup(event_html, 'lxml')
    full_date = "N/A"
    map_location = "N/A"

    date_container = soup.select_one('[data-testid="display-date-container"] .date-info__full-datetime')
    if date_container:
        full_date = date_container.get_text(strip=True)

    loc_block = soup.select_one('.location-info__address')
    if loc_block:
        venue = loc_block.select_one('p.location-info__address-text')
        venue_name = venue.get_text(strip=True) if venue else ""
        address_text = loc_block.get_text(separator="\n", strip=True).split("\n")
        if len(address_text) >= 2:
            map_location = address_text[1]
        elif len(address_text) == 1:
            map_location = address_text[0]

    return {
        "full_date": full_date,
        "map_location": map_location
    }

@app.get("/events")
def get_events(state: str = Query(..., description="State or region name"),
               country: str = Query(..., description="Country name")):
    print(f"📍 Getting events for: {state}, {country}…")
    page_source = get_event_page(state, country)
    print("✅ Received HTML from browser_scraper. Length:", len(page_source))

    events = extract_events_from_html(page_source)
    unique_events = []
    seen_urls = set()

    for event in events:
        if event["url"] in seen_urls:
            continue
        seen_urls.add(event["url"])

        try:
            event_html = get_single_event_page(event["url"])
            details = parse_event_details(event_html)
            event["full_date_time"] = details["full_date"]
            event["map_location"] = details["map_location"]
        except Exception as e:
            print(f"⚠️ Failed to fetch full details for: {event['title']}")
            event["full_date_time"] = "N/A"
            event["map_location"] = "N/A"

        unique_events.append(event)

    print(f"\n🎉 Total {len(unique_events)} Unique Events Found.")
    return unique_events
