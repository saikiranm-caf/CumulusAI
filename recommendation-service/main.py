# recommendation-service/main.py

import os
import requests
import asyncio
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from dotenv import load_dotenv

from schemas import RecommendationRequest, RecommendationResponse
from publisher import publish_recommendation_request
from config import settings
from tasks import process_recommendation_task  # Import the function, not the app

load_dotenv()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Blocking and non-blocking recommendation endpoints"
)

LLM_MODEL   = settings.LLM_MODEL # Use settings from config.py
GATEWAY_URL = settings.GATEWAY_URL # Use settings from config.py

# In-memory store for async results (swap out for DB/Redis in prod)
_async_results: dict[str, str] = {}


# --- Blocking Recommendation Endpoint ---
@app.get(
    "/recommendation",
    summary="🔄 Blocking: run all calls + LLM, then return",
    response_model=RecommendationResponse
)
async def recommend(
    user_id: str  = Query(..., description="Your user ID"),
    lat:     float = Query(..., description="Latitude"),
    lon:     float = Query(..., description="Longitude"),
):
    try:
        # Call the task function directly
        prompt_content = await process_recommendation_task(
            RecommendationRequest(user_id=user_id, lat=lat, lon=lon)
        )

        # Now, call the LLM with the generated prompt
        print("🔥 Calling LLM with prompt:")
        print(prompt_content)

        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model":  LLM_MODEL,
                "prompt": prompt_content,
                "stream": False
            }
        ).json()

        recommendation = resp.get("response", "No suggestion available.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"recommendation": recommendation}


# --- Non-blocking Recommendation Endpoint (using RabbitMQ) ---
@app.get(
    "/recommendation/async",
    summary="⚡ Non-blocking: enqueue & return immediately via RabbitMQ"
)
async def recommend_async(
    user_id:          str   = Query(...),
    lat:              float = Query(...),
    lon:              float = Query(...),
):
    """
    Publishes a recommendation request to RabbitMQ and returns immediately.
    The result can be polled via /recommendation/result.
    """
    task_payload = RecommendationRequest(user_id=user_id, lat=lat, lon=lon)
    await publish_recommendation_request(task_payload)
    return {"message": f"Enqueued recommendation for {user_id}. Poll /recommendation/result for status."}


# --- Endpoint to poll for async results ---
@app.get(
    "/recommendation/result",
    summary="📥 Poll for async recommendation result",
    response_model=RecommendationResponse # Can be pending or ready
)
def get_recommendation_result(
    user_id: str = Query(..., description="Your user ID")
):
    """
    Returns pending/ready + the recommendation when ready.
    """
    if user_id not in _async_results:
        return {"status": "pending", "recommendation": None} # Return None for recommendation when pending

    return {
        "status":         "ready",
        "recommendation": _async_results.pop(user_id)
    }

# --- Background Worker for RabbitMQ Consumer to store results ---
# This function will be called by the RabbitMQ consumer (consumer.py)
# to store the final LLM output in our in-memory cache.
async def store_async_recommendation(user_id: str, recommendation_text: str):
    """
    Stores the completed recommendation in the in-memory dictionary.
    This function will be called by the RabbitMQ consumer after processing.
    """
    _async_results[user_id] = recommendation_text
    print(f"✅ Stored async result for user {user_id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", host="0.0.0.0", port=settings.PORT, reload=True
    )