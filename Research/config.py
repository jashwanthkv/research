import os
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from dotenv import load_dotenv
load_dotenv()

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


llm = ChatGroq(
    model="llama-3.3-70b-versatile",   # best general-purpose on Groq
    temperature=0.7,
    api_key=os.getenv("API_KEY")
)

llm_extract = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY_EXTRACT"),
    model="llama-3.3-70b-versatile",
    temperature=0.7
)

llm_synth = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY_SYNTH"),
    model="llama-3.3-70b-versatile",
    temperature=0.7
)

llm_trends = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY_TRENDS"),
    model="llama-3.3-70b-versatile",
    temperature=0.7
)

llm_model_name = "sentence-transformers/all-MiniLM-L6-v2"
embeddings = HuggingFaceEmbeddings(
    model_name=llm_model_name
)


# config.py
