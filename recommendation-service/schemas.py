# schemas.py

from pydantic import BaseModel
from typing import List, Optional

class RecommendationRequest(BaseModel):
    """Message sent from API gateway to the worker via RabbitMQ."""
    user_id: str
    lat: float
    lon: float
    age: Optional[int] = None  # Optional user age
    gender: Optional[str] = None  # Optional user gender (e.g., M, F)
    time_of_day: Optional[str] = None  # Optional time as string (e.g., "01:25 PM", "10:10 AM")
    motion_state: Optional[str] = None  # Optional user motion state (e.g., "walking")

class Activity(BaseModel):
    activity_name: str
    activity_description: Optional[str] = None

class Event(BaseModel):
    title: str
    date_time: Optional[str] = None
    venue: Optional[str] = None
    price: Optional[str] = None
    url: Optional[str] = None
    full_date_time: Optional[str] = None
    map_location: Optional[str] = None

class Place(BaseModel):
    name: str
    location_address: Optional[str] = None
    distance_km: Optional[float] = None
    category: Optional[str] = None
    place_link: Optional[str] = None

class Blog(BaseModel):
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    image: Optional[str] = None
    published: Optional[str] = None
    source: Optional[str] = None

class RecommendationPayload(BaseModel):
    """
    Aggregated context passed into the LLM:
      - display of location/weather
      - lists of activities, events, places, blogs
    """
    location_display: str
    weather_desc: str
    weather_temp: float
    activities: List[Activity]
    events: List[Event]
    places: List[Place]
    blogs: List[Blog]

class RecommendationResponse(BaseModel):
    """Response returned by the API gateway after enqueuing (or by the gateway once the worker replies)."""
    status: str  # Added status field
    recommendation: Optional[str] = None  # Made recommendation optional