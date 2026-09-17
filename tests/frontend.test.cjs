// Page-specific DOM/controller tests. No browser or external network is required.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {execFileSync} = require('node:child_process');
const {JSDOM} = require('jsdom');
const path = require('node:path');
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const fixture = JSON.parse(execFileSync(python, ['-c', `
import json
from app.service import questions, diagnose, load_user_input_definitions, tariff_options
answers = {q['question_id']: q['options'][-1]['code'] for q in questions() if q['type'] == 'single_select'}
answers.update(Q01=100, Q02=24, Q03='EMPTY_31_50', Q05='BOTH_ON', Q06='OVER_30_MIN')
print(json.dumps({'questions':questions(),'measurements':load_user_input_definitions(),'tariffs':tariff_options(),'answers':answers,'report':diagnose(answers,{},True)}))
`], {encoding:'utf8'}));
const settle = async predicate => {
  for (let i = 0; i < 100; i++) {if (predicate()) return; await new Promise(r => setTimeout(r, 5));}
  throw new Error('Controller did not settle');
};

function pageHtml(page) {
  const script = `
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
env=Environment(loader=FileSystemLoader(Path('templates')))
print(env.get_template('pages/${page}.html').render(page='${page}', title='test'))
`;
  return execFileSync(python, ['-c', script], {encoding:'utf8'});
}

function backend(saved = {}) {return {state:structuredClone(saved), fail:false};}

function start(page, server) {
  const dom = new JSDOM(pageHtml(page), {runScripts:'outside-only', url:`http://localhost:8000/${page === 'cover' ? '' : page}`});
  const w = dom.window;
  const calls = [];
  const navigations = [];
  w.HTMLElement.prototype.scrollIntoView = function() {};
  w.__energyCoachNavigate = value => navigations.push(value);
  w.__energyCoachReplace = value => navigations.push('replace:' + value);
  w.fetch = async (url, options = {}) => {
    const body = options.body && JSON.parse(options.body);
    calls.push({url, body});
    if (server.fail) return {ok:false, json:async () => ({detail:'temporary failure'})};
    if (url === '/api/survey') return {ok:true, json:async () => fixture};
    if (url === '/api/diagnosis') server.state = {...server.state, answers:body.answers, measurements:body.measurements, report:fixture.report, missions:{}};
    if (url.startsWith('/api/missions/')) server.state.missions = {...server.state.missions, [url.split('/').pop()]:body.completed};
    if (url === '/api/profile') server.state.profile = body;
    return {ok:true, json:async () => structuredClone(server.state)};
  };
  require('node:vm').runInContext(readFileSync(path.join(__dirname, '../static/energy-coach.js'), 'utf8'), dom.getInternalVMContext());
  return {w, calls, navigations, close:() => w.close()};
}

function fill(w) {
  for (const [key, value] of Object.entries(fixture.answers)) {
    const input = w.document.getElementById(key) || w.document.querySelector(`input[name="${key}"][value="${value}"]`);
    if (input.type === 'radio') input.checked = true; else input.value = value;
    input.dispatchEvent(new w.Event('input', {bubbles:true}));
  }
}

test('each route contains only its own screen', () => {
  for (const page of ['cover','survey','diagnosis','guide','results','solution','myinfo']) {
    const dom = new JSDOM(pageHtml(page));
    assert.equal(dom.window.document.querySelectorAll('.screen').length, 1);
    assert.equal(dom.window.document.querySelector('.screen').id, `screen-${page}`);
    dom.window.close();
  }
});

test('survey submits diagnosis and navigates to the diagnosis page', async () => {
  const server = backend(); const app = start('survey', server); const {w, calls, navigations} = app;
  try {
    await settle(() => w.document.querySelectorAll('[data-question]').length === 17);
    fill(w);
    await w.goTo('diagnosis');
    assert.deepEqual(calls.find(c => c.url === '/api/diagnosis').body.answers, fixture.answers);
    assert.deepEqual(navigations, ['/diagnosis']);
    assert.ok(server.state.report);
  } finally {app.close();}
});

test('result pages independently restore and render the saved report', async () => {
  const server = backend({answers:fixture.answers, report:fixture.report, missions:{}});
  const checks = {
    diagnosis:(w) => assert.equal(w.document.querySelectorAll('#screen-diagnosis article').length, fixture.report.risks.length),
    guide:(w) => assert.equal(w.document.querySelectorAll('#mission-list .mission-card').length, 3),
    results:(w) => assert.equal(w.document.querySelectorAll('#screen-results .snap-center').length, 3),
    solution:(w) => assert.equal(w.document.querySelectorAll('#screen-solution article').length, fixture.report.solutions.length),
  };
  for (const [page, check] of Object.entries(checks)) {
    const app = start(page, server);
    try {await settle(() => !app.w.document.querySelector('#page-loading')); check(app.w);}
    finally {app.close();}
  }
});

test('guide mission and profile persist across independent pages', async () => {
  const server = backend({answers:fixture.answers, report:fixture.report, missions:{}, profile:{name:'<img src=x onerror=alert(1)>'}});
  const guide = start('guide', server);
  try {
    await settle(() => guide.w.document.querySelectorAll('#mission-list .mission-card').length === 3);
    guide.w.document.querySelector('#mission-list .mission-toggle').click();
    await settle(() => Object.values(server.state.missions).includes(true));
  } finally {guide.close();}
  const profile = start('myinfo', server);
  try {
    await settle(() => !profile.w.document.querySelector('#page-loading'));
    assert.equal(profile.w.document.querySelectorAll('#screen-myinfo img').length, 0);
    assert.match(profile.w.document.querySelector('#screen-myinfo main').textContent, /1 \/ 3/);
  } finally {profile.close();}
});

test('protected page without report redirects to survey', async () => {
  const app = start('results', backend());
  try {await settle(() => app.navigations.length > 0); assert.deepEqual(app.navigations, ['replace:/survey']);}
  finally {app.close();}
});

test('API failure keeps survey usable and shows retryable error', async () => {
  const server = backend(); const app = start('survey', server); const {w} = app;
  try {
    await settle(() => w.document.querySelectorAll('[data-question]').length === 17);
    fill(w); server.fail = true;
    await w.goTo('diagnosis');
    assert.match(w.document.querySelector('#app-message').textContent, /temporary failure/);
    assert.equal(w.document.querySelector('#screen-survey footer button').disabled, false);
  } finally {app.close();}
});
