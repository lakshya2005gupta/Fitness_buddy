/**
 * ================================================================
 * FITNESS BUDDY — Frontend JavaScript
 * ================================================================
 * Responsibilities:
 *  - Theme toggling (dark ↔ light)
 *  - Floating chat window: open/close, send/receive messages
 *  - Habit tracker: toggle, persist in localStorage, sync with API
 *  - Workout planner: form state, API call, render table
 *  - Nutrition planner: API call, render meal cards
 *  - Daily motivation: fetch + display AI quote
 *  - Dashboard metric counters
 * ================================================================
 */

"use strict";

// ── State ─────────────────────────────────────────────────────────
const AppState = {
  chatOpen:      false,
  chatHistory:   [],          // [{role:"user"|"assistant", content:str}]
  selectedDuration: "15",
  habits:        {},          // { habit_id: bool }
  workoutCount:  0,
  streak:        0,
};

// ── DOM ready ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initHabits();
  fetchMotivation();
  loadStoredMetrics();
  setupChatInput();
  injectWelcomeMessage();
});

// ══════════════════════════════════════════════════════════════════
//  THEME TOGGLE
// ══════════════════════════════════════════════════════════════════
function initTheme() {
  const saved = localStorage.getItem("fb_theme") || "dark";
  applyTheme(saved);

  document.getElementById("themeToggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    applyTheme(current === "dark" ? "light" : "dark");
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("fb_theme", theme);
  const icon = document.getElementById("themeIcon");
  if (icon) {
    icon.className = theme === "dark" ? "bi bi-sun-fill" : "bi bi-moon-stars-fill";
  }
}

// ══════════════════════════════════════════════════════════════════
//  CHAT WINDOW
// ══════════════════════════════════════════════════════════════════
function openChat() {
  const win = document.getElementById("chatWindow");
  const fab = document.getElementById("chatFab");
  win.hidden = false;
  fab.classList.add("open");
  fab.setAttribute("aria-expanded", "true");
  AppState.chatOpen = true;
  document.getElementById("chatInput").focus();
  scrollChatToBottom();
}

function closeChat() {
  const win = document.getElementById("chatWindow");
  const fab = document.getElementById("chatFab");
  win.hidden = true;
  fab.classList.remove("open");
  fab.setAttribute("aria-expanded", "false");
  AppState.chatOpen = false;
}

document.getElementById("chatFab").addEventListener("click", () => {
  AppState.chatOpen ? closeChat() : openChat();
});

document.getElementById("closeChatBtn").addEventListener("click", closeChat);

document.getElementById("clearChatBtn").addEventListener("click", () => {
  AppState.chatHistory = [];
  const container = document.getElementById("chatMessages");
  container.innerHTML = "";
  injectWelcomeMessage();
});

/** Open chat and pre-fill a message */
function openChatWithMessage(text) {
  openChat();
  document.getElementById("chatInput").value = text;
  updateCharCounter(text.length);
  document.getElementById("chatInput").focus();
}

function injectWelcomeMessage() {
  const welcome = `👋 Hi! I'm your **Fitness Buddy AI Coach**, powered by IBM Granite.

I can help you with:
- 🏋️ Personalised workout plans
- 🥗 Nutrition & meal ideas (including Indian food options!)
- 💧 Daily habit guidance
- ❤️ Injury-aware exercise alternatives

What's your fitness goal today?`;
  appendMessage("assistant", welcome);
}

// ── Chat input handlers ───────────────────────────────────────────
function setupChatInput() {
  const input   = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener("input", () => {
    autoResizeTextarea(input);
    updateCharCounter(input.value.length);
  });

  sendBtn.addEventListener("click", sendMessage);
}

function autoResizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

function updateCharCounter(len) {
  const el = document.querySelector(".char-counter");
  if (el) el.textContent = `${len} / 2000`;
}

// ── Send message ──────────────────────────────────────────────────
async function sendMessage() {
  const input   = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");
  const text    = input.value.trim();
  if (!text) return;

  // Clear input
  input.value = "";
  input.style.height = "auto";
  updateCharCounter(0);

  // Append user message
  appendMessage("user", text);
  AppState.chatHistory.push({ role: "user", content: text });

  // Disable send button + show typing
  sendBtn.disabled = true;
  const typingId = showTypingIndicator();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        history: AppState.chatHistory.slice(-10),
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const reply = data.reply || data.error || "Sorry, I couldn't generate a response.";

    removeTypingIndicator(typingId);
    appendMessage("assistant", reply);
    AppState.chatHistory.push({ role: "assistant", content: reply });

  } catch (err) {
    console.error("Chat error:", err);
    removeTypingIndicator(typingId);
    appendMessage("assistant",
      "⚠️ Connection error. Please check that the Flask server is running and your `.env` credentials are set."
    );
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

// ── Append a message bubble ───────────────────────────────────────
function appendMessage(role, content) {
  const container = document.getElementById("chatMessages");

  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const isUser = role === "user";

  const wrapper = document.createElement("div");
  wrapper.className = `chat-msg ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.innerHTML = isUser ? '<i class="bi bi-person-fill"></i>' : '<i class="bi bi-robot"></i>';

  const inner = document.createElement("div");

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = formatMessage(content);

  const timeEl = document.createElement("div");
  timeEl.className = "msg-time";
  timeEl.textContent = time;

  inner.appendChild(bubble);
  inner.appendChild(timeEl);

  wrapper.appendChild(avatar);
  wrapper.appendChild(inner);

  container.appendChild(wrapper);
  scrollChatToBottom();
}

/** Very lightweight Markdown-like formatting for chat bubbles */
function formatMessage(text) {
  return text
    // Bold: **text**
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    // Italic: *text* or _text_
    .replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, "<em>$1</em>")
    .replace(/_(.*?)_/g, "<em>$1</em>")
    // Inline code
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    // Numbered list
    .replace(/^(\d+)\.\s(.+)/gm, "<li>$2</li>")
    // Bullet list
    .replace(/^[-•]\s(.+)/gm, "<li>$1</li>")
    // Wrap consecutive <li> items in a <ul>
    .replace(/(<li>[\s\S]*?<\/li>)+/g, (m) => `<ul>${m}</ul>`)
    // Newlines to <br> (but not inside list blocks)
    .replace(/\n(?!<\/?(ul|li))/g, "<br>");
}

// ── Typing indicator ──────────────────────────────────────────────
function showTypingIndicator() {
  const container = document.getElementById("chatMessages");
  const id = "typing-" + Date.now();

  const wrapper = document.createElement("div");
  wrapper.className = "chat-msg assistant";
  wrapper.id = id;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.innerHTML = '<i class="bi bi-robot"></i>';

  const indicator = document.createElement("div");
  indicator.className = "typing-indicator";
  indicator.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';

  wrapper.appendChild(avatar);
  wrapper.appendChild(indicator);
  container.appendChild(wrapper);
  scrollChatToBottom();
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function scrollChatToBottom() {
  const container = document.getElementById("chatMessages");
  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
  });
}

// ══════════════════════════════════════════════════════════════════
//  HABIT TRACKER
// ══════════════════════════════════════════════════════════════════
function initHabits() {
  // Load from localStorage
  const stored = localStorage.getItem("fb_habits_" + getTodayKey());
  if (stored) {
    try {
      AppState.habits = JSON.parse(stored);
      // Re-apply visual state
      Object.entries(AppState.habits).forEach(([id, checked]) => {
        if (checked) applyHabitChecked(id, true, false);
      });
      syncHabitsWithServer();
    } catch (e) {
      AppState.habits = {};
    }
  }
}

function toggleHabit(id) {
  const current = AppState.habits[id] || false;
  AppState.habits[id] = !current;
  applyHabitChecked(id, !current, true);
  saveHabitsLocally();
  syncHabitsWithServer();
}

function applyHabitChecked(id, checked, animate) {
  const item     = document.getElementById("habit-" + id);
  const checkbox = document.getElementById("hcheck-" + id);
  if (!item || !checkbox) return;

  const icon = checkbox.querySelector("i");

  if (checked) {
    item.classList.add("completed");
    item.setAttribute("aria-checked", "true");
    checkbox.querySelector("i").style.display = "";
    if (animate) item.style.transform = "scale(1.02)";
    setTimeout(() => { item.style.transform = ""; }, 150);
  } else {
    item.classList.remove("completed");
    item.setAttribute("aria-checked", "false");
    checkbox.querySelector("i").style.display = "none";
  }
}

function saveHabitsLocally() {
  localStorage.setItem("fb_habits_" + getTodayKey(), JSON.stringify(AppState.habits));
}

async function syncHabitsWithServer() {
  try {
    const res = await fetch("/api/habits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ habits: AppState.habits }),
    });
    if (!res.ok) return;
    const data = await res.json();
    updateHabitUI(data);
  } catch (err) {
    console.warn("Habit sync error:", err);
  }
}

function updateHabitUI(data) {
  const { percent, message, completed, total } = data;

  // Ring SVG
  const ring      = document.getElementById("habitRing");
  const ringLabel = document.getElementById("ringLabel");
  const CIRCUMFERENCE = 226; // 2 * π * 36
  if (ring) {
    ring.style.strokeDashoffset = CIRCUMFERENCE - (percent / 100) * CIRCUMFERENCE;
  }
  if (ringLabel) ringLabel.textContent = percent + "%";

  // Progress message
  const msgEl = document.getElementById("habitProgressMsg");
  if (msgEl) msgEl.textContent = message;

  // Alert box
  const alertEl = document.getElementById("habitAlert");
  if (alertEl && message) {
    alertEl.className = `fb-alert mt-3 ${percent === 100 ? "success" : percent >= 50 ? "info" : "warning"}`;
    alertEl.innerHTML = `<i class="bi bi-info-circle me-2"></i>${message}`;
    alertEl.classList.remove("d-none");
  }

  // Metric card
  const habitsDoneEl = document.getElementById("habitsDoneCount");
  if (habitsDoneEl) habitsDoneEl.textContent = completed;

  const completionEl = document.getElementById("completionPct");
  if (completionEl) completionEl.textContent = percent + "%";

  // Hero panel
  const heroBadge = document.getElementById("heroBadgeHabits");
  const heroBar   = document.getElementById("heroProgressBar");
  if (heroBadge) heroBadge.textContent = `${completed} / ${total}`;
  if (heroBar)   heroBar.style.width = percent + "%";
}

// ══════════════════════════════════════════════════════════════════
//  DAILY MOTIVATION
// ══════════════════════════════════════════════════════════════════
async function fetchMotivation() {
  const el = document.getElementById("motivationQuote");
  const btn = document.getElementById("refreshMotivation");
  if (!el) return;

  // Show skeleton
  el.innerHTML = '<div class="skeleton skeleton-text wide"></div><div class="skeleton skeleton-text medium"></div>';
  if (btn) { btn.disabled = true; }

  try {
    const res = await fetch("/api/motivation");
    if (!res.ok) throw new Error("API error");
    const data = await res.json();
    el.innerHTML = formatMessage(data.quote || "Keep pushing forward. Every day counts! 💪");
  } catch (err) {
    el.textContent = "Consistency is the secret weapon of every champion. Show up today. 💪";
  } finally {
    if (btn) { btn.disabled = false; }
  }
}

// ══════════════════════════════════════════════════════════════════
//  WORKOUT PLANNER
// ══════════════════════════════════════════════════════════════════
function selectDuration(btn) {
  document.querySelectorAll(".duration-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  AppState.selectedDuration = btn.dataset.duration;
}

async function generateWorkout() {
  const btn      = document.getElementById("generateWorkoutBtn");
  const level    = document.getElementById("fitnessLevel").value;
  const focus    = document.getElementById("focusArea").value;
  const goal     = document.getElementById("workoutGoal").value;
  const tableWrap = document.getElementById("workoutTableWrap");
  const aiIntro   = document.getElementById("workoutAiIntro");
  const footerNote = document.getElementById("workoutFooterNote");

  btn.disabled = true;
  btn.innerHTML = '<span class="fb-spinner me-2"></span>Generating…';
  tableWrap.innerHTML = renderWorkoutSkeleton();

  try {
    const res = await fetch("/api/workout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        duration: AppState.selectedDuration,
        level,
        focus,
        goal,
      }),
    });

    if (!res.ok) throw new Error("API error");
    const data = await res.json();

    // Render AI intro
    if (data.ai_intro) {
      document.getElementById("workoutAiIntroText").innerHTML = formatMessage(data.ai_intro);
      aiIntro.classList.remove("d-none");
    }

    // Render table
    tableWrap.innerHTML = renderWorkoutTable(data.workout);
    footerNote.classList.remove("d-none");

    // Update badges
    document.getElementById("workoutMeta").classList.remove("d-none");
    document.getElementById("wDurationBadge").innerHTML =
      `<i class="bi bi-clock me-1"></i>${data.duration} min`;
    document.getElementById("wLevelBadge").innerHTML =
      `<i class="bi bi-bar-chart me-1"></i>${capitalise(data.level)}`;

    // Increment weekly workout counter
    AppState.workoutCount++;
    localStorage.setItem("fb_wcount_" + getWeekKey(), AppState.workoutCount);
    const wEl = document.getElementById("workoutCount");
    if (wEl) wEl.textContent = AppState.workoutCount;

  } catch (err) {
    console.error("Workout error:", err);
    tableWrap.innerHTML = `
      <div class="fb-alert error">
        <i class="bi bi-exclamation-circle me-2"></i>
        Could not load workout. Please check the server and try again.
      </div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-arrow-clockwise me-2"></i>Regenerate Workout';
  }
}

function renderWorkoutTable(exercises) {
  if (!exercises || exercises.length === 0) {
    return `<p class="text-muted text-center py-4">No exercises found for this configuration.</p>`;
  }
  const rows = exercises.map((ex, i) => `
    <tr>
      <td><span class="exercise-num">${i + 1}</span></td>
      <td><strong>${ex.exercise}</strong></td>
      <td class="text-center">${ex.sets}</td>
      <td class="text-center">${ex.reps}</td>
      <td class="text-center"><span class="fb-badge">${ex.rest}</span></td>
    </tr>`).join("");

  return `
    <div class="workout-table-wrap">
      <table class="workout-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Exercise</th>
            <th class="text-center">Sets</th>
            <th class="text-center">Reps / Time</th>
            <th class="text-center">Rest</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function renderWorkoutSkeleton() {
  const rows = Array.from({length: 5}, (_, i) => `
    <tr>
      <td><div class="skeleton skeleton-text short" style="width:26px;height:26px;border-radius:50%"></div></td>
      <td><div class="skeleton skeleton-text" style="width:${60 + (i % 3) * 15}%"></div></td>
      <td><div class="skeleton skeleton-text short mx-auto" style="width:30px"></div></td>
      <td><div class="skeleton skeleton-text short mx-auto" style="width:50px"></div></td>
      <td><div class="skeleton skeleton-text short mx-auto" style="width:40px"></div></td>
    </tr>`).join("");
  return `<div class="workout-table-wrap">
    <table class="workout-table">
      <thead><tr><th>#</th><th>Exercise</th><th>Sets</th><th>Reps</th><th>Rest</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

// ══════════════════════════════════════════════════════════════════
//  NUTRITION PLANNER
// ══════════════════════════════════════════════════════════════════
async function loadNutrition() {
  const btn        = document.getElementById("loadNutritionBtn");
  const goal       = document.getElementById("nutritionGoal").value;
  const dietType   = document.getElementById("dietType").value;
  const resultsEl  = document.getElementById("nutritionResults");
  const macroBox   = document.getElementById("macroTipBox");

  btn.disabled = true;
  btn.innerHTML = '<span class="fb-spinner me-2"></span>Loading…';
  resultsEl.innerHTML = renderNutritionSkeleton();

  try {
    const res = await fetch("/api/nutrition", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, diet_type: dietType }),
    });

    if (!res.ok) throw new Error("API error");
    const data = await res.json();
    const plan = data.plan;

    // Macro tip
    document.getElementById("macroTipText").textContent = plan.macro_tip;
    document.getElementById("calorieTipText").textContent = "🔥 " + plan.calories;
    macroBox.classList.remove("d-none");

    // Render meal cards
    resultsEl.innerHTML = renderNutritionCards(plan.meals);

  } catch (err) {
    console.error("Nutrition error:", err);
    resultsEl.innerHTML = `
      <div class="fb-alert error">
        <i class="bi bi-exclamation-circle me-2"></i>
        Could not load meal plan. Please try again.
      </div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-arrow-clockwise me-2"></i>Refresh Plan';
  }
}

function renderNutritionCards(meals) {
  const mealTypes = [
    { key: "breakfast", label: "🌅 Breakfast", cls: "breakfast", icon: "bi-brightness-high" },
    { key: "lunch",     label: "☀️ Lunch",     cls: "lunch",     icon: "bi-sun" },
    { key: "dinner",    label: "🌙 Dinner",    cls: "dinner",    icon: "bi-moon" },
    { key: "snacks",    label: "🍎 Snacks",    cls: "snack",     icon: "bi-apple" },
  ];

  const cards = mealTypes.map(mt => {
    const items = meals[mt.key] || [];
    const listItems = items.map(item =>
      `<div class="meal-item ${mt.cls}">${item}</div>`
    ).join("");
    return `
      <div class="col-md-6">
        <div class="fb-card">
          <div class="meal-group-title"><i class="bi ${mt.icon} me-1"></i>${mt.label}</div>
          ${listItems || '<div class="text-muted small">No suggestions for this meal.</div>'}
        </div>
      </div>`;
  }).join("");

  return `<div class="row g-3">${cards}</div>`;
}

function renderNutritionSkeleton() {
  const skeletonCard = (n) => `
    <div class="col-md-6">
      <div class="fb-card">
        <div class="skeleton skeleton-text short mb-3"></div>
        ${Array.from({length: n}, () =>
          '<div class="skeleton skeleton-text wide mb-2"></div>'
        ).join("")}
      </div>
    </div>`;
  return `<div class="row g-3">
    ${skeletonCard(3)}${skeletonCard(3)}${skeletonCard(2)}${skeletonCard(2)}
  </div>`;
}

// ══════════════════════════════════════════════════════════════════
//  METRICS / PERSISTENCE
// ══════════════════════════════════════════════════════════════════
function loadStoredMetrics() {
  // Workout count this week
  const stored = parseInt(localStorage.getItem("fb_wcount_" + getWeekKey()), 10) || 0;
  AppState.workoutCount = stored;
  const wEl = document.getElementById("workoutCount");
  if (wEl) wEl.textContent = stored;

  // Streak (simple: days with at least one habit)
  const streak = parseInt(localStorage.getItem("fb_streak"), 10) || 1;
  AppState.streak = streak;
  const sEl = document.getElementById("streakCount");
  if (sEl) sEl.textContent = streak;
}

// ══════════════════════════════════════════════════════════════════
//  UTILITY HELPERS
// ══════════════════════════════════════════════════════════════════
function getTodayKey() {
  return new Date().toISOString().slice(0, 10); // "YYYY-MM-DD"
}

function getWeekKey() {
  const d  = new Date();
  const jan1 = new Date(d.getFullYear(), 0, 1);
  const week = Math.ceil(((d - jan1) / 86400000 + jan1.getDay() + 1) / 7);
  return `${d.getFullYear()}-W${week}`;
}

function capitalise(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
}
