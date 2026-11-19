// Bolo owner console: vanilla JS, no build step.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const api = async (path, opts = {}) => {
  const form = opts.body instanceof FormData;
  let r;
  try {
    r = await fetch(path, { ...opts, headers: form ? opts.headers : { "Content-Type": "application/json", ...opts.headers },
      body: opts.body && typeof opts.body !== "string" && !form ? JSON.stringify(opts.body) : opts.body });
  } catch (error) {
    toast("Connection interrupted. Try again.");
    throw error;
  }
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    const message = typeof detail.detail === "string" ? detail.detail : `Request failed (HTTP ${r.status}). Try again.`;
    toast(message); throw new Error(message);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
};
const rs = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const when = (t) => new Date(t * 1000).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const LANGS = { "kn-IN": "ಕನ್ನಡ Kannada", "hi-IN": "हिंदी Hindi", "en-IN": "English", "ta-IN": "தமிழ் Tamil", "te-IN": "తెలుగు Telugu",
  "ml-IN": "മലയാളം Malayalam", "mr-IN": "मराठी Marathi", "bn-IN": "বাংলা Bengali", "gu-IN": "ગુજરાતી Gujarati", "od-IN": "ଓଡ଼ିଆ Odia", "pa-IN": "ਪੰਜਾਬੀ Punjabi" };
function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.remove("hidden"); clearTimeout(el._t); el._t = setTimeout(() => el.classList.add("hidden"), 2600); }
$$(".langsel").forEach((s) => (s.innerHTML = Object.entries(LANGS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")));

// ---------- business profile
let PROFILE = null;
const roleLabel = (r) => (PROFILE && PROFILE.roles[r]) || r;
async function loadProfile() {
  PROFILE = await api("/api/profile");
  $$(".rolesel").forEach((s) => (s.innerHTML = Object.entries(PROFILE.roles).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")));
  $("#typeSel").innerHTML = '<option value="">Auto-detect</option>' + Object.entries(PROFILE.types).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  return PROFILE;
}
async function setupShop(request, success) {
  const buttons = $$("#onboardForm button");
  buttons.forEach(b => b.disabled = true);
  $("#pageState").textContent = "Setting up your shop…";
  try {
    await request();
    toast(success);
    await boot();
  } catch { $("#pageState").textContent = "Setup did not finish. Try again."; }
  finally { buttons.forEach(b => b.disabled = false); }
}
$("#onboardForm").onsubmit = e => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target));
  setupShop(() => api("/api/onboard", {method:"POST", body}), "Shop ready");
};
$$("button[data-demo]").forEach(b => b.onclick = () =>
  setupShop(() => api("/api/seed?kind=" + b.dataset.demo, {method:"POST"}), "Demo shop ready"));

// ---------- navigation
const loaders = {};
let viewVersion = 0;
function closeMenu() {
  $(".side").classList.remove("open");
  $("#menuToggle").setAttribute("aria-expanded", "false");
}
$("#menuToggle").onclick = () => {
  const open = $(".side").classList.toggle("open");
  $("#menuToggle").setAttribute("aria-expanded", String(open));
};
async function show(view) {
  if (!document.getElementById("v-" + view)) view = "dashboard";
  if (PROFILE && !PROFILE.onboarded) view = "onboard";
  const version = ++viewVersion;
  closeMenu();
  $$("#nav a").forEach(a => {
    const active = a.dataset.view === view;
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  $$(".view").forEach(v => v.classList.toggle("hidden", v.id !== "v-" + view));
  if (location.hash.slice(1) !== view) history.replaceState(null, "", "#" + view);
  const state = $("#pageState");
  state.textContent = "Loading…";
  try { if (loaders[view]) await loaders[view](); }
  catch { if (version === viewVersion) state.textContent = "Could not load this view. Reopen it to retry."; return; }
  if (version === viewVersion) state.textContent = "";
}
$$("#nav a").forEach(a => a.onclick = e => {
  if (location.hash === a.hash) { e.preventDefault(); show(a.dataset.view); }
});

// ---------- status
async function loadStatus() {
  const s = await api("/api/status");
  const c = s.config;
  $("#status").innerHTML = `<b>WhatsApp</b>${c.whatsapp}<br><b>Speech</b>${c.stt_sarvam ? "Sarvam" : c.stt_local ? "Local Whisper" : "—"}${c.stt_groq ? " + Groq" : ""}${c.stt_gemini ? " + Gemini" : ""}<br>
    <b>AI</b>${c.llm.join(", ")}<br><b>Voice reply</b>${c.tts}<br><b>Calls</b>${c.calls}<br><b>Ledger</b>${s.verify.ok ? "✅ intact" : "⚠️ broken"}`;
  $("#liveNote").textContent = c.whatsapp === "simulator" ? "Choose a sender to try a conversation in this shop." : "Live via " + c.whatsapp + ": real WhatsApp messages arrive here. This simulator runs the same bot for any sender.";
  const st = await api("/api/settings");
  $("#shopName").textContent = st.shop_name || "Not set up yet";
  return s;
}

// ---------- dashboard
loaders.dashboard = async () => {
  const [led, claims, appr, sum] = await Promise.all([api("/api/ledger"), api("/api/claims"), api("/api/approvals"), api("/api/summary")]);
  const owing = led.balances.filter((b) => b.balance > 0);
  const total = owing.reduce((a, b) => a + b.balance, 0);
  const over = owing.filter((b) => b.age_days > 30).length;
  const openDisp = claims.filter((c) => c.kind === "dispute" && c.status === "open").length;
  const openAppr = appr.filter((a) => a.status === "open").length;
  $("#kpis").innerHTML = [[`Total ${PROFILE.dues_word}`, rs(total)], ["Given today", rs(led.today.credit)], ["Back today", rs(led.today.payment)],
    ["30+ days overdue", over], ["Open disputes", openDisp], ["Waiting approval", openAppr]]
    .map(([k, v]) => `<div class="kpi"><small>${k}</small><b>${v}</b></div>`).join("");
  $("#topOwing").innerHTML = "<tr><th>Customer</th><th>Owes</th><th>Age</th></tr>" + owing.slice(0, 8)
    .map((b) => `<tr><td>${esc(b.name)}</td><td>${rs(b.balance)}</td><td>${b.age_days ? b.age_days + " d" : "—"}</td></tr>`).join("");
  $("#claimsList").innerHTML = claims.slice(0, 8).map((c) => `<div class="entry"><div><b>${esc(c.name)}</b> · ${c.kind}
    ${c.amount ? rs(c.amount) : ""} ${c.date ? "→ " + c.date : ""}<br><small class="muted">${esc(c.text || "")}</small></div>
    <span class="pill ${c.kind === "dispute" && c.status === "open" ? "bad" : ""}">${c.status}</span></div>`).join("") || '<p class="muted">Nothing yet.</p>';
  $("#summaryText").textContent = sum.text;
  $("#bizTitle").textContent = PROFILE.name || "Today";
  $("#bizSub").textContent = `${PROFILE.label} · ${PROFILE.features.length} features enabled`;
};
$("#sendSummary").onclick = async () => { await api("/api/summary/send", { method: "POST" }); toast("Summary sent to owner"); };
$("#resetBtn").onclick = async () => {
  if (!confirm("Archive this shop and start a new one? The current shop will leave the console.")) return;
  await api("/api/reset", { method: "POST" }); toast("Fresh start"); boot();
};

// ---------- phone simulator
let current = null, lastId = 0, contactsCache = [];
async function loadWho() {
  contactsCache = await api("/api/contacts");
  $("#whoList").innerHTML = contactsCache.filter((c) => c.phone).map((c) => `<button type="button" data-phone="${esc(c.phone)}" class="${current === c.phone ? "on" : ""}">
    <b>${esc(c.name)}</b> <span class="pill">${esc(roleLabel(c.role))}</span><small>${LANGS[c.lang] || c.lang} · ${c.reply_mode === "text" ? "Text only" : c.reply_mode === "voice" ? "Voice first" : "Text + voice"}${c.balance ? " · owes " + rs(c.balance) : ""}</small></button>`).join("")
    || '<p class="muted" style="padding:12px">Add a person with a phone number in People &amp; roles.</p>';
  $$("#whoList button[data-phone]").forEach((d) => (d.onclick = () => pick(d.dataset.phone)));
}
function pick(phone) {
  current = phone; lastId = 0; $("#chat").innerHTML = '<p class="chat-empty">Record a voice note, type a message, or choose an example below.</p>';
  const c = contactsCache.find((x) => x.phone === phone);
  $("#phoneHead").innerHTML = `<span class="wa-back" aria-hidden="true">‹</span><span class="wa-avatar" aria-hidden="true">B</span>
    <span class="wa-title"><b>Bolo · ${esc(PROFILE.name || "Shop")}</b><small>chatting as ${esc(c.name)} (${esc(roleLabel(c.role))}) · ${esc(LANGS[c.lang] || c.lang)}</small></span>
    <span class="wa-icons" aria-hidden="true">📹&nbsp;&nbsp;📞&nbsp;&nbsp;⋮</span>`;
  const H = { owner: [...(PROFILE.hints || []), "Ramesh chaar sau pachaas ka saman liya, Shanivar kodthane. Lakshmi 200 kotlu", "nahi, 540", "Saturday 5 baje stock count, delivery team se pucho kaun aa raha hai",
    "Balaji ko quotation bhejo, 50 bag cement 380 ke rate se", "kaun kaun ka kitna baaki hai", "aaj ka hisaab", "galat tha hatao"],
    staff: ["Fatima 300 udhaar", "Selvi ne 100 diye"], customer: ["kitna baaki hai", "Saturday dunga", "galat hai, 350 tha", "maine 200 gpay kar diya", "2 kilo atta aur ek Fortune oil bhejo"] };
  $("#hints").innerHTML = [...new Set(H[c.role] || [])].map(h => `<button type="button">${esc(h)}</button>`).join("");
  $$("#hints button").forEach((s) => (s.onclick = () => { $("#msgInput").value = s.textContent; $("#msgInput").focus(); }));
  loadWho(); pollChat();
}
// WhatsApp-style rendering: *bold*, voice-note player with waveform, tappable reply buttons under the bubble.
const btnLabels = {};
const hm = (t) => new Date(t * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
const waText = (t) => esc(t || "").replace(/\*([^*\n]+)\*/g, "<b>$1</b>").replace(/(^|\s)_([^_\n]+)_(?=\s|$)/g, "$1<i>$2</i>");
function voiceNote(src, seed) {
  let x = Number(seed) || 7, bars = "";
  for (let i = 0; i < 32; i++) { x = (x * 9301 + 49297) % 233280; bars += `<i style="height:${6 + Math.round((x / 233280) * 18)}px"></i>`; }
  return `<div class="vn"><button type="button" class="vn-play" data-src="${esc(src)}" aria-label="Play voice note">▶</button>
    <div class="vn-bars">${bars}<div class="vn-fill">${bars}</div></div><span class="vn-dur">🎙️</span></div>`;
}
function bubble(m, allowReview = false) {
  const cls = m.direction === "in" ? "in" : "out";
  (m.buttons || []).forEach(([id, t]) => (btnLabels[id] = t));
  let body = waText(m.text);
  if (m.kind === "voice" && m.media) body = voiceNote(m.media, m.id) + (m.text ? `<div class="vn-text">${esc(m.text)}</div>` : "");
  if (m.kind === "voice" && m.direction === "in" && m.meta && m.meta.engine_b && m.meta.engine_b !== m.meta.engine_a)
    body += `<div class="vn-text">2nd engine: ${esc(m.meta.engine_b)}</div>`;
  if (m.kind === "document" && m.media) body = `<a class="doc" href="${m.media}" target="_blank"><span class="doc-ico">PDF</span><span><b>${esc((m.meta && m.meta.filename) || "Document")}</b><small>PDF · tap to open</small></span></a>${m.text ? `<div>${waText(m.text)}</div>` : ""}`;
  if (m.kind === "media" && m.direction === "in") body = `📷 Photo / document${m.text ? ": " + esc(m.text) : ""}`;
  if (m.kind === "button" && m.direction === "in") body = `<span class="tapped">↩︎ ${esc(btnLabels[m.text] || m.text)}</span>`;
  if (m.kind === "voice" && m.direction === "in" && m.meta?.review_status === "pending" && allowReview) {
    body += `<form class="voice-review" data-review="${Number(m.id)}">
      <label>Check what Bolo heard<textarea name="transcript" rows="2" placeholder="Type what you said if the note was unclear">${esc(m.meta.engine_a || "")}</textarea></label>
      <div class="formactions"><button type="submit">Use transcript</button><button type="button" class="ghost" data-discard>Discard</button></div>
    </form>`;
  }
  if (m.meta?.review_status === "used" && m.meta.reviewed_text)
    body += `<div class="reviewed"><b>Reviewed transcript</b><br>${esc(m.meta.reviewed_text)}</div>`;
  if (m.meta?.review_status === "discarded") body += '<small>Discarded by sender</small>';
  const ticks = cls === "in" ? ' <span class="ticks">✓✓</span>' : "";
  const btns = (m.buttons || []).length ? `<div class="btns">${m.buttons.map(([id, t]) => `<button data-b="${esc(id)}">${esc(t)}</button>`).join("")}</div>` : "";
  return `<div class="msgwrap ${cls}"><div class="msg ${cls}">${body}<small class="stamp">${hm(m.created_at)}${ticks}</small></div>${btns}</div>`;
}
// One shared player for every voice-note bubble.
let vnAudio = null, vnBtn = null;
document.addEventListener("click", (e) => {
  const b = e.target.closest(".vn-play"); if (!b) return;
  if (vnBtn === b && vnAudio && !vnAudio.paused) { vnAudio.pause(); b.textContent = "▶"; return; }
  if (vnAudio) { vnAudio.pause(); if (vnBtn) vnBtn.textContent = "▶"; }
  vnAudio = new Audio(b.dataset.src); vnBtn = b; b.textContent = "❚❚";
  const fill = b.parentElement.querySelector(".vn-fill"), dur = b.parentElement.querySelector(".vn-dur");
  const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  vnAudio.ontimeupdate = () => { if (vnAudio.duration) { fill.style.width = (100 * vnAudio.currentTime / vnAudio.duration) + "%"; dur.textContent = fmt(vnAudio.currentTime); } };
  vnAudio.onended = () => { b.textContent = "▶"; fill.style.width = "0"; dur.textContent = fmt(vnAudio.duration || 0); };
  vnAudio.play().catch(() => { b.textContent = "▶"; });
});
async function pollChat() {
  if (!current || $("#v-phone").classList.contains("hidden")) return;
  const phone = current, after = lastId;
  const rows = await api(`/api/messages?phone=${encodeURIComponent(phone)}&after=${after}`);
  if (phone !== current || after !== lastId) return;
  if (rows.length) {
    lastId = rows[rows.length - 1].id;
    const chat = $("#chat");
    chat.querySelector(".chat-empty")?.remove();
    chat.insertAdjacentHTML("beforeend", rows.map(m => bubble(m, true)).join(""));
    $$("button[data-b]", chat).forEach((b) => (b.onclick = () => send({ button: b.dataset.b })));
    $$(".voice-review", chat).forEach(form => {
      async function review(discard) {
        const phone = current, text = form.elements.transcript.value.trim();
        if (!discard && !text) { form.elements.transcript.focus(); return; }
        const body = {phone, message_id:Number(form.dataset.review), text, discard};
        const ok = await deliver(() => api("/api/simulate/review", {method:"POST", body}), "Saving your review…");
        if (ok && current === phone) pick(phone);
      }
      form.onsubmit = event => { event.preventDefault(); review(false); };
      form.querySelector("[data-discard]").onclick = () => review(true);
    });
    chat.scrollTop = chat.scrollHeight;
  }
}
let sending = false;
async function deliver(work, message) {
  if (sending) return false;
  sending = true;
  $("#sendBtn").disabled = $("#micBtn").disabled = true;
  $("#sendState").textContent = message;
  try {
    await work(); await pollChat();
    $("#sendState").textContent = ""; return true;
  } catch (error) {
    $("#sendState").textContent = error.message; return false;
  } finally {
    sending = false; $("#sendBtn").disabled = $("#micBtn").disabled = false;
  }
}
function send(payload) {
  if (!current) { toast("Choose a sender first"); return false; }
  const phone = current;
  return deliver(() => api("/api/simulate", {method:"POST", body:{phone, ...payload}}), "Waiting for Bolo…");
}
$("#sendBtn").onclick = async () => {
  const field = $("#msgInput"), draft = field.value;
  if (draft.trim() && await send({text:draft.trim()}) && field.value === draft) field.value = "";
};
$("#msgInput").onkeydown = e => { if (e.key === "Enter" && !e.isComposing) $("#sendBtn").click(); };
function upload(phone, file, isAudio) {
  const body = new FormData();
  body.append("phone", phone); body.append("file", file);
  return deliver(() => api(isAudio ? "/api/simulate/audio" : "/api/simulate/media", {method:"POST", body}),
    isAudio ? "Transcribing voice note…" : "Sending attachment…");
}
$("#fileInput").onchange = async e => {
  const input = e.target, file = input.files[0];
  if (!current || !file) return;
  if (await upload(current, file, file.type.startsWith("audio/") || /\.(ogg|wav|m4a|mp3|webm|opus)$/i.test(file.name))) input.value = "";
};
let rec = null;
$("#micBtn").onclick = async () => {
  if (!current) return toast("Choose a sender first");
  if (rec?.state === "recording") { rec.stop(); return; }
  const phone = current, button = $("#micBtn");
  let stream;
  button.disabled = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio:true});
    const recorder = new MediaRecorder(stream), chunks = [];
    rec = recorder;
    recorder.ondataavailable = e => chunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
      button.classList.remove("rec"); button.setAttribute("aria-pressed", "false");
      button.title = "Tap to record a voice note"; button.setAttribute("aria-label", "Record voice note");
      button.textContent = "🎙️";
      const mime = recorder.mimeType || "audio/webm";
      const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
      await upload(phone, new File(chunks, "note." + ext, {type:mime}), true);
    };
    recorder.start(); button.classList.add("rec"); button.setAttribute("aria-pressed", "true");
    button.title = "Stop and send"; button.setAttribute("aria-label", "Stop and send"); button.textContent = "■";
    $("#sendState").textContent = "Recording… tap ■ to send.";
  } catch {
    stream?.getTracks().forEach(track => track.stop());
    $("#sendState").textContent = "Microphone unavailable. Attach an audio file or type a message.";
  } finally { button.disabled = false; }
};
loaders.phone = async () => { await loadWho(); if (!current) { const o = contactsCache.find((c) => c.role === "owner"); if (o) pick(o.phone); } };
setInterval(pollChat, 1500);
setInterval(() => { const k = document.getElementById("waClock"); if (k) k.textContent = new Date().toLocaleTimeString("en-IN", {hour: "2-digit", minute: "2-digit"}); }, 1000);

// ---------- ledger
loaders.ledger = async () => {
  const led = await api("/api/ledger");
  $("#chainBadge").className = "pill " + (led.verify.ok ? "" : "bad");
  $("#chainBadge").textContent = led.verify.ok ? `🔗 Chain intact · ${led.verify.entries} rows` : `⚠️ Chain broken at #${led.verify.broken_at}`;
  $("#balTable").innerHTML = "<tr><th>Customer</th><th>Balance</th><th>Age</th><th>Limit</th></tr>" + led.balances
    .map((b) => `<tr><td>${esc(b.name)}</td><td><b>${rs(b.balance)}</b></td><td>${b.age_days ? b.age_days + " d" : "—"}</td><td>${b.credit_limit ? rs(b.credit_limit) : "—"}</td></tr>`).join("");
  $("#entries").innerHTML = led.entries.map((e) => `<div class="entry ${e.reversed ? "rev" : ""}"><div>
      <b>${esc(e.name)}</b> · ${e.kind} <span class="pill ${e.status === "disputed" ? "bad" : e.status === "claimed" ? "warn" : ""}">${e.status}</span><br>
      ${e.transcript ? `<small>“${esc(e.transcript)}”</small><br>` : ""}${e.audio ? `<audio controls src="${e.audio}"></audio><br>` : ""}
      <span class="hash">#${e.id} · ${when(e.created_at)} · ${e.hash.slice(0, 16)}…</span></div>
      <div class="amt">${e.kind === "payment" ? "−" : e.kind === "reversal" ? "↩" : "+"}${rs(e.amount)}</div></div>`).join("");
};

// ---------- polls
loaders.polls = async () => {
  const ps = await api("/api/polls");
  $("#pollList").innerHTML = ps.map((p) => `<div class="card poll"><div><b>${p.poll.kind === "task" ? "📋 Task" : "🗳️ Poll"}</b> · ${esc(p.poll.question)}
    <div class="ans">${p.targets.map((t) => `<span>${esc(t.name)}: ${esc(t.answer || (t.called ? "📞 called" : t.nudges ? "🔔 nudged" : "… waiting"))}</span>`).join("")}</div></div>
    <div><span class="pill ${p.poll.status === "open" ? "warn" : ""}">${p.answered}/${p.total}</span></div></div>`).join("") || '<p class="muted">Ask from the owner phone: "delivery team se pucho kaun aa raha hai".</p>';
};

// ---------- approvals
loaders.approvals = async () => {
  const ap = await api("/api/approvals");
  $("#approvalList").innerHTML = ap.map((a) => `<div class="card poll"><div><b>${esc(a.summary)}</b><br><small class="muted">by +${a.actor} · ${when(a.created_at)}</small></div>
    <div>${a.status === "open" ? `<button class="small" data-a="${a.id}" data-d="approve">Approve</button> <button class="small bad" data-a="${a.id}" data-d="reject">Reject</button>` : `<span class="pill">${a.status}</span>`}</div></div>`).join("")
    || '<p class="muted">Nothing waiting.</p>';
  $$("button[data-a]").forEach((b) => (b.onclick = async () => { await api(`/api/approvals/${b.dataset.a}/${b.dataset.d}`, { method: "POST" }); loaders.approvals(); refreshBadge(); }));
};
async function refreshBadge() { const n = (await api("/api/approvals")).filter((a) => a.status === "open").length; $("#apprBadge").textContent = n; $("#apprBadge").classList.toggle("hidden", !n); }

// ---------- people
loaders.people = async () => {
  const cs = await api("/api/contacts");
  $("#peopleTable").innerHTML = "<tr><th>Name</th><th>Role</th><th>Language</th><th>WhatsApp</th><th>Also called</th><th>Balance</th><th></th></tr>" + cs
    .map((c) => `<tr><td><b>${esc(c.name)}</b>${c.note ? `<br><small class="muted">${esc(c.note)}</small>` : ""}</td><td>${esc(roleLabel(c.role))}</td><td>${LANGS[c.lang] || c.lang}</td>
    <td>${c.phone ? "+" + c.phone : "—"} ${c.opted_in ? "✅" : ""}</td><td>${esc((c.aliases || []).join(", "))}</td><td>${c.balance ? rs(c.balance) : ""}</td>
    <td><button class="small ghost" data-edit="${c.id}">Edit</button></td></tr>`).join("");
  $$("button[data-edit]").forEach((b) => (b.onclick = () => {
    const c = cs.find((x) => x.id == b.dataset.edit); const f = $("#personForm");
    for (const k of ["id", "name", "phone", "role", "lang", "note", "credit_limit", "reply_mode"]) f[k].value = c[k] ?? (k === "reply_mode" ? "both" : "");
    f.aliases.value = (c.aliases || []).join(", "); f.opted_in.checked = !!c.opted_in; window.scrollTo(0, 0);
  }));
};
$("#personForm").onsubmit = async (e) => {
  e.preventDefault(); const f = e.target; const d = Object.fromEntries(new FormData(f));
  d.opted_in = f.opted_in.checked ? 1 : 0; if (!d.id) delete d.id; else d.id = Number(d.id);
  await api("/api/contacts", { method: "POST", body: d }); f.reset(); toast("Saved"); loaders.people();
};

// ---------- products
loaders.products = async () => {
  const ps = await api("/api/catalog");
  $("#productTable").innerHTML = "<tr><th>Name</th><th>Local names</th><th>Unit</th><th>Price</th><th></th></tr>" + ps
    .map((p) => `<tr><td>${esc(p.name)}</td><td>${esc(JSON.parse(p.aliases || "[]").join(", "))}</td><td>${esc(p.unit)}</td><td>${rs(p.price)}</td>
    <td><button class="small ghost" data-del="${p.id}">Delete</button></td></tr>`).join("");
  $$("button[data-del]").forEach((b) => (b.onclick = async () => { await api(`/api/catalog/${b.dataset.del}`, { method: "DELETE" }); loaders.products(); }));
};
$("#productForm").onsubmit = async (e) => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.target)); if (!d.id) delete d.id;
  await api("/api/catalog", { method: "POST", body: d }); e.target.reset(); toast("Saved"); loaders.products(); };

// ---------- templates
loaders.templates = async () => {
  const ts = await api("/api/templates");
  $("#tmplPick").innerHTML = ts.map((t) => `<option>${t.name}</option>`).join("");
  const load = () => { const t = ts.find((x) => x.name === $("#tmplPick").value); $("#tmplHtml").value = t.html; $("#tmplPreview").src = `/api/templates/${t.name}/preview?ts=${Date.now()}`; };
  $("#tmplPick").onchange = load; load();
};
$("#tmplSave").onclick = async () => { const n = $("#tmplPick").value; await api(`/api/templates/${n}`, { method: "PUT", body: { html: $("#tmplHtml").value } });
  $("#tmplPreview").src = `/api/templates/${n}/preview?ts=${Date.now()}`; toast("Template saved"); };

// ---------- settings
loaders.settings = async () => {
  const [st, s] = await Promise.all([api("/api/settings"), loadStatus()]);
  const f = $("#settingsForm"); for (const [k, v] of Object.entries(st)) if (f[k]) f[k].value = v;
  const c = s.config;
  $("#connTable").innerHTML = [["WhatsApp", c.whatsapp, "WA_TOKEN, WA_PHONE_NUMBER_ID"], ["Speech-to-text", [c.stt_sarvam && "Sarvam Saaras v4", c.stt_groq && "Groq Whisper", c.stt_gemini && "Gemini", c.stt_local && "Local Whisper"].filter(Boolean).join(" + ") || "off", "SARVAM_API_KEY, GROQ_API_KEY"],
    ["AI agent", c.llm.join(" → "), "GEMINI_API_KEY / SARVAM_API_KEY / GROQ_API_KEY"], ["Voice replies", c.tts, "SARVAM_API_KEY"], ["Translation", c.translate, "SARVAM_API_KEY"], ["Phone calls", c.calls, "BOLNA_API_KEY, BOLNA_AGENT_ID"]]
    .map(([a, b, k]) => `<tr><td>${a}</td><td><b>${esc(b)}</b></td><td><code>${k}</code></td></tr>`).join("");
};
$("#settingsForm").onsubmit = async (e) => { e.preventDefault(); await api("/api/settings", { method: "PUT", body: Object.fromEntries(new FormData(e.target)) }); toast("Settings saved"); loadStatus(); };

// ---------- activity
loaders.activity = async () => {
  const a = await api("/api/audit");
  $("#auditTable").innerHTML = "<tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr>" + a
    .map((r) => `<tr><td>${when(r.created_at)}</td><td>${r.actor ? "+" + esc(r.actor) : "Bolo"}</td><td>${esc(r.action)}</td><td><small>${esc(r.detail)}</small></td></tr>`).join("");
};

// ---------- live watch
let liveCur = null, liveLast = 0;
loaders.live = async () => {
  const d = await api("/api/live/threads");
  $("#waMode").textContent = d.whatsapp === "live" ? "WhatsApp live" : d.whatsapp === "twilio-sandbox" ? "Twilio sandbox" : "Local simulator";
  $("#pauseAll").checked = d.mode === "paused";
  $("#threadList").innerHTML = d.threads.map((t) => `<button type="button" data-phone="${esc(t.phone)}" class="${liveCur === t.phone ? "on" : ""}">
    <span class="meta"><b>${esc(t.name)}</b><small>${when(t.at)}</small></span>
    <span class="gist">${esc(t.gist || t.last)}</span><span class="pill ${t.tone === "Needs review" ? "bad" : t.tone === "Urgent wording" ? "warn" : ""}">${esc(t.tone || "Routine")}</span> ${t.paused ? '<span class="paused">✋ you are replying</span>' : ""}</button>`).join("")
    || '<p class="muted" style="padding:12px">No chats yet. Message the bot on WhatsApp (or use Try it).</p>';
  $$("#threadList button[data-phone]").forEach((el) => (el.onclick = () => openLive(el.dataset.phone, d.threads.find((x) => x.phone === el.dataset.phone))));
};
function openLive(phone, t) {
  $("#takeover").disabled = $("#liveSend").disabled = $("#liveInput").disabled = false;
  liveCur = phone; liveLast = 0; $("#liveChat").innerHTML = "";
  $("#liveHead").textContent = `${t.name} · ${t.role_label} · +${phone}`; $("#takeover").checked = t.paused;
  pollLive(); loaders.live();
}
async function pollLive() {
  if (!liveCur || $("#v-live").classList.contains("hidden")) return;
  const phone = liveCur, after = liveLast;
  const rows = await api(`/api/messages?phone=${encodeURIComponent(phone)}&after=${after}`);
  if (phone !== liveCur || after !== liveLast) return;
  if (rows.length) {
    liveLast = rows[rows.length - 1].id;
    $("#liveChat").insertAdjacentHTML("beforeend", rows.map((m) => bubble(m).replace('class="msg out"', m.meta && m.meta.human ? 'class="msg out human"' : 'class="msg out"')).join(""));
    $$("#liveChat button[data-b]").forEach((b) => (b.disabled = true));
    $("#liveChat").scrollTop = $("#liveChat").scrollHeight;
  }
}
setInterval(() => { if (!$("#v-live").classList.contains("hidden")) { pollLive(); loaders.live(); } }, 2500);
$("#pauseAll").onchange = async (e) => { await api("/api/live/mode", { method: "POST", body: { paused: e.target.checked } });
  toast(e.target.checked ? "Bot paused: watching only" : "Bot is replying again"); loadStatus(); };
$("#takeover").onchange = async (e) => { if (!liveCur) return; await api("/api/live/takeover", { method: "POST", body: { phone: liveCur, paused: e.target.checked } });
  toast(e.target.checked ? "You've taken over this chat" : "Bolo is back on this chat"); loaders.live(); };
$("#liveSend").onclick = async () => { const t = $("#liveInput").value.trim(); if (!t || !liveCur) return;
  await api("/api/live/reply", { method: "POST", body: { phone: liveCur, text: t } }); $("#liveInput").value = ""; pollLive(); };
$("#liveInput").onkeydown = (e) => { if (e.key === "Enter") $("#liveSend").click(); };

// ---------- features
loaders.features = async () => {
  await loadProfile();
  $("#featGrid").innerHTML = Object.entries(PROFILE.all_features).map(([k, f]) => {
    const on = PROFILE.features.includes(k);
    return `<div class="feat ${on ? "on" : ""}"><header><b>${esc(f.label)}</b>${f.core ? '<span class="pill">core</span>'
      : `<label class="switch small"><input type="checkbox" data-f="${k}" ${on ? "checked" : ""}><span>${on ? "On" : "Off"}</span></label>`}</header>
      <small>${esc(f.desc)}</small></div>`; }).join("");
  $$("input[data-f]").forEach((i) => (i.onchange = async () => { await api(`/api/features/${i.dataset.f}`, { method: "PUT", body: { on: i.checked } }); loaders.features(); }));
};

// ---------- knowledge
loaders.knowledge = async () => {
  const ks = await api("/api/knowledge");
  $("#kbTable").innerHTML = "<tr><th>Title</th><th>Type</th><th>For</th><th>What the bot knows</th><th></th></tr>" + ks.map((k) => `<tr>
    <td><b>${esc(k.title)}</b></td><td>${k.kind === "file" ? `<a href="/files/${encodeURIComponent(k.path.split(/[\\/]/).pop())}" target="_blank">📄 file</a>` : "📝 fact"}</td>
    <td>${esc(roleLabel(k.audience))}</td><td><small>${esc((k.text || "").slice(0, 160)) || '<span class="muted">(no text read yet)</span>'}</small></td>
    <td>${k.kind === "file" ? `<button class="small" data-send="${k.id}" data-aud="${k.audience}">Send to all ${esc(roleLabel(k.audience))}s</button> ` : ""}
    <button class="small ghost" data-kdel="${k.id}">Delete</button></td></tr>`).join("");
  $$("button[data-send]").forEach((b) => (b.onclick = async () => { if (!confirm(`Send to every ${roleLabel(b.dataset.aud)}?`)) return;
    const r = await api(`/api/knowledge/${b.dataset.send}/send`, { method: "POST", body: { role: b.dataset.aud } }); toast(`Sent to ${r.sent}`); }));
  $$("button[data-kdel]").forEach((b) => (b.onclick = async () => { await api(`/api/knowledge/${b.dataset.kdel}`, { method: "DELETE" }); loaders.knowledge(); }));
};
$("#kbFile").onsubmit = async (e) => { e.preventDefault(); toast("Uploading & reading…");
  await api("/api/knowledge/file", { method: "POST", body: new FormData(e.target) }); e.target.reset(); loaders.knowledge(); };
$("#kbFact").onsubmit = async (e) => { e.preventDefault(); await api("/api/knowledge/fact", { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
  e.target.reset(); loaders.knowledge(); };

async function boot() { await loadProfile(); if (!PROFILE.onboarded) { current = liveCur = null; lastId = liveLast = 0; } await loadStatus(); refreshBadge(); const h = location.hash.slice(1); show(PROFILE.onboarded ? (h && h !== "onboard" ? h : "dashboard") : "onboard"); }
window.addEventListener("hashchange", () => { if (PROFILE) show(location.hash.slice(1)); });
boot().catch(() => { $("#pageState").textContent = "Could not open the shop. Check the server and reload."; });
setInterval(refreshBadge, 15000);
