"""Permanent hosting configuration is fail-closed and preserves preview separation."""
import json
from pathlib import Path
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from permanent_network import load_hosting, tunnel_config
import event_network


def configured(tmp_path):
    private = tmp_path / 'data-private'
    private.mkdir()
    hosting = {'tunnel_id': str(uuid.uuid4()), 'app_host': 'studio.example.org',
               'preview_host': 'games.example.org'}
    (private / 'permanent-hosting.json').write_text(json.dumps(hosting))
    (private / 'tunnel-credentials.json').write_text(json.dumps({
        'TunnelID': hosting['tunnel_id'], 'TunnelSecret': 'test-secret'}))
    return private, hosting


def test_named_routes_only_expose_loopback_app_and_preview(tmp_path):
    _, hosting = configured(tmp_path)
    assert load_hosting(tmp_path) == hosting
    config = json.loads(tunnel_config(tmp_path, hosting))
    assert config['ingress'] == [
        {'hostname': 'studio.example.org', 'service': 'http://127.0.0.1:8080'},
        {'hostname': 'games.example.org', 'service': 'http://127.0.0.1:8081'},
        {'service': 'http_status:404'},
    ]
    assert config['metrics'] == '127.0.0.1:0'
    assert 'test-secret' not in tunnel_config(tmp_path, hosting)


@pytest.mark.parametrize('change', ['same-host', 'invalid-host', 'missing-credentials', 'wrong-tunnel'])
def test_invalid_named_setup_never_falls_back_to_anonymous_links(tmp_path, change):
    private, hosting = configured(tmp_path)
    if change == 'same-host':
        hosting['preview_host'] = hosting['app_host']
    elif change == 'invalid-host':
        hosting['app_host'] = 'https://studio.example.org/path'
    elif change == 'missing-credentials':
        (private / 'tunnel-credentials.json').unlink()
    else:
        hosting['tunnel_id'] = str(uuid.uuid4())
    (private / 'permanent-hosting.json').write_text(json.dumps(hosting))
    with pytest.raises(RuntimeError, match='incomplete'):
        load_hosting(tmp_path)


def test_an_old_quick_tunnel_cannot_be_reused_for_permanent_hosting(tmp_path, monkeypatch):
    (tmp_path / 'artifacts').mkdir()
    (tmp_path / 'artifacts' / 'online-status.json').write_text(json.dumps({
        'status': 'ready', 'app_url': 'https://old-link.trycloudflare.com', 'pid': 12345}))
    def unexpected(*args, **kwargs):
        pytest.fail('Should reject the old URL before contacting it')
    monkeypatch.setattr(event_network.urllib.request, 'urlopen', unexpected)
    assert not event_network.reuse_online(tmp_path, expected_app='https://studio.example.org')
