"""Regression checks for the deployment privilege boundary and browser policy."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def test_all_actions_are_pinned_and_checkout_does_not_retain_credentials():
    for path in (ROOT/'.github/workflows').glob('*.yml'):
        content=path.read_text()
        for action in re.findall(r'uses:\s*(\S+)',content):
            assert re.fullmatch(r'[\w./-]+@[0-9a-f]{40}',action), (path,action)
        for match in re.finditer(r'uses: actions/checkout@',content):
            assert 'persist-credentials: false' in content[match.start():match.start()+160]


def test_pages_deployment_permissions_are_separate_from_build():
    content=(ROOT/'.github/workflows/pages.yml').read_text()
    build,deploy=content.split('\n  deploy:\n')
    assert 'pages: write' not in build and 'id-token: write' not in build
    assert 'needs: build' in deploy and "github.ref == 'refs/heads/main'" in deploy
    assert 'pages: write' in deploy and 'id-token: write' in deploy
    assert 'pip install' not in deploy and 'scripts/build_pages.py' not in deploy


def test_browser_csp_prohibits_external_scripts_and_inline_styles():
    html=(ROOT/'web/index.html').read_text()
    assert 'http-equiv="Content-Security-Policy"' in html
    assert "script-src 'self'" in html and "connect-src 'self'" in html
    assert "'unsafe-inline'" not in html and "'unsafe-eval'" not in html
    assert 'style="' not in html
    assert 'style="' not in (ROOT/'web/app.js').read_text()


def test_azure_secret_is_only_available_to_cloud_steps():
    content=(ROOT/'.github/workflows/daily-data.yml').read_text()
    before_steps=content.split('    steps:')[0]
    assert 'AZURE_STORAGE_CONNECTION_STRING' not in before_steps
    steps=content.split('      - ')
    secret_steps=[step for step in steps if 'secrets.AZURE_STORAGE_CONNECTION_STRING' in step]
    assert len(secret_steps)==2
    assert all(step.startswith('run: fraudopt cloud ') for step in secret_steps)
