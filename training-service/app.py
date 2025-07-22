# app.py
from fastapi import FastAPI, HTTPException
import os
import requests
import pandas as pd
import train
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
port = int(os.getenv("PORT", 8010))
app = FastAPI()

# Configuration for location-service API
LOCATION_SERVICE_URL = os.getenv("LOCATION_SERVICE_URL", "http://localhost:8002")
MIN_DATA_ROWS = 5  # Minimum number of rows to consider new data sufficient

# app.py (partial update for /train function)
@app.post("/train")
def train_model():
    try:
        # Fetch data from location-service
        logger.info("Attempting to fetch data from location-service...")
        response = requests.get(
            f"{LOCATION_SERVICE_URL}/location",
            params={
                "lat": 37.7749,
                "lon": -122.4194,
                "time": "12:23 PM",  # Updated to current time
                "user_id": "user123",
                "age": 30,
                "gender": "M",
                "motion_state": "walking"
            },
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        if not data or "activities" not in data:
            logger.warning("Invalid or empty response from location-service")
            raise ValueError("No valid activity data received")

        # Process activity context into DataFrame with default Message_Index
        activities = data["activities"]
        new_data = pd.DataFrame([{
            "Age": data.get("age", 30),
            "Gender_M": 1 if data.get("gender", "M").lower() == "m" else 0,
            "Gender_F": 1 if data.get("gender", "M").lower() == "f" else 0,
            **{k: v for k, v in activities.items()},
            "Message_Index": 0  # Default value for new data
        }])

        # Ensure minimum data rows
        if len(new_data) < MIN_DATA_ROWS:
            logger.info(f"Insufficient new data ({len(new_data)} rows), falling back to training_data.csv")
            fallback_data = pd.read_csv("training_data.csv")
            new_data = pd.concat([new_data, fallback_data], ignore_index=True)

        # Save updated data
        new_data.to_csv("training_data.csv", index=False)
        logger.info("Data saved to training_data.csv")

        # Train the model
        train.main()
        logger.info("Training completed successfully")

        return {"status": "training completed", "model_path": os.getenv("MODEL_PATH", "recommendation_model.h5")}

    except requests.RequestException as e:
        logger.error(f"Failed to connect to location-service: {e}")
        try:
            logger.info("Falling back to training_data.csv")
            train.main()
            return {"status": "training completed (fallback)", "model_path": os.getenv("MODEL_PATH", "recommendation_model.h5")}
        except Exception as fallback_e:
            logger.error(f"Fallback failed: {fallback_e}")
            raise HTTPException(status_code=500, detail="Training failed, no valid data available")
    except Exception as e:
        logger.error(f"Training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
def get_status():
    last_trained = os.getenv("LAST_TRAINED", "never")
    return {"status": "ready", "last_trained": last_trained}