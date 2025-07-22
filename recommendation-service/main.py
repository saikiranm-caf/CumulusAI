# recommendation-service/main.py
import os
import requests
import asyncio
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from dotenv import load_dotenv
import redis.asyncio as redis
from schemas import RecommendationRequest, RecommendationResponse
from publisher import publish_recommendation_request
from config import settings
from tasks import process_recommendation_task
import logging

logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Blocking and non-blocking recommendation endpoints"
)

LLM_MODEL = settings.LLM_MODEL
GATEWAY_URL = settings.GATEWAY_URL
redis_client: redis.Redis = None

@app.on_event("startup")
async def startup_event():
    global redis_client
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await redis_client.ping()
        logger.info("💡 Connected to Redis")
    except redis.exceptions.ConnectionError as e:
        logger.error(f"❌ Could not connect to Redis: {e}")
        raise ConnectionError(f"Failed to connect to Redis on startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    if redis_client:
        await redis_client.close()
        logger.info("🛑 Disconnected from Redis")

@app.get(
    "/recommendation",
    summary="🔄 Blocking: run all calls + LLM, then return",
    response_model=RecommendationResponse
)
async def recommend(
    user_id: str = Query(..., description="Your user ID"),
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    age: int = Query(None, description="User age, optional"),
    gender: str = Query(None, description="User gender, optional (M/F)"),
    time_of_day: str = Query(None, description="Time of day, optional (e.g., '01:25 PM')"),
    motion_state: str = Query(None, description="User motion state, optional (e.g., 'walking')")
):
    try:
        prompt_content = await process_recommendation_task(
            RecommendationRequest(user_id=user_id, lat=lat, lon=lon, age=age, gender=gender, time_of_day=time_of_day,motion_state=motion_state)
        )
        llm_resp = await asyncio.to_thread(
            requests.post,
            "http://localhost:11434/api/generate",
            json={
                "model": LLM_MODEL,
                "prompt": prompt_content,
                "stream": False
            }
        )
        llm_resp.raise_for_status()
        recommendation_text = llm_resp.json().get("response", "No suggestion available.")
        logger.info(f"LLM response: {recommendation_text}")
        
        # Store in Redis for async polling
        await redis_client.set(f"recommendation:{user_id}", recommendation_text)
        print(f"Stored recommendation for {user_id}: {recommendation_text}")
        return {"status": "ready", "recommendation": recommendation_text}
    except Exception as e:
        logger.error(f"Error in recommendation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/recommendation/async",
    summary="🚀 Non-blocking: enqueue, return immediately",
    response_model=dict
)
async def recommend_async(
    background_tasks: BackgroundTasks,
    user_id: str = Query(..., description="Your user ID"),
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    age: int = Query(None, description="User age, optional"),
    gender: str = Query(None, description="User gender, optional (M/F)"),
    time_of_day: str = Query(None, description="Time of day, optional (e.g., '01:25 PM')"),
    motion_state: str = Query(None, description="User motion state, optional (e.g., 'walking')")
):
    task_payload = RecommendationRequest(user_id=user_id, lat=lat, lon=lon, age=age, gender=gender, time_of_day=time_of_day, motion_state=motion_state)
    background_tasks.add_task(publish_recommendation_request, task_payload)
    return {"message": f"Enqueued recommendation for {user_id}. Poll /recommendation/result for status."}

@app.get(
    "/recommendation/result",
    summary="📥 Poll for async recommendation result",
    response_model=RecommendationResponse
)
async def get_recommendation_result(
    user_id: str = Query(..., description="Your user ID")
):
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis client not initialized.")
    
    try:
        recommendation_text = await redis_client.get(f"recommendation:{user_id}")
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Redis connection error: {e}")
        raise HTTPException(status_code=500, detail=f"Redis connection error: {e}")

    if recommendation_text is None:
        return {"status": "pending", "recommendation": None}

    try:
        await redis_client.delete(f"recommendation:{user_id}")
    except redis.exceptions.ConnectionError as e:
        logger.warning(f"Could not delete from Redis for user {user_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error deleting from Redis for user {user_id}: {e}")
    print(f"Stored recommendation for {user_id}: {recommendation_text}")
    return {
        "status": "ready",
        "recommendation": recommendation_text
    }