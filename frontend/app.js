/**
 * app.js — AWS S3 Knowledge Base frontend logic
 *
 * Handles: S3 file browsing, selective/bulk ingestion,
 *          RAG chat, KB management, session control.
 */

// const API_BASE = "http://localhost:8000/api"; //local
const API_BASE = "https://aws-s3-knowledge-base.onrender.com/api"; //render url

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let sessionId     = "";
let isWaiting     = false;
let s3Files       = [];
let selectedKeys  = new Set();

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const messagesEl       = document.getElementById("messages");
const messageInput     = document.getElementById("messageInput");
const sendBtn          = document.getElementById("sendBtn");
const clearChatBtn     = document.getElementById("clearChatBtn");
const statusDot        = document.getElementById("statusDot");
const statusText       = document.getElementById("statusText");
const s3Dot            = document.getElementById("s3Dot");
const s3Text           = document.getElementById("s3Text");
const s3Meta           = document.getElementById("s3Meta");
const s3Timestamp      = document.getElementById("s3Timestamp");
const fileList         = document.getElementById("fileList");
const prefixInput      = document.getElementById("prefixInput");
const refreshFilesBtn  = document.getElementById("refreshFilesBtn");
const testConnectionBtn= document.getElementById("testConnectionBtn");
const ingestSelectedBtn= document.getElementById("ingestSelectedBtn");
const ingestAllBtn     = document.getElementById("ingestAllBtn");
const ingestStatus     = document.getElementById("ingestStatus");
const docList          = document.getElementById("docList");
const refreshDocsBtn   = document.getElementById("refreshDocsBtn");
const clearKbBtn       = document.getElementById("clearKbBtn");
const sidebar          = document.getElementById("sidebar");
const sidebarToggle    = document.getElementById("sidebarToggle");
const openSidebar      = document.getElementById("openSidebar");

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  loadS3Files();
  loadDocuments();
  setupInputAutoResize();
});

// ---------------------------------------------------------------------------
// Health / connection
// ---------------------------------------------------------------------------
async function checkHealth() {
  setStatus("loading", "Connecting…");
  try {
    const res  = await fetch(`${API_BASE}/health`);
    const data = await res.json();

    if (data.rag_ready) {
      setStatus("online", "API connected");
    } else {
      setStatus("offline", "RAG not ready");
    }

    const s3 = data.s3 || {};
    if (s3.connected) {
      setS3Status("online", "Connected");
      s3Meta.textContent = `Bucket: ${s3.bucket}  ·  ${s3.file_count} file(s)`;
      stampLastUpdated();
      loadS3Files();
    } else {
      setS3Status("offline", "Not connected");
      s3Meta.textContent = s3.error || "Check AWS env vars";
      s3Timestamp.textContent = "";
    }
  } catch {
    setStatus("offline", "Server offline");
    setS3Status("offline", "Server offline");
    s3Timestamp.textContent = "";
  }
}

function stampLastUpdated() {
  const now = new Date();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const date = now.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
  s3Timestamp.textContent = `Last updated: ${date} at ${time}`;
}

function setStatus(state, text) {
  statusDot.className  = `status-dot ${state}`;
  statusText.textContent = text;
}

function setS3Status(state, text) {
  s3Dot.className = `status-dot ${state}`;
  s3Text.textContent = text;
}

testConnectionBtn.addEventListener("click", checkHealth);

// ---------------------------------------------------------------------------
// Sidebar toggle
// ---------------------------------------------------------------------------
sidebarToggle.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
  sidebar.classList.remove("open");
});

openSidebar.addEventListener("click", () => {
  if (window.innerWidth <= 720) {
    sidebar.classList.add("open");
    sidebar.classList.remove("collapsed");
  } else {
    sidebar.classList.remove("collapsed");
  }
});

// ---------------------------------------------------------------------------
// S3 file browser
// ---------------------------------------------------------------------------
refreshFilesBtn.addEventListener("click", loadS3Files);

prefixInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadS3Files();
});

async function loadS3Files() {
  const prefix = prefixInput.value.trim();
  fileList.innerHTML = '<li class="file-empty">Loading…</li>';
  selectedKeys.clear();
  ingestSelectedBtn.disabled = true;

  try {
    const res  = await fetch(`${API_BASE}/s3/files?prefix=${encodeURIComponent(prefix)}`);
    const data = await res.json();
    s3Files = data.files || [];
    renderFileList();
    stampLastUpdated();
  } catch {
    fileList.innerHTML = '<li class="file-empty">Could not reach server.</li>';
  }
}

function renderFileList() {
  if (s3Files.length === 0) {
    fileList.innerHTML = '<li class="file-empty">No supported files found in bucket.</li>';
    return;
  }

  fileList.innerHTML = "";
  s3Files.forEach((file) => {
    const li = document.createElement("li");
    li.className = `file-item${file.ingested ? " ingested" : ""}`;
    li.dataset.key = file.key;

    const icon = file.extension === ".pdf" ? "📄" : "📝";

    li.innerHTML = `
      <input type="checkbox" ${file.ingested ? "disabled" : ""} data-key="${file.key}" />
      <span class="file-icon">${icon}</span>
      <span class="file-name" title="${file.key}">${file.key}</span>
      <span class="file-size">${file.size_kb}KB</span>
      ${file.ingested ? '<span class="file-badge">Ingested</span>' : ""}
    `;

    const cb = li.querySelector("input[type='checkbox']");
    cb.addEventListener("change", () => {
      if (cb.checked) {
        selectedKeys.add(file.key);
        li.classList.add("selected");
      } else {
        selectedKeys.delete(file.key);
        li.classList.remove("selected");
      }
      ingestSelectedBtn.disabled = selectedKeys.size === 0;
    });

    fileList.appendChild(li);
  });
}

// ---------------------------------------------------------------------------
// Ingestion
// ---------------------------------------------------------------------------
ingestSelectedBtn.addEventListener("click", () => ingest([...selectedKeys]));

ingestAllBtn.addEventListener("click", async () => {
  if (!confirm(`Ingest all supported files from the S3 bucket?`)) return;
  setIngestStatus("Ingesting all files…", "");
  ingestAllBtn.disabled = true;

  try {
    const prefix = prefixInput.value.trim();
    const res    = await fetch(`${API_BASE}/s3/ingest-all?prefix=${encodeURIComponent(prefix)}`, {
      method: "POST",
    });
    const data = await res.json();
    handleIngestResult(data);
  } catch {
    setIngestStatus("❌ Could not reach server.", "error");
  } finally {
    ingestAllBtn.disabled = false;
  }
});

async function ingest(keys) {
  if (!keys.length) return;
  setIngestStatus(`Ingesting ${keys.length} file(s)…`, "");
  ingestSelectedBtn.disabled = true;

  try {
    const res  = await fetch(`${API_BASE}/s3/ingest`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ keys }),
    });
    const data = await res.json();
    handleIngestResult(data);
  } catch {
    setIngestStatus("❌ Could not reach server.", "error");
  } finally {
    ingestSelectedBtn.disabled = selectedKeys.size === 0;
  }
}

function handleIngestResult(data) {
  const ok  = data.ingested?.length || 0;
  const err = data.errors?.length   || 0;

  if (err === 0) {
    setIngestStatus(`✅ ${ok} file(s) ingested successfully.`, "success");
  } else {
    setIngestStatus(`⚠️ ${ok} ingested, ${err} failed.`, "error");
  }

  selectedKeys.clear();
  loadS3Files();
  loadDocuments();
}

function setIngestStatus(msg, cls) {
  ingestStatus.textContent = msg;
  ingestStatus.className   = `ingest-status ${cls}`;
}

// ---------------------------------------------------------------------------
// Knowledge base (ingested docs list)
// ---------------------------------------------------------------------------
refreshDocsBtn.addEventListener("click", loadDocuments);

async function loadDocuments() {
  try {
    const res  = await fetch(`${API_BASE}/documents`);
    const data = await res.json();
    renderDocList(data.documents || []);
  } catch { /* silent */ }
}

function renderDocList(docs) {
  if (docs.length === 0) {
    docList.innerHTML = '<li class="doc-empty">No documents ingested yet.</li>';
    return;
  }
  docList.innerHTML = "";
  docs.forEach((doc) => {
    const li = document.createElement("li");
    li.className = "doc-item";
    li.innerHTML = `
      <span class="doc-item-icon">📄</span>
      <span class="doc-item-name" title="${doc.s3_key || doc.filename}">${doc.filename}</span>
      <button class="doc-delete" title="Remove" onclick="deleteDocument('${doc.doc_id}')">🗑</button>
    `;
    docList.appendChild(li);
  });
}

async function deleteDocument(docId) {
  if (!confirm("Remove this document from the knowledge base?")) return;
  try {
    const res = await fetch(`${API_BASE}/documents/${docId}`, { method: "DELETE" });
    if (res.ok) { await loadDocuments(); await loadS3Files(); }
  } catch { alert("Failed to delete document."); }
}

clearKbBtn.addEventListener("click", async () => {
  if (!confirm("Remove ALL documents from the knowledge base? This cannot be undone.")) return;
  clearKbBtn.disabled = true;
  clearKbBtn.textContent = "Clearing…";
  try {
    const res  = await fetch(`${API_BASE}/documents`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      await loadDocuments();
      await loadS3Files();
      setIngestStatus(`✅ ${data.message}`, "success");
    }
  } catch { alert("Could not reach server."); }
  finally {
    clearKbBtn.disabled = false;
    clearKbBtn.innerHTML = "&#x1F5D1; Clear Knowledge Base";
  }
});

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
sendBtn.addEventListener("click", sendMessage);

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

messageInput.addEventListener("input", () => {
  sendBtn.disabled = !messageInput.value.trim() || isWaiting;
});

async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text || isWaiting) return;

  const welcome = messagesEl.querySelector(".welcome");
  if (welcome) welcome.remove();

  appendMessage("user", text);
  messageInput.value = "";
  messageInput.style.height = "auto";
  sendBtn.disabled = true;
  isWaiting = true;

  const typingId = showTyping();

  try {
    const res  = await fetch(`${API_BASE}/chat`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ message: text, session_id: sessionId }),
    });
    const data = await res.json();
    removeTyping(typingId);

    if (res.ok) {
      sessionId = data.session_id;
      appendMessage("ai", data.answer, data.sources || []);
    } else {
      appendMessage("ai", `Error: ${data.detail || "Unknown error."}`, [], true);
    }
  } catch {
    removeTyping(typingId);
    appendMessage("ai", "Could not reach the server. Make sure the backend is running.", [], true);
  } finally {
    isWaiting = false;
    sendBtn.disabled = !messageInput.value.trim();
  }
}

function appendMessage(role, text, sources = [], isError = false) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  if (role === "ai") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = "in";
    row.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (isError) bubble.style.color = "#CC1016";

  const displayText = text;
  bubble.innerHTML = renderMarkdown(displayText);

  if (sources.length > 0) {
    const srcDiv = document.createElement("div");
    srcDiv.className = "sources";
    const label = document.createElement("span");
    label.style.cssText = "font-size:11px;color:#666;width:100%;";
    label.textContent = "Sources:";
    srcDiv.appendChild(label);
    sources.forEach((src) => {
      const tag  = document.createElement("span");
      tag.className = "source-tag";
      const page = src.page !== "" ? ` · p.${Number(src.page) + 1}` : "";
      tag.textContent = `📄 ${src.filename}${page}`;
      srcDiv.appendChild(tag);
    });
    bubble.appendChild(srcDiv);
  }

  row.appendChild(bubble);
  messagesEl.appendChild(row);
  scrollBottom();
}

function renderMarkdown(text) {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  html = html.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
  html = html.replace(/`([^`]+)`/g, "<code style='background:#f3f4f6;padding:2px 5px;border-radius:3px;font-size:13px;'>$1</code>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/\n/g, "<br/>");
  return html;
}

let typingCounter = 0;
function showTyping() {
  const id  = `typing-${typingCounter++}`;
  const row = document.createElement("div");
  row.className = "message-row ai typing";
  row.id = id;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "in";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  scrollBottom();
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function scrollBottom() { messagesEl.scrollTop = messagesEl.scrollHeight; }

// ---------------------------------------------------------------------------
// Clear chat
// ---------------------------------------------------------------------------
clearChatBtn.addEventListener("click", async () => {
  if (sessionId) {
    try {
      await fetch(`${API_BASE}/session/clear`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ session_id: sessionId }),
      });
    } catch { /* ignore */ }
    sessionId = "";
  }
  resetChatUI();
});

function resetChatUI() {
  messagesEl.innerHTML = `
    <div class="welcome">
      <div class="welcome-icon">🤖</div>
      <h2>Hello! Ask me about your S3 documents.</h2>
      <p>Browse your S3 bucket in the sidebar, select files to ingest,<br/>
         then ask me anything about their contents.</p>
      <div class="welcome-chips">
        <button class="chip" onclick="insertChip('What documents are in the knowledge base?')">What documents are loaded?</button>
        <button class="chip" onclick="insertChip('Summarise the key points.')">Summarise key points</button>
        <button class="chip" onclick="insertChip('What are the main topics covered?')">Main topics covered</button>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Auto-resize input
// ---------------------------------------------------------------------------
function setupInputAutoResize() {
  messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
  });
}

// ---------------------------------------------------------------------------
// Chip shortcuts
// ---------------------------------------------------------------------------
function insertChip(text) {
  messageInput.value = text;
  messageInput.dispatchEvent(new Event("input"));
  messageInput.focus();
}
