(function () {
  "use strict";

  var ORDER = ["review", "approve", "run", "verify"];
  var STATUS = {
    review: "Step 1 of 4 — review the plan.",
    approve: "Step 2 of 4 — type APPROVE yourself.",
    run: "Step 3 of 4 — the approved command is running.",
    verify: "Step 4 of 4 — receipt ready. You can inspect a refused check."
  };
  var STAMP = {
    review: { className: "", label: "Pending", spoken: "Run plan status: pending review." },
    approve: { className: "", label: "Waiting on you", spoken: "Run plan status: waiting for APPROVE." },
    run: { className: "is-running", label: "Running", spoken: "Run plan status: running." },
    bound: { className: "is-bound", label: "Approved", spoken: "Run plan status: approved. Starting the run." },
    verify: { className: "is-certified", label: "All good", spoken: "Run plan status: this run matches what you allowed." },
    refused: { className: "is-refused", label: "Changed", spoken: "Run plan status: something changed — the result no longer matches." }
  };
  var RUN_LINES = [
    "Checking that your yes is still valid…",
    "Checking that the command and files have not changed…",
    "Running python3 work/compute.py (30 second limit)…",
    "Writing outputs/result.json…",
    "Checking the result and that the files did not change…",
    "Saving a local receipt…"
  ];

  var state = "review";
  var highest = 0;
  var runTimer = 0;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var tabs = Array.prototype.slice.call(document.querySelectorAll(".step-tab"));
  var panels = {
    review: document.getElementById("panel-review"),
    approve: document.getElementById("panel-approve"),
    run: document.getElementById("panel-run"),
    verify: document.getElementById("panel-verify")
  };
  var stamp = document.getElementById("stamp");
  var stampLabel = stamp.querySelector(".stamp-label");
  var stampStatus = document.getElementById("stamp-status");
  var live = document.getElementById("live-status");
  var continueReview = document.getElementById("continue-review");
  var approveForm = document.getElementById("approve-form");
  var approveInput = document.getElementById("approve-input");
  var approveBtn = document.getElementById("approve-btn");
  var approveError = document.getElementById("approve-error");
  var runLog = document.getElementById("run-log");
  var progressBar = document.getElementById("progress-bar");
  var resetBtn = document.getElementById("reset-btn");
  var tamperToggle = document.getElementById("tamper-toggle");
  var certificate = document.getElementById("certificate");
  var certKicker = document.getElementById("cert-kicker");
  var certTitle = document.getElementById("cert-title");
  var certBody = document.getElementById("cert-body");
  var certFacts = document.getElementById("cert-facts");

  if (new URLSearchParams(window.location.search).get("embed") === "1") {
    document.documentElement.classList.add("embed");
  }

  function indexOf(name) {
    return ORDER.indexOf(name);
  }

  function headingFor(name) {
    return panels[name].querySelector("h4");
  }

  function setStamp(key) {
    var info = STAMP[key];
    stamp.className = "stamp" + (info.className ? " " + info.className : "");
    stampLabel.textContent = info.label;
    stampStatus.textContent = info.spoken;
  }

  function updateTabs() {
    tabs.forEach(function (tab, i) {
      var name = tab.getAttribute("data-goto");
      var allowed = i <= highest;
      tab.disabled = !allowed;
      tab.classList.toggle("is-current", name === state);
      tab.classList.toggle("is-done", i < indexOf(state));
      if (name === state) {
        tab.setAttribute("aria-current", "step");
      } else {
        tab.removeAttribute("aria-current");
      }
    });
  }

  function showPanel(name, moveFocus) {
    ORDER.forEach(function (key) {
      var panel = panels[key];
      var active = key === name;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    live.textContent = STATUS[name];
    updateTabs();
    if (moveFocus) {
      var heading = headingFor(name);
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
  }

  function goto(name, moveFocus) {
    var i = indexOf(name);
    if (i < 0 || i > highest) {
      return;
    }
    if (name !== "run") {
      window.clearTimeout(runTimer);
    }
    state = name;
    if (name === "verify") {
      applyTamper(tamperToggle.checked);
    } else if (name === "approve") {
      setStamp("approve");
    } else if (name === "review") {
      setStamp("review");
    }
    showPanel(name, moveFocus);
  }

  function unlock(name) {
    highest = Math.max(highest, indexOf(name));
  }

  function phraseOk() {
    return approveInput.value === "APPROVE";
  }

  function syncApprove() {
    var ok = phraseOk();
    approveBtn.disabled = !ok;
    if (ok) {
      approveError.hidden = true;
      approveError.textContent = "";
      approveInput.removeAttribute("aria-invalid");
    }
  }

  function startRun() {
    unlock("run");
    state = "run";
    setStamp("run");
    showPanel("run", true);
    runLog.innerHTML = "";
    progressBar.style.width = "0%";

    var delay = reduced ? 0 : 700;
    var i = 0;

    function step() {
      if (state !== "run") {
        return;
      }
      if (i > 0) {
        runLog.children[i - 1].classList.remove("is-on");
        runLog.children[i - 1].classList.add("is-done");
      }
      if (i === RUN_LINES.length) {
        progressBar.style.width = "100%";
        finishVerify();
        return;
      }
      var li = document.createElement("li");
      li.className = "is-on";
      li.textContent = RUN_LINES[i];
      runLog.appendChild(li);
      progressBar.style.width = String(Math.round(((i + 1) / (RUN_LINES.length + 1)) * 100)) + "%";
      i += 1;
      runTimer = window.setTimeout(step, delay);
    }

    step();
  }

  function finishVerify() {
    unlock("verify");
    state = "verify";
    tamperToggle.checked = false;
    tamperToggle.setAttribute("aria-checked", "false");
    applyTamper(false);
    showPanel("verify", true);
  }

  function applyTamper(on) {
    certificate.classList.toggle("is-refused", on);
    tamperToggle.setAttribute("aria-checked", on ? "true" : "false");
    if (on) {
      setStamp("refused");
      certKicker.textContent = "Something changed";
      certTitle.textContent = "The result no longer matches the receipt";
      certBody.innerHTML = "Someone (in this simulation) changed <code>outputs/result.json</code> after the run. A real check re-reads the file on disk and will not call this all good.";
      certFacts.innerHTML =
        "<div><dt>Plan fingerprint</dt><dd><code>sim-contract · demo only</code></dd></div>" +
        "<div><dt>Files fingerprint</dt><dd><code>sim-source · work/</code></dd></div>" +
        "<div><dt>Output</dt><dd>Mismatch — the file is not the certified result</dd></div>" +
        "<div><dt>History</dt><dd>Receipt does not match live files</dd></div>";
      live.textContent = "Something changed: the result file was edited after the run.";
    } else {
      setStamp("verify");
      certKicker.textContent = "All good";
      certTitle.textContent = "This run matches what you allowed";
      certBody.innerHTML = "The command you approved is the command that ran. The result file is present, the declared field is <code>ok</code>, and the history looks intact.";
      certFacts.innerHTML =
        "<div><dt>Plan fingerprint</dt><dd><code>sim-contract · demo only</code></dd></div>" +
        "<div><dt>Files fingerprint</dt><dd><code>sim-source · work/</code></dd></div>" +
        "<div><dt>Output</dt><dd><code>outputs/result.json</code> · status ok</dd></div>" +
        "<div><dt>History</dt><dd>Looks intact (checkable log)</dd></div>";
      live.textContent = STATUS.verify;
    }
  }

  function reset() {
    window.clearTimeout(runTimer);
    highest = 0;
    state = "review";
    approveInput.value = "";
    approveBtn.disabled = true;
    approveError.hidden = true;
    runLog.innerHTML = "";
    progressBar.style.width = "0%";
    tamperToggle.checked = false;
    tamperToggle.setAttribute("aria-checked", "false");
    setStamp("review");
    showPanel("review", true);
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      goto(tab.getAttribute("data-goto"), true);
    });
  });

  continueReview.addEventListener("click", function () {
    unlock("approve");
    goto("approve", true);
    approveInput.focus();
  });

  approveInput.addEventListener("input", syncApprove);

  approveForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!phraseOk()) {
      approveError.hidden = false;
      approveError.textContent = "Type APPROVE exactly — capital letters, nothing else.";
      approveInput.setAttribute("aria-invalid", "true");
      approveInput.focus();
      return;
    }
    approveInput.removeAttribute("aria-invalid");
    setStamp("bound");
    startRun();
  });

  tamperToggle.addEventListener("change", function () {
    applyTamper(tamperToggle.checked);
  });

  resetBtn.addEventListener("click", reset);

  setStamp("review");
  showPanel("review", false);
})();
