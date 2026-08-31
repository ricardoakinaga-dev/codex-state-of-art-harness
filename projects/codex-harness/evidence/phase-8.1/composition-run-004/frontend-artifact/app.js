"use strict";

const URGENCY_LABELS = Object.freeze({
  critical: "Critical",
  urgent: "Urgent",
  soon: "Soon",
  routine: "Routine",
});

function caseLabel(count) {
  return count === 1 ? "case" : "cases";
}
const FILTER_VALUES = new Set(["all", ...Object.keys(URGENCY_LABELS)]);

const state = {
  value: Object.freeze({
    phase: "loading",
    items: Object.freeze([]),
    selectedUrgency: "all",
    error: "",
    submitting: false,
    feedback: "",
    feedbackTone: "",
    requestNumber: 0,
  }),
};

const elements = {};
let queueRequest = 0;
let intakeIdempotencyKey = null;

function query(selector) {
  return document.querySelector(selector);
}

function setState(patch) {
  state.value = Object.freeze({ ...state.value, ...patch });
  render();
}

function currentScenario() {
  return new URLSearchParams(window.location.search).get("scenario") || "default";
}

function readUrgencyFromLocation() {
  const urgency = new URLSearchParams(window.location.search).get("urgency");
  return FILTER_VALUES.has(urgency) ? urgency : "all";
}

function syncInvalidUrgencyLocation(selectedUrgency) {
  const url = new URL(window.location.href);
  const rawUrgency = url.searchParams.get("urgency");
  if (rawUrgency === null || rawUrgency === selectedUrgency) return;
  if (selectedUrgency === "all") url.searchParams.delete("urgency");
  else url.searchParams.set("urgency", selectedUrgency);
  window.history.replaceState({ urgency: selectedUrgency }, "", url);
}

function setUrgencyFilter(value, updateHistory = false) {
  const selectedUrgency = FILTER_VALUES.has(value) ? value : "all";
  if (updateHistory) {
    const url = new URL(window.location.href);
    if (selectedUrgency === "all") url.searchParams.delete("urgency");
    else url.searchParams.set("urgency", selectedUrgency);
    window.history.pushState({ urgency: selectedUrgency }, "", url);
  }
  elements.urgencyFilter.value = selectedUrgency;
  setState({ selectedUrgency });
}

function queueEndpoint(recover = false) {
  const scenario = recover && currentScenario() === "error" ? "recovered" : currentScenario();
  const params = new URLSearchParams({ scenario });
  return `/api/queue?${params.toString()}`;
}

function createElement(tag, text, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderQueueRows(items) {
  const rows = items.map((item) => {
    const row = document.createElement("tr");
    const patientCell = createElement("td", undefined, "patient-cell");
    patientCell.dataset.label = "Patient";
    const avatar = createElement("span", item.patient.slice(0, 1).toUpperCase(), "patient-avatar");
    avatar.setAttribute("aria-hidden", "true");
    const copy = createElement("span", undefined, "patient-copy");
    copy.append(createElement("strong", item.patient), createElement("span", item.detail));
    patientCell.append(avatar, copy);

    const speciesCell = createElement("td", item.species);
    speciesCell.dataset.label = "Species";
    const triageCell = createElement("td", undefined);
    triageCell.dataset.label = "Triage";
    const triage = createElement("span", URGENCY_LABELS[item.urgency] || item.urgency, "triage-label");
    triage.dataset.level = item.urgency;
    triageCell.append(triage);
    const waitCell = createElement("td", item.waiting);
    waitCell.dataset.label = "Waiting";
    const actionCell = createElement("td", undefined);
    actionCell.dataset.label = "Action";
    const action = createElement("button", "Review", "row-action");
    action.type = "button";
    action.setAttribute("aria-label", `Review ${item.patient}`);
    action.addEventListener("click", () => {
      elements.patient.value = item.patient;
      elements.patient.focus();
      elements.feedback.textContent = `${item.patient} is ready for a new handoff.`;
      elements.feedback.dataset.tone = "success";
    });
    actionCell.append(action);
    row.append(patientCell, speciesCell, triageCell, waitCell, actionCell);
    return row;
  });
  elements.queueBody.replaceChildren(...rows);
}

function renderLoadingRows() {
  const rows = [0, 1, 2].map(() => {
    const row = createElement("tr", undefined, "loading-row");
    const cells = ["Patient", "Species", "Triage", "Waiting", "Action"].map((label, index) => {
      const cell = createElement("td", undefined);
      cell.dataset.label = label;
      const bar = createElement("span", undefined, index === 0 ? "loading-bar" : "loading-bar loading-bar--short");
      bar.setAttribute("aria-hidden", "true");
      cell.append(bar);
      return cell;
    });
    row.append(...cells);
    return row;
  });
  elements.queueBody.replaceChildren(...rows);
}

function renderStateRow(title, detail, actionLabel, actionHandler, tone = "") {
  const row = createElement("tr", undefined, "state-row");
  const cell = createElement("td", undefined);
  cell.colSpan = 5;
  const cardClass = tone === "error" ? "state-card state-card--error" : "state-card";
  const card = createElement("div", undefined, cardClass);
  if (tone === "error") card.setAttribute("role", "alert");
  card.append(createElement("strong", title), createElement("span", detail));
  if (actionLabel) {
    const action = createElement("button", actionLabel, "button button--primary");
    action.type = "button";
    action.addEventListener("click", actionHandler);
    card.append(action);
  }
  cell.append(card);
  row.append(cell);
  elements.queueBody.replaceChildren(row);
}

function visibleItems() {
  if (state.value.selectedUrgency === "all") return state.value.items;
  return state.value.items.filter((item) => item.urgency === state.value.selectedUrgency);
}

function renderQueue() {
  const current = state.value;
  elements.queuePanel.setAttribute("aria-busy", String(current.phase === "loading"));
  elements.queueState.removeAttribute("data-tone");
  if (current.phase === "loading") {
    renderLoadingRows();
    elements.queueState.textContent = "Loading current queue…";
    return;
  }
  if (current.phase === "error") {
    elements.queueState.textContent = current.error;
    elements.queueState.dataset.tone = "error";
    renderStateRow("The queue needs a moment.", "No case data was changed. Try the local fixture again.", "Try again", () => loadQueue(true), "error");
    return;
  }
  const items = visibleItems();
  if (items.length === 0) {
    elements.queueState.textContent = current.items.length === 0 ? "No active cases" : "No cases match this filter";
    renderStateRow("The desk is clear.", "There are no active cases in this view right now.", current.items.length === 0 ? "Refresh queue" : "Show all", () => {
      if (current.items.length === 0) loadQueue();
      else setUrgencyFilter("all", true);
    });
    return;
  }
  elements.queueState.textContent = current.selectedUrgency === "all" ? `${items.length} active cases · sorted by arrival` : `${items.length} ${URGENCY_LABELS[current.selectedUrgency].toLowerCase()} ${caseLabel(items.length)}`;
  elements.queueState.dataset.tone = "success";
  renderQueueRows(items);
}

function renderSummary() {
  const current = state.value;
  elements.activeCaption.removeAttribute("data-tone");
  elements.urgentCaption.removeAttribute("data-tone");
  elements.summaryRetry.hidden = true;
  if (current.phase === "loading" || current.phase === "error") {
    elements.activeCount.textContent = "—";
    elements.urgentCount.textContent = "—";
    elements.activeCaption.textContent = current.phase === "error" ? "Queue unavailable" : "Loading current cases…";
    elements.urgentCaption.textContent = current.phase === "error" ? "Try the queue again" : "Triage still in progress";
    if (current.phase === "error") {
      elements.activeCaption.dataset.tone = "error";
      elements.urgentCaption.dataset.tone = "error";
      elements.summaryRetry.hidden = false;
    }
    elements.navQueueCount.textContent = "—";
    return;
  }
  const urgent = current.items.filter((item) => item.urgency === "critical" || item.urgency === "urgent").length;
  elements.activeCount.textContent = String(current.items.length).padStart(2, "0");
  elements.urgentCount.textContent = String(urgent).padStart(2, "0");
  elements.activeCaption.textContent = current.items.length ? "Cases awaiting a room" : "No cases waiting";
  elements.urgentCaption.textContent = urgent ? "Critical or urgent triage" : "No immediate escalation";
  elements.navQueueCount.textContent = String(current.items.length);
}

function renderFeedback() {
  elements.submitIntake.disabled = state.value.submitting;
  elements.submitIntake.textContent = state.value.submitting ? "Sending to triage…" : "Send to triage →";
  elements.feedback.textContent = state.value.feedback;
  if (state.value.feedbackTone) elements.feedback.dataset.tone = state.value.feedbackTone;
  else elements.feedback.removeAttribute("data-tone");
}

function render() {
  renderQueue();
  renderSummary();
  renderFeedback();
}

async function loadQueue(recover = false) {
  const requestId = ++queueRequest;
  setState({ phase: "loading", error: "" });
  try {
    const response = await fetch(queueEndpoint(recover), { headers: { Accept: "application/json" } });
    const payload = await response.json();
    if (!response.ok || payload.status !== "success") throw new Error(payload.message || "Queue request failed");
    if (requestId !== queueRequest) return;
    const items = Array.isArray(payload.items) ? payload.items.map((item) => Object.freeze({ ...item })) : [];
    setState({ phase: "success", items: Object.freeze(items), error: "" });
  } catch (error) {
    if (requestId !== queueRequest) return;
    const message = error instanceof Error ? error.message : "The queue could not be loaded.";
    setState({ phase: "error", error: message });
  }
}

function clearFieldError(field) {
  const error = query(`#${field.id}-error`);
  field.removeAttribute("aria-invalid");
  if (error) error.textContent = "";
}

function validateForm() {
  const values = Object.freeze({
    patient: elements.patient.value.trim(),
    species: elements.species.value,
    urgency: elements.urgency.value,
    notes: elements.notes.value.trim(),
  });
  const errors = {};
  if (!values.patient) errors.patient = "Add the patient name.";
  else if (values.patient.length < 2) errors.patient = "Use at least two characters.";
  if (!values.species) errors.species = "Choose a species.";
  if (!values.urgency) errors.urgency = "Choose an urgency.";
  return Object.freeze({ values, errors: Object.freeze(errors) });
}

function showFormErrors(errors) {
  [elements.patient, elements.species, elements.urgency, elements.notes].forEach((field) => {
    const message = typeof errors[field.name] === "string" ? errors[field.name] : "";
    const error = query(`#${field.id}-error`);
    if (message) {
      field.setAttribute("aria-invalid", "true");
      if (error) error.textContent = message;
    } else {
      clearFieldError(field);
    }
  });
}

function newIdempotencyKey() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
  return `intake-${Date.now()}-${state.value.requestNumber + 1}`;
}

async function submitIntake(event) {
  event.preventDefault();
  if (state.value.submitting) return;
  const result = validateForm();
  showFormErrors(result.errors);
  if (Object.keys(result.errors).length > 0) {
    setState({ feedback: "Complete the highlighted fields before sending.", feedbackTone: "error" });
    const firstInvalid = [elements.patient, elements.species, elements.urgency].find((field) => field.getAttribute("aria-invalid") === "true");
    if (firstInvalid) firstInvalid.focus();
    return;
  }
  setState({ submitting: true, feedback: "Sending a single intake to triage…", feedbackTone: "" });
  if (!intakeIdempotencyKey) intakeIdempotencyKey = newIdempotencyKey();
  try {
    const params = new URLSearchParams({ scenario: currentScenario() });
    const response = await fetch(`/api/intakes?${params.toString()}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", "Idempotency-Key": intakeIdempotencyKey },
      body: JSON.stringify(result.values),
    });
    const payload = await response.json();
    if (!response.ok || payload.status === "error") {
      if (payload.errors && typeof payload.errors === "object") showFormErrors(payload.errors);
      throw new Error(payload.message || "The intake could not be sent.");
    }
    elements.form.reset();
    showFormErrors({});
    intakeIdempotencyKey = null;
    setState({ submitting: false, requestNumber: state.value.requestNumber + 1, feedback: `Intake accepted for triage. Reference ${payload.intake_id}.`, feedbackTone: "success" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "The intake could not be sent.";
    setState({ submitting: false, feedback: `${message} You can safely try again.`, feedbackTone: "error" });
  }
}

function bind() {
  elements.queuePanel = query(".queue-panel");
  elements.queueBody = query("#queue-body");
  elements.queueState = query("#queue-state");
  elements.urgencyFilter = query("#urgency-filter");
  elements.refreshQueue = query("#refresh-queue");
  elements.activeCount = query("#active-count");
  elements.urgentCount = query("#urgent-count");
  elements.activeCaption = query("#active-caption");
  elements.urgentCaption = query("#urgent-caption");
  elements.summaryRetry = query("#summary-retry");
  elements.navQueueCount = query("#nav-queue-count");
  elements.form = query("#intake-form");
  elements.patient = query("#patient");
  elements.species = query("#species");
  elements.urgency = query("#urgency");
  elements.notes = query("#notes");
  elements.submitIntake = query("#submit-intake");
  elements.feedback = query("#intake-feedback");
  const selectedUrgency = readUrgencyFromLocation();
  syncInvalidUrgencyLocation(selectedUrgency);
  elements.urgencyFilter.value = selectedUrgency;
  setState({ selectedUrgency });
  elements.urgencyFilter.addEventListener("change", (event) => setUrgencyFilter(event.target.value, true));
  window.addEventListener("popstate", () => setUrgencyFilter(readUrgencyFromLocation()));
  elements.refreshQueue.addEventListener("click", () => loadQueue());
  elements.summaryRetry.addEventListener("click", () => loadQueue(true));
  elements.form.addEventListener("submit", submitIntake);
  [elements.patient, elements.species, elements.urgency, elements.notes].forEach((field) => field.addEventListener("input", () => clearFieldError(field)));
  window.__phase8 = Object.freeze({ getState: () => state.value, reload: loadQueue });
  window.__phase81 = Object.freeze({
    getState: () => state.value,
    reload: loadQueue,
    readUrgencyFromLocation,
  });
  render();
  loadQueue();
}

document.addEventListener("DOMContentLoaded", bind, { once: true });
