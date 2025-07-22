# recommendation-service/tasks.py
import asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from config import settings
from rpc_client import rpc_call
from datetime import datetime
import pytz
import tensorflow as tf
import numpy as np
import logging

logger = logging.getLogger(__name__)

app = FastAPI()

class RecommendationRequest(BaseModel):
    user_id: str
    lat: float
    lon: float
    age: Optional[int] = None
    gender: Optional[str] = None
    time_of_day: Optional[str] = None
    motion_state: Optional[str] = None  # Added optional motion_state

# Predefined messages for model predictions with comments for clarity
MESSAGES = [
    "You're in a green space. Let's disconnect to reconnect.",  # 0: Near_Park
    "Sweat mode activated! Your focus is your fitness.",  # 1: In_Gym
    "Time to learn! Playtime resumes after school hours.",  # 2: At_School_Zone
    "Shop smart, stay sharp! Enjoy offers while keeping distractions away.",  # 3: In_Shopping_Mall
    "A moment of peace. Your phone joins the calm.",  # 4: At_Religious_Place
    "Quiet zone activated. Calls and health alerts only.",  # 5: Near_Hospital
    "Nature’s therapy is here. Relax, your device will too.",  # 6: At_Beach_or_Lake
    "Book mode on. Notifications turned down for wisdom.",  # 7: At_Library
    "Enjoy the show! Your phone is quietly watching too.",  # 8: At_Movie_Theatre
    "Eyes on the road. Drive mode is protecting you.",  # 9: Driving
    "Privacy first. You're in control of what appears.",  # 10: Female_in_Public
    "Focus zone: Social media returns after your study session.",  # 11: Teen_at_Home_Study
    "Let’s play safe. Learning games only for now.",  # 12: Child_at_Play
    "Easy view activated. You’re just a tap away from what matters.",  # 13: Elderly_User
    "Time to rest. Sleep mode will hold your messages till morning.",  # 14: Late_Night_Use
    "Work mode engaged. Productivity is your priority.",  # 15: Work_Hours
    "It’s the weekend! Work apps are snoozing for now.",  # 16: Weekend_Chill
    "Capture moments, not distractions. Event mode is live!",  # 17: At_Outdoor_Event
    "Welcome home! Your digital space is open and ready.",  # 18: At_Home
    "Steps count. Your phone's cheering for your next move!"  # 19: Walking_Jogging
]

# Mapping from message_index to fetch types and queries for dynamic fetching
CATEGORY_MAPPINGS = {
    0: {"type": "places", "query": "park"},  # Near_Park
    1: {"type": "places", "query": "gym"},  # In_Gym
    2: {"type": "places", "query": "school"},  # At_School_Zone
    3: {"type": "places", "query": "shopping mall"},  # In_Shopping_Mall
    4: {"type": "places", "query": "temple"},  # At_Religious_Place
    5: {"type": "places", "query": "cafe"},  # Near_Hospital (suggest quiet cafe)
    6: {"type": "places", "query": "beach"},  # At_Beach_or_Lake
    7: {"type": "places", "query": "library"},  # At_Library
    8: {"type": "places", "query": "movie theater"},  # At_Movie_Theatre
    9: {"type": "none"},  # Driving (no fetch)
    10: {"type": "none"},  # Female_in_Public
    11: {"type": "blogs", "query": "study tips"},  # Teen_at_Home_Study
    12: {"type": "places", "query": "playground"},  # Child_at_Play
    13: {"type": "none"},  # Elderly_User
    14: {"type": "none"},  # Late_Night_Use
    15: {"type": "none"},  # Work_Hours
    16: {"type": "blogs", "query": "weekend relaxation"},  # Weekend_Chill
    17: {"type": "events"},  # At_Outdoor_Event
    18: {"type": "none"},  # At_Home
    19: {"type": "places", "query": "walking trail"}  # Walking_Jogging
}

# Load model on startup
model = tf.keras.models.load_model(settings.MODEL_PATH)

@app.get("/recommendation/async")
async def recommend_async(req: RecommendationRequest):
    asyncio.create_task(process_recommendation_task(req))
    return {"message": f"Enqueued recommendation for {req.user_id}"}

@app.get("/recommendation")
async def recommend(req: RecommendationRequest):
    prompt = await process_recommendation_task(req)
    return {"recommendation": prompt}

async def process_recommendation_task(task: RecommendationRequest) -> str:
    user_id = task.user_id
    lat = task.lat
    lon = task.lon
    age = task.age
    gender = task.gender
    time_of_day = task.time_of_day
    motion_state = task.motion_state  # Use the provided motion_state

    # Parse time_of_day
    parsed_time = time_of_day if time_of_day else "unknown"
    if time_of_day and len(time_of_day.split()) == 2:
        hour, period = time_of_day.split()[0].split(':')[0], time_of_day.split()[1]
        parsed_time = f"{hour} {period}"

    # Fetch location, weather, and user prefs (always needed)
    location = await rpc_call(
        settings.LOCATION_RPC_QUEUE,
        {"lat": lat, "lon": lon, "time": time_of_day, "user_id": user_id, "age": age, "gender": gender, "motion_state": motion_state}
    )
    weather = await rpc_call(settings.WEATHER_RPC_QUEUE, {"lat": lat, "lon": lon})
    prefs_resp = await rpc_call(settings.USER_PREFS_RPC_QUEUE, {"user_id": user_id})
    activities = prefs_resp.get("activities", [])  # Assume this includes behaviors if expanded

    # Adjust activity flags based on user preferences (if available)
    activities_flags = location.get("activities", {})
    if activities:
        # Example: If user prefers "fitness", boost gym/walking flags
        for activity in activities:
            if "fitness" in activity.lower():
                activities_flags["In_Gym"] = 1
                activities_flags["Walking_Jogging"] = 1
            # Add more preference-based adjustments as needed

    # Neural Network Prediction
    input_data = np.array([[
        age or 30,
        1 if gender == "M" else 0,
        1 if gender == "F" else 0,
        activities_flags.get("Near_Park", 0),
        activities_flags.get("In_Gym", 0),
        activities_flags.get("At_School_Zone", 0),
        activities_flags.get("In_Shopping_Mall", 0),
        activities_flags.get("At_Religious_Place", 0),
        activities_flags.get("Near_Hospital", 0),
        activities_flags.get("At_Beach_or_Lake", 0),
        activities_flags.get("At_Library", 0),
        activities_flags.get("At_Movie_Theatre", 0),
        activities_flags.get("Driving", 0),
        activities_flags.get("Female_in_Public", 0),
        activities_flags.get("Teen_at_Home_Study", 0),
        activities_flags.get("Child_at_Play", 0),
        activities_flags.get("Elderly_User", 0),
        activities_flags.get("Late_Night_Use", 0),
        activities_flags.get("Work_Hours", 0),
        activities_flags.get("Weekend_Chill", 0),
        activities_flags.get("At_Outdoor_Event", 0),
        activities_flags.get("At_Home", 0),
        activities_flags.get("Walking_Jogging", 0)
    ]])
    prediction = model.predict(input_data)
    message_index = np.argmax(prediction)
    recommended_message = MESSAGES[message_index]
    logger.info(f"Predicted message index: {message_index}, message: {recommended_message}")

    # Dynamic conditional data fetching based on category mapping
    places, events, blogs = [], [], []
    mapping = CATEGORY_MAPPINGS.get(message_index, {"type": "none"})
    fetch_type = mapping.get("type", "none")
    
    if fetch_type == "places":
        query = mapping.get("query", "relaxation spot")  # Fallback query
        places_resp = await rpc_call(settings.PLACES_RPC_QUEUE, {"lat": lat, "lon": lon, "query": query})
        places = places_resp.get("places", [])
    elif fetch_type == "events":
        events_resp = await rpc_call(settings.EVENTS_RPC_QUEUE, {"state": location.get("address", {}).get("state", ""), "country": location.get("address", {}).get("country", "")}, timeout=120.0)
        events = events_resp.get("events", [])
    elif fetch_type == "blogs":
        query = mapping.get("query", "local activities")  # Fallback query
        blogs_resp = await rpc_call(settings.BLOGS_RPC_QUEUE, {"query": query})
        blogs = blogs_resp.get("blogs", [])

    # Log responses for debugging
    logger.info(f"Location: {location}")
    logger.info(f"Weather: {weather}")
    logger.info(f"User preferences: {activities}")
    logger.info(f"Places: {places}")
    logger.info(f"Events: {events}")
    logger.info(f"Blogs: {blogs}")

    # Strengthened prompt to prevent hallucinations and ensure dynamism
    prompt = f"""
        You are a friendly local guide. Your goal is to suggest ONE personalized activity based STRICTLY on the predicted category and provided context. Focus ONLY on recommending a specific activity (e.g., visiting a place, attending an event). Do NOT invent, alter, or add any locations, activities, or details—use EXACTLY the provided data without changes. If no relevant data is provided, suggest a simple activity tied directly to the category.

        Predicted category: {recommended_message}

        Context (MUST USE THESE EXACT VALUES WITHOUT ALTERATION):
        Location: {location.get('display_name', 'Unknown Location')} (use this exact name; do not change or shorten it)
        Weather: {weather.get('description', 'N/A')} at {weather.get('temperature', 'N/A')}°C
        Time: {parsed_time}
        User: Age {age or 'unknown'}, Gender {gender or 'unknown'}
        Preferences: {activities or 'None'} (prioritize these if available; incorporate one if it fits the category)

        Relevant data (use only if applicable and provided; select the most relevant one and integrate exactly):
        Places: {places[0] if places else 'None'}
        Events: {events[0] if events else 'None'}
        Blogs: {blogs[0] if blogs else 'None'}

        Output: A short, friendly sentence suggesting one specific activity with emojis (e.g., '☕ Relax at Nearby Cafe in Exact Location Name during this cloudy afternoon!'). Keep it concise and actionable.
    """
    logger.info(f"Prompt sent to LLM: {prompt}")
    return prompt