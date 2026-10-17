"""Read actual model IDs with the selected provider SDK; never fabricate a catalog."""
from __future__ import annotations

import asyncio


async def discover_models(settings):
    settings.require_model_key()
    if settings.provider == "openai":
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.api_key, base_url=settings.models_base_url or settings.base_url, timeout=15, max_retries=0)
    else:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=settings.api_key, base_url=settings.models_base_url or settings.base_url, timeout=15, max_retries=0)
    models = set()
    complete = True
    async with asyncio.timeout(15), client:
        page = await client.models.list()
        for page_number in range(10):
            for model in page.data:
                identifier = getattr(model, "id", "")
                if isinstance(identifier, str) and identifier:
                    models.add(identifier)
            more = page.has_next_page()
            if not more:
                break
            if page_number == 9 or len(models) >= 500:
                complete = False
                break
            page = await page.get_next_page()
    return {"models": sorted(models), "complete": complete}
