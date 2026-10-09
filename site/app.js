// Live countdowns to kick-off, and a warning when the nightly run looks stale.
(() => {
  const HOUR = 3600 * 1000;

  const describe = (ms) => {
    const minutes = Math.round(ms / 60000);
    if (minutes < 60) return `Kick-off in ${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Kick-off in ${hours}h ${minutes % 60}m`;
    const days = Math.floor(hours / 24);
    const rest = hours % 24;
    return `Kick-off in ${days} day${days === 1 ? "" : "s"}${rest ? `, ${rest}h` : ""}`;
  };

  const tick = () => {
    const now = Date.now();
    document.querySelectorAll("[data-kickoff]").forEach((el) => {
      const diff = Date.parse(el.dataset.kickoff) - now;
      if (Number.isNaN(diff)) return;
      el.textContent = diff > 0 ? describe(diff) : diff > -2 * HOUR ? "On now" : "Finished";
    });
  };

  tick();
  setInterval(tick, 60 * 1000);

  const generated = Date.parse(document.body.dataset.generated || "");
  if (!Number.isNaN(generated) && Date.now() - generated > 30 * HOUR) {
    document.getElementById("stale").hidden = false;
  }
})();
