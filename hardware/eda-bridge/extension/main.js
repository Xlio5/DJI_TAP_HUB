(function () {
  "use strict";

  const gateway = "http://127.0.0.1:17321";

  async function fetchImportPlan() {
    const response = await fetch(`${gateway}/api/projects/tun-nat-hub-v3s-evt/import-plan`);
    if (!response.ok) {
      throw new Error(`Gateway request failed: ${response.status}`);
    }
    return response.json();
  }

  async function runImportDryRun() {
    const result = await fetchImportPlan();
    console.log("[TUN_NAT_HUB] Import dry run", result);
    return result;
  }

  // Lceda Pro exposes its in-app API through the extension runtime. Keep the
  // dry-run global so the API calls can be filled in after local API inspection.
  window.TunNatHubLcedaBridge = {
    gateway,
    runImportDryRun
  };
})();
