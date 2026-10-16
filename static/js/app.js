/* CoreCloud interactive UI layer.
   Progressive enhancement: without JS the server-rendered links/forms keep working.
   With JS, elements marked with data-ajax are handled in-place. */
(function () {
    "use strict";

    var App = {};

    /* ------------------------------ helpers ------------------------------ */

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : "";
    }

    function iconFor(type) {
        switch (type) {
            case "success": return "fa-circle-check";
            case "danger": return "fa-circle-exclamation";
            case "warning": return "fa-triangle-exclamation";
            case "info": return "fa-circle-info";
            default: return "fa-circle-info";
        }
    }

    function normalizeType(t) {
        if (t === "error") return "danger";
        if (t === "primary") return "info";
        return t || "info";
    }

    /* ------------------------------ toasts ------------------------------- */

    function container() {
        var c = document.querySelector(".app-toast-container");
        if (!c) {
            c = document.createElement("div");
            c.className = "app-toast-container toast-container position-fixed top-0 end-0 p-3";
            document.body.appendChild(c);
        }
        return c;
    }

    App.toast = function (message, type, delay) {
        if (!message) return;
        type = normalizeType(type);
        var wrap = document.createElement("div");
        wrap.className = "toast app-toast toast-" + type;
        wrap.setAttribute("role", "alert");
        wrap.setAttribute("aria-live", "assertive");
        wrap.setAttribute("aria-atomic", "true");
        wrap.innerHTML =
            '<div class="toast-body">' +
            '<i class="fas ' + iconFor(type) + '"></i>' +
            "<span>" + message + "</span>" +
            '<button type="button" class="btn-close ms-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
            "</div>";
        container().appendChild(wrap);

        if (window.bootstrap && bootstrap.Toast) {
            var instance = new bootstrap.Toast(wrap, { delay: delay || 4000 });
            instance.show();
            wrap.addEventListener("hidden.bs.toast", function () { wrap.remove(); });
        } else {
            setTimeout(function () { wrap.remove(); }, delay || 4000);
        }
        return wrap;
    };

    /* --------------------------- confirm modal --------------------------- */

    function confirmModal() {
        var el = document.getElementById("ccConfirmModal");
        if (el) return el;
        el = document.createElement("div");
        el.className = "modal fade";
        el.id = "ccConfirmModal";
        el.tabIndex = -1;
        el.setAttribute("aria-hidden", "true");
        el.innerHTML =
            '<div class="modal-dialog modal-dialog-centered">' +
            '<div class="modal-content">' +
            '<div class="modal-header">' +
            '<h5 class="modal-title" id="ccConfirmTitle">Please confirm</h5>' +
            '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>' +
            "</div>" +
            '<div class="modal-body" id="ccConfirmText"></div>' +
            '<div class="modal-footer">' +
            '<button type="button" class="btn btn-secondary" data-bs-dismiss="modal" id="ccConfirmCancel">Cancel</button>' +
            '<button type="button" class="btn btn-primary" id="ccConfirmOk">Confirm</button>' +
            "</div>" +
            "</div></div>";
        document.body.appendChild(el);
        return el;
    }

    App.confirm = function (opts) {
        opts = opts || {};
        return new Promise(function (resolve) {
            var el = confirmModal();
            el.querySelector("#ccConfirmTitle").textContent = opts.title || "Please confirm";
            el.querySelector("#ccConfirmText").innerHTML = opts.text || "Are you sure?";
            var ok = el.querySelector("#ccConfirmOk");
            ok.textContent = opts.okText || "Confirm";
            ok.className = "btn " + (opts.danger ? "btn-danger" : "btn-primary");

            if (!window.bootstrap || !bootstrap.Modal) {
                resolve(window.confirm(opts.text || "Are you sure?"));
                return;
            }

            var modal = bootstrap.Modal.getOrCreateInstance(el);
            var settled = false;
            function done(value) {
                if (settled) return;
                settled = true;
                resolve(value);
                ok.removeEventListener("click", onOk);
                el.removeEventListener("hidden.bs.modal", onHidden);
            }
            function onOk() { modal.hide(); done(true); }
            function onHidden() { done(false); }
            ok.addEventListener("click", onOk);
            el.addEventListener("hidden.bs.modal", onHidden);
            modal.show();
        });
    };

    /* ----------------------------- busy state ---------------------------- */

    App.busy = function (el, on) {
        if (!el) return;
        if (on) {
            el.classList.add("is-busy");
            el.setAttribute("aria-busy", "true");
            if (el.tagName === "BUTTON" || el.tagName === "A") {
                if (!el.dataset.ccOriginal) el.dataset.ccOriginal = el.innerHTML;
                el.insertAdjacentHTML("afterbegin", '<span class="cc-spinner"></span>');
            } else {
                if (!el.dataset.ccOriginal) el.dataset.ccOriginal = el.innerHTML;
                el.innerHTML = '<span class="cc-spinner"></span> Loading…';
            }
        } else {
            el.classList.remove("is-busy");
            el.removeAttribute("aria-busy");
            if (el.dataset.ccOriginal !== undefined) {
                el.innerHTML = el.dataset.ccOriginal;
                delete el.dataset.ccOriginal;
            }
        }
    };

    App.setLoading = function (target, on, label) {
        var el = typeof target === "string" ? document.querySelector(target) : target;
        if (!el) return;
        if (on) {
            if (!el.dataset.ccOriginal) el.dataset.ccOriginal = el.innerHTML;
            el.innerHTML = '<div class="cc-chart-loading"><span class="cc-spinner ' +
                'text-primary"></span> ' + (label || "Loading…") + "</div>";
        } else if (el.dataset.ccOriginal !== undefined) {
            el.innerHTML = el.dataset.ccOriginal;
            delete el.dataset.ccOriginal;
        }
    };

    /* ----------------------------- fetch api ---------------------------- */

    App.request = function (url, options) {
        options = options || {};
        var method = (options.method || "POST").toUpperCase();
        var init = {
            method: method,
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfToken() }
        };
        if (method !== "GET" && options.data) {
            var params = new URLSearchParams();
            Object.keys(options.data).forEach(function (k) { params.append(k, options.data[k]); });
            init.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8";
            init.body = params.toString();
        }
        return fetch(url, init).then(function (resp) {
            var ct = resp.headers.get("content-type") || "";
            if (ct.indexOf("application/json") === -1) {
                if (!resp.ok) throw new Error("Request failed (" + resp.status + ")");
                return { ok: true };
            }
            return resp.json().then(function (data) {
                if (!resp.ok || data.ok === false) {
                    throw new Error(data && data.message ? data.message : "Request failed");
                }
                return data;
            });
        });
    };

    /* --------------------- delegated data-ajax handling ------------------ */

    function closestRow(el) {
        return el.closest("tr, .list-group-item, .cc-row, li, .card");
    }

    function removeTarget(el, selector) {
        if (!selector || selector === "closest") {
            var row = closestRow(el);
            if (row) {
                row.classList.add("row-removing");
                setTimeout(function () { row.remove(); }, 220);
            }
            return;
        }
        var target = document.querySelector(selector);
        if (target) target.remove();
    }

    function dispatch(name, detail) {
        document.dispatchEvent(new CustomEvent(name, { detail: detail }));
    }

    function handleAjax(el) {
        var url = el.dataset.ajax;
        if (!url) return;
        var method = el.dataset.ajaxMethod || (el.tagName === "A" ? "POST" : "POST");
        var payload = {};
        if (el.dataset.ajaxExtra) {
            try { payload = JSON.parse(el.dataset.ajaxExtra); } catch (e) { /* ignore */ }
        }

        var proceed = Promise.resolve(true);
        if (el.dataset.ajaxConfirm) {
            proceed = App.confirm({
                title: el.dataset.ajaxConfirmTitle || "Please confirm",
                text: el.dataset.ajaxConfirm,
                okText: el.dataset.ajaxConfirmOk || "Confirm",
                danger: el.dataset.ajaxConfirmDanger === "true"
            });
        }

        proceed.then(function (yes) {
            if (!yes) return;
            App.busy(el, true);
            App.request(url, { method: method, data: payload })
                .then(function (data) {
                    App.busy(el, false);
                    if (el.dataset.ajaxRemove !== undefined) removeTarget(el, el.dataset.ajaxRemove);
                    if (el.dataset.ajaxReload === "true") { window.location.reload(); return; }
                    var type = data.type || (data.ok === false ? "danger" : "success");
                    if (data.message) App.toast(data.message, type);
                    dispatch("cc:success", { el: el, data: data });
                })
                .catch(function (err) {
                    App.busy(el, false);
                    App.toast(err.message || "Something went wrong.", "danger");
                    dispatch("cc:error", { el: el, error: err });
                });
        });
    }

    document.addEventListener("click", function (e) {
        var el = e.target.closest("[data-ajax]");
        if (!el) return;
        // Forms are handled by the submit listener; ignore their controls here.
        if (el.tagName === "FORM" || el.closest("form[data-ajax]")) return;
        if (el.tagName === "A") e.preventDefault();
        handleAjax(el);
    });

    document.addEventListener("submit", function (e) {
        var form = e.target.closest("form[data-ajax]");
        if (!form) return;
        e.preventDefault();
        var submitter = e.submitter || form.querySelector('[type="submit"]');
        var proceed = Promise.resolve(true);
        if (form.dataset.ajaxConfirm) {
            proceed = App.confirm({
                title: form.dataset.ajaxConfirmTitle || "Please confirm",
                text: form.dataset.ajaxConfirm,
                okText: form.dataset.ajaxConfirmOk || "Confirm",
                danger: form.dataset.ajaxConfirmDanger === "true"
            });
        }
        proceed.then(function (yes) {
            if (!yes) return;
            App.busy(submitter || form, true);
            var fd = new FormData(form);
            fetch(form.dataset.ajax, {
                method: "POST",
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfToken() },
                body: fd
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    App.busy(submitter || form, false);
                    if (!data.ok) throw new Error(data.message || "Request failed");
                    if (form.dataset.ajaxRemove !== undefined) removeTarget(form, form.dataset.ajaxRemove);
                    if (data.message) App.toast(data.message, data.type || "success");
                    dispatch("cc:success", { el: form, data: data });
                })
                .catch(function (err) {
                    App.busy(submitter || form, false);
                    App.toast(err.message || "Something went wrong.", "danger");
                });
        });
    });

    /* ----------------------------- counters ------------------------------ */

    App.countUp = function (el) {
        var target = parseFloat(el.dataset.countTo || el.textContent.replace(/[^0-9.-]/g, ""));
        if (isNaN(target)) return;
        var prefix = el.dataset.countPrefix || "";
        var suffix = el.dataset.countSuffix || "";
        var start = performance.now();
        var duration = 650;
        function frame(now) {
            var p = Math.min((now - start) / duration, 1);
            var eased = 1 - Math.pow(1 - p, 3);
            el.textContent = prefix + Math.round(target * eased).toLocaleString() + suffix;
            if (p < 1) requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    };

    function runCounters(root) {
        (root || document).querySelectorAll("[data-count-to]").forEach(function (el) {
            if (el.dataset.ccCounted) return;
            el.dataset.ccCounted = "1";
            App.countUp(el);
        });
    }

    /* --------------------------- sidebar drawer -------------------------- */

    function initSidebar() {
        var sidebar = document.getElementById("sidebar");
        var toggle = document.querySelector(".menu-toggle");
        if (!sidebar || !toggle) return;

        var backdrop = document.createElement("div");
        backdrop.className = "sidebar-backdrop";
        document.body.appendChild(backdrop);
        toggle.setAttribute("aria-controls", "sidebar");
        toggle.setAttribute("aria-expanded", "false");

        function setOpen(open) {
            sidebar.classList.toggle("show", open);
            backdrop.classList.toggle("show", open);
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
            document.body.style.overflow = open ? "hidden" : "";
            if (open) {
                var link = sidebar.querySelector(".nav-link");
                if (link) link.focus();
            } else {
                toggle.focus();
            }
        }

        toggle.addEventListener("click", function (e) {
            e.preventDefault();
            setOpen(!sidebar.classList.contains("show"));
        });
        backdrop.addEventListener("click", function () { setOpen(false); });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && sidebar.classList.contains("show")) setOpen(false);
        });
        sidebar.addEventListener("click", function (e) {
            if (e.target.closest(".nav-link") && window.innerWidth <= 768) setOpen(false);
        });
    }

    /* --------------------------- flash -> toast -------------------------- */

    function initMessages() {
        var source = document.getElementById("cc-message-source");
        if (!source) return;
        source.querySelectorAll(".alert").forEach(function (alert) {
            var type = "info";
            ["success", "danger", "warning", "info"].forEach(function (t) {
                if (alert.classList.contains("alert-" + t)) type = t;
            });
            App.toast(alert.textContent.trim(), type);
            alert.remove();
        });
    }

    /* ------------------------------- init -------------------------------- */

    function init() {
        initSidebar();
        initMessages();
        runCounters(document);
        var wrapper = document.querySelector(".content-wrapper");
        if (wrapper) wrapper.classList.add("cc-animate-in");
        // Feature tiles: replace inline hover JS with the cc-tile class.
        document.querySelectorAll('[onmouseover*="translateY"]').forEach(function (el) {
            el.classList.add("cc-tile");
            el.removeAttribute("onmouseover");
            el.removeAttribute("onmouseout");
            el.style.transition = "";
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    window.App = App;
})();
