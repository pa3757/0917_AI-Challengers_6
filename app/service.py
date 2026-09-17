"""Request-independent adapter around the existing diagnosis engines."""
from functools import lru_cache
from math import isfinite
from pathlib import Path
import os

from visualstudio_project.src.survey_loader import load_survey_questions
from visualstudio_project.src.rule_engine import evaluate_risks
from visualstudio_project.src.solution_engine import recommend_solutions
from visualstudio_project.src.calculator import calculate_all_solutions
from visualstudio_project.src.mvp_calculation_engine import calculate_all_solutions_mvp
from visualstudio_project.src.ranking_engine import rank_solutions
from visualstudio_project.src.rag_indexer import load_knowledge_base, build_document, split_waste_codes
from visualstudio_project.src.calculation_input_resolver import load_user_input_definitions, load_reference_db

DATA = Path(__file__).resolve().parents[1] / 'visualstudio_project' / 'data'


@lru_cache
def questions():
    return load_survey_questions(DATA / '01_survey/survey_questions.json')


def validate_answers(answers):
    errors = {}
    known = {q['question_id'] for q in questions()}
    for key in answers.keys() - known:
        errors[key] = '알 수 없는 설문 항목입니다.'
    for q in questions():
        key = q['question_id']
        value = answers.get(key)
        if value is None or value == '':
            if q['required']:
                errors[key] = '응답이 필요합니다.'
            continue
        if q['type'] == 'single_select':
            if value not in [o['code'] for o in q['options']]:
                errors[key] = '허용되지 않은 선택값입니다.'
        elif value != q.get('unknown_code'):
            bounds = q.get('validation', {})
            if (type(value) not in (int, float) or not isfinite(value)
                or value < bounds.get('min', 0) or value > bounds.get('max', 1e9)
                or (key == 'Q01' and int(value) != value)):
                errors[key] = '허용 범위의 숫자를 입력하세요.'
    return errors


def validate_measurements(values):
    definitions = {r['input_id']: r for r in load_user_input_definitions()}
    errors = {}
    for key, value in values.items():
        definition = definitions.get(key)
        if not definition:
            errors[key] = '알 수 없는 측정 항목입니다.'
            continue
        rule = definition['validation_rule']
        if rule.get('type') == 'string':
            if not isinstance(value, str) or len(value) > 200:
                errors[key] = '문자열을 입력하세요.'
            continue
        if (type(value) not in (int, float) or not isfinite(value)
            or value < rule.get('minimum', 0) or value > rule.get('maximum', 1e9)
            or (rule.get('type') == 'integer' and int(value) != value)):
            errors[key] = '허용 범위의 숫자를 입력하세요.'
        other = rule.get('lte_input')
        if other in values and isinstance(value, (int, float)) and isinstance(values[other], (int, float)) and value > values[other]:
            errors[key] = f'{other}보다 클 수 없습니다.'
    return errors


def ground_solutions(solutions):
    mode = os.getenv('ENERGY_RAG_MODE', 'catalog')
    if mode == 'chroma':
        from visualstudio_project.src.retriever import retrieve_for_solutions, _get_collection
        from visualstudio_project.src.embedding_provider import SentenceTransformerEmbeddingProvider
        return retrieve_for_solutions(solutions, collection=_get_collection(), embedding_provider=SentenceTransformerEmbeddingProvider()), mode
    if mode != 'catalog':
        raise RuntimeError('ENERGY_RAG_MODE must be catalog or chroma')
    rows = load_knowledge_base()
    grounded = []
    for solution in solutions:
        evidence = [dict(row, document=build_document(row)) for row in rows
                    if solution['waste_code'] in split_waste_codes(row['waste_code'])][:3]
        grounded.append(dict(solution, rag_evidence=evidence, rag_evidence_count=len(evidence), rag_grounded=bool(evidence)))
    return grounded, mode


def tariff_options():
    result = []
    for row in load_reference_db():
        app = row.get('applicability', {})
        if row.get('parameter') != 'energy_rate' or not app.get('calculation_eligible') or row.get('value_min') != row.get('value_max'):
            continue
        context = {target: app.get(source) for source, target in [('contract_type', 'contract_type'), ('voltage', 'voltage_class'), ('option', 'tariff_option'), ('season', 'season'), ('band', 'band'), ('region', 'region')]}
        label = ' / '.join(str(context[k]) for k in ['contract_type', 'voltage_class', 'tariff_option', 'season', 'band'])
        result.append({'id': row['reference_id'], 'label': f'{label} · {row["value_min"]}원/kWh', 'context': context})
    return result


def diagnose(answers, measurements, scenario, tariff_id=None):
    risks = evaluate_risks(answers)
    solutions = recommend_solutions(risks)
    grounded, retrieval_mode = ground_solutions(solutions)
    tariff = next((r['context'] for r in tariff_options() if r['id'] == tariff_id), None)
    calculations = (calculate_all_solutions_mvp(solutions, answers, measurements) if scenario
                    else calculate_all_solutions(solutions, answers, measurements, tariff))
    ranking = rank_solutions(grounded, calculations, top_n=3)
    # Never sum independently estimated effects: even different overlap groups may
    # use the same monthly proxy. Display each selected recommendation separately.
    return dict(risks=risks, solutions=grounded, calculations=calculations, ranking=ranking,
                retrieval_mode=retrieval_mode, scenario=scenario,
                notice=('기존 MVP 참고 시나리오 · 130원/kWh 가정 · 실제 청구액/확정 절감액이 아닙니다.'
                        if scenario else '측정·입력 기반 계산 · 기존 DB 요율 적용 · 기본요금/세금 제외 · 입력이 부족한 항목은 계산하지 않습니다.'))
