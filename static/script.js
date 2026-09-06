/* ============================================================
   ShopLinq — shared script
   All page behavior lives here; each module activates itself only
   when its elements exist on the current page.
   ============================================================ */
(function () {
  "use strict";

  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };

  function money(n) { return "$" + Number(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function escapeHTML(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------- toast ---------- */
  var toastTimer = null;
  function toast(msg) {
    var el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 2600);
  }

  function updateBadge(count) {
    var badge = $("#cart-badge");
    if (badge && typeof count === "number") {
      badge.textContent = count;
      badge.classList.remove("pop");
      void badge.offsetWidth; // restart the animation
      badge.classList.add("pop");
    }
  }

  function postJSON(url, data) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
        "X-CSRF-Token": csrfToken()
      },
      body: JSON.stringify(data || {})
    }).then(function (res) { return res.json().then(function (j) { j._status = res.status; return j; }); });
  }

  function setLoading(btn) {
    if (!btn) return;
    btn.classList.add("loading");
    btn.disabled = true;
  }
  function clearLoading(btn) {
    if (!btn) return;
    btn.classList.remove("loading");
    btn.disabled = false;
  }

  /* ---------- cart summary DOM updater (cart page) ---------- */
  function applySummary(data) {
    if (!$("#sum-subtotal")) return;
    $("#sum-subtotal").textContent = money(data.subtotal);
    var promoRow = $("#sum-promo-row");
    if (promoRow) {
      promoRow.hidden = !(data.discount > 0);
      var codeEl = $("#sum-promo-code");
      if (codeEl) codeEl.textContent = data.promo ? "Promo (" + data.promo + ")" : "Promo";
      var valEl = $("#sum-discount");
      if (valEl) valEl.textContent = "-" + money(data.discount || 0);
    }
    $("#sum-tax").textContent = money(data.tax);
    var shipEl = $("#sum-shipping");
    if (shipEl) shipEl.textContent = (data.shipping_fee === 0 ? "FREE" : money(data.shipping_fee));
    $("#sum-total").textContent = money(data.total);
    updateBadge(data.count);
  }

  /* ---------- flash dismiss ---------- */
  $$(".flash-close").forEach(function (btn) {
    btn.addEventListener("click", function () { btn.parentElement.remove(); });
  });
  setTimeout(function () {
    $$(".flash").forEach(function (f) { f.remove(); });
  }, 9000);

  /* ---------- dropdowns (account menu, category mega-menu) ---------- */
  (function initDropdowns() {
    $$(".dropdown").forEach(function (dd) {
      var toggle = $(".dropdown-toggle", dd), menu = $(".dropdown-menu", dd);
      if (!toggle || !menu) return;
      toggle.setAttribute("aria-expanded", "false");
      toggle.addEventListener("click", function (e) {
        e.stopPropagation();
        menu.hidden = !menu.hidden;
        toggle.setAttribute("aria-expanded", String(!menu.hidden));
      });
      document.addEventListener("click", function () {
        menu.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
      });
    });
  })();

  /* ---------- search autocomplete ---------- */
  (function initSuggest() {
    var input = $("#search-input"), box = $("#search-suggest");
    if (!input || !box) return;
    var timer = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) { box.hidden = true; return; }
      timer = setTimeout(function () {
        fetch("/api/search/suggest?q=" + encodeURIComponent(q))
          .then(function (r) { return r.json(); })
          .then(function (data) {
            box.innerHTML = "";
            if (!data.results.length) {
              box.innerHTML = '<div class="search-empty">No matches — press Enter to search everything</div>';
            } else {
              data.results.forEach(function (r) {
                var a = document.createElement("a");
                a.href = r.url;
                a.innerHTML = (r.image ? '<img src="' + escapeHTML(r.image) + '" alt="">' : "") +
                  '<span class="s-name">' + escapeHTML(r.name) + (r.brand ? ' <em class="muted">' + escapeHTML(r.brand) + "</em>" : "") + "</span>" +
                  '<span class="s-price">' + money(r.price) + "</span>";
                box.appendChild(a);
              });
            }
            box.hidden = false;
          });
      }, 180);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") box.hidden = true;
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".search")) box.hidden = true;
    });
  })();

  /* ---------- hero carousel ---------- */
  (function initCarousel() {
    var carousel = $("#hero-carousel");
    if (!carousel) return;
    var track = $(".hero-track", carousel);
    var slides = $$(".hero-slide", carousel);
    if (!track || slides.length === 0) return;
    var dots = $("#hero-dots");
    var index = 0, auto = null;

    slides.forEach(function (_, i) {
      var dot = document.createElement("button");
      dot.className = "hero-dot" + (i === 0 ? " active" : "");
      dot.setAttribute("aria-label", "Go to slide " + (i + 1));
      dot.addEventListener("click", function () { go(i); restart(); });
      if (dots) dots.appendChild(dot);
    });

    function go(i) {
      index = (i + slides.length) % slides.length;
      track.style.transform = "translateX(-" + index * 100 + "%)";
      $$(".hero-dot", carousel).forEach(function (d, di) {
        d.classList.toggle("active", di === index);
      });
      slides.forEach(function (s, si) {
        s.classList.toggle("hero-slide-active", si === index);
      });
    }
    function restart() { clearInterval(auto); auto = setInterval(function () { go(index + 1); }, 5500); }

    var prev = $(".hero-prev", carousel), next = $(".hero-next", carousel);
    if (prev) prev.addEventListener("click", function () { go(index - 1); restart(); });
    if (next) next.addEventListener("click", function () { go(index + 1); restart(); });
    restart();
  })();

  /* ---------- deals countdown ---------- */
  (function initCountdown() {
    var el = $("#deal-countdown");
    if (!el) return;
    function tick() {
      var now = new Date();
      var end = new Date(now); end.setHours(23, 59, 59, 999);
      var diff = Math.max(0, end - now);
      var h = Math.floor(diff / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      var s = Math.floor((diff % 60000) / 1000);
      el.textContent = ("0" + h).slice(-2) + ":" + ("0" + m).slice(-2) + ":" + ("0" + s).slice(-2);
    }
    tick(); setInterval(tick, 1000);
  })();

  /* ---------- add to cart (everywhere) ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-add-to-cart");
    if (!btn) return;
    e.preventDefault();
    var qtyInput = $("#qty-input");
    var qty = qtyInput ? parseInt(qtyInput.value, 10) || 1 : 1;
    var productRow = btn.closest(".cart-row");
    setLoading(btn);
    postJSON("/api/cart/add", { product_id: btn.dataset.productId, quantity: qty })
      .then(function (data) {
        clearLoading(btn);
        if (productRow) { location.reload(); return; }
        if (data.ok === false) { toast(data.message || "Could not add to cart."); return; }
        updateBadge(data.count);
        toast(data.message || "Added to your cart.");
      })
      .catch(function () { clearLoading(btn); toast("Network error — please try again."); });
  });

  /* ---------- buy now (product page) ---------- */
  (function initBuyNow() {
    var btn = $("#buy-now");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var qtyInput = $("#qty-input");
      var qty = qtyInput ? parseInt(qtyInput.value, 10) || 1 : 1;
      setLoading(btn);
      postJSON("/api/cart/add", { product_id: btn.dataset.productId, quantity: qty })
        .then(function (data) {
          if (data.ok === false) { clearLoading(btn); toast(data.message || "Could not add to cart."); return; }
          updateBadge(data.count);
          window.location.href = "/checkout";
        })
        .catch(function () { clearLoading(btn); toast("Network error — please try again."); });
    });
  })();

  /* ---------- wishlist toggle (everywhere) ---------- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-wishlist");
    if (!btn) return;
    e.preventDefault();
    postJSON("/api/wishlist/toggle", { product_id: btn.dataset.productId })
      .then(function (data) {
        if (data.ok === false && data.login_required) {
          toast("Please sign in to use your wishlist.");
          return;
        }
        if (data.ok === false) { toast(data.message || "Something went wrong."); return; }
        btn.classList.toggle("active", !!data.added);
        toast(data.message);
      })
      .catch(function () { toast("Network error — please try again."); });
  });

  /* ---------- product page: qty stepper + gallery + notify ---------- */
  (function initProductPage() {
    var minus = $("#qty-minus"), plus = $("#qty-plus"), qtyInput = $("#qty-input");
    if (minus && qtyInput) minus.addEventListener("click", function () {
      qtyInput.value = Math.max(1, (parseInt(qtyInput.value, 10) || 1) - 1);
    });
    if (plus && qtyInput) plus.addEventListener("click", function () {
      var max = parseInt(qtyInput.max, 10) || 99;
      qtyInput.value = Math.min(max, (parseInt(qtyInput.value, 10) || 1) + 1);
    });

    $$(".gallery-thumb").forEach(function (thumb) {
      thumb.addEventListener("click", function () {
        var main = $("#gallery-main-img");
        if (main) main.src = thumb.dataset.src;
        $$(".gallery-thumb").forEach(function (t) { t.classList.remove("active"); });
        thumb.classList.add("active");
      });
    });

    var notifyForm = $("#notify-form");
    if (notifyForm) notifyForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var btn = $("button", notifyForm);
      var email = $("#notify-email").value;
      var pid = $("#buy-now") ? $("#buy-now").dataset.productId : null;
      if (!pid) {
        var buyBox = notifyForm.closest(".buy-box");
        pid = buyBox ? buyBox.dataset.productId : null;
      }
      setLoading(btn);
      postJSON("/api/notify", { product_id: pid, email: email })
        .then(function (data) {
          clearLoading(btn);
          var hint = $("#notify-hint");
          if (hint) { hint.textContent = data.message || "Done."; hint.hidden = false; }
          if (data.ok) notifyForm.reset();
        })
        .catch(function () { clearLoading(btn); toast("Network error — please try again."); });
    });
  })();

  /* ---------- cart page ---------- */
  (function initCartPage() {
    if (document.body.dataset.page !== "cart") return;

    function cartAction(url, payload, btn) {
      setLoading(btn);
      return postJSON(url, payload)
        .then(function (data) {
          clearLoading(btn);
          if (data.ok === false) { toast(data.message || "Could not update cart."); return; }
          applySummary(data);
          if (data.count === 0) { location.reload(); return; }
        })
        .catch(function () { clearLoading(btn); toast("Network error — please try again."); });
    }

    $$(".js-qty-minus").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var input = $('.js-qty-input[data-product-id="' + btn.dataset.productId + '"]');
        var next = (parseInt(input.value, 10) || 1) - 1;
        input.value = next;
        if (next <= 0) {
          cartAction("/api/cart/remove", { product_id: btn.dataset.productId }, btn)
            .then(function () { removeRow(btn.dataset.productId); });
        } else {
          cartAction("/api/cart/update", { product_id: btn.dataset.productId, quantity: next }, btn)
            .then(function () { updateRowTotal(btn.dataset.productId, next); });
        }
      });
    });

    $$(".js-qty-plus").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var input = $('.js-qty-input[data-product-id="' + btn.dataset.productId + '"]');
        var max = parseInt(input.max, 10) || 99;
        var next = Math.min(max, (parseInt(input.value, 10) || 0) + 1);
        input.value = next;
        cartAction("/api/cart/update", { product_id: btn.dataset.productId, quantity: next }, btn)
          .then(function () { updateRowTotal(btn.dataset.productId, next); });
      });
    });

    $$(".js-qty-input").forEach(function (input) {
      input.addEventListener("change", function () {
        var next = parseInt(input.value, 10);
        if (isNaN(next) || next < 0) { input.value = 1; next = 1; }
        var payload = { product_id: input.dataset.productId, quantity: next };
        if (next === 0) {
          cartAction("/api/cart/remove", payload, null).then(function () { removeRow(input.dataset.productId); });
        } else {
          cartAction("/api/cart/update", payload, null).then(function () { updateRowTotal(input.dataset.productId, next); });
        }
      });
    });

    function removeRow(productId) {
      var row = $('.cart-row[data-product-id="' + productId + '"]');
      if (row) row.remove();
    }
    function updateRowTotal(productId, qty) {
      var row = $('.cart-row[data-product-id="' + productId + '"]');
      if (!row) return;
      var unit = parseFloat(($(".price", row) || {}).dataset ? $(".price", row).dataset.unitPrice : 0);
      var cell = $("#row-total-" + productId);
      if (cell && unit) cell.textContent = money(unit * qty);
    }

    $$(".js-remove").forEach(function (btn) {
      btn.addEventListener("click", function () {
        cartAction("/api/cart/remove", { product_id: btn.dataset.productId }, btn)
          .then(function () { removeRow(btn.dataset.productId); });
      });
    });

    $$(".js-save-later").forEach(function (btn) {
      btn.addEventListener("click", function () {
        setLoading(btn);
        postJSON("/api/cart/save-later", { product_id: btn.dataset.productId })
          .then(function (data) {
            clearLoading(btn);
            if (data.ok === false) {
              toast(data.message || "Could not save this item.");
              return;
            }
            removeRow(btn.dataset.productId);
            applySummary(data);
            if (data.count === 0) { location.reload(); return; }
            toast(data.message || "Saved to your wishlist.");
          })
          .catch(function () { clearLoading(btn); toast("Network error."); });
      });
    });

    var promoForm = $("#promo-form");
    if (promoForm) promoForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var code = $("#promo-input").value.trim();
      var btn = $("button", promoForm);
      setLoading(btn);
      postJSON("/api/promo", { code: code })
        .then(function (data) {
          clearLoading(btn);
          var msg = $("#promo-msg");
          if (msg) { msg.textContent = data.message || ""; msg.style.color = data.ok === false ? "#c23b3b" : "#147d3f"; }
          if (data.ok !== false) applySummary(data);
        })
        .catch(function () { clearLoading(btn); toast("Network error."); });
    });
  })();

  /* ---------- checkout wizard ---------- */
  (function initCheckout() {
    if (document.body.dataset.page !== "checkout") return;
    var form = $("#checkout-form");
    if (!form) return;

    var panels = $$(".checkout-panel");
    var steps = $$("#checkout-steps li");
    var nextBtn = $("#checkout-next"), prevBtn = $("#checkout-prev"),
        placeBtn = $("#place-order"), placeBtn2 = $("#place-order-2"),
        loader = $("#checkout-loader");
    var current = 1;
    var TOTAL = panels.length;

    var addressRadios = $$('input[name="address_choice"]');
    var newFields = $("#new-address-fields");
    addressRadios.forEach(function (r) {
      r.addEventListener("change", function () {
        if (newFields) newFields.hidden = r.value !== "new" || !r.checked;
      });
    });

    var methodBlocks = {
      upi: $("#upi-fields"), card: $("#card-fields"),
      netbanking: $("#netbanking-fields"), wallet: $("#wallet-fields"),
    };
    $$('input[name="payment"]').forEach(function (r) {
      r.addEventListener("change", function () {
        Object.keys(methodBlocks).forEach(function (m) {
          var block = methodBlocks[m];
          if (block) block.hidden = m !== r.value || block.dataset.native === "1";
        });
      });
    });

    function money2(n) { return "$" + Number(n).toFixed(2); }
    function updateCheckoutTotals() {
      var del = $('input[name="delivery"]:checked');
      var fee = del ? Number(del.dataset.fee || 0) : 0;
      var shipEl = $("#sum-shipping");
      if (shipEl) shipEl.textContent = fee === 0 ? "FREE" : money2(fee);
      var totEl = $("#sum-total");
      if (totEl) {
        var base = Number(form.dataset.subtotal || 0)
                 - Number(form.dataset.discount || 0)
                 + Number(form.dataset.tax || 0);
        totEl.textContent = money2(base + fee);
      }
    }
    $$('input[name="delivery"]').forEach(function (r) {
      r.addEventListener("change", updateCheckoutTotals);
    });
    updateCheckoutTotals();

    function show(n) {
      current = n;
      panels.forEach(function (p) { p.hidden = Number(p.dataset.panel) !== n; });
      steps.forEach(function (s) { s.classList.toggle("active", Number(s.dataset.step) === n); });
      nextBtn.hidden = n >= TOTAL;
      prevBtn.hidden = n <= 1;
      placeBtn.hidden = n !== TOTAL;
      if (placeBtn2) placeBtn2.hidden = n !== TOTAL;
      if (n === TOTAL) fillReview();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function fillReview() {
      var addrEl = $("#review-address");
      if (addrEl) {
        var choice = ($('input[name="address_choice"]:checked') || {}).value;
        if (choice === "new") {
          var parts = [
            ($('input[name="full_name"]') || {}).value,
            ($('input[name="line1"]') || {}).value,
            ($('input[name="line2"]') || {}).value,
            (($('input[name="city"]') || {}).value + ", " + ($('input[name="state"]') || {}).value + " " + ($('input[name="postal_code"]') || {}).value)
          ].filter(Boolean);
          addrEl.textContent = parts.join(" — ") || "New address (please fill in the fields)";
        } else {
          var row = choice.closest ? null : null;
          var label = $('input[name="address_choice"]:checked');
          if (label) {
            var copy = label.parentElement.querySelector(".choice-copy");
            if (copy) addrEl.textContent = copy.innerText.replace(/\s+/g, " ").trim();
          }
        }
      }
      var delEl = $("#review-delivery");
      if (delEl) {
        var del = $('input[name="delivery"]:checked');
        delEl.textContent = del && del.dataset.desc ? del.dataset.desc : "Standard delivery (5 business days)";
      }
      var payEl = $("#review-payment");
      if (payEl) {
        var pay = ($('input[name="payment"]:checked') || {}).value;
        var sel;
        if (pay === "cod") payEl.textContent = "Cash on delivery";
        else if (pay === "upi") payEl.textContent = "UPI" + (((sel = $('input[name="upi_vpa"]')) && sel.value.trim()) ? " (" + sel.value.trim() + ")" : "");
        else if (pay === "netbanking") payEl.textContent = "Netbanking" + (((sel = $('select[name="netbanking_bank"]')) && sel.value) ? " — " + sel.value : "");
        else if (pay === "wallet") payEl.textContent = "Wallet" + (((sel = $('select[name="wallet_choice"]')) && sel.value) ? " — " + sel.value : "");
        else payEl.textContent = "Card";
      }
    }

    function methodHidden(m) {
      var block = methodBlocks[m];
      return !block || block.hidden || block.dataset.native === "1";
    }

    var errEl = $("#checkout-error");
    function fail(msg) {
      if (errEl) { errEl.textContent = msg; errEl.hidden = false; }
      return false;
    }
    function clearError() { if (errEl) errEl.hidden = true; }

    function filled(name) {
      var el = $('input[name="' + name + '"]');
      return !!el && el.value.trim() !== "";
    }

    function validatePanel(n) {
      if (n === 1) {
        var choice = ($('input[name="address_choice"]:checked') || {}).value;
        if (choice === "new") {
          var need = ["full_name", "line1", "city", "state", "postal_code", "country"];
          for (var i = 0; i < need.length; i++) {
            if (!filled(need[i]))
              return fail("Please complete your shipping address before continuing.");
          }
        }
      }
      if (n === 3) {
        var pay = ($('input[name="payment"]:checked') || {}).value;
        var upiBlock = $("#upi-fields");
        if (pay === "upi" && (!upiBlock || upiBlock.dataset.native !== "1")) {
          var vpa = $('input[name="upi_vpa"]');
          var v = vpa && vpa.value.trim() || "";
          if (!/^[\w.\-]{2,}@[a-zA-Z]{2,}$/.test(v))
            return fail("Please enter a valid UPI ID, e.g. name@okhdfcbank.");
        }
        if (pay === "card" && !methodHidden("card")) {
          var need = ["card_name", "card_number", "exp_month", "exp_year", "cvc"];
          for (var j = 0; j < need.length; j++) {
            if (!filled(need[j]))
              return fail("Please fill in all card details, or choose another payment method.");
          }
        }
        if (pay === "netbanking" && !methodHidden("netbanking")) {
          var bank = $('select[name="netbanking_bank"]');
          if (!bank || !bank.value) return fail("Please choose your bank for netbanking.");
        }
        if (pay === "wallet" && !methodHidden("wallet")) {
          var w = $('select[name="wallet_choice"]');
          if (!w || !w.value) return fail("Please choose a wallet.");
        }
      }
      clearError();
      return true;
    }

    if (nextBtn) nextBtn.addEventListener("click", function () {
      if (current < TOTAL && validatePanel(current)) show(current + 1);
    });
    if (prevBtn) prevBtn.addEventListener("click", function () { if (current > 1) show(current - 1); });
    steps.forEach(function (s) {
      s.addEventListener("click", function () {
        var n = Number(s.dataset.step);
        if (n <= current) show(n);
      });
    });
    if (placeBtn2) placeBtn2.addEventListener("click", function () { form.submit(); });

    form.addEventListener("submit", function (e) {
      if (!validatePanel(1) || !validatePanel(3)) { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
      if (!placeBtn.hidden) {
        placeBtn.textContent = "Placing your order…";
        setLoading(placeBtn);
      }
      if (loader) loader.hidden = false;
      if (placeBtn2) { setLoading(placeBtn2); }
    });

    show(1);
  })();

  /* ---------- image fade-in (shimmer -> reveal) ---------- */
  (function initImageFade() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    function mark(img) { img.classList.add("is-loaded"); img.removeAttribute("data-fade"); }
    document.querySelectorAll("img").forEach(function (img) {
      if (img.complete && img.naturalWidth > 0) { mark(img); return; }
      img.setAttribute("data-fade", "");
      img.addEventListener("load", function () { mark(img); });
      img.addEventListener("error", function () { img.classList.add("is-loaded"); img.removeAttribute("data-fade"); });
    });
  })();

  /* ---------- scroll-to-top button ---------- */
  (function initToTop() {
    var btn = document.createElement("button");
    btn.className = "to-top";
    btn.setAttribute("aria-label", "Back to top");
    btn.innerHTML = "&uarr;";
    document.body.appendChild(btn);
    var onScroll = function () {
      btn.classList.toggle("visible", window.scrollY > 400);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    btn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  })();

  /* ---------- listing filters auto-submit ---------- */
  (function initFilters() {
    $$(".js-filter-control").forEach(function (el) {
      el.addEventListener("change", function () {
        var f = el.closest("form");
        if (f) f.submit();
      });
    });
  })();
})();

  /* ---------- product page: interactive star picker ---------- */
  (function initStarPicker() {
    var picker = $("#star-picker");
    if (!picker) return;
    var labels = Array.prototype.slice.call(picker.querySelectorAll("label"));
    var radios = Array.prototype.slice.call(picker.querySelectorAll("input"));
    function paint(n) {
      labels.forEach(function (l, i) { l.classList.toggle("on", i < n); });
    }
    radios.forEach(function (r) {
      r.addEventListener("change", function () { paint(Number(r.value)); });
    });
    labels.forEach(function (l, i) {
      l.addEventListener("mouseenter", function () { paint(i + 1); });
    });
    picker.addEventListener("mouseleave", function () {
      var checked = $('input[name="rating"]:checked');
      paint(Number(checked && checked.value) || 0);
    });
    var checked = $('input[name="rating"]:checked');
    paint(Number(checked && checked.value) || 0);
  })();
