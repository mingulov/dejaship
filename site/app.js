(function () {
  const API = "https://api.dejaship.com";

  async function loadStats() {
    try {
      const resp = await fetch(`${API}/v1/stats`);
      if (!resp.ok) return;
      const data = await resp.json();
      document.getElementById("stat-total").textContent = data.total_claims;
      document.getElementById("stat-active").textContent = data.active;
      document.getElementById("stat-shipped").textContent = data.shipped;
    } catch {
      // Stats unavailable — leave dashes
    }
  }

  loadStats();
})();
