import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import service


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('ENERGY_DB_PATH', str(tmp_path / 'state.sqlite3'))
    monkeypatch.setenv('ENERGY_RAG_MODE', 'catalog')
    with TestClient(app) as client:
        yield client


@pytest.fixture
def answers():
    values = {q['question_id']: q['options'][-1]['code'] for q in service.questions() if q['type'] == 'single_select'}
    return dict(values, Q01=100, Q02=24, Q03='EMPTY_31_50', Q05='BOTH_ON', Q06='OVER_30_MIN')


def test_frontend_and_schema(client):
    assert '/static/energy-coach.js' in client.get('/').text
    assert client.get('/static/energy-coach.js').status_code == 200
    assert client.get('/static/../visualstudio_project/.env').status_code == 404
    assert len(client.get('/api/survey').json()['questions']) == 17
    assert client.get('/docs').status_code == 200


def test_diagnosis_persistence_and_session_isolation(client, answers):
    result = client.post('/api/diagnosis', json={'answers': answers})
    assert result.status_code == 200, result.text
    data = result.json()
    report = data['report']
    assert report['risks'] == service.evaluate_risks(answers)
    assert report['ranking']['selected_count'] == 3
    top = report['ranking']['top_recommendations']
    assert all(row['rag_grounded'] for row in top)
    assert all(row['energy_saving_kwh_min'] is not None for row in top)
    assert report['retrieval_mode'] == 'catalog'
    assert report['scenario'] is True
    solution = top[0]['solution_id']
    assert client.put('/api/missions/' + solution, json={'completed': True}).status_code == 200
    assert client.get('/api/state').json()['missions'][solution] is True
    with TestClient(app) as other:
        assert other.get('/api/state').json() == {}
        assert other.put('/api/missions/' + solution, json={'completed': True}).status_code == 404
    with TestClient(app, cookies=client.cookies) as reopened:
        assert reopened.get('/api/state').json()['answers'] == answers
    assert client.put('/api/profile', json={'name': '우리 PC방'}).json()['profile']['name'] == '우리 PC방'
    assert client.post('/api/diagnosis', json={'answers': answers}).json()['missions'] == {}


@pytest.mark.parametrize('patch', [{'Q01': True}, {'Q01': -1}, {'Q01': 1.5}, {'Q02': 25}, {'Q05': 'INVALID'}, {'Q04': []}, {'Q99': 1}])
def test_answer_validation(client, answers, patch):
    assert client.post('/api/diagnosis', json={'answers': dict(answers, **patch)}).status_code == 422


def test_missing_answers(client):
    response = client.post('/api/diagnosis', json={'answers': {}})
    assert response.status_code == 422
    assert 'Q01' in response.json()['detail']


@pytest.mark.parametrize('measurement', [{'PC_COUNT': -1}, {'PC_COUNT': True}, {'PC_COUNT': 0.5}, {'PC_SAVABLE_HOURS': -2}, {'NONSENSE': 3}])
def test_measurement_validation(client, answers, measurement):
    assert client.post('/api/diagnosis', json={'answers': answers, 'measurements': measurement}).status_code == 422


def test_measured_calculation_matches_engine(client, answers):
    measured = {'PC_MEASURED_IDLE_W': 100, 'PC_MEASURED_SLEEP_W': 5, 'PC_SAVABLE_HOURS': 2, 'OCCURRENCE_DAYS': 30}
    response = client.post('/api/diagnosis', json={'answers': answers, 'measurements': measured, 'scenario': False})
    assert response.status_code == 200, response.text
    report = response.json()['report']
    assert report['calculations'] == service.calculate_all_solutions(service.recommend_solutions(service.evaluate_risks(answers)), answers, measured)
    assert report['scenario'] is False


def test_rag_failure_does_not_replace_saved_report(client, answers, monkeypatch):
    previous = client.post('/api/diagnosis', json={'answers': answers}).json()
    def fail(_):
        raise RuntimeError('not indexed')
    monkeypatch.setattr(service, 'ground_solutions', fail)
    assert client.post('/api/diagnosis', json={'answers': answers}).status_code == 503
    assert client.get('/api/state').json() == previous


def test_tariff_is_applied_only_to_measured_mode(client, answers):
    measured = {'PC_MEASURED_IDLE_W': 100, 'PC_MEASURED_SLEEP_W': 5, 'PC_SAVABLE_HOURS': 2, 'OCCURRENCE_DAYS': 30}
    tariff = service.tariff_options()[0]
    body = {'answers': answers, 'measurements': measured, 'scenario': False, 'tariff_id': tariff['id']}
    response = client.post('/api/diagnosis', json=body)
    assert response.status_code == 200, response.text
    calculations = response.json()['report']['calculations']
    expected = service.calculate_all_solutions(service.recommend_solutions(service.evaluate_risks(answers)), answers, measured, tariff['context'])
    assert calculations == expected
    assert any(c['cost_saving_krw_min'] is not None for c in calculations)
    body['tariff_id'] = 'INVALID'
    assert client.post('/api/diagnosis', json=body).status_code == 422


def test_concurrent_missions_do_not_overwrite_each_other(client, answers):
    from concurrent.futures import ThreadPoolExecutor
    data = client.post('/api/diagnosis', json={'answers': answers}).json()
    ids = [r['solution_id'] for r in data['report']['ranking']['top_recommendations']]
    cookies = dict(client.cookies)
    def complete(solution_id):
        with TestClient(app, cookies=cookies) as tab:
            return tab.put('/api/missions/' + solution_id, json={'completed': True}).status_code
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(complete, ids)) == [200, 200, 200]
    assert client.get('/api/state').json()['missions'] == {sid: True for sid in ids}
