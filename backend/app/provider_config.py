"""Private organizer-managed configuration. This file is never mounted into preview."""
import json
import os
import tempfile
from pathlib import Path
from .config import Settings

FIELDS = {f'{provider}_{field}' for provider in ['openai', 'gemini']
          for field in ['api_key', 'model', 'input_price', 'output_price']}


def load_private_config(settings):
    path = Path(settings.provider_config_path)
    if not path.exists():
        return
    values = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(values, dict) or not set(values) <= FIELDS:
        raise ValueError('Invalid private provider configuration')
    validated = Settings.model_validate({**settings.model_dump(), **values})
    for key in FIELDS:
        setattr(settings, key, getattr(validated, key))


def persist_private_config(settings, values):
    path = Path(settings.provider_config_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    existing.update(values)
    fd, temporary = tempfile.mkstemp(prefix='.providers-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(existing, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def public_provider_config(settings):
    return {name: {'configured': bool(getattr(settings, f'{name}_api_key')),
                   'model': getattr(settings, f'{name}_model'),
                   'input_price': getattr(settings, f'{name}_input_price'),
                   'output_price': getattr(settings, f'{name}_output_price')}
            for name in ['openai', 'gemini']}
