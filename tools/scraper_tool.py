from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from bs4 import BeautifulSoup


class WebScraperTool:
    """
    Simple web scraper that fetches a URL and extracts the main text content.
    """

    DEFAULT_TIMEOUT = 15.0

    @classmethod
    async def scrape_url(
        cls,
        url: str,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        """
        Fetch a URL and return the main text content.
        """
        headers = {}
        if user_agent:
            headers["User-Agent"] = user_agent
        else:
            headers["User-Agent"] = "AgentFlowLocalScraper/1.0"

        async with httpx.AsyncClient(timeout=timeout or cls.DEFAULT_TIMEOUT, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Try to find a main/article section, otherwise fall back to body.
        main = soup.find("main") or soup.find("article") or soup.body
        if not main:
            main = soup

        # Remove script/style/noscript tags
        for tag in main(["script", "style", "noscript"]):
            tag.decompose()

        text = main.get_text(separator="\n", strip=True)

        # Collapse excessive newlines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Optional function-calling schema for future tool integration.
        """
        return {
            "name": "web_scraper_tool",
            "description": "Fetch a web page and return the main textual content for further analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The HTTP/HTTPS URL to scrape.",
                    },
                    "user_agent": {
                        "type": "string",
                        "description": "Optional custom User-Agent header value.",
                    },
                },
                "required": ["url"],
            },
        }


