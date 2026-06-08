const state = {
  screen: null,
  timer: null,
  timerInterval: null,
};

const elements = {
  recipeHero: document.querySelector(".recipe-hero"),
  ingredientsPanel: document.querySelector(".ingredients-panel"),
  title: document.getElementById("title"),
  subtitle: document.getElementById("subtitle"),
  servings: document.getElementById("servings"),
  ingredientsList: document.getElementById("ingredients-list"),
  ingredientsCount: document.getElementById("ingredients-count"),
  stepsPanel: document.querySelector(".steps-panel"),
  stepsList: document.getElementById("steps-list"),
  stepsCount: document.getElementById("steps-count"),
  notesList: document.getElementById("notes-list"),
  timerLabel: document.getElementById("timer-label"),
  timerDisplay: document.getElementById("timer-display"),
  timerState: document.getElementById("timer-state"),
  linkPill: document.getElementById("link-pill"),
  clock: document.getElementById("clock"),
};

function formatDisplayTime(totalSeconds) {
  const safe = Math.max(0, Number(totalSeconds) || 0);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function sanitizeIngredientText(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  return text.replace(/^\s*(?:[-*]\s*)?\[(?:\s|x|X)\]\s*/, "");
}

function renderIngredients(ingredients) {
  elements.ingredientsList.innerHTML = "";
  elements.ingredientsCount.textContent = `${ingredients.length} item${ingredients.length === 1 ? "" : "s"}`;
  ingredients.forEach((item) => {
    const li = document.createElement("li");
    li.className = `ingredient-item${item.checked ? " checked" : ""}`;
    const span = document.createElement("span");
    span.className = "ingredient-text";
    span.textContent = sanitizeIngredientText(item.text);
    li.appendChild(span);
    elements.ingredientsList.appendChild(li);
  });
}

function renderSteps(steps) {
  elements.stepsList.innerHTML = "";
  elements.stepsCount.textContent = `${steps.length} step${steps.length === 1 ? "" : "s"}`;
  steps.forEach((step, index) => {
    const li = document.createElement("li");
    li.className = `step-card${step.done ? " done" : ""}`;
    li.innerHTML = `
      <div class="step-number">${index + 1}</div>
      <div class="step-text">${step.text || ""}</div>
    `;
    elements.stepsList.appendChild(li);
  });
}

function renderNotes(notes) {
  elements.notesList.innerHTML = "";
  notes.forEach((note) => {
    const li = document.createElement("li");
    li.className = "note-item";
    li.textContent = note;
    elements.notesList.appendChild(li);
  });
}

function renderTimer(timer) {
  state.timer = {
    label: timer.label || "Timer",
    remainingSeconds: Number(timer.remaining_seconds) || 0,
    durationSeconds: Number(timer.duration_seconds) || 0,
    running: Boolean(timer.running),
    finished: Boolean(timer.finished),
  };
  elements.timerLabel.textContent = state.timer.label;
  updateTimerVisuals();
}

const ingredientFitPresets = [
  { fontSize: 26, paddingY: 7, paddingX: 10, gap: 8 },
  { fontSize: 24, paddingY: 6, paddingX: 9, gap: 7 },
  { fontSize: 22, paddingY: 5, paddingX: 8, gap: 6 },
  { fontSize: 20, paddingY: 4, paddingX: 7, gap: 5 },
  { fontSize: 18, paddingY: 3, paddingX: 6, gap: 4 },
  { fontSize: 16, paddingY: 2, paddingX: 5, gap: 3 },
];

const stepFitPresets = [
  { textFont: 28, numberFont: 32, numberWidth: 50, padding: 10, gap: 8, innerGap: 8 },
  { textFont: 26, numberFont: 30, numberWidth: 46, padding: 9, gap: 7, innerGap: 7 },
  { textFont: 24, numberFont: 28, numberWidth: 42, padding: 8, gap: 6, innerGap: 6 },
  { textFont: 22, numberFont: 26, numberWidth: 38, padding: 7, gap: 5, innerGap: 5 },
  { textFont: 20, numberFont: 24, numberWidth: 34, padding: 6, gap: 4, innerGap: 4 },
  { textFont: 18, numberFont: 22, numberWidth: 30, padding: 5, gap: 3, innerGap: 3 },
];

function sanitizeHeroText(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const normalized = text.toLowerCase();
  if (normalized === "kitchen recipe terminal") {
    return "";
  }
  if (normalized === "kitchen recipe display online") {
    return "";
  }
  return text;
}

function updateTimerVisuals() {
  if (!state.timer) {
    return;
  }
  elements.timerDisplay.textContent = formatDisplayTime(state.timer.remainingSeconds);
  if (state.timer.finished) {
    elements.timerState.textContent = "DONE";
  } else if (state.timer.running) {
    elements.timerState.textContent = "RUNNING";
  } else {
    elements.timerState.textContent = "IDLE";
  }
}

function applyState(screenState) {
  state.screen = screenState;
  const heroTitle = sanitizeHeroText(screenState.title);
  const heroSubtitle = sanitizeHeroText(screenState.subtitle);
  elements.title.textContent = heroTitle;
  elements.subtitle.textContent = heroSubtitle;
  elements.recipeHero.classList.toggle("is-empty", !heroTitle && !heroSubtitle);
  elements.servings.textContent = screenState.servings || "";
  elements.linkPill.textContent = screenState.link_status || "LINK NOMINAL";
  renderIngredients(screenState.ingredients || []);
  renderSteps(screenState.steps || []);
  renderNotes(screenState.notes || []);
  renderTimer(screenState.timer || {});
  fitRecipePanels();
}

function fitRecipePanels() {
  window.requestAnimationFrame(() => {
    fitIngredientsPanel();
    fitStepsPanel();
  });
}

function fitIngredientsPanel() {
  const panel = elements.ingredientsPanel;
  const list = elements.ingredientsList;
  if (!panel || !list) {
    return;
  }

  for (const preset of ingredientFitPresets) {
    panel.style.setProperty("--ingredient-font-size", `${preset.fontSize}px`);
    panel.style.setProperty("--ingredient-padding-y", `${preset.paddingY}px`);
    panel.style.setProperty("--ingredient-padding-x", `${preset.paddingX}px`);
    panel.style.setProperty("--ingredient-gap", `${preset.gap}px`);
    if (list.scrollHeight <= list.clientHeight + 1) {
      return;
    }
  }
}

function fitStepsPanel() {
  const panel = elements.stepsPanel;
  const list = elements.stepsList;
  if (!panel || !list) {
    return;
  }

  for (const preset of stepFitPresets) {
    panel.style.setProperty("--step-text-font-size", `${preset.textFont}px`);
    panel.style.setProperty("--step-number-font-size", `${preset.numberFont}px`);
    panel.style.setProperty("--step-number-width", `${preset.numberWidth}px`);
    panel.style.setProperty("--step-padding", `${preset.padding}px`);
    panel.style.setProperty("--step-gap", `${preset.gap}px`);
    panel.style.setProperty("--step-gap-inner", `${preset.innerGap}px`);
    if (list.scrollHeight <= list.clientHeight + 1) {
      return;
    }
  }
}

async function fetchState() {
  const response = await fetch("/api/state", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (!payload.ok) {
    throw new Error(payload.error || "State fetch failed.");
  }
  applyState(payload.state);
}

function startLocalClock() {
  setInterval(() => {
    const now = new Date();
    elements.clock.textContent = now.toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    });
  }, 250);
}

function startTimerTicker() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
  }
  state.timerInterval = setInterval(() => {
    if (!state.timer || !state.timer.running) {
      return;
    }
    if (state.timer.remainingSeconds > 0) {
      state.timer.remainingSeconds -= 1;
      if (state.timer.remainingSeconds === 0) {
        state.timer.running = false;
        state.timer.finished = true;
      }
      updateTimerVisuals();
    }
  }, 1000);
}

async function pollLoop() {
  try {
    await fetchState();
  } catch (error) {
    elements.linkPill.textContent = "LINK DEGRADED";
    console.error(error);
  } finally {
    setTimeout(pollLoop, 1500);
  }
}

startLocalClock();
startTimerTicker();
window.addEventListener("resize", fitRecipePanels);
pollLoop();
