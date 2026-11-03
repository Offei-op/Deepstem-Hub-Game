"""Private style guides: decode/re-encode images, never publish supplied bytes or filenames."""
import base64
import hashlib
import io
import warnings
from dataclasses import dataclass
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 2_000_000
MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(frozen=True)
class ReferenceImage:
    data: bytes
    mime_type: str = 'image/jpeg'


def normalize_image(encoded):
    if len(encoded) > 2_700_000:
        raise HTTPException(413, 'Reference image is too large. Choose a smaller image.')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(422, 'That image could not be read. Choose a JPEG, PNG or WebP file.') from None
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, 'Reference image is too large. Choose a smaller image.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'} or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Unsupported image')
                if source.width * source.height > MAX_PIXELS or min(source.size) < 8:
                    raise ValueError('Image dimensions out of bounds')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGBA')
                image.thumbnail((768, 768), Image.Resampling.LANCZOS)
                background = Image.new('RGB', image.size, 'white')
                background.paste(image, mask=image.getchannel('A'))
                output = io.BytesIO()
                # Fresh encoding strips metadata and any trailing/polyglot content.
                background.save(output, format='JPEG', quality=82, optimize=True)
                data = output.getvalue()
                return data, background.width, background.height, hashlib.sha256(data).hexdigest()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'Use a still JPEG, PNG or WebP image, up to 16 megapixels.') from None


def reference_dict(row):
    return {'id': row.id, 'name': row.name, 'width': row.width, 'height': row.height,
            'bytes': len(row.data), 'created': row.created, 'url': f'/api/references/{row.id}/image'}
