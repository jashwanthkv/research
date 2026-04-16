import os
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from dotenv import load_dotenv
load_dotenv()

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# Initialize Shared LLM
llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0,
    api_key=os.getenv("API_KEY")
)

llm_model_name = "sentence-transformers/all-MiniLM-L6-v2"
embeddings = HuggingFaceEmbeddings(
    model_name=llm_model_name
)


llm_extract = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY_EXTRACT"),
    model="openai/gpt-oss-120b",
    temperature=0
)

# 🔹 2. Paper synthesis LLM
llm_synth = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY_SYNTH"),
    model="openai/gpt-oss-120b",
    temperature=0
)

# 🔹 3. Overall trends LLM (can reuse synth)
llm_trends = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY_TRENDS"),
    model="openai/gpt-oss-120b",
    temperature=0
)