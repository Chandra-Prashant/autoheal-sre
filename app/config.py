import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# llama-3.3-70b-versatile isn't available on this project's Groq key (404
# model_not_found) - openai/gpt-oss-120b is the closest available tier
GROQ_MODEL = "openai/gpt-oss-120b"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")

CHROMA_DIR = os.getenv("CHROMA_DIR", ".chroma")


def get_llm(temperature: float = 0.2):
    return ChatGroq(model=GROQ_MODEL, groq_api_key=GROQ_API_KEY, temperature=temperature)
