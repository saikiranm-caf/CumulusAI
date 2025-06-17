import sys
import os
import json
import time
from math import radians, cos, sin, asin, sqrt
from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from typing import List

port = int(os.getenv("PORT", 8003))
# Windows asyncio fix for Playwright subprocess support
if sys.platform.startswith("win"):
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.sync_api import sync_playwright

load_dotenv()

app = FastAPI()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("Missing GOOGLE_API_KEY in environment variables")


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two lat/lon points in km"""
    R = 6371  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


def reverse_geocode_nominatim(lat: float, lon: float) -> Optional[dict]:
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=15000)
            time.sleep(1)
            content = page.text_content("body")
            browser.close()
        data = json.loads(content)
        return {
            "display_name": data.get("display_name"),
            "address": data.get("address", {})
        }
    except Exception as e:
        print(f"[Nominatim error] {e}")
        return None


def get_google_maps_search_page(lat: float, lon: float, query: str) -> str:
    from playwright.sync_api import sync_playwright
    import time

    search_term = query.replace(" ", "+")
    url = f"https://www.google.com/maps/search/{search_term}/@{lat},{lon}z"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
        )
        print(f"🌐 Navigating to {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Wait explicitly for place cards container to appear (adjust selector as needed)
        print("Waiting for place cards to load...")
        page.wait_for_selector('div.Nv2PK', timeout=30000)  # Wait up to 30 seconds

        # Extra delay to allow all JS and lazy loading to finish
        time.sleep(5)

        # Scroll down to load more results dynamically
        print("Scrolling to load more results...")
        max_scrolls = 10
        for _ in range(max_scrolls):
            prev_count = len(page.query_selector_all("div.Nv2PK"))
            page.mouse.wheel(0, 5000)
            time.sleep(1.5)
            curr_count = len(page.query_selector_all("div.Nv2PK"))
            if curr_count == prev_count:
                break  # no new cards loaded

        # Drag map to trigger more pins (optional)
        print("Dragging map to trigger more nearby pins...")
        page.mouse.move(300, 300)
        page.mouse.down()
        page.mouse.move(250, 250)
        page.mouse.up()
        time.sleep(3)

        # Click "Search this area" button if visible
        try:
            if page.is_visible('button[jsaction*="search"]'):
                print("Clicking 'Search this area' button...")
                page.click('button[jsaction*="search"]')
                time.sleep(4)
        except Exception:
            print("⚠️ Could not click 'Search this area' — skipping.")

        # Final scroll for any late loading entries
        for _ in range(3):
            page.mouse.wheel(0, 3000)
            time.sleep(1.5)

        html = page.content()
        print("Finished loading all available places.")
        browser.close()
        return html



# Dummy placeholder functions for extracting and parsing places from HTML.
# These should be replaced with your existing implementations or improved scraping logic.

def extract_places_from_google_maps(html: str) -> List[dict]:
    """
    Parse Google Maps search results HTML and extract list of places with minimal info:
    [{'name': ..., 'link': ..., 'category': ...}, ...]
    """
    # TODO: Implement actual HTML parsing with e.g. BeautifulSoup, regex, or playwright selectors
    # For now, returning empty list to fallback on Google Places API
    return []


def get_single_place_html(place_url: str) -> Optional[str]:
    """Fetch individual place page HTML (optional for details)"""
    # TODO: Implement if needed, else skip
    return None


def parse_single_place_details(html: str) -> dict:
    """Parse place details from single place HTML"""
    # TODO: Implement if needed, else skip
    return {
        "name": "",
        "address": "",
        "category": ""
    }

def extract_places_from_google_maps(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    places_raw = soup.find_all("div", class_="Nv2PK")

    extracted = []
    for place in places_raw[:10]:  # Limit to top 5
        try:
            name = place.select_one("div.qBF1Pd.fontHeadlineSmall").get_text(strip=True)
        except: name = "N/A"

        try:
            link = place.select_one("a.hfpxzc")["href"]
        except: link = "N/A"

        try:
            category = place.select_one("button.DkEaL").get_text(strip=True)
        except: category = "N/A"

        try:
            address = place.select_one("div.W4Efsd span:nth-of-type(3)").get_text(strip=True)
        except: address = "N/A"

        extracted.append({
            "name": name,
            "category": category,
            "address": address,
            "link": f"https://www.google.com{link}" if link.startswith("/") else link
        })

    return extracted

def parse_single_place_details(html: str) -> dict:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    def safe_text(sel): return sel.get_text(strip=True) if sel else "N/A"

    name = safe_text(soup.select_one("h1.DUwDvf.lfPIob"))
    category = safe_text(soup.select_one("button.DkEaL"))
    address = safe_text(soup.select_one("div.Io6YTe.fontBodyMedium"))

    return {
        "name": name,
        "category": category,
        "address": address
    }

def get_single_place_html(url: str) -> str:
    from playwright.sync_api import sync_playwright
    import time

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # print(f"🌐 Visiting: {url}")
        page.goto(url, timeout=60000)
        time.sleep(5)  # Let all content render
        html = page.content()
        browser.close()
        return html

def attach_distance_to_places(places, ref_lat, ref_lon):
    enriched = []
    for place in places:
        lat, lon = extract_lat_lon_from_place_url(place["link"])
        distance = haversine_distance(ref_lat, ref_lon, lat, lon) if lat and lon else float('inf')
        enriched.append({**place, "lat": lat, "lon": lon, "distance_km": round(distance, 5)})
    return sorted(enriched, key=lambda x: x["distance_km"])

def extract_lat_lon_from_place_url(url: str):
    import re
    # Try @lat,lon first
    match = re.search(r'@([-.\d]+),([-.\d]+)', url)
    if match:
        return float(match.group(1)), float(match.group(2))

    # Fallback: !3dLAT!4dLON
    match_alt = re.search(r'!3d([-.\d]+)!4d([-.\d]+)', url)
    if match_alt:
        return float(match_alt.group(1)), float(match_alt.group(2))

    return None, None

def haversine_distance(lat1, lon1, lat2, lon2):
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_places_from_scrape(lat: float, lon: float, query: str) -> List[dict]:
    nominatim_data = reverse_geocode_nominatim(lat, lon)
    if not nominatim_data or not nominatim_data.get("display_name"):
        print("[Places scrape] Nominatim data not found, abort scraping.")
        return []

    location_name = nominatim_data["display_name"]
    search_query = f"{query} in {location_name}"
    print(f"[Places scrape] Searching Google Maps for: {search_query}")

    html = get_google_maps_search_page(lat, lon, search_query)
    if not html:
        print("[Places scrape] Google Maps page HTML not retrieved.")
        return []

    # Use the real extractor from extractor.py
    places_raw = extract_places_from_google_maps(html)
    if not places_raw:
        print("[Places scrape] No places extracted from HTML.")
        return []

    # Enrich place list with lat/lon and distance using your helper
    enriched_places = attach_distance_to_places(places_raw, lat, lon)

    # Optionally get more details for each place
    for place in enriched_places:
        single_html = get_single_place_html(place["link"])
        details = parse_single_place_details(single_html)
        place.update({
            "name": details.get("name", place.get("name")),
            "category": details.get("category", place.get("category")),
            "location_address": details.get("address", place.get("address")),
        })

    return enriched_places



def get_places_from_google_api(lat: float, lon: float, query: str, api_key: str) -> List[dict]:
    """
    Fallback: Get places from Google Places API.
    Normalizes the response to our schema.
    """
    radius = 500  # meters
    place_type = query.lower()  # crude mapping, ideally map queries to type
    url = (
        f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?"
        f"location={lat},{lon}&radius={radius}&type={place_type}&keyword={query}&key={api_key}"
    )
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        places = []
        for place in results:
            name = place.get("name", "")
            address = place.get("vicinity", "")
            location = place.get("geometry", {}).get("location", {})
            place_lat = location.get("lat")
            place_lon = location.get("lng")
            place_id = place.get("place_id", "")
            category = place.get("types", [])
            distance_km = haversine(lat, lon, place_lat, place_lon) if place_lat and place_lon else None
            place_link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

            places.append({
                "name": name,
                "location_address": address,
                "distance_km": distance_km,
                "category": ", ".join(category),
                "place_link": place_link
            })
        return places
    except Exception as e:
        print(f"[Google Places API error] {e}")
        return []


@app.get("/places")
def places_api(lat: float = Query(..., description="Latitude"),
               lon: float = Query(..., description="Longitude"),
               query: str = Query(..., description="Place query, e.g. 'park'")):

    
    print(f"[API] Request for Google places API: lat={lat}, lon={lon}, query='{query}'")
    places = get_places_from_google_api(lat, lon, query, GOOGLE_API_KEY)

    if not places:
        print("[API] Falling back to Nominatim scraping Places API")
        places = get_places_from_scrape(lat, lon, query)

    if not places:
        raise HTTPException(status_code=404, detail="No places found")

    # Sort by distance ascending if distance available
    places = sorted(places, key=lambda x: x.get("distance_km") or float("inf"))

    return places
