from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import re
import requests

from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
SERPER_KEY = os.getenv("SERPER_API_KEY")

if not API_KEY:
    raise ValueError("Missing OPENROUTER_API_KEY in environment")

if not SERPER_KEY:
    raise ValueError("Missing SERPER_API_KEY in environment")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = "sqlite:///./nexus.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    user_message = Column(Text)
    ai_response = Column(Text)

Base.metadata.create_all(bind=engine)

class ChatRequest(BaseModel):
    message: str

user_profiles = {}

def extract_user_info(user_id, message):
    msg = message.lower()

    patterns = [
        r"my name is (\w+)",
        r"i am (\w+)",
        r"i'm (\w+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, msg)
        if match:
            name = match.group(1).capitalize()
            user_profiles[user_id] = {"name": name}


def build_memory_context(user_id):
    profile = user_profiles.get(user_id, {})
    context = ""

    if "name" in profile:
        context += f"The user's name is {profile['name']}.\n"

    return context


def build_chat_context(db, user_id):
    chats = db.query(Chat).filter(Chat.user_id == user_id).order_by(Chat.id.desc()).limit(5).all()

    context = ""
    for chat in reversed(chats):
        context += f"User: {chat.user_message}\nAI: {chat.ai_response}\n"

    return context


def search_web(query):
    url = "https://google.serper.dev/search"

    payload = {
        "q": query,
        "num": 5
    }

    headers = {
        "X-API-KEY": SERPER_KEY,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=3)
        data = response.json()

        articles = []

        if "organic" in data:
            for item in data["organic"][:5]:
                articles.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link": item.get("link", "")
                })

        return articles

    except Exception as e:
        print("SERPER ERROR:", str(e))
        return []


async def get_ai_response(user_input, memory_context, chat_context):
    url = "https://openrouter.ai/api/v1/chat/completions"
    print("API KEY LOADED:", bool(API_KEY))
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = f"""
You are Nexus AI.

Rules:
- Be clear, concise, and helpful
- Use memory and conversation context

Memory:
{memory_context}

Conversation:
{chat_context}
"""

    data = {
        "model": "nvidia/nemotron-3-nano-30b-a3b:free",
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_input.strip()}
        ],
        "temperature": 0.6,
        "max_tokens": 300
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=data)

        result = response.json()

        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            print("OPENROUTER ERROR:", result)
            return "AI failed to respond. Try again."

    except Exception as e:
        print("AI ERROR:", str(e))
        return "Server busy. Try again."


@app.get("/")
def home():
    return {"message": "Nexus AI backend is running 🚀"}


@app.post("/chat")
async def chat(req: ChatRequest):

    if not req.message.strip():
        return {"type": "text", "response": "Say something first."}

    db = SessionLocal()

    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(id=1, name="User")
        db.add(user)
        db.commit()

    user_id = user.id

    extract_user_info(user_id, req.message)
    memory_context = build_memory_context(user_id)
    chat_context = build_chat_context(db, user_id)

    trigger_words = [
        "news", "latest", "today", "current",
        "stock", "market", "economy", "trend"
    ]

    if any(word in req.message.lower() for word in trigger_words):
        articles = search_web(req.message)
        db.close()

        if articles:
            return {"type": "news", "articles": articles}
        else:
            return {"type": "text", "response": "Couldn't fetch news right now."}

    reply = await get_ai_response(req.message, memory_context, chat_context)

    chat_entry = Chat(
        user_id=user_id,
        user_message=req.message,
        ai_response=reply
    )

    response_data = {
        "type": "text",
        "response": reply
    }

    db.add(chat_entry)
    db.commit()
    db.close()

    return response_data