/* ── app.js — bootstrap & glue ──────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {

  /* Wire up all modules */
  UI.initTabs();
  Upload.init();
  Chat.init();
  Video.init();

  /* Load existing jobs */
  Jobs.loadAll();
});
