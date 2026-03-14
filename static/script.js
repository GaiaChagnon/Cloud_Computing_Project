/**
 * Villa Sirene — Concierge Frontend
 *
 * Handles: chat messaging, markdown rendering, view switching,
 * rooms showcase, reservation lookup, email confirmation modal,
 * and toast notifications.
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
    const roomsGrid   = document.getElementById("roomsGrid");

    let sending = false;
    let roomsLoaded = false;

    const ROOM_IMAGES = {
        classic:   "https://images.unsplash.com/photo-1566665797739-1674de7a421a?w=480&h=300&fit=crop&q=80",
        superior:  "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=480&h=300&fit=crop&q=80",
        deluxe:    "https://images.unsplash.com/photo-1602002418082-a4443e081dd1?w=480&h=300&fit=crop&q=80",
        suite:     "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=480&h=300&fit=crop&q=80",
        penthouse: "https://images.unsplash.com/photo-1618773928121-c32242e63f39?w=480&h=300&fit=crop&q=80",
    };

    const ROOM_COLORS = {
        classic: "#c9a84c", superior: "#7a9e7e", deluxe: "#4a7a9e",
        suite: "#7a5a8e", penthouse: "#c47a3a",
    };

    /* ==============================================================
       MARKDOWN-LITE
       ============================================================== */

    function renderMarkdown(text) {
        const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        const lines = esc.split("\n");
        let html = "", inList = false;
        for (const raw of lines) {
            const line = raw.trim();
            if (line.startsWith("- ")) {
                if (!inList) { html += "<ul>"; inList = true; }
                html += "<li>" + inl(line.slice(2)) + "</li>";
                continue;
            }
            if (inList) { html += "</ul>"; inList = false; }
            if (line === "") continue;
            html += "<p>" + inl(line) + "</p>";
        }
        if (inList) html += "</ul>";
        return html;
    }

    function inl(s) {
        return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                .replace(/\*(.+?)\*/g, "<em>$1</em>");
    }

    /* ==============================================================
       DOM HELPERS
       ============================================================== */

    function scrollBottom() {
        requestAnimationFrame(() => { chatScroll.scrollTop = chatScroll.scrollHeight; });
    }

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    function hideQuickActions() { if (quickActs) quickActs.style.display = "none"; }

    function addUserMsg(text) {
        hideQuickActions();
        const el = document.createElement("div");
        el.className = "message user-message";
        el.innerHTML =
            '<div class="msg-avatar"><span>You</span></div>' +
            '<div class="msg-body"><div class="msg-content"><p>' + esc(text) + '</p></div></div>';
        chatInner.appendChild(el);
        scrollBottom();
    }

    function addBotMsg(text) {
        const el = document.createElement("div");
        el.className = "message bot-message";
        el.innerHTML =
            '<div class="msg-avatar"><span>VS</span></div>' +
            '<div class="msg-body"><div class="msg-content">' + renderMarkdown(text) + '</div></div>';
        chatInner.appendChild(el);
        scrollBottom();
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
        scrollBottom();
    }

    function hideTyping() {
        const el = document.getElementById("typingMsg");
        if (el) el.remove();
    }

    /* ==============================================================
       CHAT
       ============================================================== */

    async function sendMessage(text) {
        if (sending || !text.trim()) return;
        sending = true;
        sendBtn.disabled = true;
        switchView("chat");

        addUserMsg(text.trim());
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
            addBotMsg(data.response);

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
            addBotMsg("I apologise, but I am experiencing a temporary issue. Please try again in a moment.");
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

        const id = "view" + target.charAt(0).toUpperCase() + target.slice(1);
        const view = document.getElementById(id);
        const btn = document.querySelector('[data-target="' + target + '"]');
        if (view) view.classList.add("active");
        if (btn) btn.classList.add("active");

        if (target === "chat") inputEl.focus();
        if (target === "rooms" && !roomsLoaded) loadRooms();
    }

    /* ==============================================================
       ROOMS PAGE
       ============================================================== */

    async function loadRooms() {
        try {
            const res = await fetch("/api/rooms");
            const rooms = await res.json();
            roomsGrid.innerHTML = "";
            for (const r of rooms) {
                const img = ROOM_IMAGES[r.type] || "";
                const color = ROOM_COLORS[r.type] || "#c9a84c";
                const card = document.createElement("div");
                card.className = "room-card";
                card.innerHTML =
                    '<div class="room-card-img" style="background-image:url(' + img + ');background-color:' + color + '">' +
                        '<span class="room-card-price">EUR ' + r.price + ' / night</span>' +
                    '</div>' +
                    '<div class="room-card-body">' +
                        '<h3>' + esc(r.label) + '</h3>' +
                        '<p>' + esc(r.description) + '</p>' +
                        '<div class="room-card-meta">' +
                            '<span>Floor ' + r.floors + '</span>' +
                            '<span>' + r.total_rooms + ' room' + (r.total_rooms > 1 ? 's' : '') + '</span>' +
                        '</div>' +
                    '</div>';
                roomsGrid.appendChild(card);
            }
            roomsLoaded = true;
        } catch {
            roomsGrid.innerHTML = '<p style="text-align:center;color:#999;">Unable to load rooms.</p>';
        }
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
            const body = code ? { confirmation_code: code } : { id_number: idNum };
            const res = await fetch("/api/lookup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!data.found) { lookupError.style.display = "flex"; return; }

            const r = data.reservation;
            document.getElementById("resultCode").textContent = r.confirmation_code;
            document.getElementById("resGuest").textContent = r.guest_name;
            document.getElementById("resRoom").textContent = r.room_type + " (Room " + r.room_number + ")";
            document.getElementById("resCheckIn").textContent = fmtDate(r.check_in);
            document.getElementById("resCheckOut").textContent = fmtDate(r.check_out);
            document.getElementById("resNights").textContent = r.nights + " night" + (r.nights !== 1 ? "s" : "");
            document.getElementById("resTotal").textContent = "EUR " + Number(r.total_price).toLocaleString("en");
            document.getElementById("resEmail").textContent = "Confirmation sent to " + r.email;

            const badge = document.getElementById("resultStatus");
            const st = r.status || "confirmed";
            badge.innerHTML = '<span class="status-badge ' + st + '">' + st.charAt(0).toUpperCase() + st.slice(1) + '</span>';
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

    function fmtDate(iso) {
        const d = new Date(iso + "T00:00:00");
        return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
    }

    /* ==============================================================
       EMAIL CONFIRMATION MODAL
       ============================================================== */

    function showEmailConfirmation(conf) {
        document.getElementById("epGreeting").textContent = "Dear " + conf.guest_name + ",";
        const det = document.getElementById("epDetails");
        det.innerHTML =
            edItem("Confirmation", conf.code) +
            edItem("Room", conf.room_type + " (Room " + conf.room_number + ")") +
            edItem("Check-in", fmtDate(conf.check_in)) +
            edItem("Check-out", fmtDate(conf.check_out)) +
            edItem("Duration", conf.nights + " night" + (conf.nights !== 1 ? "s" : "")) +
            edItem("Total", "EUR " + Number(conf.total_price).toLocaleString("en"));
        emailModal.classList.add("open");
    }

    function edItem(l, v) {
        return '<div class="ed-item"><span class="ed-label">' + l + '</span><span class="ed-value">' + v + '</span></div>';
    }

    function closeModal() { emailModal.classList.remove("open"); }

    /* ==============================================================
       TOAST
       ============================================================== */

    function showToast(msg) {
        toastText.textContent = msg;
        toast.classList.add("show");
        setTimeout(() => toast.classList.remove("show"), 4500);
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
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(inputEl.value); }
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
    emailModal.addEventListener("click", (e) => { if (e.target === emailModal) closeModal(); });

    document.getElementById("btnModifyFromLookup").addEventListener("click", () => {
        switchView("chat");
        sendMessage("I would like to modify my reservation");
    });

    document.getElementById("btnPrintConfirmation").addEventListener("click", () => window.print());

    document.getElementById("btnBookFromRooms").addEventListener("click", () => {
        switchView("chat");
        sendMessage("I would like to book a room");
    });

    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

    inputEl.focus();
})();
