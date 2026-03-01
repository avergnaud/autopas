'use strict';

// ─── State ────────────────────────────────────────────────────────────────────

const state = {
  step: 'projects',       // current wizard step
  projectId: null,
  structure: null,        // DocumentStructure from API
  questions: [],          // cadrage questions
  verbosityQuestion: null,
  questionIndex: 0,
  answers: {},            // {question_id (number): answer}
  verbosityLevel: 2,
  anonymMappings: [],     // [{real, alias}]
  pollTimer: null,
};

// ─── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  try {
    const res = await fetch('/api/auth/me');
    if (!res.ok) { window.location.href = '/'; return; }
    const user = await res.json();
    document.getElementById('user-info').textContent =
      `${esc(user.name)} — ${esc(user.role)}`;
    await showProjects();
  } catch {
    window.location.href = '/';
  }
}

// ─── Navigation ───────────────────────────────────────────────────────────────

function showStep(name) {
  document.querySelectorAll('.wizard-step, #view-projects').forEach(el => {
    el.classList.add('hidden');
  });
  const el = document.getElementById(`step-${name}`) ||
              document.getElementById(`view-${name}`);
  if (el) el.classList.remove('hidden');
  state.step = name;
}

async function showProjects() {
  showStep('projects');
  await loadProjects();
}

function startNewProject() {
  // Reset state
  Object.assign(state, {
    projectId: null, structure: null, questions: [], verbosityQuestion: null,
    questionIndex: 0, answers: {}, verbosityLevel: 2, anonymMappings: [],
  });
  if (state.pollTimer) { clearTimeout(state.pollTimer); state.pollTimer = null; }

  // Reset upload UI
  document.getElementById('file-input').value = '';
  document.getElementById('selected-file').classList.add('hidden');
  document.getElementById('btn-upload').classList.add('hidden');
  document.getElementById('btn-upload')._file = null;
  hideErr('upload-error');
  document.getElementById('upload-loading').classList.add('hidden');
  showStep('upload');
}

// ─── Step 0: Project list ─────────────────────────────────────────────────────

async function loadProjects() {
  const container = document.getElementById('projects-list');
  container.innerHTML = '<p class="hint">Chargement...</p>';
  try {
    const res = await fetch('/api/projects');
    const projects = await res.json();
    if (!projects.length) {
      container.innerHTML =
        '<p class="hint">Aucun projet. Cliquez sur « + Nouveau questionnaire » pour commencer.</p>';
      return;
    }
    container.innerHTML = projects.map(p => `
      <div class="project-card" onclick="resumeProject('${esc(p.id)}')">
        <div class="project-info">
          <strong>${esc(p.original_filename)}</strong>
          <span class="project-date">${fmtDate(p.created_at)}</span>
        </div>
        <div class="project-card-actions">
          <span class="badge status-${p.status}">${statusLabel(p.status)}</span>
          <button class="btn btn-ghost btn-trash" title="Supprimer"
            onclick="event.stopPropagation(); deleteProject('${esc(p.id)}', '${esc(p.original_filename)}')">🗑</button>
        </div>
      </div>
    `).join('');
  } catch {
    container.innerHTML = '<p class="error-msg">Erreur lors du chargement.</p>';
  }
}

function statusLabel(s) {
  return {
    created: 'Créé', structure_detected: 'Structure détectée', cadrage: 'Cadrage fait',
    anonymizing: 'Prêt à générer', generating: 'Génération en cours',
    completed: 'Terminé', error: 'Erreur',
  }[s] || s;
}

async function resumeProject(projectId) {
  const res = await fetch(`/api/projects/${projectId}`);
  if (!res.ok) return;
  const project = await res.json();
  state.projectId = projectId;
  state.structure = project.structure;

  const stepMap = {
    created: 'upload',
    structure_detected: 'structure',
    cadrage: 'anonymisation',
    anonymizing: 'generation',
    generating: 'generation',
    completed: 'generation',
    error: 'generation',
  };
  const step = stepMap[project.status] || 'projects';

  if (step === 'structure') {
    showStep('structure');
    renderStructureForm(project.structure);
  } else if (step === 'generation') {
    showStep('generation');
    if (project.status === 'completed') showGenComplete(projectId);
    else if (project.status === 'error') showGenError(project.error_message);
    else startPolling(projectId);
  } else {
    showStep(step);
  }
}

async function deleteProject(projectId, filename) {
  if (!confirm(`Supprimer « ${filename} » et toutes ses données ?\nCette action est irréversible.`)) return;
  try {
    const res = await fetch(`/api/projects/${projectId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    await loadProjects();
  } catch (e) {
    alert('Erreur lors de la suppression : ' + e.message);
  }
}

// ─── Step 1: Upload ───────────────────────────────────────────────────────────

function initDropZone() {
  const zone = document.getElementById('drop-zone');
  const input = document.getElementById('file-input');

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
  input.addEventListener('change', () => {
    if (input.files[0]) handleFile(input.files[0]);
  });
}

function handleFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['xlsx', 'docx'].includes(ext)) {
    showErr('upload-error', 'Format non supporté. Utilisez .xlsx ou .docx.');
    return;
  }
  hideErr('upload-error');
  const info = document.getElementById('selected-file');
  info.textContent = `${file.name} (${fmtSize(file.size)})`;
  info.classList.remove('hidden');
  const btn = document.getElementById('btn-upload');
  btn.classList.remove('hidden');
  btn._file = file;
}

async function doUpload() {
  const file = document.getElementById('btn-upload')._file;
  if (!file) return;

  document.getElementById('btn-upload').classList.add('hidden');
  document.getElementById('upload-loading').classList.remove('hidden');
  hideErr('upload-error');

  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/projects', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Erreur upload');

    state.projectId = data.id;
    state.structure = data.structure;
    document.getElementById('upload-loading').classList.add('hidden');
    showStep('structure');
    renderStructureForm(data.structure);
  } catch (err) {
    document.getElementById('upload-loading').classList.add('hidden');
    document.getElementById('btn-upload').classList.remove('hidden');
    showErr('upload-error', err.message);
  }
}

// ─── Step 2: Structure ────────────────────────────────────────────────────────

function renderStructureForm(structure) {
  const container = document.getElementById('structure-form');
  if (!structure) { container.innerHTML = '<p>Structure non disponible.</p>'; return; }

  let html = '';
  if (structure.format === 'xlsx') {
    const sheets = structure.sheets || [];
    const onlyOne = sheets.length <= 1;
    sheets.forEach((s, i) => {
      const trashTitle = onlyOne ? 'Impossible de supprimer le seul onglet restant' : `Supprimer l'onglet "${esc(s.name)}"`;
      html += `
        <div class="structure-sheet" id="sheet-block-${i}">
          <div class="sheet-block-header">
            <h3>Onglet : <em>${esc(s.name)}</em></h3>
            <button class="btn-icon btn-trash${onlyOne ? ' disabled' : ''}"
                    onclick="deleteSheet(${i})"
                    title="${trashTitle}"
                    ${onlyOne ? 'disabled' : ''}>🗑</button>
          </div>
          <div class="form-grid">
            <label>Colonne identifiant</label>
            <input type="text" id="s${i}_id" value="${esc(s.id_column || '')}" placeholder="ex: A">

            <label>Colonne question <span class="req">*</span></label>
            <input type="text" id="s${i}_q" value="${esc(s.question_column || 'A')}">

            <label>Colonne(s) réponse <span class="req">*</span></label>
            <input type="text" id="s${i}_r" value="${esc((s.response_columns || []).join(', '))}" placeholder="ex: E, G">

            <label>Ligne en-tête</label>
            <input type="number" id="s${i}_h" value="${s.header_row || 1}" min="1">

            <label>1ère ligne données</label>
            <input type="number" id="s${i}_d" value="${s.first_data_row || 2}" min="1">

            <label>Contient des questions</label>
            <input type="checkbox" id="s${i}_hq" ${s.has_questions ? 'checked' : ''}>
          </div>
        </div>`;
    });
  } else {
    html = `
      <div class="form-grid">
        <label>Marqueur de réponse</label>
        <input type="text" id="docx_marker" value="${esc(structure.response_marker || 'Réponse du titulaire')}">

        <label>Pattern détecté</label>
        <input type="text" id="docx_pattern" value="${esc(structure.pattern || '')}" placeholder="(optionnel)">
      </div>`;
  }
  container.innerHTML = html;
}

function deleteSheet(i) {
  if ((state.structure.sheets || []).length <= 1) return;
  // Save current form values before re-rendering
  state.structure.sheets = readStructureForm().sheets;
  state.structure.sheets.splice(i, 1);
  renderStructureForm(state.structure);
}

function readStructureForm() {
  const s = state.structure;
  if (s.format === 'xlsx') {
    const sheets = (s.sheets || []).map((sheet, i) => ({
      name: sheet.name,
      has_questions: document.getElementById(`s${i}_hq`).checked,
      id_column: document.getElementById(`s${i}_id`).value.trim().toUpperCase() || null,
      question_column: document.getElementById(`s${i}_q`).value.trim().toUpperCase(),
      response_columns: document.getElementById(`s${i}_r`).value
        .split(',').map(v => v.trim().toUpperCase()).filter(Boolean),
      header_row: parseInt(document.getElementById(`s${i}_h`).value) || 1,
      first_data_row: parseInt(document.getElementById(`s${i}_d`).value) || 2,
    }));
    return { sheets };
  }
  return {
    response_marker: document.getElementById('docx_marker').value.trim(),
    pattern: document.getElementById('docx_pattern').value.trim(),
  };
}

async function doValidateStructure() {
  hideErr('structure-error');
  try {
    const res = await fetch(`/api/projects/${state.projectId}/structure`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ structure: readStructureForm() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Erreur');
    state.structure = data.structure;

    // Load cadrage questions then go to step 3
    await loadCadrageQuestions();
    showStep('cadrage');
    renderCadrageQuestion();
  } catch (err) {
    showErr('structure-error', err.message);
  }
}

// ─── Step 3: Cadrage ──────────────────────────────────────────────────────────

async function loadCadrageQuestions() {
  const res = await fetch(`/api/projects/${state.projectId}/questions`);
  const data = await res.json();
  state.questions = data.questions || [];
  state.verbosityQuestion = data.verbosity_question;
  state.questionIndex = 0;
  state.answers = {};
}

function allQuestions() {
  return [...state.questions, state.verbosityQuestion].filter(Boolean);
}

function visibleQuestions() {
  return allQuestions().filter(q => isVisible(q));
}

function isVisible(q) {
  if (!q.condition) return true;
  const prev = state.answers[q.condition.question_id];
  if (q.condition.operator === 'contains') {
    return Array.isArray(prev)
      ? prev.some(v => v.includes(q.condition.value))
      : String(prev || '').includes(q.condition.value);
  }
  return prev === q.condition.value;
}

function renderCadrageQuestion() {
  const visible = visibleQuestions();
  const container = document.getElementById('cadrage-question-container');

  if (!visible.length || state.questionIndex >= visible.length) {
    doSubmitCadrage();
    return;
  }

  const q = visible[state.questionIndex];
  const total = visible.length;
  const current = state.questionIndex + 1;
  const saved = state.answers[q.id];

  let inputHtml = '';
  if (q.type === 'options' && q.options) {
    if (q.multi) {
      inputHtml = q.options.map(opt => {
        const checked = Array.isArray(saved) && saved.includes(opt) ? 'checked' : '';
        return `<label class="choice-label">
          <input type="checkbox" name="q${q.id}" value="${esc(opt)}" ${checked}>
          <span>${esc(opt)}</span>
        </label>`;
      }).join('');
    } else {
      inputHtml = q.options.map(opt => {
        const checked = saved === opt ? 'checked' : '';
        return `<label class="choice-label">
          <input type="radio" name="q${q.id}" value="${esc(opt)}" ${checked}>
          <span>${esc(opt)}</span>
        </label>`;
      }).join('');
    }
  } else if (q.type === 'number') {
    inputHtml = `<input type="number" id="cadrage-input" class="text-input"
      value="${esc(String(saved ?? ''))}" min="0">`;
  } else {
    inputHtml = `<textarea id="cadrage-input" class="text-input" rows="3">${esc(String(saved ?? ''))}</textarea>`;
  }

  container.innerHTML = `
    <div class="q-progress">Question ${current} / ${total}</div>
    <div class="question-card">
      <p class="q-text">${esc(q.text)}</p>
      <div class="q-input">${inputHtml}</div>
    </div>`;

  // Button states
  document.getElementById('btn-cadrage-prev').disabled = (state.questionIndex === 0);
  const isLast = state.questionIndex >= visible.length - 1;
  document.getElementById('btn-cadrage-next').textContent =
    isLast ? 'Valider le cadrage →' : 'Suivant →';
}

function readAnswer() {
  const visible = visibleQuestions();
  const q = visible[state.questionIndex];
  if (!q) return null;

  if (q.type === 'options' && q.options) {
    if (q.multi) {
      return [...document.querySelectorAll(`input[name="q${q.id}"]:checked`)].map(cb => cb.value);
    }
    const checked = document.querySelector(`input[name="q${q.id}"]:checked`);
    return checked ? checked.value : null;
  }
  const input = document.getElementById('cadrage-input');
  return input ? input.value.trim() : null;
}

function cadrageBack() {
  hideErr('cadrage-error');
  if (state.questionIndex === 0) {
    showStep('structure');
    renderStructureForm(state.structure);
    return;
  }
  // Save current answer before going back
  const answer = readAnswer();
  const visible = visibleQuestions();
  if (answer !== null && answer !== '' && !(Array.isArray(answer) && !answer.length)) {
    state.answers[visible[state.questionIndex].id] = answer;
  }
  state.questionIndex--;
  renderCadrageQuestion();
}

function cadrageNext() {
  hideErr('cadrage-error');
  const visible = visibleQuestions();
  const q = visible[state.questionIndex];

  // Save answer
  const answer = readAnswer();
  if (answer !== null && answer !== '' && !(Array.isArray(answer) && !answer.length)) {
    state.answers[q.id] = answer;
  }

  if (state.questionIndex >= visible.length - 1) {
    doSubmitCadrage();
  } else {
    state.questionIndex++;
    // Re-evaluate visibility (conditions may change after answer)
    const newVisible = visibleQuestions();
    // Ensure index stays valid
    if (state.questionIndex >= newVisible.length) state.questionIndex = newVisible.length - 1;
    renderCadrageQuestion();
  }
}

async function doSubmitCadrage() {
  // Extract verbosity from answers (question id=99)
  const verbAnswer = state.answers[99] || '';
  let verbLevel = 2;
  if (typeof verbAnswer === 'string') {
    if (verbAnswer.startsWith('1')) verbLevel = 1;
    else if (verbAnswer.startsWith('3')) verbLevel = 3;
  }
  state.verbosityLevel = verbLevel;

  // Remove verbosity from cadrage answers before sending
  const cadrageAnswers = { ...state.answers };
  delete cadrageAnswers[99];

  try {
    const res = await fetch(`/api/projects/${state.projectId}/cadrage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers: cadrageAnswers, verbosity_level: verbLevel }),
    });
    if (!res.ok) throw new Error('Erreur lors de la soumission du cadrage');

    // Prefill anonymisation suggestions
    state.anonymMappings = [
      { real: '', alias: 'CLIENT' },
      { real: '', alias: 'MARCHE' },
    ];
    showStep('anonymisation');
    renderAnonTable();
  } catch (err) {
    showErr('cadrage-error', err.message);
  }
}

// ─── Step 4: Anonymisation ────────────────────────────────────────────────────

function renderAnonTable() {
  document.getElementById('anon-rows').innerHTML =
    state.anonymMappings.map((m, i) => `
      <tr>
        <td><input type="text" class="anon-real" value="${esc(m.real)}"
          placeholder="ex: Ministère des Armées"></td>
        <td><input type="text" class="anon-alias" value="${esc(m.alias)}"
          placeholder="ex: CLIENT"></td>
        <td><button onclick="removeAnonRow(${i})" class="btn-icon" title="Supprimer">✕</button></td>
      </tr>`).join('');
}

function addAnonRow() {
  state.anonymMappings.push({ real: '', alias: '' });
  renderAnonTable();
}

function removeAnonRow(i) {
  state.anonymMappings.splice(i, 1);
  renderAnonTable();
}

function readAnonMappings() {
  return [...document.querySelectorAll('#anon-rows tr')].map(row => ({
    real: row.querySelector('.anon-real').value.trim(),
    alias: row.querySelector('.anon-alias').value.trim(),
  })).filter(m => m.real && m.alias);
}

async function doAnonymize(withMappings) {
  hideErr('anon-error');
  const mappings = withMappings ? readAnonMappings() : [];
  try {
    const res = await fetch(`/api/projects/${state.projectId}/anonymize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mappings }),
    });
    if (!res.ok) throw new Error('Erreur lors de la soumission');
    await doStartGeneration();
  } catch (err) {
    showErr('anon-error', err.message);
  }
}

// ─── Step 5: Generation ───────────────────────────────────────────────────────

// Pipeline steps: each entry marks the pct at which the step is considered DONE.
const PIPELINE_STEPS = [
  { label: "Copie de travail",                   donePct: 12 },
  { label: "Anonymisation du document",           donePct: 22 },
  { label: "Extraction des questions",            donePct: 32 },
  { label: "Sélection des références",            donePct: 48 },
  { label: "Génération des réponses via Claude",  donePct: 68 },
  { label: "Écriture dans le document",           donePct: 78 },
  { label: "Dé-anonymisation",                    donePct: 86 },
  { label: "Points d'attention via Claude",       donePct: 93 },
  { label: "Finalisation",                        donePct: 99 },
];

function renderPipelineSteps(pct) {
  const ol = document.getElementById('gen-pipeline-steps');
  if (!ol) return;
  let foundActive = false;
  ol.innerHTML = PIPELINE_STEPS.map(step => {
    if (pct >= step.donePct) {
      return `<li class="pipeline-step done"><span class="step-icon">✓</span>${esc(step.label)}</li>`;
    }
    if (!foundActive) {
      foundActive = true;
      return `<li class="pipeline-step active"><span class="step-icon"><span class="spinner-sm"></span></span>${esc(step.label)}</li>`;
    }
    return `<li class="pipeline-step pending"><span class="step-icon">·</span>${esc(step.label)}</li>`;
  }).join('');
}

async function doStartGeneration() {
  showStep('generation');
  document.getElementById('gen-in-progress').classList.remove('hidden');
  document.getElementById('gen-complete').classList.add('hidden');
  document.getElementById('gen-error').classList.add('hidden');

  try {
    const res = await fetch(`/api/projects/${state.projectId}/generate`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Erreur démarrage');
    }
    startPolling(state.projectId);
  } catch (err) {
    showGenError(err.message);
  }
}

function startPolling(projectId) {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  state.projectId = projectId;
  poll();
}

async function poll() {
  try {
    const res = await fetch(`/api/projects/${state.projectId}/status`);
    const data = await res.json();

    const pct = data.progress_pct || 0;
    document.getElementById('gen-step-label').textContent =
      data.progress_step || 'Traitement en cours…';
    const bar = document.getElementById('gen-progress-bar');
    if (bar) bar.style.width = pct + '%';
    renderPipelineSteps(pct);

    if (data.status === 'completed') { showGenComplete(state.projectId); return; }
    if (data.status === 'error') { showGenError(data.error_message); return; }

    state.pollTimer = setTimeout(poll, 3000);
  } catch {
    state.pollTimer = setTimeout(poll, 5000);
  }
}

function showGenComplete(projectId) {
  document.getElementById('gen-in-progress').classList.add('hidden');
  document.getElementById('gen-complete').classList.remove('hidden');
  document.getElementById('gen-error').classList.add('hidden');
  document.getElementById('btn-dl-doc').href = `/api/projects/${projectId}/output`;
  document.getElementById('btn-dl-attention').href = `/api/projects/${projectId}/attention`;
}

function showGenError(msg) {
  document.getElementById('gen-in-progress').classList.add('hidden');
  document.getElementById('gen-complete').classList.add('hidden');
  document.getElementById('gen-error').classList.remove('hidden');
  document.getElementById('gen-error-msg').textContent = msg || 'Une erreur est survenue.';
}

async function retryGeneration() {
  await doStartGeneration();
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function showErr(id, msg) {
  const el = document.getElementById(id);
  if (el) { el.textContent = msg; el.classList.remove('hidden'); }
}

function hideErr(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1048576) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / 1048576).toFixed(1)} Mo`;
}

// ─── Bootstrap ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initDropZone();
  init();
});
