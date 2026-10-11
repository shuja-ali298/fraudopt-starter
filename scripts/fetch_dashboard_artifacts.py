"""Stage dashboard data from successful, trusted main-branch workflow artifacts."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SOURCES = {
    'model': ('weekly-model.yml', 'fraudopt-model', ('model_report.json', 'test_predictions.csv.gz')),
    'complaints': ('daily-data.yml', 'complaint-trends', ('complaint_daily_trends.csv',)),
}
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024


class GitHubClient:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {token}',
                                     'Accept': 'application/vnd.github+json',
                                     'X-GitHub-Api-Version': '2022-11-28'})
        self.session.mount('https://', HTTPAdapter(max_retries=Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))

    def json(self, path, params=None):
        try:
            response = self.session.get('https://api.github.com' + path, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            raise RuntimeError('GitHub API lookup failed; check Actions read permissions and service availability') from None

    def download(self, repository, artifact_id):
        try:
            response = self.session.get(f'https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}/zip',
                                        allow_redirects=False, timeout=60)
            response.raise_for_status()
            location = response.headers.get('Location', '')
            if response.status_code != 302 or not location.startswith('https://'):
                raise RuntimeError('GitHub did not return a secure artifact download redirect')
            # Signed artifact storage gets a fresh request without the GitHub token.
            with requests.get(location, stream=True, timeout=(20, 120)) as archive:
                archive.raise_for_status()
                chunks, size = [], 0
                for chunk in archive.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise ValueError('Artifact archive exceeds the permitted download size')
                    chunks.append(chunk)
                return b''.join(chunks)
        except requests.RequestException:
            raise RuntimeError('Artifact download failed; the currently published site will remain unchanged') from None


def trusted_run(run, repository):
    return (run.get('head_branch') == 'main' and run.get('conclusion') == 'success'
            and run.get('status') == 'completed'
            and run.get('event') in {'schedule', 'workflow_dispatch'}
            and (run.get('head_repository') or {}).get('full_name') == repository)


def latest_artifact(client, repository, workflow, prefix):
    # Bounded pagination includes the full normal 30/60-day retention windows.
    for page in range(1, 6):
        runs = client.json(f'/repos/{repository}/actions/workflows/{workflow}/runs',
                           {'branch': 'main', 'status': 'success', 'per_page': 100, 'page': page})['workflow_runs']
        for run in runs:
            if not trusted_run(run, repository):
                continue
            if run.get('path', '').split('@')[0] != f'.github/workflows/{workflow}':
                continue
            artifacts = client.json(f'/repos/{repository}/actions/runs/{int(run["id"])}/artifacts',
                                    {'per_page': 100})['artifacts']
            matching = [a for a in artifacts if a.get('name') == f'{prefix}-{run["id"]}' and not a.get('expired')]
            if len(matching) > 1:
                raise ValueError('More than one matching artifact for a source run')
            if matching:
                return run, matching[0]
        if len(runs) < 100:
            break
    return None


def read_selected_members(payload, filenames):
    """Read only allowed data files; never extract archive paths or load models."""
    selected = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in member.filename:
                raise ValueError('Artifact contains an unsafe archive path')
            if member.is_dir() or path.name not in filenames:
                continue
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Dashboard artifact files must not be symlinks')
            if path.name in selected:
                raise ValueError('Artifact contains duplicate dashboard filenames')
            if member.file_size > MAX_MEMBER_BYTES:
                raise ValueError('Dashboard artifact member exceeds the permitted size')
            selected[path.name] = archive.read(member)
    missing = set(filenames) - selected.keys()
    if missing:
        raise ValueError(f'Artifact is missing required dashboard files: {sorted(missing)}')
    return selected


def stage_sources(client, repository, fallback, destination):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid GitHub repository name')
    provenance = {'assembled_at_utc': datetime.now(timezone.utc).isoformat(), 'repository': repository, 'sources': {}}
    files = {}
    for kind, (workflow, prefix, filenames) in SOURCES.items():
        chosen = latest_artifact(client, repository, workflow, prefix)
        if chosen is None:
            data = {name: (fallback / name).read_bytes() for name in filenames}
            metadata = {'mode': 'snapshot', 'reason': 'No usable successful main-branch artifact within retention'}
            print(f'{kind}: using labelled demonstration fallback')
        else:
            run, artifact = chosen
            data = read_selected_members(client.download(repository, int(artifact['id'])), filenames)
            metadata = {'mode': 'workflow_artifact', 'workflow': workflow,
                        'run_id': int(run['id']), 'run_attempt': int(run.get('run_attempt', 1)),
                        'run_url': f'https://github.com/{repository}/actions/runs/{int(run["id"])}',
                        'head_sha': run['head_sha'], 'run_updated_at_utc': run['updated_at'],
                        'artifact_id': int(artifact['id']), 'artifact_created_at_utc': artifact['created_at']}
            print(f'{kind}: successful main run {run["id"]}, artifact {artifact["id"]}')
        metadata['file_sha256'] = {name: hashlib.sha256(content).hexdigest() for name, content in data.items()}
        provenance['sources'][kind] = metadata
        files.update(data)
    # Only stage after both sources were selected and fully downloaded.
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (destination / name).write_bytes(content)
    (destination / 'artifact_provenance.json').write_text(json.dumps(provenance, indent=2))
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--fallback', type=Path, default=Path('dashboard_data'))
    parser.add_argument('--destination', type=Path, default=Path('_dashboard_inputs'))
    args = parser.parse_args()
    token = os.environ.get('GITHUB_TOKEN')
    if not token or not args.repository:
        parser.error('GITHUB_TOKEN and a repository name are required')
    stage_sources(GitHubClient(token), args.repository, args.fallback, args.destination)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f'Dashboard refresh failed: {exc}', file=sys.stderr)
        sys.exit(1)
