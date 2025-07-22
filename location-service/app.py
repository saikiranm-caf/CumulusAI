import sys

if sys.platform.startswith("win"):
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import time
from playwright.sync_api import sync_playwright
from fastapi import FastAPI, HTTPException
import os
import requests
from dotenv import load_dotenv

port = int(os.getenv("PORT", 8002))
load_dotenv()

app = FastAPI()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

def reverse_geocode_nominatim(lat: float, lon: float):
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/91.0.4472.124 Safari/537.36"
        )
        page.goto(url, wait_until="networkidle", timeout=15000)
        time.sleep(1)
        pre = page.text_content("body")
        browser.close()
        try:
            data = json.loads(pre)
            return {
                "display_name": data.get("display_name", None),
                "address": data.get("address", None)
            }
        except Exception as e:
            return None

import requests

def get_area_info_google(lat, lon):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={GOOGLE_API_KEY}"
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set in environment variables")  
    resp = requests.get(url)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get('status') != 'OK':
        return None

    return parse_google_address_components(data)

def parse_google_address_components(google_data):
    """
    Extract address components, exclude placeholders like 'Unnamed Road',
    return clean display_name and address dict.
    """

    def is_placeholder(value):
        # Add any placeholder values you want to exclude here
        return not value or value.strip() == "" or value.lower() == "unnamed road"

    results = google_data.get('results', [])
    street_number = route = county = city = state = country = postcode = country_code = ""

    for result in results:
        components = result.get('address_components', [])

        temp_street_number = ""
        temp_route = ""
        temp_county = ""
        temp_city = ""
        temp_state = ""
        temp_country = ""
        temp_postcode = ""
        temp_country_code = ""

        for comp in components:
            types = comp.get('types', [])
            long_name = comp.get('long_name', "")

            if not temp_street_number and 'street_number' in types and not is_placeholder(long_name):
                temp_street_number = long_name
            if not temp_route and 'route' in types and not is_placeholder(long_name):
                temp_route = long_name
            if not temp_county and ('sublocality_level_1' in types or 'administrative_area_level_2' in types):
                temp_county = long_name
            if not temp_city and ('locality' in types or 'postal_town' in types):
                temp_city = long_name
            if not temp_state and 'administrative_area_level_1' in types:
                temp_state = long_name
            if not temp_country and 'country' in types:
                temp_country = long_name
                temp_country_code = comp.get('short_name', '').lower()
            if not temp_postcode and 'postal_code' in types:
                temp_postcode = long_name

        # Assign if empty and not placeholder
        if not street_number and not is_placeholder(temp_street_number):
            street_number = temp_street_number
        if not route and not is_placeholder(temp_route):
            route = temp_route
        if not county:
            county = temp_county
        if not city:
            city = temp_city
        if not state:
            state = temp_state
        if not country:
            country = temp_country
        if not postcode:
            postcode = temp_postcode
        if not country_code:
            country_code = temp_country_code

        if city and county and state and postcode and country:
            break

    # Compose display_name, skipping placeholders and empty strings
    parts_for_display = []
    for part in [street_number, route, county, city, state, postcode, country]:
        if part and not is_placeholder(part):
            parts_for_display.append(part)

    display_name = ", ".join(parts_for_display)

    return {
        "address": {
            "street_number": street_number if not is_placeholder(street_number) else "",
            "route": route if not is_placeholder(route) else "",
            "city": city or "",
            "county": county or "",
            "state": state or "",
            "postcode": postcode or "",
            "country": country or "",
            "country_code": country_code or ""
        },
        "display_name": display_name
    }

def get_nearby_places(lat: float, lon: float, radius: int = 500):
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lon}&radius={radius}&key={GOOGLE_API_KEY}"
    resp = requests.get(url)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get('status') != 'OK':
        return None

    places = []
    for place in data.get('results', []):
        place_type = place.get('types', [])[0] if place.get('types') else 'unknown'
        place_name = place.get('name', 'Unnamed')
        places.append({
            "name": place_name,
            "type": place_type,
            "vicinity": place.get('vicinity', '')
        })
    return places

def is_near_poi(lat: float, lon: float):
    places = get_nearby_places(lat, lon)
    if not places:
        return {"nearby": False, "place": None}

    poi_mapping = {
        "gym": ["gym", "fitness_center"],
        "park": ["park"],
        "school": ["school", "university"],
        "religious_place": ["church", "mosque", "temple", "synagogue"],
        "hospital": ["hospital", "clinic"],
        "beach": ["beach"],
        "library": ["library"],
        "home": ["home"]  # Note: "home" is harder to detect; may need user input or address parsing
    }

    for place in places:
        for poi_type, keywords in poi_mapping.items():
            if any(keyword in place["type"] for keyword in keywords):
                return {"nearby": True, "place": poi_type, "name": place["name"]}

    return {"nearby": False, "place": None}

def get_activity_context(lat: float, lon: float, time_str: str, age: int, gender: str, motion_state: str = None):
    places = get_nearby_places(lat, lon)
    activity_context = {
        "Near_Park": False, "In_Gym": False, "At_School_Zone": False, "In_Shopping_Mall": False,
        "At_Religious_Place": False, "Near_Hospital": False, "At_Beach_or_Lake": False, "At_Library": False,
        "At_Movie_Theatre": False, "Driving": False, "Female_in_Public": False, "Teen_at_Home_Study": False,
        "Child_at_Play": False, "Elderly_User": False, "Late_Night_Use": False, "Work_Hours": False,
        "Weekend_Chill": False, "At_Outdoor_Event": False, "At_Home": False, "Walking_Jogging": False
    }

    # Parse time
    from datetime import datetime
    time_obj = datetime.strptime(time_str, "%H:%M %p")
    hour = time_obj.hour
    weekday = time_obj.weekday()  # 0-6, 0 is Monday

    # Location-based activities
    if places:
        poi_mapping = {
            "Near_Park": ["park"],
            "In_Gym": ["gym", "fitness_center"],
            "At_School_Zone": ["school", "university"],
            "In_Shopping_Mall": ["shopping_mall"],
            "At_Religious_Place": ["church", "mosque", "temple", "synagogue"],
            "Near_Hospital": ["hospital", "clinic"],
            "At_Beach_or_Lake": ["beach"],
            "At_Library": ["library"],
            "At_Movie_Theatre": ["movie_theater"]
        }
        for place in places:
            place_type = place.get("type", "")
            for activity, keywords in poi_mapping.items():
                if any(keyword in place_type for keyword in keywords):
                    activity_context[activity] = True
                    break

    # Time-based activities
    if 22 <= hour or hour < 6:
        activity_context["Late_Night_Use"] = True
    elif 9 <= hour <= 17 and 0 <= weekday <= 4:
        activity_context["Work_Hours"] = True
    elif weekday in [5, 6]:
        activity_context["Weekend_Chill"] = True

    # Age, gender, and motion-based activities
    if age >= 60:
        activity_context["Elderly_User"] = True
    elif age < 12:
        activity_context["Child_at_Play"] = True
    elif 13 <= age <= 19:
        activity_context["Teen_at_Home_Study"] = True
    if gender.lower() == "f" and age >= 18 and age <= 30:
        activity_context["Female_in_Public"] = True
    if motion_state == "driving":
        activity_context["Driving"] = True
    elif motion_state == "walking" or motion_state == "jogging":
        activity_context["Walking_Jogging"] = True
    # At_Home and At_Outdoor_Event need user context or geofencing; assume false unless provided

    return activity_context

@app.get("/location")
def get_location(lat: float, lon: float, time: str, user_id: str, age: int, gender: str, motion_state: str = None):
    print(f"🔥Control at location")
    nominatim_result = reverse_geocode_nominatim(lat, lon)
    if nominatim_result and nominatim_result.get("display_name"):
        activity_context = get_activity_context(lat, lon, time, age, gender, motion_state)
        print(f"Weather data fetched: {nominatim_result}")
        print(f"Activity context determined: {activity_context}")
        return {"source": "nominatim","display_name": nominatim_result["display_name"], "address": nominatim_result, "activities": activity_context}

    google_result = get_area_info_google(lat, lon)
    if google_result:
        activity_context = get_activity_context(lat, lon, time, age, gender, motion_state)
        print(f"Weather data fetched: {google_result['address']}")
        print(f"Activity context determined: {activity_context}")
        return {
            "source": "google",
            "display_name": google_result["display_name"],
            "address": google_result["address"],
            "activities": activity_context
        }
    raise HTTPException(status_code=404, detail="Location data not found")
