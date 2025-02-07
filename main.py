# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from scraper import extract_listing_data
from notion_integration import create_notion_entry

app = FastAPI(
    title="New England Listings API",
    description="Scrapes listing data from a provided URL and creates an entry in Notion",
    version="1.0.0"
)

@app.post("/add_listing")
async def add_listing(req: Request):
    try:
        req_data = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    url = req_data.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL not provided")
    
    try:
        # Extract listing data using your scraper.
        data = extract_listing_data(url)
        # Create a new entry in your Notion database.
        result = create_notion_entry(data)
        return JSONResponse(content={"message": "Entry created", "id": result.get("id")})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
