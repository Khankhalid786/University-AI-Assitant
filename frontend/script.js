const loginShell = document.getElementById("loginShell");
const chatShell = document.getElementById("chatShell");

const loginForm = document.getElementById("loginForm");
const usernameInput = document.getElementById("usernameInput");
const passwordInput = document.getElementById("passwordInput");
const loginBtn = document.getElementById("loginBtn");
const loginError = document.getElementById("loginError");

const startSessionBtn = document.getElementById("startSessionBtn");
const exitSessionBtn = document.getElementById("exitSessionBtn");
const resetBtn = document.getElementById("resetBtn");
const sessionStateText = document.getElementById("sessionStateText");

const form = document.getElementById("chatForm");
const input = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const chatMessages = document.getElementById("chatMessages");
const chips = document.querySelectorAll(".chip");

let sessionStarted = false;
let busy = false;

function addMessage(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;
  bubble.textContent = text;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function addTypingIndicator() {
  const bubble = document.createElement("div");
  bubble.className = "message typing";
  const dots = document.createElement("div");
  dots.className = "dots";
  for (let i = 0; i < 3; i += 1) {
    dots.appendChild(document.createElement("span"));
  }
  bubble.appendChild(dots);
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
}

function updateChatControls() {
  const disableChat = !sessionStarted || busy;
  sendBtn.disabled = disableChat;
  input.disabled = disableChat;
  resetBtn.disabled = !sessionStarted || busy;
  startSessionBtn.disabled = sessionStarted || busy;
  exitSessionBtn.disabled = busy;
  chips.forEach((chip) => {
    chip.disabled = disableChat;
  });
}

function setBusy(nextBusy) {
  busy = nextBusy;
  updateChatControls();
}

function setSessionStarted(started) {
  sessionStarted = started;
  sessionStateText.textContent = started
    ? "Session active. You can now chat with the University Bot."
    : "Session not started. Click Start Session to begin.";
  updateChatControls();
}

function showLogin() {
  loginShell.classList.remove("hidden");
  chatShell.classList.add("hidden");
  loginError.textContent = "";
  passwordInput.value = "";
  usernameInput.focus();
}

function showChat() {
  loginShell.classList.add("hidden");
  chatShell.classList.remove("hidden");
}

function resetChatWithMessage(message) {
  chatMessages.replaceChildren();
  addMessage("bot", message);
}

function readErrorMessage(data, fallback) {
  if (data && typeof data.detail === "string" && data.detail.trim()) {
    return data.detail;
  }
  return fallback;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    data = null;
  }
  return { response, data };
}

async function syncSessionOnLoad() {
  try {
    const { response, data } = await fetchJson("/api/session/status");
    if (!response.ok || !data || !data.logged_in) {
      showLogin();
      return;
    }

    showChat();
    setSessionStarted(Boolean(data.session_started));

    if (data.session_started) {
      resetChatWithMessage("Welcome back. Your session is active. Ask about courses, exam rules, or faculty details.");
      input.focus();
    } else {
      resetChatWithMessage("Login successful. Click Start Session to open the University Bot.");
    }
  } catch (error) {
    showLogin();
    loginError.textContent = "Unable to reach server. Please try again.";
  }
}

function returnToLogin(message) {
  setSessionStarted(false);
  showLogin();
  if (message) {
    loginError.textContent = message;
  }
}

async function sendMessage(message) {
  addMessage("user", message);
  setBusy(true);

  const typingBubble = addTypingIndicator();

  try {
    const { response, data } = await fetchJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });

    typingBubble.remove();

    if (response.status === 401) {
      returnToLogin("Session expired. Please login again.");
      return;
    }

    if (response.status === 403) {
      setSessionStarted(false);
      addMessage("bot", "Please click Start Session before chatting.");
      return;
    }

    if (!response.ok) {
      throw new Error(readErrorMessage(data, `Request failed with status ${response.status}`));
    }

    addMessage("bot", data.reply || "I could not generate a response.");
  } catch (error) {
    typingBubble.remove();
    addMessage("bot", "I couldn't connect to the server. Please try again.");
  } finally {
    setBusy(false);
    if (sessionStarted) {
      input.focus();
    }
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";

  const username = usernameInput.value.trim();
  const password = passwordInput.value;

  if (!username || !password) {
    loginError.textContent = "Please enter username and password.";
    return;
  }

  loginBtn.disabled = true;

  try {
    const { response, data } = await fetchJson("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    if (!response.ok) {
      loginError.textContent = readErrorMessage(data, "Login failed.");
      return;
    }

    showChat();
    setSessionStarted(false);
    resetChatWithMessage("Login successful. Click Start Session to open the University Bot.");
  } catch (error) {
    loginError.textContent = "Unable to login right now. Please try again.";
  } finally {
    loginBtn.disabled = false;
  }
});

startSessionBtn.addEventListener("click", async () => {
  setBusy(true);

  try {
    const { response, data } = await fetchJson("/api/session/start", { method: "POST" });

    if (response.status === 401) {
      returnToLogin("Session expired. Please login again.");
      return;
    }

    if (!response.ok) {
      addMessage("bot", readErrorMessage(data, "Failed to start session."));
      return;
    }

    setSessionStarted(true);
    resetChatWithMessage("Session started. Ask me anything about your university.");
    input.focus();
  } catch (error) {
    addMessage("bot", "Unable to start session. Please try again.");
  } finally {
    setBusy(false);
  }
});

exitSessionBtn.addEventListener("click", async () => {
  setBusy(true);

  try {
    await fetch("/api/session/exit", { method: "POST" });
  } catch (error) {
    // Ignore; return to login UI regardless.
  } finally {
    setBusy(false);
    returnToLogin("");
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!sessionStarted || busy) {
    return;
  }

  const message = input.value.trim();
  if (!message) {
    return;
  }

  input.value = "";
  resizeInput();
  await sendMessage(message);
});

resetBtn.addEventListener("click", async () => {
  if (!sessionStarted) {
    return;
  }

  try {
    const { response } = await fetchJson("/api/reset", { method: "POST" });
    if (response.status === 401) {
      returnToLogin("Session expired. Please login again.");
      return;
    }
    if (response.status === 403) {
      setSessionStarted(false);
      resetChatWithMessage("Session not started. Click Start Session to begin.");
      return;
    }
  } catch (error) {
    // Ignore network issues here; reset UI anyway.
  }

  resetChatWithMessage("New chat started. Ask me anything about your university.");
  input.focus();
});

input.addEventListener("input", resizeInput);

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    if (!sessionStarted) {
      return;
    }
    input.value = chip.dataset.prompt || "";
    resizeInput();
    input.focus();
  });
});

setSessionStarted(false);
syncSessionOnLoad();
