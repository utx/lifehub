// Live countdowns to kick-off, and a warning when the nightly run looks stale.
(() => {
  const MINUTE = 60 * 1000;
  const HOUR = 60 * MINUTE;
  const DAY = 24 * HOUR;
  const pad = (n) => String(n).padStart(2, "0");

  const tick = () => {
    const now = Date.now();
    document.querySelectorAll(".countdown[data-kickoff]").forEach((el) => {
      const diff = Date.parse(el.dataset.kickoff) - now;
      if (Number.isNaN(diff)) return;
      if (diff <= 0) {
        el.classList.add("live");
        el.dataset.status = diff > -2 * HOUR ? "On now" : "Full time";
        return;
      }
      const units = {
        d: Math.floor(diff / DAY),
        h: Math.floor((diff % DAY) / HOUR),
        m: Math.floor((diff % HOUR) / MINUTE),
      };
      for (const [unit, value] of Object.entries(units)) {
        const slot = el.querySelector(`[data-unit="${unit}"]`);
        if (slot) slot.textContent = pad(value);
      }
    });
  };

  tick();
  setInterval(tick, 30 * 1000);

  const generated = Date.parse(document.body.dataset.generated || "");
  if (!Number.isNaN(generated) && Date.now() - generated > 30 * HOUR) {
    document.getElementById("stale").hidden = false;
  }
})();
