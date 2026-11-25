from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"


def mock_client(routes: dict[str, str]) -> httpx.AsyncClient:
    """AsyncClient that answers each URL in `routes` with that fixture file; other URLs get 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        name = routes.get(str(request.url))
        if name is None:
            return httpx.Response(404)
        ctype = "text/xml; charset=utf-8" if name.endswith(".xml") else "application/json"
        return httpx.Response(200, content=(FIXTURES / name).read_bytes(), headers={"content-type": ctype})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
