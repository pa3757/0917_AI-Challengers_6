// DOM/controller tests. No browser rendering or external network is required.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {execFileSync} = require('node:child_process');
const {JSDOM} = require('jsdom');
const path = require('node:path');
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const fixture = JSON.parse(execFileSync(python, ['-c', `
import json
from app.service import questions, diagnose, load_user_input_definitions
answers = {q['question_id']: q['options'][-1]['code'] for q in questions() if q['type'] == 'single_select'}
answers.update(Q01=100, Q02=24, Q03='EMPTY_31_50', Q05='BOTH_ON', Q06='OVER_30_MIN')
print(json.dumps({'questions':questions(),'measurements':load_user_input_definitions(),'answers':answers,'report':diagnose(answers,{},True)}))
`], {encoding:'utf8'}));
const settle = async predicate => {
  for (let i = 0; i < 100; i++) {if (predicate()) return; await new Promise(r => setTimeout(r, 5));}
  throw new Error('Controller did not settle');
};
function start(saved = {}) {
  const dom = new JSDOM(readFileSync(path.join(__dirname, '../energy-coach.html'), 'utf8'), {runScripts:'outside-only', url:'http://localhost:8000'});
  const w = dom.window;
  let server = structuredClone(saved);
  let fail = false;
  const calls = [];
  w.HTMLElement.prototype.scrollIntoView = function() {};
  w.fetch = async (url, options) => {
    const body = options.body && JSON.parse(options.body);
    calls.push({url, body});
    if (fail) return {ok:false, json:async () => ({detail:'temporary failure'})};
    if (url === '/api/survey') return {ok:true, json:async () => fixture};
    if (url === '/api/diagnosis') server = {...server, answers:body.answers, measurements:body.measurements, report:fixture.report, missions:{}};
    if (url.startsWith('/api/missions/')) server.missions = {...server.missions, [url.split('/').pop()]:body.completed};
    if (url === '/api/profile') server.profile = body;
    return {ok:true, json:async () => structuredClone(server)};
  };
  require('node:vm').runInContext(readFileSync(path.join(__dirname, '../static/energy-coach.js'), 'utf8'), dom.getInternalVMContext());
  return {w, calls, close:() => w.close(), fail:value => fail = value};
}
function fill(w) {
  for (const [key, value] of Object.entries(fixture.answers)) {
    const input = w.document.getElementById(key) || w.document.querySelector(`input[name="${key}"][value="${value}"]`);
    if (input.type === 'radio') input.checked = true; else input.value = value;
    input.dispatchEvent(new w.Event('input', {bubbles:true}));
  }
}

test('survey → diagnosis → guide → results → details → profile and re-diagnosis', async () => {
  const app = start(); const {w, calls} = app;
  try {
    await settle(() => w.document.querySelectorAll('[data-question]').length === 17);
    await w.goTo('diagnosis');
    assert.equal(calls.filter(c => c.url === '/api/diagnosis').length, 0);
    w.document.querySelector('#app-message button').click();
    fill(w);
    await w.goTo('diagnosis');
    assert.equal(w.document.querySelector('.screen.active').id, 'screen-diagnosis');
    assert.deepEqual(calls.find(c => c.url === '/api/diagnosis').body.answers, fixture.answers);
    assert.equal(w.document.querySelectorAll('#screen-diagnosis article').length, fixture.report.risks.length);
    await w.goTo('guide');
    assert.equal(w.document.querySelectorAll('#mission-list .mission-card').length, 3);
    w.document.querySelector('#mission-list .mission-toggle').click();
    await settle(() => w.document.querySelector('#mission-list .mission-toggle').getAttribute('aria-pressed') === 'true');
    await w.goTo('results');
    assert.equal(w.document.querySelectorAll('#screen-results .snap-center').length, 3);
    assert.ok(!w.document.querySelector('#screen-results main').textContent.includes('520 ~ 840'));
    await w.goTo('solution');
    assert.equal(w.document.querySelectorAll('#screen-solution article').length, fixture.report.solutions.length);
    await w.goTo('myinfo');
    assert.match(w.document.querySelector('#screen-myinfo main').textContent, /1 \/ 3/);
    await w.goTo('survey');
    w.document.querySelector('#Q01').value = '80';
    w.document.querySelector('#Q01').dispatchEvent(new w.Event('input', {bubbles:true}));
    await w.goTo('diagnosis');
    assert.equal(calls.filter(c => c.url === '/api/diagnosis').length, 2);
    assert.equal(w.document.querySelectorAll('#screen-diagnosis nav').length, 1);
  } finally {app.close();}
});

test('saved report restores; profile text escapes markup; no-risk report can rerender', async () => {
  const saved = {answers:fixture.answers, report:fixture.report, missions:{}, profile:{name:'<img src=x onerror=alert(1)>'}};
  const app = start(saved); const {w} = app;
  try {
    await settle(() => w.document.querySelectorAll('[data-question]').length === 17);
    await w.goTo('myinfo');
    assert.equal(w.document.querySelectorAll('#screen-myinfo img').length, 0);
    assert.match(w.document.querySelector('#screen-myinfo main').textContent, /<img src=x/);
    const empty = {risks:[], solutions:[], calculations:[], ranking:{top_recommendations:[]}, notice:'test'};
    w.renderDiagnosis(empty); w.renderGuide(empty); w.renderResults(empty); w.renderSolutions(empty);
    w.renderGuide(fixture.report);
    assert.equal(w.document.querySelectorAll('#mission-list .mission-card').length, 3);
  } finally {app.close();}
});

test('API failure preserves old report and shows retryable error', async () => {
  const app = start(); const {w} = app;
  try {
    await settle(() => w.document.querySelectorAll('[data-question]').length === 17);
    fill(w); app.fail(true);
    await w.goTo('diagnosis');
    assert.match(w.document.querySelector('#app-message').textContent, /temporary failure/);
    assert.equal(w.document.querySelector('#screen-survey footer button').disabled, false);
    app.fail(false); await w.goTo('diagnosis');
    assert.equal(w.document.querySelector('.screen.active').id, 'screen-diagnosis');
  } finally {app.close();}
});
