/* HR Policy Copilot — one app, three views, one API.
   Vanilla JS, no framework, no dependency. Shared pieces:
   api() fetch wrapper, renderAnswer(), renderCaseCard(),
   renderChecklist(), and the pipeline strip (setFlow). */
(function () {
  "use strict";

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* One fetch wrapper for every API call in the app. */
  function api(path, opts) {
    opts = opts || {};
    opts.headers = { "Content-Type": "application/json" };
    return fetch(path, opts).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok) throw new Error((data && data.detail) || ("Request failed: " + res.status));
        return data;
      });
    });
  }

  var ROUTE_LABELS = {
    answered: "Answered from policy",
    routed_to_hr: "Routed to HR",
    sensitive_pay: "Sensitive — pay",
    sensitive_grievance: "Sensitive — grievance",
    sensitive_visa: "Sensitive — visa",
    low_confidence: "Low confidence — routed"
  };
  function routeLabel(r) { return ROUTE_LABELS[r] || r; }

  /* ---- pipeline strip: question -> retrieval -> supervisor -> HITL -> answer/case -> checklist.
     Steps light up in order as a real request moves; the pulse dot travels the strip. */
  var FLOW_STEPS = ["question", "retrieval", "supervisor", "hitl", "outcome", "checklist"];
  function setFlow(active, note) {
    var strip = $("#flow-strip");
    if (!strip) return;
    $$(".flow-step", strip).forEach(function (li) {
      li.classList.toggle("is-done", active.indexOf(li.dataset.step) !== -1);
      li.classList.remove("is-active");
    });
    var last = active[active.length - 1];
    var lastLi = last && strip.querySelector('[data-step="' + last + '"]');
    if (lastLi) lastLi.classList.add("is-active");
    var dot = $("#flow-dot");
    if (dot && lastLi && window.innerWidth >= 768) {
      /* percentage, so a viewport resize never strands the dot off-screen */
      var strip = $("#flow-strip");
      dot.style.left = ((lastLi.offsetLeft + lastLi.offsetWidth / 2) / strip.offsetWidth * 100) + "%";
      dot.classList.add("on");
    }
    var n = $("#flow-note");
    if (n && note) n.textContent = note;
  }
  function animateFlow(steps, done) {
    /* Light the steps one at a time, ~250ms apart, so the order reads. */
    var i = 0;
    (function next() {
      if (i >= steps.length) { if (done) done(); return; }
      setFlow(steps.slice(0, i + 1));
      i++;
      setTimeout(next, 260);
    })();
  }

  /* ---- shared renderer: an answer with its cited clauses ---- */
  function renderAnswer(box, data) {
    var html = '<div class="answer">';
    html += '<p class="answer__text">' + esc(data.answer) + "</p>";
    html += '<p class="answer__meta">Confidence ' + Number(data.confidence).toFixed(2) +
      ' · request ' + esc(data.request_id) + "</p>";
    html += renderCitations(data.citations);
    html += "</div>";
    box.innerHTML = html;
  }

  function renderCitations(citations) {
    if (!citations || !citations.length) return '<p class="no-cite">No citations — nothing was answered from policy.</p>';
    var html = '<ul class="cites">';
    citations.forEach(function (c) {
      html += '<li class="cite"><span class="cite__id">' + esc(c.clause_id) + "</span>" +
        '<span class="cite__doc">' + esc(c.title) + " · " + esc(c.doc_id) + "</span>" +
        '<span class="cite__quote">&ldquo;' + esc(c.quote) + "&rdquo;</span></li>";
    });
    return html + "</ul>";
  }

  /* ---- shared renderer: one HR case card ---- */
  function renderCaseCard(c, opts) {
    opts = opts || {};
    var html = '<article class="case-card" data-case="' + esc(c.id) + '">' +
      '<div class="case-card__head"><strong>' + esc(c.id) + "</strong>" +
      '<span class="badge badge--' + esc(c.status) + '">' + esc(c.status.replace("_", " ")) + "</span></div>" +
      '<p class="case-card__q">' + esc(c.question) + "</p>" +
      '<p class="case-card__meta">' + esc(routeLabel(c.route_reason)) + " · " + esc(new Date(c.created_at).toLocaleString()) + "</p>";
    if (c.draft_reply) {
      html += '<blockquote class="case-card__draft">' + esc(c.draft_reply) + "</blockquote>";
    }
    if (c.citations && c.citations.length) html += renderCitations(c.citations);
    if (c.status !== "pending_review") {
      html += '<p class="case-card__review">Reviewed by ' + esc(c.reviewed_by || "—") +
        (c.review_note ? " — &ldquo;" + esc(c.review_note) + "&rdquo;" : "") + "</p>";
    } else if (opts.reviewable) {
      html += '<div class="case-card__review-form">' +
        '<label>Reviewer <input type="text" class="reviewer" value="hr-reviewer" maxlength="60"></label>' +
        '<label>Note <input type="text" class="review-note" placeholder="Optional note" maxlength="200"></label>' +
        '<div class="btn-row"><button type="button" class="btn btn--primary btn--sm" data-review="approved">Approve</button>' +
        '<button type="button" class="btn btn--sm" data-review="rejected">Reject</button></div>' +
        '<p class="case-card__err" role="alert"></p></div>';
    }
    return html + "</article>";
  }

  /* ---- shared renderer: a first-week checklist, day by day, with sources ---- */
  function checklistKey(empId, title) { return "n28-check:" + empId + ":" + title; }
  function renderChecklist(box, data) {
    var byDay = {};
    data.checklist.forEach(function (it) { (byDay[it.day] = byDay[it.day] || []).push(it); });
    var days = Object.keys(byDay).sort(function (a, b) { return a - b; });
    var total = data.checklist.length;
    var done = data.checklist.filter(function (it) {
      return localStorage.getItem(checklistKey(data.employee_id, it.title)) === "1";
    }).length;
    var html = '<div class="checklist" data-emp="' + esc(data.employee_id) + '">' +
      '<p class="checklist__head">' + esc(data.role) + " · " + esc(data.location) +
      " · " + done + " of " + total + " done</p>";
    days.forEach(function (d) {
      html += '<h4 class="app-check-day">Day ' + esc(d) + "</h4><ul class=\"app-checks\">";
      byDay[d].forEach(function (it) {
        var checked = localStorage.getItem(checklistKey(data.employee_id, it.title)) === "1";
        html += '<li class="app-check' + (checked ? " is-done" : "") + '">' +
          '<label><input type="checkbox" data-title="' + esc(it.title) + '"' + (checked ? " checked" : "") + ">" +
          '<span class="app-check__body"><span class="app-check__title">' + esc(it.title) + "</span>" +
          '<span class="app-check__detail">' + esc(it.detail) + "</span>" +
          '<span class="app-check__src">Owner: ' + esc(it.owner) + " · Source: " + esc(it.source.clause_id) +
          " · " + esc(it.source.title) + "</span></span></label></li>";
      });
      html += "</ul>";
    });
    box.innerHTML = html + "</div>";
    $$("input[type=checkbox]", box).forEach(function (cb) {
      cb.addEventListener("change", function () {
        localStorage.setItem(checklistKey(data.employee_id, cb.dataset.title), cb.checked ? "1" : "0");
        renderChecklist(box, data); /* re-render keeps the done count honest */
      });
    });
  }

  function showError(box, err) {
    box.innerHTML = '<p class="app-error" role="alert">Could not reach the copilot API: ' + esc(err.message) +
      ". Is the server running on this machine?</p>";
  }

  function askQuestion(question, employeeId) {
    setFlow(["question"]);
    return api("/ask", {
      method: "POST",
      body: JSON.stringify({ question: question, employee_id: employeeId || "EMP-001" })
    });
  }

  function handleAskResult(box, data) {
    if (data.route === "answered") {
      animateFlow(["question", "retrieval", "supervisor", "outcome"], function () {
        setFlow(["question", "retrieval", "supervisor", "outcome"],
          "Answered from policy — every sentence traces to a cited clause.");
      });
      renderAnswer(box, data);
      return Promise.resolve(data);
    }
    /* Routed: no answer, only the acknowledgement + case id; fetch the case for its draft. */
    animateFlow(["question", "retrieval", "supervisor", "hitl", "outcome"], function () {
      setFlow(["question", "retrieval", "supervisor", "hitl", "outcome"],
        "Sensitive or low-confidence — no auto-answer. A case is open for HR review.");
    });
    box.innerHTML = '<div class="routed"><p class="routed__msg">' + esc(data.message || "Routed to HR.") + "</p>" +
      '<p class="routed__meta">' + esc(routeLabel(data.route_reason)) + " · Case <strong>" + esc(data.case_id) + "</strong></p>" +
      '<p class="routed__loading">Loading the draft reply…</p></div>';
    return api("/cases?limit=100").then(function (list) {
      var c = list.cases.filter(function (x) { return x.id === data.case_id; })[0];
      if (c) box.innerHTML = renderCaseCard(c, {});
      return data;
    }).catch(function () { return data; });
  }

  /* ---- case queue (View A sidebar + View C list share this) ---- */
  function loadCases(target, opts) {
    opts = opts || {};
    var box = $(target);
    if (!box) return Promise.resolve();
    box.innerHTML = '<p class="loading">Loading cases…</p>';
    return api("/cases?status=pending_review&limit=20").then(function (list) {
      if (!list.cases.length) {
        box.innerHTML = '<p class="empty">No cases waiting for review. Ask a pay, grievance or visa question and one opens here.</p>';
        return;
      }
      box.innerHTML = list.cases.map(function (c) { return renderCaseCard(c, opts); }).join("");
      bindReviewButtons(box);
    }).catch(function (err) { showError(box, err); });
  }

  function bindReviewButtons(root) {
    $$(".case-card", root).forEach(function (card) {
      $$("[data-review]", card).forEach(function (btn) {
        btn.addEventListener("click", function () {
          var id = card.dataset.case;
          var reviewer = ($(".reviewer", card) || {}).value || "hr-reviewer";
          var note = ($(".review-note", card) || {}).value || "";
          btn.disabled = true;
          api("/cases/" + encodeURIComponent(id) + "/review", {
            method: "POST",
            body: JSON.stringify({ decision: btn.dataset.review, reviewer: reviewer, note: note || undefined })
          }).then(function () {
            refreshAll();
          }).catch(function (err) {
            var e = $(".case-card__err", card);
            if (e) e.textContent = err.message;
            btn.disabled = false;
          });
        });
      });
    });
  }

  /* ---- metrics (View C dashboard) ---- */
  function loadMetrics() {
    var box = $("#metrics-strip");
    if (!box) return;
    api("/metrics").then(function (m) {
      box.innerHTML =
        metric("Questions answered", m.answered, "of " + m.questions_total + " asked") +
        metric("Autonomous rate", (m.autonomous_rate * 100).toFixed(1) + "%", "answered without HR") +
        metric("Citation coverage", (m.citation_coverage * 100).toFixed(0) + "%", "answered with a citation") +
        metric("Open sensitive cases", m.cases_pending, "waiting for HR review") +
        metric("Cases approved", m.cases_approved, "by an HR reviewer") +
        metric("Cases rejected", m.cases_rejected, "by an HR reviewer");
      var prov = $("#metrics-provider");
      if (prov) prov.textContent = "Provider: " + m.llm_provider + " · Retrieval: " + m.retrieval +
        " · Average confidence " + (m.avg_confidence == null ? "—" : Number(m.avg_confidence).toFixed(2));
    }).catch(function (err) { showError(box, err); });
  }
  function metric(label, value, sub) {
    return '<div class="metric"><strong>' + esc(value) + "</strong><span>" + esc(label) + "</span><small>" + esc(sub) + "</small></div>";
  }

  function refreshAll() { loadCases("#case-queue", {}); loadCases("#hr-cases", { reviewable: true }); loadMetrics(); }

  /* ---- view tabs (hash-routed: #view=ask | journey | hr) ---- */
  var VIEWS = ["ask", "journey", "hr"];
  function showView(name) {
    if (VIEWS.indexOf(name) === -1) name = "ask";
    VIEWS.forEach(function (v) {
      var tab = $("#tab-" + v), panel = $("#view-" + v);
      if (tab) tab.setAttribute("aria-selected", v === name ? "true" : "false");
      if (panel) panel.hidden = v !== name;
    });
    if (name === "ask") loadCases("#case-queue", {});
    if (name === "hr") { loadMetrics(); loadCases("#hr-cases", { reviewable: true }); }
  }
  function viewFromHash() {
    var m = (location.hash || "").match(/view=(ask|journey|hr)/);
    return m ? m[1] : "ask";
  }
  $$(".app-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      history.replaceState(null, "", "#app?view=" + tab.dataset.view);
      showView(tab.dataset.view);
    });
  });
  window.addEventListener("hashchange", function () { showView(viewFromHash()); });

  /* ---- View A: ask workspace ---- */
  var askForm = $("#ask-form");
  if (askForm) {
    askForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var q = $("#ask-q").value.trim();
      if (q.length < 3) return;
      var box = $("#ask-result");
      box.innerHTML = '<p class="loading">Asking the copilot…</p>';
      askQuestion(q).then(function (data) { return handleAskResult(box, data); })
        .then(function () { loadCases("#case-queue", {}); })
        .catch(function (err) { showError(box, err); });
    });
    $$("[data-example]", askForm).forEach(function (chip) {
      chip.addEventListener("click", function () {
        $("#ask-q").value = chip.dataset.example;
        askForm.dispatchEvent(new Event("submit", { cancelable: true }));
      });
    });
  }
  var queueRefresh = $("#queue-refresh");
  if (queueRefresh) queueRefresh.addEventListener("click", function () { loadCases("#case-queue", {}); });

  /* ---- View B: guided journey, 3 steps ---- */
  var journey = { choice: null };
  function journeyStep(n) {
    [1, 2, 3].forEach(function (i) {
      var pane = $("#journey-step-" + i);
      if (pane) pane.hidden = i !== n;
    });
    $$(".journey-indicator li").forEach(function (li, idx) {
      li.classList.toggle("is-current", idx + 1 === n);
      li.classList.toggle("is-done", idx + 1 < n);
    });
  }
  function journeyChoose(choice) {
    journey.choice = choice;
    $("#journey-choice-label").textContent =
      choice === "ask" ? "Ask a question" : choice === "checklist" ? "First-week checklist" : "Track my case";
    $("#journey-ask-pane").hidden = choice !== "ask";
    $("#journey-checklist-pane").hidden = choice !== "checklist";
    $("#journey-track-pane").hidden = choice !== "track";
    journeyStep(2);
  }
  $$("[data-choice]").forEach(function (btn) {
    btn.addEventListener("click", function () { journeyChoose(btn.dataset.choice); });
  });
  $$("[data-journey-back]").forEach(function (btn) {
    btn.addEventListener("click", function () { journeyStep(1); });
  });
  $$("[data-journey-restart]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      $("#journey-result").innerHTML = "";
      journeyStep(1);
    });
  });

  var jAsk = $("#journey-ask-form");
  if (jAsk) {
    jAsk.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var q = $("#journey-q").value.trim();
      if (q.length < 3) return;
      var box = $("#journey-result");
      box.innerHTML = '<p class="loading">Asking the copilot…</p>';
      journeyStep(3);
      askQuestion(q).then(function (data) {
        if (data.route === "answered") {
          setFlow(["question", "retrieval", "supervisor", "outcome"],
            "Answered from policy — every sentence traces to a cited clause.");
          renderAnswer(box, data);
          box.insertAdjacentHTML("afterbegin", '<p>You have your answer, with the clause it comes from. ' +
            'If it does not cover your situation, ask a follow-up — or open a case with HR from the Ask workspace.</p>');
        } else {
          setFlow(["question", "retrieval", "supervisor", "hitl", "outcome"],
            "Sensitive or low-confidence — no auto-answer. A case is open for HR review.");
          box.innerHTML = '<p>Your question was routed to HR as case <strong>' +
            esc(data.case_id) + '</strong>. A draft reply is already written; an HR reviewer approves or rejects it, ' +
            'and HR responds within 5 working days. Track it any time under “Track my case”.</p>' +
            '<p><button type="button" class="btn btn--sm" data-track-case="' + esc(data.case_id) + '">Track this case</button></p>' +
            '<div class="journey-case"></div>';
          var trackBtn = $("[data-track-case]", box);
          if (trackBtn) trackBtn.addEventListener("click", function () {
            journeyChoose("track");
            $("#track-id").value = data.case_id;
            $("#journey-track-form").dispatchEvent(new Event("submit", { cancelable: true }));
          });
          api("/cases?limit=100").then(function (list) {
            var c = list.cases.filter(function (x) { return x.id === data.case_id; })[0];
            if (c) $(".journey-case", box).innerHTML = renderCaseCard(c, {});
          });
        }
        loadCases("#case-queue", {});
      }).catch(function (err) { showError(box, err); });
    });
  }

  var jCheck = $("#journey-checklist-form");
  if (jCheck) {
    jCheck.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var emp = $("#journey-emp").value.trim() || "EMP-001";
      var role = $("#journey-role").value.trim() || "Software Engineer";
      var loc = $("#journey-loc").value.trim() || "Pune";
      var box = $("#journey-result");
      box.innerHTML = '<p class="loading">Building your first week…</p>';
      journeyStep(3);
      api("/onboarding/" + encodeURIComponent(emp) + "/checklist", {
        method: "POST",
        body: JSON.stringify({ role: role, location: loc })
      }).then(function (data) {
        setFlow(["checklist"], "Checklist built from the onboarding policy — day by day, with sources.");
        box.innerHTML = '<p>Your first week is planned day by day below. ' +
          "Tick items off as you finish them — they stay ticked on this machine. Day 1 starts with HR paperwork and IT logins; " +
          "your buddy and manager pick up the rest.</p><div class=\"journey-checklist\"></div>";
        renderChecklist($(".journey-checklist", box), data);
      }).catch(function (err) { showError(box, err); });
    });
  }

  var jTrack = $("#journey-track-form");
  if (jTrack) {
    jTrack.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var id = $("#track-id").value.trim().toUpperCase();
      var box = $("#journey-result");
      if (!id) return;
      box.innerHTML = '<p class="loading">Looking up ' + esc(id) + "…</p>";
      journeyStep(3);
      api("/cases?limit=100").then(function (list) {
        var c = list.cases.filter(function (x) { return x.id === id; })[0];
        if (!c) {
          box.innerHTML = '<p class="app-error" role="alert">No case with id ' + esc(id) +
            " exists yet. Case ids look like CASE-0001 and are shown when a question is routed to HR.</p>";
          return;
        }
        var next = c.status === "pending_review"
          ? "An HR reviewer has not decided yet. HR responds within 5 working days of the case opening."
          : "This case was " + c.status + " by " + esc(c.reviewed_by || "HR") + ".";
        box.innerHTML = "<p>" + next + "</p>";
        box.insertAdjacentHTML("beforeend", renderCaseCard(c, {}));
      }).catch(function (err) { showError(box, err); });
    });
  }

  /* ---- View C: HR dashboard chat ---- */
  var hrChatForm = $("#hr-chat-form");
  if (hrChatForm) {
    hrChatForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var q = $("#hr-chat-q").value.trim();
      if (q.length < 3) return;
      var log = $("#hr-chat-log");
      log.insertAdjacentHTML("beforeend",
        '<div class="chat-msg chat-msg--me"><span class="chat-msg__text">' + esc(q) + "</span></div>");
      var bot = document.createElement("div");
      bot.className = "chat-msg chat-msg--bot";
      bot.innerHTML = '<span class="chat-msg__text loading">Asking the copilot…</span>';
      log.appendChild(bot);
      log.scrollTop = log.scrollHeight;
      $("#hr-chat-q").value = "";
      askQuestion(q).then(function (data) {
        if (data.route === "answered") {
          bot.innerHTML = '<span class="chat-msg__text">' + esc(data.answer) + "</span>" + renderCitations(data.citations);
        } else {
          bot.innerHTML = '<span class="chat-msg__text">' + esc(data.message || "Routed to HR.") +
            " Case <strong>" + esc(data.case_id) + "</strong> · " + esc(routeLabel(data.route_reason)) + ".</span>";
        }
        log.scrollTop = log.scrollHeight;
        refreshAll();
      }).catch(function (err) {
        bot.innerHTML = '<span class="chat-msg__text">Could not reach the copilot API: ' + esc(err.message) + "</span>";
      });
    });
  }

  /* ---- View C: checklist board ---- */
  var hrCheck = $("#hr-checklist-form");
  if (hrCheck) {
    hrCheck.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var emp = $("#hr-emp").value.trim() || "EMP-001";
      var role = $("#hr-role").value.trim() || "Software Engineer";
      var loc = $("#hr-loc").value.trim() || "Pune";
      var box = $("#hr-checklist-board");
      box.innerHTML = '<p class="loading">Building the first week…</p>';
      api("/onboarding/" + encodeURIComponent(emp) + "/checklist", {
        method: "POST",
        body: JSON.stringify({ role: role, location: loc })
      }).then(function (data) {
        setFlow(["checklist"], "Checklist built from the onboarding policy — day by day, with sources.");
        renderChecklist(box, data);
      }).catch(function (err) { showError(box, err); });
    });
  }
  var hrCasesRefresh = $("#hr-cases-refresh");
  if (hrCasesRefresh) hrCasesRefresh.addEventListener("click", function () { loadCases("#hr-cases", { reviewable: true }); });

  /* Boot: view from the hash, queue for the default view. */
  showView(viewFromHash());
})();
