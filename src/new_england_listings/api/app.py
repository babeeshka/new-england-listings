# src/new_england_listings/api/app.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from new_england_listings import process_listing

app = FastAPI(
    title="New England Listings API",
    description="Scrapes property data from URLs and creates Notion entries",
    version="0.1.0"
)


class ListingRequest(BaseModel):
    url: str
    use_notion: bool = True


@app.post("/process-listing")
async def process_listing_endpoint(request: ListingRequest):
    try:
        data = process_listing(request.url, use_notion=request.use_notion)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
