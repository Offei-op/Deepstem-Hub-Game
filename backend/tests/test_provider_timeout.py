import logging
import httpx
from openai import APITimeoutError
from app.providers import classify
from app.config import Settings


def test_sdk_timeout_is_clear_but_keeps_conservative_billing(caplog):
    error = APITimeoutError(request=httpx.Request('POST','https://api.openai.com/v1/responses',
                           headers={'Authorization':'Bearer secret-test-key'}, content=b'private-prompt'))
    with caplog.at_level(logging.WARNING):
        result = classify(error)
    assert result.kind == 'uncertain'
    assert 'took too long' in str(result)
    assert 'APITimeoutError' in caplog.text
    assert 'secret-test-key' not in caplog.text and 'private-prompt' not in caplog.text


def test_outer_timeout_is_also_identified_and_default_allows_detailed_games():
    assert 'took too long' in str(classify(TimeoutError()))
    assert Settings(_env_file=None).provider_timeout_seconds == 600
