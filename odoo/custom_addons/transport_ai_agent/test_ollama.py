from langchain_ollama import OllamaLLM, OllamaEmbeddings
from dotenv import load_dotenv
import os

load_dotenv()

llm = OllamaLLM(
    base_url=os.getenv("OLLAMA_BASE_URL"),
    model=os.getenv("OLLAMA_MODEL")
)
reponse = llm.invoke("Réponds en français : qu'est-ce qu'une tournée de bus ?")
print("LLM OK :", reponse[:200])

embeddings = OllamaEmbeddings(
    base_url=os.getenv("OLLAMA_BASE_URL"),
    model=os.getenv("OLLAMA_EMBED_MODEL")
)
vec = embeddings.embed_query("tournée de bus")
print(f"Embeddings OK — dimension : {len(vec)}")