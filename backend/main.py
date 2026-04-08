from dotenv import load_dotenv
import os
load_dotenv()

from fastapi import FastAPI
from pydantic import BaseModel
import httpx
from fastapi.middleware.cors import CORSMiddleware
import re
import requests

from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base

# 🔥 ENV

API_KEY = os.getenv("OPENROUTER_API_KEY")
SERPER_KEY = os.getenv("SERPER_API_KEY")

if not API_KEY:
raise ValueError("Missing OPENROUTER_API_KEY")

# 🚀 APP

app = FastAPI()

app.add_middleware(
CORSMiddleware,
allow_origins=["*"],
allow_credentials=True,
allow_methods=["*"],
allow_headers=["*"],
)

# 🧠 DB

DATABASE_URL = "sqlite:///./nexus.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
**tablename** = "users"
id = Column(Integer, primary_key=True)
name = Column(String)

class Chat(Base):
**tablename** = "chats"
id = Column(Integer, primary_key=True)
user_id = Column(Integer)
user_message = Column(Text)
ai_response = Column(Text)

Base.metadata.create_all(bind=engine)

# 📥 REQUEST

class ChatRequest(BaseModel):
message: str

user_profiles = {}

# 🧠 MEMORY

def extract_user_info(user_id, message):
msg = message.lower()
patterns = [r"my name is (\w+)", r"i am (\w+)", r"i'm (\w+)"]

```
for pattern in patterns:
    match = re.search(pattern, msg)
    if match:
        user_profiles[user_id] = {"name": match.group(1).capitalize()}
```

def build_memory_context(user_id):
profile = user_profiles.get(user_id, {})
if "name" in profile:
return f"The user's name is {profile['name']}.\n"
return ""

def build_chat_context(db, user_id):
chats = db.query(Chat).filter(Chat.user_id == user_id).order_by(Chat.id.desc()).limit(5).all()
context = ""
for chat in reversed(chats):
context += f"User: {chat.user_message}\nAI: {chat.ai_response}\n"
return context

# 🌐 SEARCH

def search_web(query):
url = "https://google.serper.dev/search"

```
headers = {
    "X-API-KEY": SERPER_KEY,
    "Content-Type": "application/json"
}

try:
    response = requests.post(url, json={"q": query}, headers=headers)
    data = response.json()

    return [
        {
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "link": item.get("link")
        }
        for item in data.get("organic", [])[:5]
    ]
except Exception as e:
    print("SERPER ERROR:", e)
    return []
```

# 🤖 AI

async def get_ai_response(user_input, memory_context, chat_context):
url = "https://openrouter.ai/api/v1/chat/completions"

```
system_prompt = f"""
```

You are Nexus AI.
Be smart, natural, and helpful.

Memory:
{memory_context}

Conversation:
{chat_context}
"""

```
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

data = {
    "model": "nvidia/nemotron-3-super-120b-a12b:free",
    "messages":[
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_input.strip()}
    ],
    "temperature": 0.7,
    "max_tokens": 250
}

try:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=data)

    if response.status_code != 200:
        return "AI error: " + response.text

    result = response.json()
    return result["choices"][0]["message"]["content"]

except Exception as e:
    print("AI ERROR:", e)
    return "AI service error."
```

# 🏠 ROOT

@app.get("/")
def home():
return {"message": "Nexus AI backend is running 🚀"}

# 💬 CHAT

@app.post("/chat")
async def chat(req: ChatRequest):

```
if not req.message.strip():
    return {"type": "text", "response": "Say something first."}

db = SessionLocal()

# ✅ FIX: auto-create user
user = db.query(User).filter(User.id == 1).first()
if not user:
    user = User(id=1, name="User")
    db.add(user)
    db.commit()

user_id = user.id

# memory
extract_user_info(user_id, req.message)
memory_context = build_memory_context(user_id)
chat_context = build_chat_context(db, user_id)

# 🔥 trigger words
trigger_words = [
    "news", "latest", "today", "current",
    "stock", "market",
    "recent", "update", "developments", "trends"
]

if any(word in req.message.lower() for word in trigger_words):
    articles = search_web(req.message)
    db.close()

    if articles:
        return {"type": "news", "articles": articles}
    return {"type": "text", "response": "Couldn't fetch news."}

# AI response
reply = await get_ai_response(req.message, memory_context, chat_context)

db.add(Chat(user_id=user_id, user_message=req.message, ai_response=reply))
db.commit()
db.close()

return {"type": "text", "response": reply}
```
