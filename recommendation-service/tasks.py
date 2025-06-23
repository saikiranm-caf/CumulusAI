# recommendation-service/tasks.py

import asyncio # Make sure asyncio is imported
from fastapi import FastAPI
from pydantic import BaseModel
from config import settings
from rpc_client import rpc_call

app = FastAPI()


class RecommendationRequest(BaseModel):
    user_id: str
    lat: float
    lon: float


@app.get("/recommendation/async")
async def recommend_async(req: RecommendationRequest):
    """
    Enqueue and return immediately (old behavior).
    """
    asyncio.create_task(process_recommendation_task(req))
    return {"message": f"Enqueued recommendation for {req.user_id}"}


@app.get("/recommendation")
async def recommend(req: RecommendationRequest):
    """
    Wait for all RPC calls to complete and return the full recommendation.
    """
    prompt = await process_recommendation_task(req)
    return {"recommendation": prompt}



async def process_recommendation_task(task: RecommendationRequest) -> str:
    user_id, lat, lon = task.user_id, task.lat, task.lon

    # 1) Retrieve location & weather (often needed for subsequent calls, so keep sequential)
    location = await rpc_call(
        settings.LOCATION_RPC_QUEUE,
        {"lat": lat, "lon": lon}
    )
    weather = await rpc_call(
        settings.WEATHER_RPC_QUEUE,
        {"lat": lat, "lon": lon}
    )

    # 2) Retrieve user preferences
    prefs_resp = await rpc_call(
        settings.USER_PREFS_RPC_QUEUE,
        {"user_id": user_id}
    )
    activities = prefs_resp.get("activities", [])

    # 3) Retrieve events, places, blogs IN PARALLEL using asyncio.gather
    # Create the coroutine objects without awaiting them immediately
    events_coro = rpc_call(
        settings.EVENTS_RPC_QUEUE,
        {
            "state": location.get("address", {}).get("state", ""),
            "country": location.get("address", {}).get("country", "")
        },
        timeout=120.0 # Ensure this timeout is sufficient for scraping
    )
    places_coro = rpc_call(
        settings.PLACES_RPC_QUEUE,
        {"lat": lat, "lon": lon, "query": "park"}
    )
    blogs_coro = rpc_call(
        settings.BLOGS_RPC_QUEUE,
        {}
    )

    # Await all three coroutines concurrently
    events_resp, places_resp, blogs_resp = await asyncio.gather(
        events_coro,
        places_coro,
        blogs_coro
    )

    events = events_resp.get("events", [])
    places = places_resp.get("places", [])
    blogs = blogs_resp.get("blogs", [])

    # 4) Build your prompt string
    prompt = f"""
    📍 Location: {location.get('display_name', 'N/A')}
    🌤️ Weather: {weather.get('description', 'N/A')} ({weather.get('temperature', 'N/A')}°C)
    👤 Preferences: {activities}
    🎫 Events Nearby: {events}
    🏞️ Places Nearby: {places}
    📰 Blogs: {blogs}

Suggest a smart activity or blog to the user with a brief natural sentence.
"""
    return prompt