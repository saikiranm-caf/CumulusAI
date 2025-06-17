from fastapi import FastAPI, Query
import requests
import os
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()
LLM_MODEL = os.getenv("LLM_MODEL")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")  # default to local nginx

@app.get("/recommendation")
def recommend(user_id: str, lat: float, lon: float):
    weather = requests.get(f"{GATEWAY_URL}/weather", params={"lat": lat, "lon": lon}).json()
    location = requests.get(f"{GATEWAY_URL}/location", params={"lat": lat, "lon": lon}).json()
    prefs = requests.get(f"{GATEWAY_URL}/user-preferences", params={"user_id": user_id}).json()

    state = location["address"].get("state", "")
    country = location["address"].get("country", "")
    events = requests.get(f"{GATEWAY_URL}/events", params={"state": state, "country": country}).json()
    places = requests.get(f"{GATEWAY_URL}/places", params={"lat": lat, "lon": lon, "query": "park"}).json()
    blogs = requests.get(f"{GATEWAY_URL}/blogs").json()

    prompt = f"""
    The user is at {location['display_name']} with weather: {weather['description']} ({weather['temperature']}°C).
    User prefers: {[p['activity_name'] for p in prefs.get('activities', [])]}.
    Nearby events: {[e['title'] for e in events.get('events', [])]}.
    Nearby places: {[p['title'] for p in places.get('places', [])]}.
    Recent blogs: {[b['title'] for b in blogs.get('blogs', [])]}.

    Suggest a smart activity or blog to the user with a brief natural sentence.
    """

    llm_response = requests.post("http://localhost:11434/api/generate", json={
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False
    }).json()

    return {
        "recommendation": llm_response.get("response", "No suggestion available.")
    }
