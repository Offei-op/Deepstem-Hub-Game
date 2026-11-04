import asyncio
import base64
import math
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from pydantic import BaseModel
from .prompt import SYSTEM_PROMPT


class GameOutput(BaseModel):
    title: str
    explanation: str
    html: str


@dataclass
class Result:
    game: GameOutput | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str = ''


class ProviderError(Exception):
    def __init__(self, kind: str, message: str, request_id=''):
        super().__init__(message)
        self.kind, self.request_id = kind, request_id


class Provider(Protocol):
    model: str
    input_price: float
    output_price: float
    async def generate(self, text: str, max_output: int, images=None) -> Result: ...


def classify(exc):
    code = getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
    # OpenAI exposes body/request_id; Google exposes details/status/response headers.
    body = str(getattr(exc, 'body', '') or getattr(exc, 'details', '')) + ' ' + str(getattr(exc, 'status', ''))
    response = getattr(exc, 'response', None)
    headers = getattr(response, 'headers', {}) or {}
    rid = str(getattr(exc, 'request_id', '') or headers.get('x-request-id', '') or headers.get('x-goog-request-id', ''))
    # Record only safe diagnostic identifiers, never exception bodies, prompts or headers.
    logging.getLogger(__name__).warning('AI request failed: exception=%s status=%s request_id=%s',
        type(exc).__name__, code if isinstance(code, (str, int)) else None, rid)
    if isinstance(exc, TimeoutError) or type(exc).__name__ in {'APITimeoutError', 'ReadTimeout', 'ConnectTimeout', 'WriteTimeout', 'PoolTimeout'}:
        return ProviderError('uncertain', 'The AI took too long to finish. Your saved game is safe. Ask your organizer to review the request before trying again.', rid)
    if code in {401, 402, 403}:
        return ProviderError('configuration', 'Provider authentication or permissions failed.', rid)
    if code == 429 and any(x in body.lower() for x in ['quota', 'billing', 'credit', 'resource_exhausted']):
        return ProviderError('configuration', 'Provider billing or quota is exhausted.', rid)
    if code == 429:
        return ProviderError('rate_limit', 'Provider is temporarily rate limited.', rid)
    if code in {400, 404, 422}:
        if any(word in body.lower() for word in ['image', 'vision']) and any(word in body.lower() for word in ['support', 'only text', 'not accept']):
            return ProviderError('configuration', 'The selected AI model cannot use reference images. Ask your organizer to choose a vision-capable model.', rid)
        return ProviderError('configuration', 'Provider rejected the model or request configuration.', rid)
    # Timeouts, disconnects and 5xx may have been billed. Do not blindly retry them.
    return ProviderError('uncertain', 'Provider did not complete reliably; cost requires reconciliation.', rid)


class OpenAIProvider:
    def __init__(self, settings):
        from openai import AsyncOpenAI
        self.model = settings.openai_model
        self.input_price, self.output_price = settings.openai_input_price, settings.openai_output_price
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, max_retries=0,
                                 timeout=settings.provider_timeout_seconds)

    async def generate(self, text, max_output, images=None):
        try:
            content = [{'type': 'input_text', 'text': text}]
            for image in images or []:
                content.append({'type': 'input_image', 'detail': 'low',
                    'image_url': f'data:{image.mime_type};base64,' + base64.b64encode(image.data).decode('ascii')})
            response = await self.client.responses.parse(
                model=self.model, instructions=SYSTEM_PROMPT,
                input=[{'role': 'user', 'content': content}] if images else text,
                text_format=GameOutput, max_output_tokens=max_output, store=False)
            usage = response.usage
            return Result(response.output_parsed, usage.input_tokens if usage else None,
                          usage.output_tokens if usage else None,
                          str(getattr(response, '_request_id', '') or response.id))
        except Exception as exc:
            raise classify(exc) from exc

    async def close(self):
        await self.client.close()


class GeminiProvider:
    def __init__(self, settings):
        from google import genai
        from google.genai import types
        self.model = settings.gemini_model
        self.input_price, self.output_price = settings.gemini_input_price, settings.gemini_output_price
        self.client = genai.Client(api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=settings.provider_timeout_seconds * 1000,
                                         retry_options=types.HttpRetryOptions(attempts=1))).aio

    async def generate(self, text, max_output, images=None):
        try:
            from google.genai import types
            contents = [text] + [types.Part.from_bytes(data=image.data, mime_type=image.mime_type) for image in images or []]
            response = await self.client.models.generate_content(model=self.model, contents=contents if images else text,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT,
                    response_mime_type='application/json', response_schema=GameOutput,
                    max_output_tokens=max_output))
            usage = response.usage_metadata
            # Output estimate includes billed thinking tokens, where supplied.
            output = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else None
            try:
                parsed = GameOutput.model_validate_json(response.text or '')
            except ValueError:
                parsed = None
            return Result(parsed, usage.prompt_token_count if usage else None, output,
                          str(getattr(response, 'response_id', '') or ''))
        except Exception as exc:
            raise classify(exc) from exc

    async def close(self):
        await self.client.aclose()


class MockProvider:
    model = 'offline-starter-demo'
    input_price = output_price = 0.0

    async def generate(self, text, max_output, images=None):
        import json
        data = json.loads(text)
        await asyncio.sleep(0.15)
        prompt = data['student_request'].lower()
        genre = next((x for x in ['puzzle', 'runner', 'platformer', 'topdown'] if x in prompt), 'arcade')
        html = (Path(__file__).parent / 'starters' / f'{genre}.html').read_text(encoding='utf-8')
        # Demo mode is explicitly a deterministic starter; never pretend it is AI editing.
        return Result(GameOutput(title={'arcade': 'Cosmic Collector', 'puzzle': 'Light Circuit',
            'runner': 'Neon Dash', 'platformer': 'Skybound', 'topdown': 'Garden Guardian'}[genre],
            explanation='Demo mode: loaded a playable offline starter. Connect an AI provider for custom generation and changes.',
            html=html), 0, 0, 'mock')

    async def close(self):
        pass


def get_provider(settings, name):
    if name == 'mock' and settings.environment != 'production':
        return MockProvider()
    if name not in {'openai', 'gemini'}:
        raise ProviderError('configuration', 'Choose a configured AI provider.')
    for field in ['api_key', 'model', 'input_price', 'output_price']:
        value = getattr(settings, f'{name}_{field}')
        if value is None or value == '' or (field.endswith('price') and (not math.isfinite(value) or value < 0)):
            raise ProviderError('configuration', f'{name} credentials, model and prices must be configured by organizers.')
    return OpenAIProvider(settings) if name == 'openai' else GeminiProvider(settings)


def estimate_cost(provider, input_tokens, output_tokens):
    # dollars/million tokens -> integer microdollars; ceil avoids under-reserving fractions.
    return math.ceil(input_tokens * provider.input_price + output_tokens * provider.output_price)
