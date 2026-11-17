/* isr-ui.js v1: shared header behaviour for every ISR kit page. Vendor unchanged as
   <package>/static/isr-ui.js next to isr-ui.css.

   Markup the page provides:
     <header class="isr-bar">
       <h1>Change detect</h1><span class="isr-sub">Before and after</span>
       <div class="isr-right">
         <button class="isr-pill" id="isr-status">Starting</button>
         <a class="isr-kit-link" id="isr-kit-link" href="#">Kit</a>
       </div>
       <div class="isr-status-list" id="isr-status-list"></div>
     </header>

   Then call, whenever the page's own status changes:
     ISR.setStatus([{name: "AI", state: "ok", text: "qwen3-vl"}, {name: "TAK", state: "bad", text: "not connected"}]);
   state is ok | warn | bad | idle. The pill shows the worst one as a single word; clicking it lists all.
   Mark checks that don't matter for this demo with optional: true (they can only make it "Degraded"). */
(function () {
  var WORD = { ok: "Ready", warn: "Degraded", bad: "Offline", idle: "Off" };
  var RANK = { ok: 0, idle: 1, warn: 2, bad: 3 };

  function kitUrl() {
    // The launcher runs on the Pi at :8050. Viewed on the Pi's own names, keep that host;
    // viewed on a Mac (localhost), point at the Pi by its cable name.
    var h = location.hostname;
    if (!h || h === "localhost" || h === "127.0.0.1" || h === "::1") h = (window.ISR_HUB || "isr-pi.local");
    return location.protocol + "//" + h + ":8050/";
  }

  function setStatus(checks) {
    var pill = document.getElementById("isr-status");
    var list = document.getElementById("isr-status-list");
    if (!pill) return;
    var worst = "ok";
    (checks || []).forEach(function (c) {
      var s = c.state in RANK ? c.state : "idle";
      if (c.optional && s === "bad") s = "warn";
      if (RANK[s] > RANK[worst]) worst = s;
    });
    if (!checks || !checks.length) worst = "idle";
    pill.className = "isr-pill " + worst;
    pill.textContent = WORD[worst];
    if (list) {
      list.innerHTML = "";
      (checks || []).forEach(function (c) {
        var row = document.createElement("div");
        var k = document.createElement("span"); k.className = "k"; k.textContent = c.name;
        var v = document.createElement("span"); v.className = "isr-pill " + c.state; v.textContent = c.text || WORD[c.state] || "";
        row.appendChild(k); row.appendChild(v); list.appendChild(row);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var link = document.getElementById("isr-kit-link");
    if (link) link.href = kitUrl();
    var pill = document.getElementById("isr-status"), list = document.getElementById("isr-status-list");
    if (pill && list) {
      pill.addEventListener("click", function (e) { e.stopPropagation(); list.classList.toggle("open"); });
      document.addEventListener("click", function () { list.classList.remove("open"); });
    }
  });

  window.ISR = { setStatus: setStatus, kitUrl: kitUrl };
})();
