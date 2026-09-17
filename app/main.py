from pathlib import Path
from typing import Annotated, Any
import logging

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import service, store

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title='Energy Coach', version='1.0.0')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
templates = Jinja2Templates(directory=ROOT / 'templates')

PAGES = {
    'cover': ('시작', '/'),
    'survey': ('에너지 습관 설문', '/survey'),
    'diagnosis': ('AI 진단 결과', '/diagnosis'),
    'guide': ('실천 가이드', '/guide'),
    'results': ('예상 절감 효과', '/results'),
    'solution': ('솔루션 상세', '/solution'),
    'myinfo': ('내 정보', '/myinfo'),
}


def get_session(response: Response, energy_session: Annotated[str | None, Cookie()] = None):
    key = store.session_id(energy_session)
    if key != energy_session:
        response.set_cookie('energy_session', key, httponly=True, samesite='strict', max_age=31536000)
    response.headers['Cache-Control'] = 'no-store'
    return key


Session = Annotated[str, Depends(get_session)]


class DiagnosisInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answers: dict[str, Any]
    measurements: dict[str, Any] = Field(default_factory=dict)
    scenario: StrictBool = True
    tariff_id: str | None = Field(default=None, max_length=150)


class MissionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    completed: StrictBool


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)


@app.get('/', include_in_schema=False)
def index(request: Request):
    title, _ = PAGES['cover']
    return templates.TemplateResponse(request, 'pages/cover.html', {'page': 'cover', 'title': title}, headers={'Cache-Control': 'no-cache'})


@app.get('/{page}', include_in_schema=False)
def page(request: Request, page: str):
    if page not in PAGES or page == 'cover':
        raise HTTPException(404, detail='화면을 찾을 수 없습니다.')
    title, _ = PAGES[page]
    return templates.TemplateResponse(request, f'pages/{page}.html', {'page': page, 'title': title}, headers={'Cache-Control': 'no-cache'})


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/survey')
def survey():
    return {'questions': service.questions(), 'measurements': service.load_user_input_definitions(), 'tariffs': service.tariff_options()}


@app.get('/api/state')
def state(key: Session):
    return store.read(key)


@app.post('/api/diagnosis')
def diagnosis(body: DiagnosisInput, key: Session):
    errors = service.validate_answers(body.answers)
    errors.update(service.validate_measurements(body.measurements))
    if body.tariff_id and body.tariff_id not in {r['id'] for r in service.tariff_options()}:
        errors['tariff_id'] = '알 수 없는 요금 조건입니다.'
    if errors:
        raise HTTPException(422, detail=errors)
    try:
        report = service.diagnose(body.answers, body.measurements, body.scenario, body.tariff_id)
    except (RuntimeError, ImportError) as exc:
        logging.getLogger(__name__).exception('Diagnosis dependency unavailable')
        raise HTTPException(503, detail='근거 검색 준비가 필요합니다. 서버의 RAG 설정과 인덱스를 확인하세요.') from exc
    return store.update(key, {'answers': body.answers, 'measurements': body.measurements,
                              'report': report, 'tariff_id': body.tariff_id, 'missions': {}})


@app.put('/api/missions/{solution_id}')
def mission(solution_id: str, body: MissionInput, key: Session):
    data = store.set_mission(key, solution_id, body.completed)
    if data is None:
        raise HTTPException(404, detail='현재 진단에 없는 미션입니다.')
    return data


@app.put('/api/profile')
def profile(body: ProfileInput, key: Session):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, detail='업장 이름을 입력하세요.')
    return store.update(key, {'profile': {'name': name}})
