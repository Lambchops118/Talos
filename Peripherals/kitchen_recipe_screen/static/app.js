const state = {
  screen: null,
  timer: null,
  timerInterval: null,
};

const elements = {
  recipeHero: document.querySelector(".recipe-hero"),
  title: document.getElementById("title"),
  subtitle: document.getElementById("subtitle"),
  servings: document.getElementById("servings"),
  ingredientsList: document.getElementById("ingredients-list"),
  ingredientsCount: document.getElementById("ingredients-count"),
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

function renderIngredients(ingredients) {
  elements.ingredientsList.innerHTML = "";
  elements.ingredientsCount.textContent = `${ingredients.length} item${ingredients.length === 1 ? "" : "s"}`;
  ingredients.forEach((item) => {
    const li = document.createElement("li");
    li.className = `ingredient-item${item.checked ? " checked" : ""}`;
    li.innerHTML = `
      <span class="ingredient-marker">${item.checked ? "[X]" : "[ ]"}</span>
      <span class="ingredient-text">${item.text || ""}</span>
    `;
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
pollLoop();
