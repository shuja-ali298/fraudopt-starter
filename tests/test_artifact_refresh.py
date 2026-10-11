import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from scripts.fetch_dashboard_artifacts import (
    GitHubClient, trusted_run, latest_artifact, read_selected_members, stage_sources)
from scripts.build_pages import build

REPO='example/fraudopt'


def run(identifier, workflow='weekly-model.yml', **changes):
    result={'id':identifier,'head_branch':'main','conclusion':'success','status':'completed',
            'event':'workflow_dispatch','head_repository':{'full_name':REPO},
            'path':f'.github/workflows/{workflow}', 'head_sha':'a'*40,
            'updated_at':'2026-10-11T10:00:00Z','run_attempt':1}
    result.update(changes)
    return result


def artifact(identifier, name, expired=False):
    return {'id':identifier,'name':name,'expired':expired,'created_at':'2026-10-11T09:59:00Z'}


def archive(files):
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w') as zip_file:
        for name,body in files.items():zip_file.writestr(name,body)
    return result.getvalue()


class FakeClient:
    def __init__(self, model_runs=(), complaint_runs=(), artifacts=None, archives=None):
        self.runs={'weekly-model.yml':list(model_runs),'daily-data.yml':list(complaint_runs)}
        self.artifacts=artifacts or {};self.archives=archives or {};self.downloaded=[]
    def json(self,path,params):
        if path.endswith('/artifacts'):
            return {'artifacts':self.artifacts.get(int(path.split('/')[-2]),[])}
        assert params['branch']=='main' and params['status']=='success'
        return {'workflow_runs':self.runs[path.split('/')[-2]]}
    def download(self,repo,identifier):
        assert repo==REPO
        self.downloaded.append(identifier)
        return self.archives[identifier]


@pytest.mark.parametrize('changes',[
    {'head_branch':'other'},{'conclusion':'failure'}, {'event':'pull_request'},
    {'status':'in_progress'}, {'head_repository':{'full_name':'attacker/fraudopt'}},
    {'head_repository':None}])
def test_untrusted_runs_are_rejected(changes):
    assert not trusted_run(run(1,**changes),REPO)


def test_selection_skips_untrusted_runs_and_expired_artifacts():
    client=FakeClient(model_runs=[run(3,event='pull_request'),run(2),run(1)],
        artifacts={2:[artifact(22,'fraudopt-model-2',expired=True)],1:[artifact(11,'fraudopt-model-1')]})
    chosen=latest_artifact(client,REPO,'weekly-model.yml','fraudopt-model')
    assert chosen[0]['id']==1 and chosen[1]['id']==11


def test_archive_reads_only_allowed_files_and_never_extracts_models():
    data=archive({'outputs/model_report.json':b'{}','outputs/model.joblib':b'untrusted model',
                  'data/complaints.sqlite':b'database'})
    assert read_selected_members(data,('model_report.json',))=={'model_report.json':b'{}'}


@pytest.mark.parametrize('files',[
    {'../model_report.json':b'{}'}, {'/model_report.json':b'{}'},
    {'a/model_report.json':b'{}','b/model_report.json':b'{}'}, {'different.json':b'{}'}])
def test_unsafe_missing_or_duplicate_archive_files_fail(files):
    with pytest.raises(ValueError):read_selected_members(archive(files),('model_report.json',))


def test_archive_symlinks_and_size_limits_fail(monkeypatch):
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w') as file:
        member=zipfile.ZipInfo('model_report.json')
        member.external_attr=(stat.S_IFLNK|0o777)<<16
        file.writestr(member,'target')
    with pytest.raises(ValueError,match='symlinks'):
        read_selected_members(payload.getvalue(),('model_report.json',))
    monkeypatch.setattr('scripts.fetch_dashboard_artifacts.MAX_MEMBER_BYTES',1)
    with pytest.raises(ValueError,match='size'):
        read_selected_members(archive({'model_report.json':b'{}'}),('model_report.json',))


@pytest.fixture
def fallback(tmp_path):
    source=tmp_path/'snapshot';source.mkdir()
    pd.DataFrame({'elapsed_seconds':[0,1,86400,86401],'amount':[100,200,50,100],
                  'true_label':[1,0,1,0],'fraud_risk':[.9,.8,.01,.02]}).to_csv(
        source/'test_predictions.csv.gz',index=False,compression='gzip')
    (source/'model_report.json').write_text(json.dumps({'chosen_model':'fixture'}))
    pd.DataFrame({'date_received':['2026-10-01'],'complaint_count':[5],
                  'potential_fraud_issue_count':[2]}).to_csv(source/'complaint_daily_trends.csv',index=False)
    return source


def test_mixed_sources_publish_explicit_fallback_and_hashes(fallback,tmp_path):
    live_csv=b'date_received,complaint_count,potential_fraud_issue_count\n2026-10-10,9,3\n'
    client=FakeClient(complaint_runs=[run(7,'daily-data.yml')],
        artifacts={7:[artifact(77,'complaint-trends-7')]},
        archives={77:archive({'complaint_daily_trends.csv':live_csv})})
    staged=tmp_path/'inputs'
    provenance=stage_sources(client,REPO,fallback,staged)
    assert provenance['sources']['model']['mode']=='snapshot'
    assert provenance['sources']['complaints']['mode']=='workflow_artifact'
    assert provenance['sources']['complaints']['run_id']==7
    assert provenance['sources']['complaints']['file_sha256']['complaint_daily_trends.csv']==hashlib.sha256(live_csv).hexdigest()
    build(staged,tmp_path/'site')
    payload=json.loads((tmp_path/'site/data.json').read_text())
    assert payload['complaints'][0]['count']==9
    assert payload['provenance']==provenance


def test_bad_download_preserves_existing_staging(fallback,tmp_path):
    client=FakeClient(model_runs=[run(1)], artifacts={1:[artifact(11,'fraudopt-model-1')]},
        archives={11:archive({'wrong.json':b'{}'})})
    staged=tmp_path/'inputs';staged.mkdir()
    (staged/'model_report.json').write_text('previous')
    with pytest.raises(ValueError):stage_sources(client,REPO,fallback,staged)
    assert (staged/'model_report.json').read_text()=='previous'


def test_build_rejects_file_changed_after_staging(fallback,tmp_path):
    staged=tmp_path/'inputs'
    stage_sources(FakeClient(),REPO,fallback,staged)
    with (staged/'complaint_daily_trends.csv').open('a') as file:
        file.write('2026-10-02,3,1\n')
    with pytest.raises(ValueError,match='hash'):
        build(staged,tmp_path/'site')


def test_signed_storage_download_never_receives_github_authorization(monkeypatch):
    client=GitHubClient('test-only-token')
    class Redirect:
        status_code=302
        headers={'Location':'https://artifact-storage.example/signed'}
        def raise_for_status(self):pass
    class Download:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        def iter_content(self,size):yield b'zip-data'
    monkeypatch.setattr(client.session,'get',lambda *args,**kwargs:Redirect())
    def get(url,**kwargs):
        assert url.startswith('https://artifact-storage.example/')
        assert 'headers' not in kwargs and 'auth' not in kwargs
        return Download()
    monkeypatch.setattr('scripts.fetch_dashboard_artifacts.requests.get',get)
    assert client.download(REPO,1)==b'zip-data'
