/**
 * Villa Sirene — Concierge Frontend
 *
 * Handles: chat messaging, markdown rendering, view switching,
 * reservation lookup, email confirmation modal, toast notifications.
 */

(function () {
    "use strict";

    const chatScroll  = document.getElementById("chatScroll");
    const chatInner   = document.getElementById("chatInner");
    const inputEl     = document.getElementById("userInput");
    const sendBtn     = document.getElementById("btnSend");
    const resetBtn    = document.getElementById("btnReset");
    const quickActs   = document.getElementById("quickActions");
    const nav         = document.getElementById("mainNav");
    const lookupForm  = document.getElementById("lookupForm");
    const lookupError = document.getElementById("lookupError");
    const resultCard  = document.getElementById("resultCard");
    const emailModal  = document.getElementById("emailModal");
    const modalClose  = document.getElementById("modalClose");
    const toast       = document.getElementById("toast");
    const toastText   = document.getElementById("toastText");

    let sending = false;

    /* ==============================================================
       MARKDOWN-LITE RENDERER
       ============================================================== */

    function renderMarkdown(text) {
        const esc = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        const lines = esc.split("\n");
        let html = "";
        let inList = false;

        for (const raw of lines) {
            const line = raw.trim();
            if (line.startsWith("- ")) {
                if (!inList) { html += "<ul>"; inList = true; }
                html += "<li>" + inline(line.slice(2)) + "</li>";
                continue;
            }
            if (inList) { html += "</ul>"; inList = false; }
            if (line === "") continue;
            html += "<p>" + inline(line) + "</p>";
        }
        if (inList) html += "</ul>";
        return html;
    }

    function inline(s) {
        return s
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.+?)\*/g, "<em>$1</em>");
    }

    /* ==============================================================
       DOM HELPERS
       ============================================================== */

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatScroll.scrollTop = chatScroll.scrollHeight;
        });
    }

    function escapeHtml(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    function hideQuickActions() {
        if (quickActs) quickActs.style.display = "none";
    }

    function addUserMessage(text) {
        hideQuickActions();
        const el = document.createElement("div");
        el.className = "message user-message";
        el.innerHTML =
            '<div class="msg-avatar"><span>You</span></div>' +
            '<div class="msg-body"><div class="msg-content"><p>' +
            escapeHtml(text) + '</p></div></div>';
        chatInner.appendChild(el);
        scrollToBottom();
    }

    function addBotMessage(text) {
        const el = document.createElement("div");
        el.className = "message bot-message";
        el.innerHTML =
            '<div class="msg-avatar"><span>VS</span></div>' +
            '<div class="msg-body"><div class="msg-content">' +
            renderMarkdown(text) + '</div></div>';
        chatInner.appendChild(el);
        scrollToBottom();
    }

    function showTyping() {
        const el = document.createElement("div");
        el.className = "message bot-message";
        el.id = "typingMsg";
        el.innerHTML =
            '<div class="msg-avatar"><span>VS</span></div>' +
            '<div class="msg-body"><div class="msg-content typing-dots">' +
            '<span></span><span></span><span></span></div></div>';
        chatInner.appendChild(el);
        scrollToBottom();
    }

    function hideTyping() {
        const el = document.getElementById("typingMsg");
        if (el) el.remove();
    }

    /* ==============================================================
       CHAT NETWORK
       ============================================================== */

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

            if (data.event === "booking_confirmed" && data.confirmation) {
                showEmailConfirmation(data.confirmation);
                showToast("Confirmation email sent to " + data.confirmation.email);
            } else if (data.event === "booking_modified") {
                showToast("Updated confirmation sent to your email");
            } else if (data.event === "booking_cancelled") {
                showToast("Cancellation confirmation sent to your email");
            }
        } catch {
            hideTyping();
            addBotMessage("I apologise, but I am experiencing a temporary issue. Please try again in a moment.");
        } finally {
            sending = false;
            sendBtn.disabled = false;
            inputEl.focus();
        }
    }

    async function resetChat() {
        try { await fetch("/api/reset", { method: "POST" }); } catch {}
        location.reload();
    }

    /* ==============================================================
       VIEW SWITCHING
       ============================================================== */

    function switchView(target) {
        document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
        document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));

        const view = document.getElementById("view" + target.charAt(0).toUpperCase() + target.slice(1));
        const btn = document.querySelector('[data-target="' + target + '"]');
        if (view) view.classList.add("active");
        if (btn) btn.classList.add("active");

        if (target === "chat") inputEl.focus();
    }

    /* ==============================================================
       RESERVATION LOOKUP
       ============================================================== */

    async function lookupReservation(e) {
        e.preventDefault();
        const code = document.getElementById("lookupCode").value.trim();
        const idNum = document.getElementById("lookupId").value.trim();

        if (!code && !idNum) return;

        lookupError.style.display = "none";
        resultCard.style.display = "none";

        const btn = document.getElementById("btnLookup");
        btn.disabled = true;
        btn.textContent = "Searching...";

        try {
            const body = {};
            if (code) body.confirmation_code = code;
            else body.id_number = idNum;

            const res = await fetch("/api/lookup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();

            if (!data.found) {
                lookupError.style.display = "flex";
                return;
            }

            const r = data.reservation;
            document.getElementById("resultCode").textContent = r.confirmation_code;
            document.getElementById("resGuest").textContent = r.guest_name;
            document.getElementById("resRoom").textContent = r.room_type + " (Room " + r.room_number + ")";
            document.getElementById("resCheckIn").textContent = formatDate(r.check_in);
            document.getElementById("resCheckOut").textContent = formatDate(r.check_out);
            document.getElementById("resNights").textContent = r.nights + " night" + (r.nights !== 1 ? "s" : "");
            document.getElementById("resTotal").textContent = "EUR " + Number(r.total_price).toLocaleString("en");
            document.getElementById("resEmail").textContent = "Confirmation sent to " + r.email;

            const badge = document.getElementById("resultStatus");
            const status = r.status || "confirmed";
            badge.innerHTML = '<span class="status-badge ' + status + '">' +
                status.charAt(0).toUpperCase() + status.slice(1) + '</span>';

            resultCard.style.display = "block";
        } catch {
            lookupError.style.display = "flex";
        } finally {
            btn.disabled = false;
            btn.innerHTML =
                '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
                ' Look Up Reservation';
        }
    }

    function formatDate(iso) {
        const d = new Date(iso + "T00:00:00");
        return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
    }

    /* ==============================================================
       EMAIL CONFIRMATION MODAL
       ============================================================== */

    function showEmailConfirmation(conf) {
        document.getElementById("epGreeting").textContent = "Dear " + conf.guest_name + ",";

        const details = document.getElementById("epDetails");
        details.innerHTML =
            item("Confirmation", conf.code) +
            item("Room", conf.room_type + " (Room " + conf.room_number + ")") +
            item("Check-in", formatDate(conf.check_in)) +
            item("Check-out", formatDate(conf.check_out)) +
            item("Duration", conf.nights + " night" + (conf.nights !== 1 ? "s" : "")) +
            item("Total", "EUR " + Number(conf.total_price).toLocaleString("en"));

        emailModal.classList.add("open");
    }

    function item(label, value) {
        return '<div class="ed-item"><span class="ed-label">' + label +
               '</span><span class="ed-value">' + value + '</span></div>';
    }

    function closeModal() {
        emailModal.classList.remove("open");
    }

    /* ==============================================================
       TOAST
       ============================================================== */

    function showToast(message) {
        toastText.textContent = message;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 4000);
    }

    /* ==============================================================
       TEXTAREA AUTO-RESIZE
       ============================================================== */

    function autoResize() {
        inputEl.style.height = "auto";
        inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
    }

    /* ==============================================================
       EVENT BINDINGS
       ============================================================== */

    sendBtn.addEventListener("click", () => sendMessage(inputEl.value));

    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage(inputEl.value);
        }
    });

    inputEl.addEventListener("input", autoResize);
    resetBtn.addEventListener("click", resetChat);

    nav.addEventListener("click", (e) => {
        const btn = e.target.closest(".nav-btn");
        if (btn && btn.dataset.target) switchView(btn.dataset.target);
    });

    quickActs.addEventListener("click", (e) => {
        const btn = e.target.closest(".qa-btn");
        if (btn && btn.dataset.msg) sendMessage(btn.dataset.msg);
    });

    lookupForm.addEventListener("submit", lookupReservation);

    modalClose.addEventListener("click", closeModal);
    emailModal.addEventListener("click", (e) => {
        if (e.target === emailModal) closeModal();
    });

    document.getElementById("btnModifyFromLookup").addEventListener("click", () => {
        switchView("chat");
        sendMessage("I would like to modify my reservation");
    });

    document.getElementById("btnPrintConfirmation").addEventListener("click", () => {
        window.print();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeModal();
    });

    inputEl.focus();
})();
