import httpx

from pipelines.embed import EmbeddingPipeline
from services.retrieval import search_workspace


def _embedder_returning(vector: list[float]) -> EmbeddingPipeline:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": vector}]})

    return EmbeddingPipeline("http://emb", "m", transport=httpx.MockTransport(handler))


async def test_search_workspace_embeds_query_and_ranks(session, repo, seeder):
    await seeder(
        "ws",
        [
            ("k1", [1.0, 0, 0, 0, 0, 0, 0, 0]),
            ("k2", [0.9, 0.1, 0, 0, 0, 0, 0, 0]),
            ("k3", [0.0, 1.0, 0, 0, 0, 0, 0, 0]),
        ],
    )

    embedder = _embedder_returning([1.0, 0, 0, 0, 0, 0, 0, 0])
    res = await search_workspace(
        session, "query about k1", "ws", k=2, embedder=embedder, repository=repo
    )

    assert [r.chunk_id for r in res] == ["k1", "k2"]
    assert res[0].file_id  # joined metadata present


async def test_search_workspace_respects_workspace(session, repo, seeder):
    await seeder("ws-a", [("a1", [1.0, 0, 0, 0, 0, 0, 0, 0])])
    embedder = _embedder_returning([1.0, 0, 0, 0, 0, 0, 0, 0])

    res = await search_workspace(session, "q", "ws-b", k=5, embedder=embedder, repository=repo)
    assert res == []
