import os

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")


def get_embeddings_client() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)


def get_llm_client() -> ChatOpenAI:
    return ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0)


def embed_text(text: str) -> list[float]:
    """Embed a single query string."""
    return get_embeddings_client().embed_query(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed a list of document strings."""
    return get_embeddings_client().embed_documents(texts)
