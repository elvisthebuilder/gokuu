import os
import asyncio
import logging
import httpx # type: ignore
import json

logger = logging.getLogger("GeminiSearch")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-latest:generateContent"

async def gemini_search(query: str) -> str:
    """
    Perform a Google search using Gemini's native search grounding via direct HTTP API.
    Returns a cited summary of findings.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "Error: No Gemini/Google API key configured for search grounding."

    url = f"{GEMINI_API_URL}?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    # Grounding payload using Google Search Retrieval
    payload = {
        "contents": [{"parts": [{"text": query}]}],
        "tools": [
            {
                "google_search_retrieval": {}
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            
            if resp.status_code != 200:
                logger.error(f"Gemini API Error ({resp.status_code}): {resp.text}")
                return f"Web search failed: Gemini API returned status {resp.status_code}"

            data = resp.json()
            
            # 1. Extract the synthesized answer
            candidates = data.get("candidates", [])
            if not candidates:
                return "No information found for that query."
            
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            # Some parts might be text, some might be grounding-related
            text = "".join([p.get("text", "") for p in parts if "text" in p])
            
            if not text:
                return "Search was performed but no synthesized answer was generated."

            # 2. Extract Grounding Metadata / Citations
            grounding = candidates[0].get("groundingMetadata", {})
            search_entry = grounding.get("searchEntryPoint", {})
            html_chunk = search_entry.get("renderedContent", "")
            
            # Append grounding metadata if found (as an 'About this result' link)
            if html_chunk:
                result = f"{text}\n\n[🔍 Grounded by Google Search]"
            else:
                result = text

            return result

    except Exception as e:
        logger.error(f"Gemini Search Exception: {e}")
        return f"Error during web search: {str(e)}"
    
    return "An unexpected error occurred during search."

if __name__ == "__main__":
    # Quick standalone test
    import sys
    async def main():
        q = sys.argv[1] if len(sys.argv) > 1 else "Latest status of SpaceX Starship launch"
        print(f"Searching for: {q}...")
        res = await gemini_search(q)
        print("-" * 30)
        print(res)
    
    asyncio.run(main())
