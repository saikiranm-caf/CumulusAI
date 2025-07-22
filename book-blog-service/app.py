# book-blog-service/app.py
from fastapi import FastAPI, Query
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "your_api_key_here")

port = int(os.getenv("PORT", 8006))

@app.get("/blogs")
def get_blogs(query: str = Query("local activities", description="Search query, e.g., 'local activities'"),
              language: str = Query("en", description="Language code"),
              max_results: int = Query(1, description="Max number of results")):
    print(f"🔥Control at blogs")
    url = (
        f"https://newsapi.org/v2/everything?q={query}+travel+OR+lifestyle+-politics+-business"
        f"&language={language}&sortBy=relevancy&pageSize={max_results}&apiKey={NEWS_API_KEY}"
    )
    response = requests.get(url)
    data = response.json()

    if data.get("status") != "ok":
        return {"error": "Failed to fetch data from NewsAPI"}

    articles = data.get("articles", [])
    return {
        "total_results": len(articles),
        "blogs": [
            {
                "title": article.get("title"),
                "description": article.get("description"),
                "url": article.get("url"),
                "image": article.get("urlToImage"),
                "published": article.get("publishedAt"),
                "source": article.get("source", {}).get("name"),
            }
            for article in articles
        ],
    }