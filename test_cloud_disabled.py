"""test_cloud_disabled.py -- ADR-047 §7: the cloud path is disabled.

Proves call_openrouter() returns the disabled error without any network call,
even with an API key configured. Run inside the container:
    docker exec openclaw_fastapi python test_cloud_disabled.py
"""
import asyncio
import httpx
from app import llm


class _NoNetwork:
    def __init__(self, *a, **k):
        raise AssertionError("network client constructed -- cloud path is not disabled")


def main():
    llm.httpx.AsyncClient = _NoNetwork
    settings = llm.get_settings()
    settings.openrouter_api_key = "test-key-not-real"
    result = asyncio.run(llm.call_openrouter(None))
    assert result["error"] == "cloud path disabled (ADR-047 §7)", result
    assert result["model_used"] == "cloud_disabled", result
    assert result["input_tokens"] == 0 and result["output_tokens"] == 0
    print("ok   call_openrouter returns disabled error, no network, key present")
    print("\ncloud-disabled test passed")


if __name__ == "__main__":
    main()
