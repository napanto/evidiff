/* SPDX-License-Identifier: AGPL-3.0-only */
'use strict';
const store = {
  get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* Storage is optional. */ } },
  remove(key) { try { localStorage.removeItem(key); } catch (_) { /* Storage is optional. */ } }
};
const root = document.documentElement;
const savedTheme = store.get('me-theme');
if (savedTheme === 'dark' || savedTheme === 'light') root.dataset.theme = savedTheme;
document.querySelectorAll('.theme-toggle').forEach(button => button.addEventListener('click', () => {
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  store.set('me-theme', root.dataset.theme);
}));
document.querySelectorAll('[data-language]').forEach(button => button.addEventListener('click', event => {
  store.set('me-lang', event.currentTarget.dataset.language);
}));
const savedLang = store.get('me-lang');
if (!new URL(location.href).searchParams.has('lang') && ['it', 'en'].includes(savedLang) && savedLang !== root.lang) {
  const next = new URL(location.href); next.searchParams.set('lang', savedLang); location.replace(next);
}
const sessionId = document.body.dataset.session;
if (sessionId) {
  const codeKey = 'me-code-' + sessionId;
  const newCode = document.querySelector('[data-new-code]')?.dataset.newCode;
  if (newCode) store.set(codeKey, newCode);
  const code = newCode || store.get(codeKey);
  if (code && code.endsWith(document.body.dataset.codeHint)) {
    document.querySelectorAll('.personal-code').forEach(el => { el.textContent = code; });
    document.querySelectorAll('.code-unavailable').forEach(el => { el.hidden = true; });
    document.querySelectorAll('.copy-code').forEach(el => el.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(code); el.textContent = el.dataset.copied; }
      catch (_) { const range = document.createRange(); range.selectNodeContents(el.previousElementSibling); const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range); }
    }));
  } else document.querySelectorAll('.copy-code').forEach(el => { el.disabled = true; });
}
const confirmedDraft = document.body.dataset.savedDraft;
if (confirmedDraft && sessionId) store.remove('me-draft-' + sessionId + '-' + confirmedDraft);
const confirmedFeedback = document.body.dataset.savedFeedback;
if (confirmedFeedback) store.remove('me-draft-feedback-' + (sessionId || 'visitor') + '-' + confirmedFeedback);
const form = document.querySelector('.answer-form');
if (form) {
  // The only navigation state is a question id. Answers are ordinary form values;
  // a radio change never changes the current question or the reader's position.
  // What the result sentence states first (finding, comparison, statistics), then the
  // methods in the order an abstract is usually read; codes unchanged.
  const fields = ['result', 'comparison', 'significance', 'analysis', 'groups', 'sample_size', 'context'];
  const q2Fields = ['exposure', 'outcome', 'comparison'];
  const steps = [...form.querySelectorAll('.task-step[data-step]')];
  const byId = new Map(steps.map(step => [step.dataset.step, step]));
  const controls = [...form.querySelectorAll('input:not([type=hidden]), select, textarea')];
  const draftKey = 'me-draft-' + sessionId + '-' + form.dataset.draft;
  // A correction of a submitted pair starts from the latest saved answer, sent by the
  // server, and keeps no local draft: leaving the page discards unsaved changes.
  let prefill = null;
  try { prefill = JSON.parse(form.dataset.prefill || 'null'); } catch (_) { prefill = null; }
  const pathInput = form.querySelector('[name=path]');
  const nextButton = form.querySelector('.task-continue, .instrument-next');
  const backButton = form.querySelector('.decision-back');
  const saveButton = form.querySelector('.submit-answer');
  const card = document.querySelector('.task-card');
  const source = document.querySelector('.source-column');
  const narrow = matchMedia('(max-width: 899px)');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const it = root.lang === 'it';
  const copy = {
    next: it ? 'Continua →' : 'Continue →',
    nextB: it ? 'Continua con l’abstract B →' : 'Continue to abstract B →',
    nextComparison: it ? 'Continua con il confronto →' : 'Continue to comparison →',
    review: it ? 'Rivedi e invia →' : 'Review and submit →',
    edit: it ? 'Modifica' : 'Change',
    answer: it ? 'Scegli una risposta.' : 'Choose an answer.',
    problem: it ? 'Indica qual è il problema.' : 'Choose the problem.',
    reason: it ? 'Scegli il motivo.' : 'Choose a reason.',
    main: it ? 'Scegli il motivo principale.' : 'Choose the main reason.',
    detail: it ? 'Descrivi brevemente la differenza.' : 'Briefly describe the difference.',
    factor: it ? 'Scegli la differenza indicata negli abstract.' : 'Choose the difference described in the abstracts.',
    cleared: it ? 'Il percorso è cambiato: le risposte alle domande che dipendevano da questa scelta sono state cancellate.' : 'The path has changed: answers to questions that depended on this choice have been cleared.',
    stage: {a: 'Abstract A', b: 'Abstract B', comparison: it ? 'Confronto' : 'Comparison', review: it ? 'Invio' : 'Submit'},
    locked: it ? 'Prima rispondi alle domande precedenti' : 'Answer the earlier questions first',
  };
  let current = `q1.a.${fields[0]}`;
  let editReturn = '';
  let passed = new Set();
  let branchChanged = false;
  let programmaticFocus = false;
  let pointerFocus = false;
  document.addEventListener('pointerdown', () => { pointerFocus = true; }, {capture: true});
  document.addEventListener('keydown', () => { pointerFocus = false; }, {capture: true});
  const focusWithoutScroll = target => {
    if (!target) return;
    programmaticFocus = true; target.focus({preventScroll: true}); programmaticFocus = false;
  };
  const headerOffset = () => {
    const header = document.querySelector('.task-header');
    return header && ['sticky', 'fixed'].includes(getComputedStyle(header).position) ? header.getBoundingClientRect().height : 0;
  };
  const matching = name => controls.filter(el => el.name === name);
  const value = name => {
    const list = matching(name);
    return list[0]?.type === 'radio' ? list.find(el => el.checked)?.value || '' : list[0]?.value || '';
  };
  const checked = name => matching(name).filter(el => el.checked).map(el => el.value);
  const clear = name => matching(name).forEach(el => {
    if (el.type === 'radio' || el.type === 'checkbox') el.checked = false;
    else el.value = '';
  });
  const hasIssue = () => ['a', 'b'].some(side => fields.some(field => ['no', 'cannot_tell'].includes(value(`q1.${side}.${field}`))));
  const hasError = () => ['a', 'b'].some(side => fields.some(field => value(`q1.${side}.${field}`) === 'no'));
  // Result problems that usually change the finding itself (non-blocking relevance notice).
  const findingProblems = ['not_supported_by_abstract', 'wrong_direction', 'wrong_exposure_outcome', 'planned_as_observed'];
  const findingChanged = () => ['a', 'b'].some(side => value(`q1.${side}.result`) === 'no'
    && checked(`q1.${side}.result.problems`).some(problem => findingProblems.includes(problem)));
  const failures = () => q2Fields.filter(field => ['no', 'cannot_tell'].includes(value('q2.' + field)));
  // «I cannot establish what is being compared» is offered only when a Finding or
  // Comparison row has a problem or an uncertainty. The server
  // still accepts it on any path, so a page loaded before this change keeps working.
  const coreIssue = () => ['a', 'b'].some(side => ['result', 'comparison'].some(field => ['no', 'cannot_tell'].includes(value(`q1.${side}.${field}`))));
  const unoffered = () => value('q1.relevance') === 'cannot_establish_comparison' && !coreIssue();
  // Drafts saved from this wording on; an older draft's Q2 «other» reason had another label.
  const wording = '2026-11-15';
  const route = () => {
    const ids = ['a', 'b'].flatMap(side => fields.map(field => `q1.${side}.${field}`));
    if (hasIssue()) {
      ids.push('q1.relevance');
      if (value('q1.relevance') !== 'not_material') return [...ids, 'review'];
    }
    ids.push(...q2Fields.map(field => 'q2.' + field));
    if (failures().length) {
      if (failures().length > 1) ids.push('q2.primary');
      return [...ids, 'review'];
    }
    ids.push('q3');
    if (value('q3') === 'no') {
      ids.push('q4');
      if (value('q4') === 'opposite') ids.push('q5.answer');
    }
    return [...ids, 'review'];
  };
  // A stage opens once every question of the earlier stages is answered.
  const stageOrder = ['a', 'b', 'comparison', 'review'];
  const reachable = (target, ids = route()) => ids.every(id => id === 'review'
    || stageOrder.indexOf(byId.get(id)?.dataset.stage) >= stageOrder.indexOf(target) || !issue(id));
  const issue = id => {
    if (id === 'review') return '';
    const answer = value(id);
    if (!answer) return copy.answer;
    if (/^q1\.[ab]\./.test(id) && answer === 'no' && !checked(id + '.problems').length) return copy.problem;
    if (id === 'q1.relevance' && answer === 'material' && !hasError()) return form.dataset.materialError || copy.problem;
    if (['q2.exposure', 'q2.comparison'].includes(id) && answer === 'no') {
      if (!value(id + '.reason')) return copy.reason;
      if (value(id + '.reason') === 'other' && !value(id + '.detail').trim()) return copy.detail;
    }
    if (id === 'q2.primary' && !failures().includes(answer)) return copy.main;
    if (id === 'q5.answer' && answer === 'yes') {
      if (!value('q5.factor')) return copy.factor;
      if (value('q5.factor') === 'other' && !value('q5.detail').trim()) return copy.detail;
    }
    return '';
  };
  const path = () => {
    const result = {q1: Object.fromEntries(['a', 'b'].map(side => [side, Object.fromEntries(fields.map(field => {
      const name = `q1.${side}.${field}`;
      return [field, {answer: value(name), problems: value(name) === 'no' ? checked(name + '.problems') : []}];
    }))]))};
    if (hasIssue()) {
      result.q1_relevance = value('q1.relevance');
      if (result.q1_relevance !== 'not_material') return result;
    }
    if (!q2Fields.some(field => value('q2.' + field))) return result;
    result.q2 = Object.fromEntries(q2Fields.map(field => {
      const id = 'q2.' + field, row = {answer: value(id)};
      if (row.answer === 'no') {
        row.reason = field === 'outcome' ? 'outcome_definition' : value(id + '.reason');
        if (row.reason === 'other') row.detail = value(id + '.detail').trim();
      }
      return [field, row];
    }));
    if (failures().length) {
      result.q2_primary = failures().length === 1 ? failures()[0] : value('q2.primary');
      return result;
    }
    if (!value('q3')) return result;
    result.q3 = value('q3');
    if (result.q3 !== 'no' || !value('q4')) return result;
    result.q4 = value('q4');
    if (result.q4 !== 'opposite' || !value('q5.answer')) return result;
    result.q5 = {answer: value('q5.answer')};
    if (result.q5.answer === 'yes') {
      result.q5.factor = value('q5.factor');
      if (result.q5.factor === 'other') result.q5.detail = value('q5.detail').trim();
    }
    return result;
  };
  const selectionText = name => {
    const list = matching(name);
    const selected = list[0]?.tagName === 'SELECT' ? list[0].selectedOptions[0] : list.find(el => el.checked)?.closest('label');
    return (selected?.querySelector(':scope > span') || selected)?.textContent.trim() || '';
  };
  const answerText = id => {
    let text = selectionText(id);
    if (/^q1\.[ab]\./.test(id) && value(id) === 'no') {
      text += ': ' + matching(id + '.problems').filter(el => el.checked).map(el => el.closest('label').textContent.trim()).join(', ');
    } else if (id.startsWith('q2.') && value(id) === 'no') {
      const reason = id === 'q2.outcome' ? byId.get(id).querySelector('.comparison-reason')?.textContent.trim() : selectionText(id + '.reason');
      if (reason) text += ': ' + reason;
      if (value(id + '.reason') === 'other') text += ' — ' + value(id + '.detail').trim();
    }
    return text;
  };
  const save = () => {
    if (prefill) return;
    const values = {};
    controls.forEach(el => { values[el.name] = el.type === 'checkbox' ? checked(el.name) : el.type === 'radio' ? value(el.name) : el.value; });
    store.set(draftKey, JSON.stringify({version: '2.0', wording, values, step: current, presentation: {model: 24, passed: [...passed], editReturn}}));
  };
  const scrollFrames = new WeakMap();
  const scrollTo = (container, top) => {
    cancelAnimationFrame(scrollFrames.get(container));
    if (reduced.matches) { container.scrollTop = top; return; }
    const from = container.scrollTop, start = performance.now();
    const frame = now => {
      const t = Math.min(1, (now - start) / 180);
      container.scrollTop = from + (top - from) * (1 - (1 - t) ** 2);
      if (t < 1) scrollFrames.set(container, requestAnimationFrame(frame));
    };
    scrollFrames.set(container, requestAnimationFrame(frame));
  };
  const revealFocused = target => {
    if (!target || !target.getClientRects().length || target.closest('.task-actions')) return;
    const barHeight = narrow.matches ? form.querySelector('.task-actions')?.getBoundingClientRect().height || 100 : 0;
    const box = target.getBoundingClientRect(), visibleTop = headerOffset() + 12;
    if (box.bottom > innerHeight - barHeight - 12 || box.top < visibleTop) {
      const delta = box.top < visibleTop ? box.top - visibleTop : box.bottom - innerHeight + barHeight + 16;
      scrollTo(document.scrollingElement, document.scrollingElement.scrollTop + delta);
    }
  };
  const animate = el => {
    if (!reduced.matches && el) el.animate([{opacity: .4, transform: 'translateY(3px)'}, {opacity: 1, transform: 'translateY(0)'}], {duration: 160, easing: 'ease-out'});
  };
  const progressText = step => {
    const stage = step.dataset.stage, id = step.dataset.step;
    if (id === 'q1.relevance') return it ? 'A e B · effetto sul risultato' : 'A and B · effect on the finding';
    if (stage === 'a' || stage === 'b') return `${copy.stage[stage]} · ${it ? 'controllo' : 'check'} ${fields.indexOf(id.split('.')[2]) + 1} ${it ? 'di' : 'of'} 7`;
    if (stage === 'comparison') return `${copy.stage.comparison} · ${it ? 'domanda' : 'question'} ${route().filter(key => byId.get(key)?.dataset.stage === stage).indexOf(id) + 1}`;
    return copy.stage.review;
  };
  const makeSummaryRow = (id, review = false, factor = false) => {
    const row = document.createElement('div'); row.className = 'answer-summary-row'; row.dataset.summaryStep = id;
    const keyword = document.createElement('span'); keyword.className = 'summary-keyword'; keyword.textContent = factor ? (it ? 'Differenza indicata' : 'Difference chosen') : byId.get(id).dataset.keyword;
    const answer = document.createElement('span'); answer.className = 'summary-answer'; answer.textContent = factor ? selectionText('q5.factor') + (value('q5.factor') === 'other' ? ' — ' + value('q5.detail').trim() : '') : answerText(id);
    const button = document.createElement('button'); button.type = 'button'; button.className = 'change-check'; button.textContent = copy.edit;
    button.setAttribute('aria-label', `${copy.edit}: ${keyword.textContent}`);
    button.addEventListener('click', () => { editReturn = review ? 'review' : ''; navigate(id); });
    row.append(keyword, answer, button); return row;
  };
  const renderSummaries = () => {
    const ids = route(), step = byId.get(current), list = form.querySelector('.done-list');
    const done = ids.slice(0, ids.indexOf(current)).filter(id => byId.get(id)?.dataset.stage === step.dataset.stage && !issue(id));
    list?.replaceChildren(...done.map(id => makeSummaryRow(id)));
    const disclosure = form.querySelector('.done-disclosure');
    if (disclosure) {
      disclosure.hidden = !done.length || current === 'review';
      if (!narrow.matches) disclosure.open = true;
      const count = disclosure.querySelector('.done-count');
      if (count) count.textContent = step.dataset.stage === 'comparison'
        ? (it ? `${done.length} ${done.length === 1 ? 'domanda fatta' : 'domande fatte'}` : `${done.length} ${done.length === 1 ? 'question answered' : 'questions answered'}`)
        : (it ? `${done.length} ${done.length === 1 ? 'controllo fatto' : 'controlli fatti'}` : `${done.length} ${done.length === 1 ? 'check done' : 'checks done'}`);
    }
    const review = form.querySelector('.review-list');
    if (review && current === 'review') {
      review.replaceChildren();
      ['a', 'b', 'comparison'].forEach(stage => {
        const group = ids.filter(id => id !== 'review' && byId.get(id)?.dataset.stage === stage);
        if (!group.length) return;
        const section = document.createElement('section'); section.className = 'review-group';
        const heading = document.createElement('h3'); heading.textContent = copy.stage[stage]; section.append(heading, ...group.flatMap(id => id === 'q5.answer' && value(id) === 'yes' ? [makeSummaryRow(id, true), makeSummaryRow(id, true, true)] : [makeSummaryRow(id, true)])); review.append(section);
      });
    }
    const problems = form.querySelector('.problem-review-list');
    problems?.replaceChildren(...ids.filter(id => /^q1\.[ab]\./.test(id) && ['no', 'cannot_tell'].includes(value(id))).map(id => {
      const row = document.createElement('p'); row.textContent = `${id.split('.')[1].toUpperCase()} · ${byId.get(id).dataset.keyword} · ${answerText(id)}`; return row;
    }));
  };
  let previousSourceStage = '', previousSourceQuestion = '';
  const renderSources = () => {
    if (!source) return;
    const step = byId.get(current), stage = step.dataset.stage;
    const side = current === 'q1.relevance' ? '' : ['a', 'b'].includes(stage) ? stage : '';
    source.hidden = stage === 'review';
    source.querySelectorAll('[data-source-side]').forEach(article => {
      article.hidden = !!side && article.dataset.sourceSide !== side;
      const ids = (step.dataset['evidence' + article.dataset.sourceSide.toUpperCase()] || '').split(',').filter(Boolean);
      article.querySelectorAll('[data-sentence-id]').forEach(sentence => sentence.classList.toggle('active-evidence', ids.includes(sentence.dataset.sentenceId)));
    });
    if (stage !== previousSourceStage) { animate(source); previousSourceStage = stage; }
    const questionChanged = current !== previousSourceQuestion;
    previousSourceQuestion = current;
    if (questionChanged && !narrow.matches && !source.hidden) requestAnimationFrame(() => {
      const target = source.querySelector('[data-source-side]:not([hidden]) .active-evidence') || source.querySelector('[data-source-side]:not([hidden])');
      if (!target) return;
      const box = source.getBoundingClientRect(), targetBox = target.getBoundingClientRect();
      if (targetBox.top < box.top + 12 || targetBox.bottom > box.bottom - 12) scrollTo(source, source.scrollTop + targetBox.top - box.top - 16);
    });
  };
  const render = () => {
    const ids = route();
    if (!ids.includes(current) || !byId.has(current)) current = ids.find(id => issue(id)) || 'review';
    const step = byId.get(current), stage = step.dataset.stage;
    form.dataset.currentStep = current; form.dataset.currentStage = stage;
    const badge = form.querySelector('.current-block-badge');
    if (badge) { badge.textContent = stage === 'a' ? 'A' : stage === 'b' ? (current === 'q1.relevance' ? 'A+B' : 'B') : stage === 'review' ? '✓' : '⇄'; badge.dataset.side = stage; }
    steps.forEach(el => { el.hidden = el !== step; el.classList.toggle('is-current-step', el === step); });
    form.querySelectorAll('.field-problems').forEach(el => { el.hidden = value(el.closest('.task-step').dataset.step) !== 'no'; });
    form.querySelectorAll('.comparison-reason').forEach(el => { el.hidden = value(el.closest('.task-step').dataset.step) !== 'no'; });
    form.querySelectorAll('.q2-other').forEach(el => { el.hidden = value('q2.comparison') !== 'no' || value('q2.comparison.reason') !== 'other'; });
    form.querySelectorAll('[data-primary]').forEach(el => { el.hidden = !failures().includes(el.dataset.primary); });
    form.querySelectorAll('.q5-factor').forEach(el => { el.hidden = value('q5.answer') !== 'yes'; });
    form.querySelectorAll('.q5-other').forEach(el => { el.hidden = value('q5.answer') !== 'yes' || value('q5.factor') !== 'other'; });
    const material = form.querySelector('[name="q1.relevance"][value="material"]');
    if (material) material.disabled = !hasError();
    const uncertain = form.querySelector('[name="q1.relevance"][value="cannot_establish_comparison"]');
    if (uncertain) {
      uncertain.disabled = !coreIssue();
      const label = uncertain.closest('label'); if (label) label.hidden = uncertain.disabled;
    }
    const notice = form.querySelector('.relevance-notice');
    if (notice) {
      const show = value('q1.relevance') === 'not_material' && findingChanged();
      const text = show ? notice.dataset.notice : '';
      notice.hidden = !show;
      if (notice.textContent !== text) notice.textContent = text;
    }
    const caption = form.querySelector('.card-progress'); if (caption) caption.textContent = progressText(step);
    const dots = form.querySelector('.stage-dots');
    if (dots) {
      dots.replaceChildren();
      if (['a', 'b'].includes(stage) && current !== 'q1.relevance') fields.forEach((field, index) => {
        const dot = document.createElement('span'); dot.className = 'stage-dot'; dot.classList.toggle('is-current', index === fields.indexOf(current.split('.')[2])); dot.classList.toggle('is-done', passed.has(`q1.${stage}.${field}`)); dots.append(dot);
      });
    }
    document.querySelectorAll('[data-go-stage], [data-stage-target]').forEach(button => {
      const target = button.dataset.goStage || button.dataset.stageTarget;
      const group = ids.filter(id => byId.get(id)?.dataset.stage === target && id !== 'review');
      const complete = target === 'review' ? ids.every(id => !issue(id)) : !!group.length && group.every(id => !issue(id) && passed.has(id));
      const terminal = hasIssue() && ['material', 'cannot_establish_comparison'].includes(value('q1.relevance'));
      const locked = target !== stage && !reachable(target, ids);
      button.hidden = target === 'comparison' && terminal;
      button.disabled = locked;
      button.classList.toggle('is-locked', locked);
      if (locked) button.title = copy.locked; else button.removeAttribute('title');
      button.classList.toggle('is-current', target === stage); button.classList.toggle('is-complete', complete && target !== stage);
      const tick = button.querySelector('.stage-complete'); if (tick) tick.hidden = !(complete && target !== stage);
      if (target === stage) button.setAttribute('aria-current', 'step'); else button.removeAttribute('aria-current');
    });
    nextButton.hidden = current === 'review'; nextButton.disabled = false;
    saveButton.hidden = current !== 'review';
    document.body.classList.toggle('task-review', current === 'review');
    form.querySelectorAll('.comment-toggle, .comment-disclosure').forEach(el => { el.hidden = current === 'review'; });
    backButton.hidden = ids.indexOf(current) === 0;
    const next = ids[ids.indexOf(current) + 1], nextStage = byId.get(next)?.dataset.stage;
    nextButton.textContent = editReturn === 'review' && !ids.some(id => id !== current && issue(id)) ? copy.review : next === 'review' ? copy.review : nextStage === 'b' && stage === 'a' ? copy.nextB : nextStage === 'comparison' && stage === 'b' ? copy.nextComparison : copy.next;
    const branch = form.querySelector('.branch-notice'); if (branch) { branch.hidden = !branchChanged; branch.textContent = copy.cleared; }
    pathInput.value = JSON.stringify(path()); renderSummaries(); renderSources();
  };
  const hideErrors = () => {
    form.querySelectorAll('.step-error, .instrument-error').forEach(el => { el.hidden = true; });
    controls.filter(el => el.dataset.taskError).forEach(el => {
      const ids = (el.getAttribute('aria-describedby') || '').split(' ').filter(id => id && id !== el.dataset.taskError);
      if (ids.length) el.setAttribute('aria-describedby', ids.join(' ')); else el.removeAttribute('aria-describedby');
      el.removeAttribute('aria-invalid'); delete el.dataset.taskError;
    });
  };
  const navigate = id => {
    current = id; hideErrors();
    const doneDisclosure = form.querySelector('.done-disclosure');
    if (narrow.matches && doneDisclosure) doneDisclosure.open = false;
    render(); save();
    const step = byId.get(current), heading = step.querySelector('.question-heading');
    focusWithoutScroll(heading);
    const announcement = form.querySelector('.check-announcement'); if (announcement) announcement.textContent = progressText(step);
    animate(step);
    if (card) {
      const top = card.getBoundingClientRect().top + document.scrollingElement.scrollTop - headerOffset();
      scrollTo(document.scrollingElement, Math.max(0, top));
    }
  };
  const showError = id => {
    if (current !== id) navigate(id);
    hideErrors();
    const step = byId.get(id), error = step.querySelector('.step-error') || form.querySelector('.instrument-error');
    if (!error) return;
    let container = step.querySelector('.instrument-options'), control = null;
    if (/^q1\.[ab]\./.test(id) && value(id) === 'no') {
      container = step.querySelector('.field-problems');
      control = container?.querySelector('input[type=checkbox]:not(:disabled)');
    } else if (['q2.exposure', 'q2.comparison'].includes(id) && value(id) === 'no') {
      container = step.querySelector('.comparison-reason');
      control = container?.querySelector(value(id + '.reason') === 'other' ? '.q2-other input' : 'select');
    } else if (id === 'q5.answer' && value(id) === 'yes') {
      container = step.querySelector('.q5-factor');
      control = container?.querySelector(value('q5.factor') === 'other' ? '.q5-other input' : 'select');
    }
    control ||= [...(container?.querySelectorAll('input,select,textarea') || [])].find(el => !el.disabled && el.getClientRects().length);
    if (container) container.prepend(error);
    error.id = 'task-error-' + id.replaceAll('.', '-');
    error.textContent = issue(id); error.hidden = false;
    if (control) {
      control.dataset.taskError = error.id;
      control.setAttribute('aria-invalid', 'true');
      control.setAttribute('aria-describedby', [control.getAttribute('aria-describedby'), error.id].filter(Boolean).join(' '));
      focusWithoutScroll(control);
    }
    const top = error.getBoundingClientRect().top + document.scrollingElement.scrollTop - headerOffset() - 16;
    scrollTo(document.scrollingElement, Math.max(0, top));
  };

  const advance = () => {
    if (issue(current)) { showError(current); return; }
    passed.add(current);
    const ids = route();
    let next = ids[ids.indexOf(current) + 1] || 'review';
    if (editReturn === 'review') {
      // Changed from the summary: go back to it, or to a question the change opened.
      next = ids.find(id => issue(id)) || 'review';
    }
    editReturn = '';
    branchChanged = false; navigate(next);
  };
  const clearRemoved = oldRoute => {
    const removed = oldRoute.filter(id => id !== 'review' && !route().includes(id));
    const hadAnswers = removed.some(id => byId.get(id)?.querySelectorAll('input,select,textarea') && [...byId.get(id).querySelectorAll('input,select,textarea')].some(el => el.type === 'radio' || el.type === 'checkbox' ? el.checked : !!el.value));
    for (const id of removed) {
      const step = byId.get(id);
      step?.querySelectorAll('input,select,textarea').forEach(el => { if (el.name) clear(el.name); });
      passed.delete(id);
    }
    if (hadAnswers) branchChanged = true;
  };
  let previousRoute = route();
  let dropped = false;
  try {
    const draft = prefill || JSON.parse(store.get(draftKey) || 'null');
    if (draft?.version === '2.0' && draft.values && typeof draft.values === 'object') {
      controls.forEach(el => {
        const stored = draft.values[el.name];
        if (el.type === 'checkbox') el.checked = Array.isArray(stored) && stored.includes(el.value);
        else if (el.type === 'radio') el.checked = stored === el.value;
        else if (typeof stored === 'string') {
          el.value = stored;
          // A choice this page no longer offers is dropped quietly.
          if (el.value !== stored) { el.value = ''; dropped = true; }
        }
      });
      new Set(controls.filter(el => el.type === 'radio').map(el => el.name)).forEach(name => {
        const stored = draft.values[name];
        if (typeof stored === 'string' && stored && value(name) !== stored) dropped = true;
      });
      if (!prefill && draft.wording !== wording && value('q2.comparison.reason') === 'other') {
        clear('q2.comparison.reason'); dropped = true;
      }
      if (draft.presentation?.model === 24) {
        if (typeof draft.step === 'string' && byId.has(draft.step)) current = draft.step;
        if (Array.isArray(draft.presentation.passed)) passed = new Set(draft.presentation.passed.filter(id => byId.has(id)));
        if (draft.presentation.editReturn === 'review') editReturn = 'review';
      } else {
        // Preserve answers/comments from the previous UI, without inheriting its
        // scrolling or auto-advance state.
        current = route().find(id => issue(id)) || 'review';
        passed = new Set(route().filter(id => id !== current && id !== 'review' && !issue(id)));
      }
    }
  } catch (_) { /* Broken or absent local storage must never block the task. */ }
  // The server marks a check whose values are all Not extracted or Not reported: only a
  // value missing from the extraction can be wrong there, so the other problems go.
  form.querySelectorAll('.task-step[data-empty-check] .problem-options input').forEach(el => {
    if (el.value === 'missing_from_extraction') return;
    el.checked = false; el.disabled = true; el.closest('label').hidden = true;
  });
  if (unoffered()) { clear('q1.relevance'); dropped = true; }
  if (dropped) {
    // Land on the first question a dropped choice leaves open; every other answer stays.
    current = route().find(id => issue(id)) || current;
    passed = new Set([...passed].filter(id => !issue(id)));
  }
  if (prefill) {
    // Open the summary of the saved answer, or the first question the current rules leave open.
    current = route().find(id => issue(id)) || 'review';
    passed = new Set(route().filter(id => id !== current && id !== 'review' && !issue(id)));
  }
  previousRoute = route();
  form.addEventListener('change', event => {
    const el = event.target, name = el.name || '';
    if (!name || !controls.includes(el)) return;
    if (/^q1\.[ab]\.[^.]+$/.test(name) && value(name) !== 'no') clear(name + '.problems');
    if (!hasIssue() || (!hasError() && value('q1.relevance') === 'material') || unoffered()) clear('q1.relevance');
    if (q2Fields.some(field => name === 'q2.' + field) && value(name) !== 'no') { clear(name + '.reason'); clear(name + '.detail'); }
    if (!failures().includes(value('q2.primary')) || failures().length < 2) clear('q2.primary');
    if (value('q2.comparison.reason') !== 'other') clear('q2.comparison.detail');
    if (value('q5.answer') !== 'yes') { if (value('q5.factor') || value('q5.detail')) branchChanged = true; clear('q5.factor'); clear('q5.detail'); }
    if (value('q5.factor') !== 'other') clear('q5.detail');
    clearRemoved(previousRoute); previousRoute = route();
    if (issue(current)) passed.delete(current);
    hideErrors(); render(); save();
  });
  form.addEventListener('input', () => { pathInput.value = JSON.stringify(path()); save(); });
  form.addEventListener('focusin', event => {
    if (!programmaticFocus && !pointerFocus && event.target.matches('input,select,textarea,button,summary')) {
      requestAnimationFrame(() => { if (!pointerFocus) revealFocused(event.target); });
    }
  });
  nextButton.addEventListener('click', advance);
  backButton.addEventListener('click', () => { editReturn = ''; branchChanged = false; const ids = route(); navigate(ids[Math.max(0, ids.indexOf(current) - 1)]); });
  document.querySelectorAll('[data-go-stage], [data-stage-target]').forEach(button => button.addEventListener('click', () => {
    const stage = button.dataset.goStage || button.dataset.stageTarget, ids = route();
    const group = ids.filter(key => byId.get(key)?.dataset.stage === stage);
    if (!group.length || !reachable(stage, ids) || byId.get(current)?.dataset.stage === stage) return;
    // Open the stage at its first unanswered question, else at its start; then move linearly.
    editReturn = ''; branchChanged = false; navigate(group.find(id => issue(id)) || group[0]);
  }));
  form.addEventListener('submit', event => {
    const incomplete = route().find(id => issue(id));
    if (incomplete) { event.preventDefault(); showError(incomplete); save(); return; }
    if (current !== 'review') { event.preventDefault(); advance(); return; }
    pathInput.value = JSON.stringify(path()); save();
    // Only the server-confirmed saved page removes this draft.
  });
  document.addEventListener('keydown', event => {
    if (event.ctrlKey || event.altKey || event.metaKey || event.defaultPrevented || event.isComposing) return;
    const target = event.target;
    if (target.closest('textarea,select,input:not([type=radio]):not([type=checkbox]),[contenteditable=true],.work-menu,.task-menu')) return;
    if (/^[123]$/.test(event.key) && current !== 'review') {
      const options = [...byId.get(current).querySelectorAll('.instrument-options input[type=radio]')].filter(el => !el.disabled && el.getClientRects().length);
      const option = options[Number(event.key) - 1];
      if (option) { event.preventDefault(); option.checked = true; option.dispatchEvent(new Event('change', {bubbles: true})); focusWithoutScroll(option); revealFocused(option.closest('label')); }
    } else if (event.key === 'Enter' && current !== 'review' && !target.closest('button,a,summary,input[type=checkbox]')) {
      event.preventDefault(); advance();
    } else if (event.key === 'Escape') {
      const help = target.closest('details.check-help[open]');
      if (help) { help.open = false; help.querySelector('summary').focus({preventScroll: true}); event.preventDefault(); }
    }
  });
  const commentToggle = form.querySelector('.comment-toggle');
  const commentDisclosure = form.querySelector('.comment-disclosure');
  if (commentToggle && commentDisclosure) {
    commentToggle.hidden = false;
    commentToggle.setAttribute('aria-expanded', String(commentDisclosure.open));
    commentToggle.addEventListener('click', () => {
      commentDisclosure.open = true;
      const textarea = commentDisclosure.querySelector('textarea');
      focusWithoutScroll(textarea);
      if (narrow.matches) revealFocused(textarea);
      else textarea?.scrollIntoView({block: 'center', behavior: 'instant'});
    });
    commentDisclosure.addEventListener('toggle', () => commentToggle.setAttribute('aria-expanded', String(commentDisclosure.open)));
  }
  // The whole abstract starts closed. Once the reader opens or closes it for one
  // abstract, every other step keeps that choice for the same abstract.
  document.addEventListener('toggle', event => {
    const target = event.target;
    if (!(target instanceof HTMLDetailsElement) || !target.classList.contains('full-abstract')) return;
    document.querySelectorAll(`.full-abstract[data-side="${target.dataset.side}"]`).forEach(other => {
      if (other !== target && other.open !== target.open) other.open = target.open;
    });
  }, true);
  const actions = form.querySelector('.task-actions');
  const header = document.querySelector('.task-header');
  const measureActions = () => {
    if (actions) root.style.setProperty('--task-actions-height', Math.ceil(actions.getBoundingClientRect().height) + 'px');
    if (header) root.style.setProperty('--task-header-height', Math.ceil(header.getBoundingClientRect().height) + 'px');
  };
  if (typeof ResizeObserver !== 'undefined') {
    const observer = new ResizeObserver(measureActions);
    if (actions) observer.observe(actions);
    if (header) observer.observe(header);
  }
  narrow.addEventListener('change', () => { render(); measureActions(); });
  document.body.classList.add('task-enhanced'); form.classList.add('task-enhanced');
  render(); measureActions();
}
for (const feedbackForm of document.querySelectorAll('form[data-feedback-draft]')) {
  const key = 'me-draft-feedback-' + (sessionId || 'visitor') + '-' + feedbackForm.dataset.feedbackDraft;
  const message = feedbackForm.querySelector('textarea');
  if (!message) continue;
  const saved = store.get(key);
  if (saved !== null) message.value = saved;
  message.addEventListener('input', () => store.set(key, message.value));
  feedbackForm.addEventListener('submit', () => store.set(key, message.value));
}
const programme = document.querySelector('[name=programme]');
if (programme) {
  const update = () => {
    const other = programme.value === 'other';
    document.querySelector('.other-programme').hidden = !other;
    document.querySelector('[name=other_programme]').required = other;
  };
  programme.addEventListener('change', update); update();
}
// Automatic resubmission. A POST that meets a network error or a
// gateway error (a reload, a dropped connection, proxy 52x) is sent again for about
// 15 seconds before the browser shows the error. Resending is safe: every form carries a
// single-use nonce, so a POST the server already saved comes back as a redirect to the
// saved page. The handler sits on document, after every form's own submit handler, and
// acts only on submissions those handlers let through. Without JavaScript nothing changes.
(() => {
  const RETRY_STATUS = new Set([502, 503, 504, 520, 521, 522, 523, 524, 530]);
  const DELAYS = [500, 1000, 2000, 3000, 4000, 5000];
  const ATTEMPT_TIMEOUT = 20000;
  const it = document.documentElement.lang === 'it';
  const waitText = it ? 'Connessione in corso, riprovo…' : 'Connecting, trying again…';
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  // The page returned by a POST is written into this document. Its app.js runs again as a
  // module, under a new URL, so its top-level names do not clash with this run's.
  const render = html => {
    const marked = html.replace(
      /<script\b[^>]*\bsrc="([^"]*\/app\.js)(?:\?[^"]*)?"[^>]*><\/script>/,
      (_, src) => `<script type="module" src="${src}?rendered=${Date.now()}"></script>`
    );
    document.open(); document.write(marked); document.close();
  };
  const busy = new WeakSet();
  const reset = form => {
    busy.delete(form);
    form.querySelectorAll('[data-retry-disabled]').forEach(el => { el.disabled = false; delete el.dataset.retryDisabled; });
    form.querySelector('.retry-notice')?.remove();
  };
  const nativeSubmit = (form, submitter) => {
    // The last resort shows the real error page; the local draft stays until a saved page.
    if (submitter?.name) {
      const carried = document.createElement('input');
      carried.type = 'hidden'; carried.name = submitter.name; carried.value = submitter.value;
      form.append(carried);
    }
    reset(form);
    HTMLFormElement.prototype.submit.call(form);
  };
  const send = async (form, url, body, submitter) => {
    let notice = null;
    for (let attempt = 0; ; attempt += 1) {
      let response = null;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT);
      try {
        response = await fetch(url, {method: 'POST', body, credentials: 'same-origin', signal: controller.signal});
      } catch (_) { response = null; }
      clearTimeout(timer);
      if (response && !RETRY_STATUS.has(response.status)) {
        if (response.redirected) { location.assign(response.url); return; }
        render(await response.text());
        return;
      }
      if (attempt >= DELAYS.length) { nativeSubmit(form, submitter); return; }
      if (!notice) {
        notice = document.createElement('p');
        notice.className = 'fine retry-notice';
        notice.setAttribute('role', 'status'); notice.setAttribute('aria-live', 'polite');
        (submitter && form.contains(submitter) ? submitter : form.lastElementChild || form).after(notice);
        notice.textContent = waitText;
      }
      await sleep(DELAYS[attempt]);
    }
  };
  const onSubmit = event => {
    const form = event.target;
    if (event.defaultPrevented || !(form instanceof HTMLFormElement)) return;
    if ((form.getAttribute('method') || '').toLowerCase() !== 'post' || form.getAttribute('target')) return;
    let action;
    try { action = new URL(form.getAttribute('action') || location.href, location.href); } catch (_) { return; }
    if (action.origin !== location.origin) return;
    event.preventDefault();
    if (busy.has(form)) return;
    const submitter = event.submitter || null;
    let data;
    try { data = new FormData(form, submitter || undefined); } catch (_) { data = new FormData(form); }
    if (submitter?.name && !data.has(submitter.name)) data.append(submitter.name, submitter.value);
    const body = new URLSearchParams(data);  // the same encoding as a native form post
    busy.add(form);
    form.querySelectorAll('button, input[type=submit]').forEach(el => {
      if (!el.disabled) { el.disabled = true; el.dataset.retryDisabled = '1'; }
    });
    send(form, action.href, body, submitter).catch(() => nativeSubmit(form, submitter));
  };
  // Browsers without fetch keep the plain form post. So do automated browsers (the
  // browser checks expect one navigation per click) unless a test turns this on.
  if (!window.fetch || !window.URLSearchParams || !window.AbortController) return;
  if (navigator.webdriver && !window.meRetryTest) return;
  // A page written over this one runs this code again: keep one handler only.
  if (window.meRetrySubmit) document.removeEventListener('submit', window.meRetrySubmit);
  window.meRetrySubmit = onSubmit;
  document.addEventListener('submit', onSubmit);
  // Back to a page kept in the browser's cache: its forms must work again.
  window.addEventListener('pageshow', event => {
    if (event.persisted) document.querySelectorAll('form').forEach(reset);
  });
})();
