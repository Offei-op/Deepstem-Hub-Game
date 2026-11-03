import re
from html.parser import HTMLParser
from tree_sitter import Language, Parser
import tree_sitter_javascript

JS_LANGUAGE = Language(tree_sitter_javascript.language())


class InvalidGame(ValueError):
    pass


class GameParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = set()
        self.script = False
        self.js = []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        if tag in {'iframe', 'frame', 'frameset', 'object', 'embed', 'base', 'link', 'form', 'a', 'svg', 'math'}:
            raise InvalidGame(f'Unsupported game element: {tag}')
        for key, value in attrs:
            value = value or ''
            if key in {'src', 'href', 'srcset', 'action', 'formaction', 'poster', 'data', 'ping', 'srcdoc', 'http-equiv'}:
                raise InvalidGame('Games must contain only inline procedural graphics and scripts.')
            if key.startswith('on') or value.strip().lower().startswith(('javascript:', 'http:', 'https:', '//')):
                raise InvalidGame('Use inline script event listeners and no external resources.')
        if tag == 'script':
            if dict(attrs).get('type', '') not in {'', 'text/javascript', 'application/javascript'}:
                raise InvalidGame('Only classic inline JavaScript is supported.')
            self.script = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'script':
            self.script = False

    def handle_data(self, data):
        if self.script:
            self.js.append(data)


FORBIDDEN = re.compile(r'\b(fetch|XMLHttpRequest|WebSocket|EventSource|Worker|SharedWorker|importScripts|eval|'
                       r'localStorage|sessionStorage|indexedDB|serviceWorker|sendBeacon|RTCPeerConnection)\b|'
                       r'\b(?-i:Function)\s*\(|\bimport\s*(?:\(|[\w{*])|\b(?:window|document|parent|top|self)\s*\[|'
                       r'\b(?:location|cookie)\b|\bwindow\s*\.\s*open\b|\b(?:parent|top|opener)\s*\.|'
                       r'\bcreateElement\s*\(\s*[\'\"](?:script|iframe|img|link|a)[\'\"]', re.I)


def validate_game(html: str, max_bytes: int, secrets_to_check=()) -> str:
    if len(html.encode('utf-8')) > max_bytes:
        raise InvalidGame('The game is too large. Ask for a simpler game.')
    if not re.match(r'\s*<!doctype\s+html\s*>', html, re.I) or not re.search(r'</html>\s*$', html, re.I):
        raise InvalidGame('The provider did not return a complete HTML document.')
    if any(secret and len(secret) >= 8 and secret in html for secret in secrets_to_check):
        raise InvalidGame('The generated file contained prohibited secret material.')
    parser = GameParser()
    try:
        parser.feed(html)
        parser.close()
    except InvalidGame:
        raise
    except Exception as exc:
        raise InvalidGame('The generated HTML could not be parsed.') from exc
    if not {'html', 'head', 'body', 'canvas', 'script'} <= parser.tags:
        raise InvalidGame('The game needs a complete page, a canvas, and an inline script.')
    js = '\n'.join(parser.js)
    # Parsing builds a syntax tree only; it never evaluates or executes JavaScript.
    if Parser(JS_LANGUAGE).parse(js.encode('utf-8')).root_node.has_error:
        raise InvalidGame('The generated JavaScript has a syntax error. Your previous game is safe.')
    if FORBIDDEN.search(js) or re.search(r'@import|url\s*\(', html, re.I):
        raise InvalidGame('The game attempted a prohibited browser capability or external resource.')
    if not all(re.search(pattern, js, re.I) for pattern in [r'requestAnimationFrame', r'key(?:down|up)', r'restart|reset']):
        raise InvalidGame('The game needs an animation loop, keyboard controls, and a restart mechanism.')
    return html


def preview_csp(app_origin):
    return ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "img-src data:; media-src data:; font-src 'none'; connect-src 'none'; worker-src 'none'; "
            "frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; "
            f"frame-ancestors {app_origin}; sandbox allow-scripts")
