# recommendation-service/app.py

import os
import requests
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="recommendation-service",
    version="0.1.0",
    description="Blocking and non-blocking recommendation endpoints"
)

LLM_MODEL   = os.getenv("LLM_MODEL")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")

# In-memory store for async results (swap out for DB/Redis in prod)
_async_results: dict[str, str] = {}


def _fetch_all(user_id: str, lat: float, lon: float):
    """
    Call each microservice via HTTP (proxied through nginx on :8000),
    print debug info, then return all raw JSON blobs.
    """
    print("🔥 Calling weather…")
    weather = requests.get(
        f"{GATEWAY_URL}/weather", params={"lat": lat, "lon": lon}
    ).json()

    print("🔥 Calling location…")
    location = requests.get(
        f"{GATEWAY_URL}/location", params={"lat": lat, "lon": lon}
    ).json()

    print("🔥 Calling user-prefs…")
    prefs = requests.get(
        f"{GATEWAY_URL}/user-preferences", params={"user_id": user_id}
    ).json()

    state   = location["address"].get("state", "")
    country = location["address"].get("country", "")

    print("🔥 Calling events…")
    events = requests.get(
        f"{GATEWAY_URL}/events", params={"state": state, "country": country}
    ).json()

    print("🔥 Calling places…")
    places = requests.get(
        f"{GATEWAY_URL}/places",
        params={"lat": lat, "lon": lon, "query": "park"}
    ).json()

    print("🔥 Calling blogs…")
    blogs = requests.get(f"{GATEWAY_URL}/blogs").json()

    return weather, location, prefs, events, places, blogs


def _build_and_call_llm(user_id: str, lat: float, lon: float) -> str:
    """
    1) Fetch all microservices
    2) Build the prompt
    3) Call your LLM
    4) Return the recommendation string
    """
    weather, location, prefs, events, places, blogs = _fetch_all(user_id, lat, lon)

    prompt = f"""
    The user is at {location['display_name']} with weather: 
      {weather['description']} ({weather['temperature']}°C).
    User prefers: {[p['activity_name'] for p in prefs.get('activities', [])]}.
    Nearby events: {[e['title'] for e in events.get('events', [])]}.
    Nearby places: {[p['name']  for p in places.get('places', [])]}.
    Recent blogs: {[b['title']  for b in blogs.get('blogs', [])]}.

    Suggest a smart activity or blog to the user with a brief natural sentence.
    """.strip()

    print("🔥 Calling LLM with prompt:")
    print(prompt)

    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model":  LLM_MODEL,
            "prompt": prompt,
            "stream": False
        }
    ).json()

    return resp.get("response", "No suggestion available.")


@app.get(
    "/recommendation",
    summary="🔄 Blocking: run all calls + LLM, then return"
)
def recommend(
    user_id: str  = Query(..., description="Your user ID"),
    lat:     float = Query(..., description="Latitude"),
    lon:     float = Query(..., description="Longitude"),
):
    try:
        recommendation = _build_and_call_llm(user_id, lat, lon)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"recommendation": recommendation}


@app.get(
    "/recommendation/async",
    summary="⚡ Non-blocking: enqueue & return immediately"
)
def recommend_async(
    background_tasks: BackgroundTasks,
    user_id:          str   = Query(...),
    lat:              float = Query(...),
    lon:              float = Query(...),
):
    """
    Fires off the same logic in the background, returns an enqueue message.
    """
    background_tasks.add_task(
        lambda: _async_worker(user_id, lat, lon)
    )
    return {"message": f"Enqueued recommendation for {user_id}"}


def _async_worker(user_id: str, lat: float, lon: float):
    """
    Background task: compute and store in our in-memory dict.
    """
    _async_results[user_id] = _build_and_call_llm(user_id, lat, lon)


@app.get(
    "/recommendation/result",
    summary="📥 Poll for async recommendation"
)
def get_recommendation_result(
    user_id: str = Query(..., description="Your user ID")
):
    """
    Returns pending/ready + the recommendation when ready.
    """
    if user_id not in _async_results:
        return {"status": "pending"}

    return {
        "status":         "ready",
        "recommendation": _async_results.pop(user_id)
    }
