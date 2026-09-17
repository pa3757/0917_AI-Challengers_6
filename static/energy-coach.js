'use strict';

const currentScreen = document.body.dataset.page || 'cover';
let state = {};
let survey = [];
let measurements = [];
let tariffs = [];
let ready = false;
let busy = false;
let dirty = false;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const number = value => Number(value).toLocaleString('ko-KR', {maximumFractionDigits: 1});
const range = (row, prefix, unit) => row?.[prefix + '_min'] == null ? '추가 입력 필요' :
  `${number(row[prefix + '_min'])} ~ ${number(row[prefix + '_max'] ?? row[prefix + '_min'])} ${unit}`;
const cardClass = 'bg-white rounded-2xl p-5 shadow-sm border border-gray-100';
const inputClass = 'w-full rounded-xl border-gray-200 bg-white text-sm p-3 mt-2';
const steps = {CONFIRM_FIRST:'상태 확인 먼저', MEASURE_FIRST:'현장 측정 먼저', COLLECT_INPUT_FIRST:'추가 입력 필요', CHECK_FIRST:'점검 먼저', ACTION:'실천 가능'};
const cats = {basic:'기본 정보', pc:'PC·모니터', hvac:'냉난방·환기', kitchen:'운영 관리', drink:'음료·쇼케이스'};
const catFor = q => ({basic:'basic', pc_monitor:'pc', pc_operation:'pc', hvac:'hvac', low_occupancy:'kitchen', energy_monitoring:'kitchen', refrigeration:'drink'}[q.section]);

const pagePaths = {cover:'/', survey:'/survey', diagnosis:'/diagnosis', guide:'/guide', results:'/results', solution:'/solution', myinfo:'/myinfo'};
const protectedPages = new Set(['diagnosis', 'guide', 'results', 'solution']);
const navigate = window.__energyCoachNavigate || (path => location.assign(path));
const replacePage = window.__energyCoachReplace || (path => location.replace(path));
const templates = {};
if ($('#screen-diagnosis')) {
  templates.diagnosisSummary = $('#screen-diagnosis main > section').cloneNode(true);
  templates.risk = $('#screen-diagnosis article').cloneNode(true);
}
if ($('#screen-guide .mission-card')) templates.mission = $('#screen-guide .mission-card').cloneNode(true);
if ($('#screen-results')) {
  templates.resultHeading = $('#screen-results main > section').cloneNode(true);
  templates.resultHero = $('#screen-results .snap-center').closest('section').cloneNode(true);
}
if ($('#screen-myinfo main > div')) templates.profile = $('#screen-myinfo main > div').cloneNode(true);

async function api(path, method = 'GET', body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch('/api/' + path, {method, credentials:'same-origin', signal:controller.signal,
      headers:body === undefined ? {} : {'Content-Type':'application/json'}, body:body === undefined ? undefined : JSON.stringify(body)});
    const result = await response.json();
    if (!response.ok) {
      const detail = result.detail;
      throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? '입력값을 확인하세요.' : Object.entries(detail || {}).map(([key, value]) => `${key}: ${value}`).join('\n'));
    }
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('응답 시간이 초과되었습니다. 잠시 후 다시 시도하세요.');
    throw error;
  } finally { clearTimeout(timeout); }
}

function message(text, retry = false) {
  let box = $('#app-message');
  if (!box) {
    box = document.createElement('div');
    box.id = 'app-message';
    box.className = 'absolute top-16 inset-x-4 z-50 rounded-2xl bg-white border border-emerald-200 shadow-lg p-4 text-sm text-gray-800';
    box.setAttribute('role', 'alert');
    $('#phone').append(box);
  }
  box.innerHTML = `<p class="whitespace-pre-line">${esc(text)}</p><button type="button" class="mt-3 text-primary font-bold">${retry ? '다시 연결' : '확인'}</button>`;
  $('button', box).onclick = () => {box.remove(); if (retry) initialize();};
}

function render() {
  const active = $('#screen-' + currentScreen);
  if (!active) return;
  active.scrollTop = 0;
  const main = $('main, .scr-main', active);
  if (main) main.scrollTop = 0;
}

async function goTo(id) {
  if (!pagePaths[id] || id === currentScreen) return;
  if (!ready && id !== 'cover') return message('서버에 연결 중입니다. 연결에 실패하면 다시 연결을 눌러 주세요.');
  if (busy) return;
  if (currentScreen === 'survey' && protectedPages.has(id) && (!state.report || dirty)) {
    if (!await submitDiagnosis()) return;
  }
  if (protectedPages.has(id) && !state.report) return navigate('/survey');
  navigate(pagePaths[id]);
}
function goBack() {if (!busy) {if (history.length > 1) history.back(); else navigate('/');}}
function closeScreen() {if (!busy) navigate(currentScreen === 'myinfo' ? '/' : '/myinfo');}

function selectCategory(cat) {
  $$('.cat-chip').forEach(chip => chip.classList.toggle('active', chip.dataset.cat === cat));
  $$('.survey-question').forEach(panel => panel.classList.toggle('active', panel.id === 'q-' + cat));
}

function updateSurveyProgress() {
  const required = survey.filter(q => q.required);
  const done = required.filter(q => answerValue(q) !== undefined).length;
  const pct = required.length ? Math.round(done / required.length * 100) : 0;
  $('#survey-progress-pct').textContent = pct + '%';
  $('#survey-progress-frac').textContent = `${done}/${required.length}`;
  $('#survey-progress-bar').style.width = pct + '%';
}

function answerValue(q) {
  const input = q.type === 'single_select' ? $(`input[name="${q.question_id}"]:checked`) : $('#' + q.question_id);
  if (!input || input.value === '') return undefined;
  return q.type === 'single_select' ? input.value : Number(input.value);
}

function renderSurvey() {
  if (!$('#screen-survey')) return;
  const nav = $('#screen-survey nav[aria-label="설문 항목 카테고리"]');
  nav.innerHTML = Object.entries(cats).map(([id, label]) => `<button type="button" class="cat-chip" data-cat="${id}">${label}</button>`).join('');
  $$('button', nav).forEach(button => button.onclick = () => selectCategory(button.dataset.cat));
  const container = $('#q-pc').parentElement;
  container.innerHTML = Object.keys(cats).map(cat => `<div id="q-${cat}" class="survey-question space-y-6"></div>`).join('');
  survey.forEach(q => {
    const saved = state.answers?.[q.question_id];
    const field = document.createElement('fieldset');
    field.dataset.question = q.question_id;
    field.innerHTML = `<legend class="text-sm font-bold text-gray-900 mb-3 leading-snug"><span class="block text-[11px] text-gray-400 mb-1">${q.question_id} · ${q.required ? '필수' : '선택'}</span>${esc(q.question)}</legend>`;
    if (q.type === 'single_select') {
      const group = document.createElement('div');
      group.className = 'space-y-2.5';
      group.innerHTML = q.options.map(option => `<label class="q-option"><input class="sr-only" type="radio" name="${q.question_id}" value="${esc(option.code)}" ${saved === option.code ? 'checked' : ''}><span class="q-dot"><svg class="q-check" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M4.5 12.75l6 6 9-13.5"/></svg></span><span class="q-label-text">${esc(option.label)}</span></label>`).join('');
      field.append(group);
    } else {
      field.insertAdjacentHTML('beforeend', `<input id="${q.question_id}" aria-label="${esc(q.question)}" class="${inputClass}" type="number" min="${q.validation?.min ?? 0}" ${q.validation?.max == null ? '' : `max="${q.validation.max}"`} step="${q.question_id === 'Q01' ? '1' : 'any'}" value="${typeof saved === 'number' ? saved : ''}" placeholder="${q.required ? '숫자를 입력하세요' : '모르면 비워두세요'}">`);
    }
    $('#q-' + catFor(q)).append(field);
  });
  const extra = document.createElement('details');
  extra.className = 'mt-5 text-sm';
  extra.innerHTML = `<summary class="font-semibold text-primary cursor-pointer">측정값 입력 (선택)</summary><p class="text-xs text-gray-500 mt-2">측정한 값만 입력하세요. 비워 둔 항목은 기존 계산 엔진이 판단합니다.</p><div class="mt-3 space-y-3" id="measurement-fields"></div>`;
  container.append(extra);
  measurements.forEach(m => {
    const rule = m.validation_rule;
    if (!['number', 'integer', 'string'].includes(rule.type)) return;
    const value = state.measurements?.[m.input_id] ?? '';
    $('#measurement-fields', extra).insertAdjacentHTML('beforeend', `<label class="block text-xs text-gray-600">${esc(m.input_name)} (${esc(m.unit)})<input class="${inputClass}" data-measurement="${esc(m.input_id)}" aria-label="${esc(m.input_name)}" type="${rule.type === 'string' ? 'text' : 'number'}" step="${rule.type === 'integer' ? '1' : 'any'}" min="${rule.minimum ?? 0}" ${rule.maximum == null ? '' : `max="${rule.maximum}"`} value="${esc(value)}"></label>`);
  });
  container.insertAdjacentHTML('beforeend', `<label class="flex items-start gap-2 mt-5 text-xs text-gray-600"><input id="scenario-mode" type="checkbox" class="accent-emerald-700 mt-0.5" ${state.report?.scenario !== false ? 'checked' : ''}><span>MVP 참고 추정 사용 (미측정 항목은 가정값 적용, 130원/kWh)</span></label>`);
  container.insertAdjacentHTML('beforeend', `<label class="block text-xs text-gray-600 mt-4">요금 조건 (참고 추정을 끈 경우 적용)<select id="tariff-id" class="${inputClass}"><option value="">모름 · 전력량만 계산</option>${tariffs.map(t => `<option value="${esc(t.id)}" ${state.tariff_id === t.id ? 'selected' : ''}>${esc(t.label)}</option>`).join('')}</select></label><p class="text-xs text-gray-400 mt-2">기존 DB에 저장된 요율입니다. 계약·계절·시간대가 일치하는 조건을 선택하세요.</p>`);
  container.addEventListener('input', () => {dirty = true; updateSurveyProgress();});
  selectCategory('basic');
  updateSurveyProgress();
}

async function submitDiagnosis() {
  const answers = {};
  for (const q of survey) {
    const value = answerValue(q);
    if (value === undefined && q.required) {
      selectCategory(catFor(q));
      $(`[data-question="${q.question_id}"]`).scrollIntoView({block:'center'});
      message(q.question + '\n이 문항에 응답해 주세요.');
      return false;
    }
    if (value !== undefined) answers[q.question_id] = value;
  }
  const measureValues = {};
  for (const input of $$('[data-measurement]')) {
    if (input.value !== '') measureValues[input.dataset.measurement] = input.type === 'number' ? Number(input.value) : input.value;
  }
  const invalid = $$('#screen-survey input').find(input => !input.checkValidity());
  if (invalid) {
    const question = invalid.closest('[data-question]');
    if (question) selectCategory(catFor(survey.find(q => q.question_id === question.dataset.question)));
    const details = invalid.closest('details'); if (details) details.open = true;
    invalid.scrollIntoView({block:'center'}); invalid.reportValidity();
    message('입력값의 허용 범위를 확인해 주세요.'); return false;
  }
  busy = true;
  const button = $('#screen-survey footer button');
  button.disabled = true;
  const label = $('span', button);
  label.textContent = '진단하는 중…';
  button.setAttribute('aria-busy', 'true');
  try {
    state = await api('diagnosis', 'POST', {answers, measurements:measureValues, scenario:$('#scenario-mode').checked, tariff_id:$('#tariff-id').value || null});
    dirty = false;
    return true;
  } catch (error) {message(error.message); return false;}
  finally {busy = false; button.disabled = false; label.textContent = 'AI 진단하기'; button.removeAttribute('aria-busy');}
}

function evidenceHtml(row) {
  return (row.rag_evidence || []).map(e => {
    const href = /^https?:\/\//i.test(e.source_url || '') ? e.source_url : '';
    return `<details class="mt-3 text-xs text-gray-500"><summary class="cursor-pointer text-primary">${esc(e.source_organization)} · ${esc(e.source_document)}</summary><p class="whitespace-pre-line mt-2">${esc(e.document)}</p>${href ? `<a class="text-primary underline block mt-2" target="_blank" rel="noopener noreferrer" href="${esc(href)}">출처 보기</a>` : ''}</details>`;
  }).join('');
}

function renderDiagnosis(report) {
  if (!$('#screen-diagnosis') || !templates.diagnosisSummary) return;
  const main = $('#screen-diagnosis main');
  const stepsNav = $('.step-pill', main)?.parentElement;
  const summary = templates.diagnosisSummary.cloneNode(true);
  const count = report.risks.length;
  // Keep the original score card and ring, but show the engine's real count.
  const textNodes = [];
  const walk = document.createTreeWalker(summary, NodeFilter.SHOW_TEXT);
  while (walk.nextNode()) textNodes.push(walk.currentNode);
  textNodes.forEach(node => {
    if (node.textContent.trim() === '52') node.textContent = String(count);
    else if (node.textContent.includes('종합 에너지 효율 점수')) node.textContent = '확인된 에너지 낭비 요인';
    else if (node.textContent.includes('/ 100점')) node.textContent = '건';
    else if (node.textContent.trim() === 'SCORE') node.textContent = 'CHECK';
    else if (node.textContent.includes('개선 여지 있음')) node.textContent = count ? '점검 및 개선 필요' : '추가 낭비 요인 없음';
  });
  $('.progress-circle-val', summary).style.strokeDashoffset = '0';
  $('p', summary).textContent = '설문 응답 기반 내부 진단입니다. 공식 효율등급이나 실측 결과가 아닙니다.';
  main.replaceChildren();
  if (stepsNav) main.append(stepsNav);
  main.append(summary);
  const list = document.createElement('section'); list.className = 'space-y-3';
  list.innerHTML = '<h2 class="text-sm font-bold px-1">정밀 진단 분석 리포트</h2>';
  report.risks.forEach(risk => {
    const card = templates.risk.cloneNode(true);
    const solution = report.solutions.find(s => s.waste_code === risk.waste_code);
    $('h3', card).textContent = solution?.solution_name || risk.waste_code;
    $('h3', card).classList.remove('truncate');
    $('h3', card).nextElementSibling.textContent = risk.needs_confirmation ? '확인 필요' : ({HIGH:'높은 개선 필요', MEDIUM:'개선 필요', LOW:'점검 권장'}[risk.risk_level]);
    $('p', card).textContent = risk.reasons.join(' ');
    const foot = $('p', card).nextElementSibling;
    foot.innerHTML = `<span class="text-gray-500">내부 위험 점수</span><span class="font-bold text-primary">${risk.risk_score}점</span>`;
    list.append(card);
  });
  if (!count) list.insertAdjacentHTML('beforeend', `<p class="${cardClass} text-sm text-gray-600">현재 응답에서 진단 규칙에 해당하는 낭비 요인이 발견되지 않았습니다.</p>`);
  main.append(list);
}

function renderGuide(report) {
  if (!$('#screen-guide') || !templates.mission) return;
  const list = $('#screen-guide .mission-card')?.parentElement || $('#mission-list');
  list.id = 'mission-list';
  list.innerHTML = '<h3 class="font-headline-sm text-headline-sm">실천 미션 리스트</h3>';
  const top = report.ranking.top_recommendations;
  top.forEach(row => {
    const card = templates.mission.cloneNode(true);
    card.dataset.missionId = row.solution_id;
    $('h4', card).textContent = row.solution_name;
    $('.font-display-lg-mobile', card).textContent = String(row.rank).padStart(2, '0');
    const badges = $$('.flex.flex-wrap span', card);
    badges[0].textContent = '추천 ' + row.rank + '순위';
    badges[1].textContent = steps[row.next_step];
    $('.font-label-lg', card).textContent = range(row, 'cost_saving_krw', '원 / 월');
    const content = $('.space-y-2', card);
    const action = row.rag_evidence?.[0]?.recommended_action || row.solution_name;
    content.innerHTML = `<p class="text-xs text-gray-500 mb-2">${esc(steps[row.next_step])} · ${esc(report.notice)}</p><label class="flex items-start gap-2.5 cursor-pointer"><input class="checklist-item mt-1 w-4 h-4 accent-emerald-700" type="checkbox"><span class="text-sm text-gray-600">${esc(action)}</span></label>${evidenceHtml(row)}`;
    const checkbox = $('input', content);
    const toggle = $('.mission-toggle', card);
    toggle.setAttribute('aria-label', row.solution_name + ' 완료 토글');
    const sync = () => {
      const completed = !!state.missions?.[row.solution_id];
      checkbox.checked = completed;
      toggle.classList.toggle('bg-primary', completed);
      toggle.classList.toggle('text-on-primary', completed);
      toggle.setAttribute('aria-pressed', String(completed));
      card.classList.toggle('bg-secondary-container/20', completed);
    };
    const save = async completed => {
      if (busy) {sync(); return;}
      busy = true;
      checkbox.disabled = toggle.disabled = true;
      try {state = await api('missions/' + row.solution_id, 'PUT', {completed});}
      catch (error) {message(error.message);}
      finally {sync(); checkbox.disabled = toggle.disabled = false; busy = false;}
    };
    toggle.onclick = () => save(!state.missions?.[row.solution_id]);
    checkbox.onchange = () => save(checkbox.checked);
    sync(); list.append(card);
  });
  if (!top.length) list.insertAdjacentHTML('beforeend', '<p class="text-sm text-gray-500">현재 진단에서 추천할 미션이 없습니다.</p>');
  const tip = list.nextElementSibling;
  if (tip) tip.innerHTML = `<h4 class="text-lg font-bold mb-2">산정 기준</h4><p class="text-sm text-gray-600">${esc(report.notice)}</p><p class="text-xs text-gray-500 mt-2">근거 문서에 연결된 솔루션을 우선순위로 표시합니다. 완료 체크는 실천 기록이며 설비를 원격 제어하지 않습니다.</p>`;
}

function renderResults(report) {
  if (!$('#screen-results') || !templates.resultHero) return;
  const main = $('#screen-results main');
  const nav = $('.step-pill', main)?.parentElement;
  main.replaceChildren(); if (nav) main.append(nav);
  const top = report.ranking.top_recommendations;
  const hero = templates.resultHero.cloneNode(true);
  const first = top[0];
  const headingCard = templates.resultHeading.cloneNode(true);
  $('span', headingCard).textContent = report.scenario ? 'MVP 참고 시나리오' : '측정·입력 기반 계산';
  $('p', headingCard).textContent = first ? '1순위 추천의 개별 예상 효과입니다.' : '현재 추천된 솔루션이 없습니다.';
  main.append(headingCard);
  const figures = $$('.snap-center', hero);
  if (figures.length === 3) {
    figures.forEach((fig, i) => {
      const block = fig.lastElementChild;
      block.children[0].textContent = ['1순위 예상 전력량요금 절감', '1순위 예상 절감 전력', '월 탄소 감축량'][i];
      block.children[1].textContent = i === 0 ? range(first, 'cost_saving_krw', '') : i === 1 ? range(first, 'energy_saving_kwh', '') : '산정하지 않음';
      block.children[2].textContent = ['원 / 월', 'kWh / 월', '배출계수 및 계측 정보 없음'][i];
    });
  }
  const heading = $('h1', hero) || $('h2', hero);
  if (heading) heading.textContent = '예상 절감 효과';
  main.append(hero);
  main.insertAdjacentHTML('beforeend', `<section class="${cardClass} mb-5"><h2 class="text-sm font-bold mb-3">추천별 예상 절감량</h2>${top.map(row => `<div class="py-3 border-b border-gray-100"><p class="text-sm font-semibold">${esc(row.solution_name)}</p><p class="text-primary font-bold mt-1">${esc(range(row, 'energy_saving_kwh', 'kWh / 월'))}</p><p class="text-xs text-gray-500">${esc(range(row, 'cost_saving_krw', '원 / 월'))}</p></div>`).join('') || '<p class="text-sm">추천 결과가 없습니다.</p>'}<p class="text-xs text-gray-500 mt-3">동일 설비와 가정값이 겹칠 수 있어 개별 절감량을 합산하지 않습니다.</p></section>`);
  main.insertAdjacentHTML('beforeend', `<section class="${cardClass} mb-6"><h2 class="text-sm font-bold mb-2">산정 기준 및 출처</h2><p class="text-xs text-gray-500">${esc(report.notice)}</p>${top.map(evidenceHtml).join('')}</section>`);
  // Keep the existing CTA, removing its fictional extra-savings teaser.
  const teaser = $('#screen-results [role="button"]');
  if (teaser) teaser.innerHTML = '<span class="text-sm font-semibold text-primary">솔루션별 계산 근거와 추가 입력 확인</span><span>›</span>';
}

function renderSolutions(report) {
  if (!$('#screen-solution')) return;
  const main = $('#screen-solution main > div');
  main.innerHTML = '<section><h2 class="text-headline-lg font-bold">솔루션 상세 근거</h2><p class="text-sm text-gray-500 mt-2">진단에 연결된 전체 솔루션과 계산 상태입니다.</p></section>';
  const byId = Object.fromEntries(report.calculations.map(row => [row.solution_id, row]));
  report.solutions.forEach(row => {
    const calc = byId[row.solution_id];
    const needs = calc.missing_inputs || [];
    main.insertAdjacentHTML('beforeend', `<article class="bg-white rounded-[2rem] p-5 shadow-sm"><h3 class="text-lg font-bold">${esc(row.solution_name)}</h3><p class="text-primary font-bold mt-2">${esc(range(calc, 'energy_saving_kwh', 'kWh / 월'))}</p><p class="text-xs text-gray-500 mt-2">${esc(report.notice)}</p>${needs.length ? `<p class="text-xs text-amber-700 mt-2">추가 입력: ${esc(needs.join(', '))}</p><button type="button" class="text-primary underline text-sm mt-2" onclick="goTo('survey')">설문에서 측정값 입력</button>` : ''}<details class="text-xs text-gray-500 mt-3"><summary>계산 가정 및 주의사항</summary><p class="whitespace-pre-line mt-2">${esc([...(calc.assumptions || []), ...(calc.warnings || []), calc.energy_estimate_basis || ''].join('\n'))}</p></details>${evidenceHtml(row)}</article>`);
  });
  if (!report.solutions.length) main.insertAdjacentHTML('beforeend', `<p class="${cardClass} text-sm">추가 솔루션이 없습니다.</p>`);
}

function renderProfile() {
  if (!$('#screen-myinfo') || !templates.profile) return;
  const main = $('#screen-myinfo main');
  const actions = main.lastElementChild;
  main.replaceChildren();
  const profile = templates.profile.cloneNode(true);
  profile.innerHTML = `<div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full bg-primary"></span><span class="text-sm font-semibold">${esc(state.profile?.name || '내 PC방')}</span><span class="text-xs text-gray-400">${state.answers?.Q01 ? state.answers.Q01 + '석' : '좌석 미입력'}</span></div><span class="text-xs text-primary">저장된 현황</span>`;
  main.append(profile);
  main.insertAdjacentHTML('beforeend', `<section class="${cardClass}"><h2 class="text-lg font-bold">업장 정보</h2><form id="profile-form"><label class="block text-xs text-gray-500 mt-3">업장 이름<input name="name" required maxlength="80" value="${esc(state.profile?.name || '')}" class="${inputClass}" placeholder="업장 이름을 입력하세요"></label><button class="mt-3 rounded-full bg-primary text-white py-2 px-5 text-sm" type="submit">저장</button></form></section><section class="${cardClass}"><h2 class="text-lg font-bold">월별 절감 추이</h2><p class="text-sm text-gray-500 mt-3">월별 계측·요금 이력이 없습니다. 현재 입력한 월 사용량: ${state.answers?.Q04 != null ? esc(number(state.answers.Q04)) + ' kWh' : '미입력'}</p></section><section class="${cardClass}"><h2 class="text-lg font-bold">실천 현황</h2><p class="text-3xl text-primary font-bold mt-3">${Object.values(state.missions || {}).filter(Boolean).length} / ${state.report?.ranking.selected_count || 0}</p><p class="text-xs text-gray-500 mt-2">완료한 미션 · 이 브라우저에 연결된 기록</p></section><section class="bg-[#3D4756] text-white rounded-2xl p-5"><h2 class="text-sm font-bold">이번 달 예상 청구액</h2><p class="text-xl font-bold text-emerald-300 mt-3">산정 자료 없음</p><p class="text-xs text-gray-300 mt-2">실제 요금 및 계측 연동이 없어 확정 청구액을 제공하지 않습니다.</p></section>`);
  if (actions && $('button', actions)) main.append(actions);
  $('#profile-form').onsubmit = async event => {
    event.preventDefault();
    const button = $('button', event.target); button.disabled = true;
    try {state = await api('profile', 'PUT', {name:new FormData(event.target).get('name')}); renderProfile(); message('업장 정보를 저장했습니다.');}
    catch (error) {message(error.message);}
    finally {button.disabled = false;}
  };
}

function renderReport() {
  if (!state.report) return;
  renderDiagnosis(state.report); renderGuide(state.report); renderResults(state.report); renderSolutions(state.report);
}

async function initialize() {
  try {
    if (currentScreen === 'survey') {
      const [definition, saved] = await Promise.all([api('survey'), api('state')]);
      survey = definition.questions; measurements = definition.measurements; tariffs = definition.tariffs || []; state = saved;
      renderSurvey();
    } else {
      state = await api('state');
    }
    if (protectedPages.has(currentScreen) && !state.report) return replacePage('/survey');
    renderReport();
    if (currentScreen === 'myinfo') renderProfile();
    ready = true;
    $('#page-loading')?.remove();
  } catch (error) {
    $('#page-loading')?.remove();
    message('서버에 연결할 수 없습니다.\n' + error.message, true);
  }
}
render();
initialize();
