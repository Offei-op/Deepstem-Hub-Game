"""Explicit opt-in only. Never run automatically; no fallback or retries."""
import os
import pytest
from app.config import Settings
from app.providers import get_provider, estimate_cost


@pytest.mark.paid
@pytest.mark.skipif(os.getenv('RUN_PAID_INTEGRATION') != 'YES', reason='Real API spending requires RUN_PAID_INTEGRATION=YES')
async def test_real_provider_small_budget():
    settings=Settings()
    name=os.environ.get('INTEGRATION_PROVIDER','openai')
    provider=get_provider(settings,name)
    assert name in {'openai','gemini'}
    # Hard guard: this single small schema probe may reserve no more than $0.05.
    assert estimate_cost(provider,2500,256)<=50_000, 'Configured model exceeds the integration budget guard'
    try:
        result=await provider.generate('Return title="Probe", explanation="SDK integration probe", html="<!doctype html><html></html>". Keep it very short.',256)
        assert result.game and result.game.title
        assert result.input_tokens is not None
    finally:
        await provider.close()
