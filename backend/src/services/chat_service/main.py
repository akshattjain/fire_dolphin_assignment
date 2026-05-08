from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

SYSTEM_PROMPT = (
    "You are an expert code analyst. "
    "Answer questions about the codebase strictly using the provided code context. "
    "Always cite the exact file path and line numbers (e.g. `src/auth/login.py:42-67`). "
    "Format code snippets inside markdown code blocks with the language tag. "
    "If the answer is not in the provided context, say so clearly instead of guessing."
)

HISTORY_WINDOW = 10  # number of prior turns to include


def build_context_block(search_results: list[dict]) -> str:
    """Format Qdrant search results into a readable context block."""
    parts: list[str] = []
    for i, result in enumerate(search_results, 1):
        p = result["payload"]
        header = (
            f"[{i}] {p['file_path']} "
            f"(lines {p['start_line']}–{p['end_line']}) "
            f"| {p['chunk_type']}: {p.get('name') or 'N/A'}"
        )
        body = f"```{p.get('language', '')}\n{p['content']}\n```"
        parts.append(f"{header}\n{body}")
    return "\n\n---\n\n".join(parts)


def answer_question(
    question: str,
    search_results: list[dict],
    chat_history: list[dict],
) -> str:
    """Run the RAG chain: inject context + history and call the LLM."""
    from src.services.llm_service.main import get_llm_client

    llm = get_llm_client()
    messages: list = [SystemMessage(content=SYSTEM_PROMPT)]

    if search_results:
        context = build_context_block(search_results)
        messages.append(
            SystemMessage(content=f"Relevant code retrieved from the repository:\n\n{context}")
        )

    # Append rolling history window
    for turn in chat_history[-HISTORY_WINDOW:]:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn["role"] == "assistant":
            messages.append(AIMessage(content=turn["content"]))

    messages.append(HumanMessage(content=question))

    response = llm.invoke(messages)
    return response.content
