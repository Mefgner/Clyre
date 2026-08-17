import json

import httpx

from pipelines.llama import LlamaLLMPipeline


async def test_count_tokens_many_uses_tokenize_endpoint():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        content = json.loads(request.content)["content"]
        return httpx.Response(200, json={"tokens": list(range(len(content)))})

    pipeline = LlamaLLMPipeline("http://llama", "model", httpx.MockTransport(handler))

    assert await pipeline.count_tokens_many(["one", "two words"]) == [3, 9]
    assert [request.url.path for request in requests] == ["/tokenize", "/tokenize"]
