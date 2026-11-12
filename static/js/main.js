// Small progressive-enhancement script. All data & business logic now lives on the server (app.py).
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const csrf = document.body.dataset.csrf;

  // ---- toasts: close button + auto dismiss
  function wireToast(t) {
    const x = $(".toast-close", t);
    if (x) x.addEventListener("click", () => t.remove());
    setTimeout(() => {
      if (!t.parentNode) return;
      t.style.cssText += ";opacity:0;transform:translateX(50px);transition:all .5s ease";
      setTimeout(() => t.remove(), 500);
    }, 4000);
  }
  $$("#toast-container .toast").forEach(wireToast);
  function toast(message, isError) {
    const c = $("#toast-container");
    const t = document.createElement("div");
    t.className = "toast" + (isError ? " toast-error" : "");
    t.innerHTML = '<div style="display:flex;align-items:center;gap:.6rem;"><span style="font-size:.85rem;font-weight:500;"></span></div><span class="toast-close" style="font-weight:700;margin-left:1rem;">&times;</span>';
    t.querySelector("span").textContent = message; // textContent: never inject HTML
    c.appendChild(t);
    wireToast(t);
  }

  // ---- mobile drawer
  const burger = $("#mobile-hamburger-btn"), drawer = $("#mobile-drawer-links");
  if (burger && drawer) burger.addEventListener("click", () => {
    drawer.style.display = drawer.style.display === "none" ? "block" : "none";
  });

  // ---- confirm dialogs on destructive forms
  $$("form[data-confirm]").forEach(f => f.addEventListener("submit", e => {
    if (!confirm(f.dataset.confirm)) e.preventDefault();
  }));

  // ---- listing filters: auto-submit
  $$("[data-autosubmit]").forEach(el => el.addEventListener("change", () => el.form && el.form.submit()));
  const priceSlider = $("#filter-price"), priceLabel = $("#price-val-indicator");
  if (priceSlider && priceLabel) priceSlider.addEventListener("input", () => priceLabel.textContent = "₹" + priceSlider.value);

  // ---- FAQ accordion
  $$(".faq-question").forEach(q => q.addEventListener("click", () => q.closest(".faq-item").classList.toggle("active")));

  // ---- trek detail page
  $$(".itinerary-header").forEach(h => h.addEventListener("click", () =>
    document.getElementById("itinerary-content-" + h.dataset.index).classList.toggle("active")));
  $$(".carry-checklist-item input").forEach(c => c.addEventListener("change", () =>
    document.getElementById("carry-item-" + c.dataset.idx).classList.toggle("checked", c.checked)));

  const dateCards = $$(".sidebar-date-option");
  if (dateCards.length || $("#sidebar-book-btn")) {
    let selected = ($(".sidebar-date-option.selected") || {}).dataset?.dateId || "";
    dateCards.forEach(card => {
      if (card.classList.contains("disabled")) return;
      card.addEventListener("click", () => {
        dateCards.forEach(c => c.classList.remove("selected"));
        card.classList.add("selected");
        selected = card.dataset.dateId;
      });
    });
    const go = () => {
      const btn = $("#sidebar-book-btn");
      if (!selected) return toast("Please choose an upcoming trek date first.", true);
      const qty = parseInt($("#booking-people-qty").value, 10) || 1;
      const card = dateCards.find(c => c.dataset.dateId === selected);
      if (card && parseInt(card.dataset.seats, 10) < qty)
        return toast("Insufficient seats. Selected date only has " + card.dataset.seats + " remaining seats.", true);
      location.href = btn.dataset.bookingUrl + "?date=" + encodeURIComponent(selected) + "&qty=" + qty;
    };
    ["#sidebar-book-btn", "#sticky-mob-book-btn"].forEach(s => { const b = $(s); if (b) b.addEventListener("click", go); });
  }

  // ---- booking wizard
  const wiz = $("#wizard");
  if (wiz) {
    const form = $("#booking-form"), next = $("#wizard-next-btn"), prev = $("#wizard-prev-btn");
    const panels = [1, 2, 3].map(i => $("#panel-step-" + i)), nodes = [1, 2, 3].map(i => $("#node-step-" + i));
    let step = 1;

    function render() {
      panels.forEach((p, i) => p.classList.toggle("active", i === step - 1));
      nodes.forEach((n, i) => n.className = "wizard-step-node" + (i < step - 1 ? " completed" : i === step - 1 ? " active" : ""));
      prev.style.visibility = step === 1 ? "hidden" : "visible";
      next.textContent = ["Continue", "Accept & Proceed", "Complete Booking (Pay)"][step - 1];
      wiz.scrollIntoView();
    }

    // coupon: the server validates the code and returns the amounts (code isn't hard-coded here)
    $("#apply-coupon-btn").addEventListener("click", async () => {
      const code = $("#coupon-code-input").value.trim();
      const msg = $("#coupon-status-msg");
      try {
        const r = await fetch(wiz.dataset.couponUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({ trek_id: wiz.dataset.trekId, qty: +wiz.dataset.qty, code })
        });
        const d = await r.json();
        if (d.ok) {
          $("#coupon-hidden").value = d.coupon;
          $("#summary-coupon-discount-val").textContent = "-₹" + d.discount;
          $("#summary-coupon-discount-row").style.display = "flex";
          $("#summary-tax-amount").textContent = "₹" + d.tax;
          $("#summary-grand-total").textContent = "₹" + d.total;
          $("#pay-upi-amt-label").textContent = "₹" + d.total;
          msg.textContent = d.message; msg.style.color = "#2e7d32";
          toast("Promo Code Applied! 10% Discount.");
        } else {
          msg.textContent = d.message; msg.style.color = "#d90429";
          toast("Invalid Promo Code.", true);
        }
      } catch (e) { toast("Could not check the coupon. Try again.", true); }
    });

    $$(".pay-tab").forEach(tab => tab.addEventListener("click", () => {
      $$(".pay-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      ["upi", "card", "net"].forEach(k => $("#pay-content-" + k).style.display = k === tab.dataset.type ? "block" : "none");
    }));

    next.addEventListener("click", () => {
      if (step === 1) {
        const fields = $$("#panel-step-1 input, #panel-step-1 select, #panel-step-1 textarea");
        const bad = fields.find(f => !f.checkValidity());
        if (bad) { bad.reportValidity(); return toast("Please fill in all required fields accurately.", true); }
        $("#summary-attendees-names").textContent = $$(".part-name").map(i => i.value.trim()).join(", ");
        step = 2;
      } else if (step === 2) {
        if (!$("#rules-checkbox-agree").checked)
          return toast("You must accept the trekking rules & emergency disclaimer to proceed.", true);
        step = 3;
      } else {
        next.disabled = true;      // avoid double-submits
        return form.submit();
      }
      render();
    });
    prev.addEventListener("click", () => { if (step > 1) { step--; render(); } });
  }
})();
