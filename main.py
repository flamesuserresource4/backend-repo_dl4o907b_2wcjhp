import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from random import choice
from bson import ObjectId

from database import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PromptCreate(BaseModel):
    option_a: str = Field(..., min_length=3, max_length=140)
    option_b: str = Field(..., min_length=3, max_length=140)
    category: str = Field("general")
    created_by: Optional[str] = None


class PromptResponse(BaseModel):
    id: str
    option_a: str
    option_b: str
    category: str
    created_by: Optional[str] = None
    a_count: int
    b_count: int


class VoteRequest(BaseModel):
    prompt_id: str
    option: str = Field(..., pattern="^(a|b)$")


@app.get("/")
def read_root():
    return {"message": "Family Would You Rather API"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "Unknown"
            response["connection_status"] = "Connected"
            collections = db.list_collection_names()
            response["collections"] = collections[:10]
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:100]}"
    return response


# Utility to seed starter prompts if collection empty
STARTER_PROMPTS = [
    ("be able to fly for a day", "turn invisible for a day"),
    ("eat pancakes for dinner", "eat pizza for breakfast"),
    ("have a pet dinosaur", "have a pet dragon"),
    ("swim with dolphins", "camp under the stars"),
    ("build a giant pillow fort", "have a massive water balloon fight"),
    ("never do homework again", "never do chores again"),
]


def _serialize(doc) -> PromptResponse:
    return PromptResponse(
        id=str(doc.get("_id")),
        option_a=doc.get("option_a"),
        option_b=doc.get("option_b"),
        category=doc.get("category", "general"),
        created_by=doc.get("created_by"),
        a_count=int(doc.get("a_count", 0)),
        b_count=int(doc.get("b_count", 0)),
    )


def _ensure_seeded():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    count = db["prompt"].count_documents({})
    if count == 0:
        for a, b in STARTER_PROMPTS:
            db["prompt"].insert_one({
                "option_a": a,
                "option_b": b,
                "category": "general",
                "created_by": "seed",
                "a_count": 0,
                "b_count": 0,
            })


@app.get("/api/prompts/random", response_model=PromptResponse)
def get_random_prompt():
    _ensure_seeded()
    docs = list(db["prompt"].aggregate([{ "$sample": { "size": 1 } }]))
    if not docs:
        raise HTTPException(status_code=404, detail="No prompts available")
    return _serialize(docs[0])


@app.post("/api/prompts", response_model=PromptResponse)
def create_prompt(body: PromptCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    doc = body.model_dump()
    doc.update({"a_count": 0, "b_count": 0})
    res = db["prompt"].insert_one(doc)
    doc["_id"] = res.inserted_id
    return _serialize(doc)


@app.post("/api/votes", response_model=PromptResponse)
def vote(body: VoteRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(body.prompt_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid prompt_id")
    field = "a_count" if body.option == "a" else "b_count"
    updated = db["prompt"].find_one_and_update(
        {"_id": oid},
        {"$inc": {field: 1}},
        return_document=True
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _serialize(updated)


@app.get("/api/prompts/top", response_model=List[PromptResponse])
def top_prompts(limit: int = 10):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    docs = db["prompt"].find({}).sort([("a_count", -1), ("b_count", -1)]).limit(limit)
    return [_serialize(d) for d in docs]


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
