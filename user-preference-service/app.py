from fastapi import FastAPI, Query
from service import fetch_user_preferences
import os
port = int(os.getenv("PORT", 8005))
app = FastAPI()

@app.get("/user-preferences")
def get_user_preferences(user_id: str = Query(...)):
    activities = fetch_user_preferences(user_id)
    return {
        "user_id": user_id,
        "preferred_activities": activities
    }
