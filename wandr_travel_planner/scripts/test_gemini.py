"""Quick sanity test: can we talk to Groq at all?"""
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    temperature=0.0,
    groq_api_key=os.getenv("GROQ_API_KEY"),
)

response = llm.invoke("Say 'hello from Groq' and nothing else.")
print("Response:", response.content)
