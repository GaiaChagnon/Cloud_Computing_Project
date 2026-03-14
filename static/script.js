/**
 * Villa Sirene — Concierge Chat Frontend
 *
 * Handles message sending, response rendering (with markdown-lite),
 * typing indicator, auto-resize of textarea, and keyboard shortcuts.
 */

(function () {
    "use strict";

    const chatEl    = document.getElementById("chat");
    const innerEl   = chatEl.querySelector(".chat-inner");
    const inputEl   = document.getElementById("userInput");
    const sendBtn   = document.getElementById("btnSend");
    const resetBtn  = document.getElementById("btnReset");

    let sending = false;

    // ------------------------------------------------------------------
    // Markdown-lite: bold, italic, bullet lists, paragraphs
    // ------------------------------------------------------------------
    function renderMarkdown(text) {
        const escaped = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        const lines = escaped.split("\n");
        let html = "";
        let inList = false;

        for (const raw of lines) {
            const line = raw.trim();

            if (line.startsWith("- ")) {
                if (!inList) { html += "<ul>"; inList = true; }
                html += "<li>" + inlineFormat(line.slice(2)) + "</li>";
                continue;
            }

            if (inList) { html += "</ul>"; inList = false; }

            if (line === "") {
                continue;
            }

            html += "<p>" + inlineFormat(line) + "</p>";
        }

        if (inList) html += "</ul>";
        return html;
    }

    function inlineFormat(s) {
        return s
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.+?)\*/g, "<em>$1</em>");
    }

    // ------------------------------------------------------------------
    // DOM helpers
    // ------------------------------------------------------------------
    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatEl.scrollTop = chatEl.scrollHeight;
        });
    }

    function addUserMessage(text) {
        const msg = document.createElement("div");
        msg.className = "message user-message";
        msg.innerHTML = `
            <div class="message-avatar">You</div>
            <div class="message-body">
                <div class="message-content"><p>${escapeHtml(text)}</p></div>
            </div>`;
        innerEl.appendChild(msg);
        scrollToBottom();
    }

    function addBotMessage(text) {
        const msg = document.createElement("div");
        msg.className = "message bot-message";
        msg.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                    <path d="M24 4 L6 20 L6 42 L18 42 L18 30 L30 30 L30 42 L42 42 L42 20 Z"
                          fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/>
                    <circle cx="24" cy="22" r="4" fill="none" stroke="currentColor" stroke-width="2"/>
                </svg>
            </div>
            <div class="message-body">
                <div class="message-content">${renderMarkdown(text)}</div>
            </div>`;
        innerEl.appendChild(msg);
        scrollToBottom();
    }

    function showTyping() {
        const msg = document.createElement("div");
        msg.className = "message bot-message";
        msg.id = "typingMsg";
        msg.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                    <path d="M24 4 L6 20 L6 42 L18 42 L18 30 L30 30 L30 42 L42 42 L42 20 Z"
                          fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/>
                    <circle cx="24" cy="22" r="4" fill="none" stroke="currentColor" stroke-width="2"/>
                </svg>
            </div>
            <div class="message-body">
                <div class="message-content typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>`;
        innerEl.appendChild(msg);
        scrollToBottom();
    }

    function hideTyping() {
        const el = document.getElementById("typingMsg");
        if (el) el.remove();
    }

    function escapeHtml(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    // ------------------------------------------------------------------
    // Network
    // ------------------------------------------------------------------
    async function sendMessage(text) {
        if (sending || !text.trim()) return;
        sending = true;
        sendBtn.disabled = true;

        addUserMessage(text.trim());
        inputEl.value = "";
        autoResize();
        showTyping();

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text.trim() }),
            });
            const data = await res.json();
            hideTyping();
            addBotMessage(data.response);
        } catch {
            hideTyping();
            addBotMessage("I apologise, but I am experiencing a temporary issue. Please try again in a moment.");
        } finally {
            sending = false;
            sendBtn.disabled = false;
            inputEl.focus();
        }
    }

    async function resetConversation() {
        try {
            await fetch("/api/reset", { method: "POST" });
        } catch { /* ignore */ }

        innerEl.innerHTML = "";
        const welcome = document.getElementById("welcomeMessage");
        if (welcome) innerEl.appendChild(welcome.cloneNode(true));
        location.reload();
    }

    // ------------------------------------------------------------------
    // Textarea auto-resize
    // ------------------------------------------------------------------
    function autoResize() {
        inputEl.style.height = "auto";
        inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
    }

    // ------------------------------------------------------------------
    // Event bindings
    // ------------------------------------------------------------------
    sendBtn.addEventListener("click", () => sendMessage(inputEl.value));

    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage(inputEl.value);
        }
    });

    inputEl.addEventListener("input", autoResize);
    resetBtn.addEventListener("click", resetConversation);

    inputEl.focus();
})();
