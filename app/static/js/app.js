(() => {
  const apiBase = (window.PIDGIN_LAW_API_BASE || "").replace(/\/+$/, "");
  const staticMode = Boolean(window.PIDGIN_LAW_STATIC_MODE);
  const els = {
    source: document.getElementById("source"),
    output: document.getElementById("output"),
    status: document.getElementById("status"),
    translateBtn: document.getElementById("translate-btn"),
    file: document.getElementById("source-file"),
    fileBtn: document.getElementById("translate-file-btn"),
    url: document.getElementById("source-url"),
    urlBtn: document.getElementById("translate-url-btn"),
    copyBtn: document.getElementById("copy-btn"),
    txtBtn: document.getElementById("txt-btn"),
    pdfBtn: document.getElementById("pdf-btn"),
    clearBtn: document.getElementById("clear-input"),
    includeGlossary: document.getElementById("include-glossary"),
    wordCount: document.getElementById("word-count"),
    sampleRow: document.getElementById("sample-row"),
    glossaryBlock: document.getElementById("glossary-results"),
    glossaryGrid: document.getElementById("glossary-grid"),
    libraryGrid: document.getElementById("glossary-library-grid"),
    glossarySearch: document.getElementById("glossary-search"),
    menuToggle: document.getElementById("menu-toggle"),
    nav: document.querySelector(".nav"),
  };

  const state = {
    tone: "everyday",
    view: "split",
    result: null,
    busy: false,
  };
  let glossaryEntries = null;

  init();

  async function init() {
    bindEvents();
    updateWordCount();
    await Promise.all([loadHealth(), loadSamples(), loadGlossaryLibrary("")]);
  }

  function bindEvents() {
    document.querySelectorAll(".tone-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tone-btn").forEach((el) => el.classList.remove("is-active"));
        btn.classList.add("is-active");
        state.tone = btn.dataset.tone;
      });
    });

    document.querySelectorAll(".chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".chip").forEach((el) => el.classList.remove("is-active"));
        btn.classList.add("is-active");
        state.view = btn.dataset.view;
        if (state.result) renderResult(state.result);
      });
    });

    els.source.addEventListener("input", updateWordCount);
    els.translateBtn.addEventListener("click", translate);
    els.fileBtn.addEventListener("click", translateFile);
    els.urlBtn.addEventListener("click", translateURL);
    els.url.addEventListener("keydown", (event) => {
      if (event.key === "Enter") translateURL();
    });
    els.source.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        translate();
      }
    });
    els.copyBtn.addEventListener("click", copyPidgin);
    els.txtBtn.addEventListener("click", () => download("txt"));
    els.pdfBtn.addEventListener("click", () => download("pdf"));
    els.clearBtn.addEventListener("click", () => {
      els.source.value = "";
      updateWordCount();
      els.source.focus();
    });
    els.glossarySearch.addEventListener("input", debounce(() => {
      loadGlossaryLibrary(els.glossarySearch.value.trim());
    }, 220));
    els.menuToggle.addEventListener("click", () => {
      const open = els.nav.classList.toggle("is-open");
      els.menuToggle.setAttribute("aria-expanded", String(open));
    });
  }

  async function loadHealth() {
    if (staticMode) {
      return;
    }
    try {
      await api("/api/health");
      updateWordCount();
    } catch {
      showStatus("warn", "Could not reach the API health check. You fit still try translate.");
    }
  }

  async function loadSamples() {
    try {
      const samples = staticMode
        ? await loadLocalData("/data/samples.json")
        : await api("/api/samples");
      els.sampleRow.innerHTML = "";
      samples.forEach((sample) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "sample-chip";
        btn.textContent = sample.title;
        btn.title = sample.description;
        btn.addEventListener("click", () => {
          els.source.value = sample.text;
          updateWordCount();
          els.source.focus();
        });
        els.sampleRow.appendChild(btn);
      });
    } catch {
      els.sampleRow.innerHTML = "";
    }
  }

  async function loadGlossaryLibrary(query) {
    const path = query ? `/api/glossary?q=${encodeURIComponent(query)}&limit=60` : "/api/glossary?limit=24";
    try {
      if (staticMode) {
        glossaryEntries ||= await loadLocalData("/data/legal_glossary.json");
        const needle = query.toLowerCase();
        const entries = glossaryEntries.filter((entry) =>
          [entry.term, entry.pidgin_term, entry.explanation, ...(entry.aliases || [])]
            .some((value) => value.toLowerCase().includes(needle))
        ).slice(0, query ? 60 : 24);
        renderGlossary(els.libraryGrid, entries);
      } else {
        const data = await api(path);
        renderGlossary(els.libraryGrid, data.entries);
      }
    } catch {
      els.libraryGrid.innerHTML = "<p class='muted'>Glossary no load.</p>";
    }
  }

  async function translate() {
    const text = els.source.value.trim();
    if (!text) {
      showStatus("error", "Paste or type some legal English first.");
      els.source.focus();
      return;
    }
    const words = countWords(text);
    if (state.busy) return;
    state.busy = true;
    els.translateBtn.disabled = true;
    els.translateBtn.textContent = "Translating…";
    showStatus("loading", "Pidgin Law dey read the paper. Hold on…");

    try {
      const result = staticMode
        ? await translateLocally(text, state.tone, els.includeGlossary.checked)
        : await api("/api/translate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text,
            tone: state.tone,
            include_glossary: els.includeGlossary.checked,
          }),
        });
      presentResult(result);
    } catch (error) {
      showStatus("error", error.message || "Translation no work. Try again.");
    } finally {
      state.busy = false;
      els.translateBtn.disabled = false;
      els.translateBtn.textContent = "Translate to Pidgin";
    }
  }

  async function translateFile() {
    const file = els.file.files[0];
    if (!file) {
      showStatus("error", "Choose a document or audio file first.");
      return;
    }
    const payload = new FormData();
    payload.append("file", file);
    payload.append("tone", state.tone);
    payload.append("include_glossary", String(els.includeGlossary.checked));
    await submitSource("/api/translate/file", payload, "Translating file…");
  }

  async function translateURL() {
    const url = els.url.value.trim();
    if (!url) {
      showStatus("error", "Paste a public article, PDF, or audio link first.");
      els.url.focus();
      return;
    }
    await submitSource("/api/translate/url", {
      url,
      tone: state.tone,
      include_glossary: els.includeGlossary.checked,
    }, "Reading link…");
  }

  async function submitSource(path, payload, loadingMessage) {
    if (state.busy) return;
    if (staticMode) {
      showStatus("error", "File, audio, and link translation need a deployed FastAPI service. Set API_BASE_URL in Netlify and redeploy; for local use, start the server with python run.py.");
      return;
    }
    state.busy = true;
    els.translateBtn.disabled = true;
    els.fileBtn.disabled = true;
    els.urlBtn.disabled = true;
    showStatus("loading", loadingMessage);
    try {
      const isForm = payload instanceof FormData;
      const result = await api(path, {
        method: "POST",
        body: isForm ? payload : JSON.stringify(payload),
        headers: isForm ? undefined : { "Content-Type": "application/json" },
      });
      presentResult(result);
    } catch (error) {
      showStatus("error", error.message || "Could not translate that source.");
    } finally {
      state.busy = false;
      els.translateBtn.disabled = false;
      els.fileBtn.disabled = false;
      els.urlBtn.disabled = false;
    }
  }

  function presentResult(result) {
    state.result = result;
    renderResult(result);
    if (result.mode === "dictionary" && !result.caution) {
      els.status.hidden = true;
    } else if (result.caution) {
      showStatus("warn", result.caution);
    } else {
      showStatus("info", `Done · ${result.word_count} words · ${result.tone} Pidgin`);
    }
  }

  function renderResult(result) {
    els.output.classList.remove("empty");
    els.copyBtn.disabled = false;
    els.txtBtn.disabled = false;
    els.pdfBtn.disabled = false;

    if (state.view === "pidgin") {
      els.output.className = "output";
      els.output.innerHTML = `<p class="pidgin-only"></p>`;
      els.output.querySelector(".pidgin-only").textContent = result.translation;
    } else {
      els.output.className = "output split";
      els.output.innerHTML = "";
      const pairs = result.paragraphs && result.paragraphs.length
        ? result.paragraphs
        : [{ english: result.original, pidgin: result.translation }];
      pairs.forEach((pair) => {
        const row = document.createElement("div");
        row.className = "pair";
        const en = document.createElement("p");
        en.className = "en";
        en.textContent = pair.english;
        const pidgin = document.createElement("p");
        pidgin.className = "pidgin";
        pidgin.textContent = pair.pidgin;
        row.append(en, pidgin);
        els.output.appendChild(row);
      });
    }

    if (result.glossary && result.glossary.length) {
      els.glossaryBlock.hidden = false;
      renderGlossary(els.glossaryGrid, result.glossary);
    } else {
      els.glossaryBlock.hidden = true;
      els.glossaryGrid.innerHTML = "";
    }
  }

  function renderGlossary(container, entries) {
    container.innerHTML = "";
    if (!entries.length) {
      container.innerHTML = "<p class='muted'>No terms match that search.</p>";
      return;
    }
    entries.forEach((entry) => {
      const card = document.createElement("article");
      card.className = "g-card";
      const badge = entry.source === "model" ? `<span class="badge">from text</span>` : "";
      card.innerHTML = `
        <h3></h3>
        <p class="pidgin-term"></p>
        <p class="explain"></p>
        <p class="example"></p>
      `;
      card.querySelector("h3").innerHTML = "";
      card.querySelector("h3").append(entry.term);
      if (badge) card.querySelector("h3").insertAdjacentHTML("beforeend", badge);
      card.querySelector(".pidgin-term").textContent = entry.pidgin_term;
      card.querySelector(".explain").textContent = entry.explanation;
      card.querySelector(".example").textContent = entry.example ? `Example: ${entry.example}` : "";
      container.appendChild(card);
    });
  }

  async function copyPidgin() {
    if (!state.result) return;
    try {
      await navigator.clipboard.writeText(state.result.translation);
      flashButton(els.copyBtn, "Copied");
    } catch {
      showStatus("error", "Browser block copy. Select the Pidgin text yourself.");
    }
  }

  async function download(kind) {
    if (!state.result) return;
    const payload = {
      original: state.result.original,
      translation: state.result.translation,
      tone: state.result.tone,
      glossary: state.result.glossary || [],
      title: "Pidgin Law translation",
    };
    if (staticMode) {
      downloadLocally(kind, payload);
      return;
    }
    try {
      const response = await fetch(`${apiBase}/api/export/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await readError(response));
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `pidgin-law-translation.${kind}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      showStatus("error", error.message || "Download no work.");
    }
  }

  async function loadLocalData(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`Could not load ${path}`);
    return response.json();
  }

  async function translateLocally(text, tone, includeGlossary) {
    glossaryEntries ||= await loadLocalData("/data/legal_glossary.json");
    const hits = includeGlossary ? findLocalTerms(text) : [];
    let annotated = text;
    for (const hit of [...hits].sort((a, b) => b.start - a.start)) {
      const match = annotated.slice(hit.start, hit.end);
      annotated = `${annotated.slice(0, hit.start)}${match} (${hit.entry.pidgin_term})${annotated.slice(hit.end)}`;
    }
    const translation =
      "DICTIONARY MODE: legal terms get Pidgin explanations in brackets. The rest of the English stays unchanged.\n\n" + annotated;
    return {
      original: text,
      translation,
      tone,
      glossary: hits.map((hit) => ({ ...hit.entry, source: "dictionary" })),
      paragraphs: [{ english: text, pidgin: translation }],
      word_count: countWords(text),
      mode: "dictionary",
      caution: null,
      disclaimer: "This is not legal advice. Confirm important matters with a qualified Nigerian lawyer.",
    };
  }

  function findLocalTerms(text) {
    const index = glossaryEntries.map((entry) => {
      const phrases = [entry.term, ...(entry.aliases || [])].sort((a, b) => b.length - a.length);
      return { entry, phrases, length: phrases[0]?.length || 0 };
    }).sort((a, b) => b.length - a.length);
    const occupied = [];
    const found = [];

    for (const { entry, phrases } of index) {
      let matched = null;
      for (const phrase of phrases) {
        const parts = phrase.trim().split(/\s+/).map(escapeRegex);
        const pattern = new RegExp(`(?<![A-Za-z0-9])${parts.join("[\\s\\-./]*")}(?![A-Za-z0-9])`, "gi");
        for (const result of text.matchAll(pattern)) {
          const start = result.index;
          const end = start + result[0].length;
          if (!occupied.some(([from, to]) => start < to && end > from)) {
            matched = { entry, start, end };
            break;
          }
        }
        if (matched) break;
      }
      if (matched) {
        occupied.push([matched.start, matched.end]);
        found.push(matched);
        if (found.length >= 24) break;
      }
    }
    return found;
  }

  function escapeRegex(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function downloadLocally(kind, payload) {
    const glossary = payload.glossary.length
      ? payload.glossary.map((entry) => `- ${entry.term}: ${entry.pidgin_term}\n  ${entry.explanation}`).join("\n")
      : "(no terms detected)";
    const report = [
      payload.title,
      "Pidgin Law · Dictionary mode",
      "DISCLAIMER: This is not legal advice. Confirm important matters with a qualified Nigerian lawyer.",
      "ORIGINAL ENGLISH",
      payload.original,
      "PIDGIN EXPLANATION",
      payload.translation,
      "LEGAL GLOSSARY",
      glossary,
    ].join("\n\n");

    if (kind === "txt") {
      const url = URL.createObjectURL(new Blob([report], { type: "text/plain;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "pidgin-law-translation.txt";
      link.click();
      URL.revokeObjectURL(url);
      return;
    }

    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      showStatus("error", "Allow pop-ups to print or save this translation as PDF.");
      return;
    }
    printWindow.document.title = payload.title;
    const content = printWindow.document.createElement("pre");
    content.textContent = report;
    content.style.cssText = "white-space: pre-wrap; overflow-wrap: anywhere; font: 12pt/1.5 Georgia, serif; margin: 2rem;";
    printWindow.document.body.appendChild(content);
    printWindow.print();
  }

  function updateWordCount() {
    const words = countWords(els.source.value);
    els.wordCount.textContent = `${words.toLocaleString()} words`;
    els.wordCount.classList.remove("is-over");
  }

  function countWords(text) {
    const trimmed = text.trim();
    return trimmed ? trimmed.split(/\s+/).length : 0;
  }

  function showStatus(kind, message) {
    els.status.hidden = false;
    els.status.className = `status ${kind}`;
    els.status.textContent = message;
  }

  function flashButton(button, label) {
    const original = button.textContent;
    button.textContent = label;
    setTimeout(() => {
      button.textContent = original;
    }, 1400);
  }

  async function api(path, options) {
    const response = await fetch(`${apiBase}${path}`, options);
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    return response.json();
  }

  async function readError(response) {
    try {
      const data = await response.json();
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail.map((item) => item.msg || JSON.stringify(item)).join(" ");
      }
      return data.detail ? JSON.stringify(data.detail) : response.statusText;
    } catch {
      return response.statusText;
    }
  }

  function debounce(fn, wait) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }
})();
