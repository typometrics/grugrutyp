/* The cookie notice (named site-notice, not cookie-notice: content blockers drop any
 * script called cookie-notice.js, Kim's Firefox did on 2026-11-24) for typometrics.elizia.net and grugrutyp (one file, both sites).
 *
 * Informational, not a consent dialog: the sites set only what the ePrivacy rules exempt
 * from consent -- the login cookie (grugrutyp_session) and preferences kept in the
 * browser (theme, last plot, panel widths). No tracking, no third-party cookies, and the
 * visit counter stores no IP address. An "accept / refuse" choice would refuse nothing.
 * If that ever changes (analytics, embeds), this has to become a real consent dialog.
 */
(function () {
  var KEY = 'typometrics-site-notice';
  try {
    if (localStorage.getItem(KEY)) return;
  } catch (e) { /* storage blocked: show it, it costs nothing */ }

  function show() {
    var css = document.createElement('style');
    css.textContent =
      '.tm-sitenote{position:fixed;left:16px;right:16px;bottom:12px;margin:0 auto;z-index:99999;' +
      'max-width:680px;box-sizing:border-box;display:flex;align-items:center;gap:12px;' +
      'padding:8px 10px 8px 14px;border-radius:8px;font:13px/1.4 system-ui,-apple-system,sans-serif;' +
      'background:rgba(250,250,247,.96);color:#333;border:1px solid #d9d9d2;' +
      'box-shadow:0 2px 10px rgba(0,0,0,.08)}' +
      '.tm-sitenote a{color:inherit;text-decoration:underline}' +
      '.tm-sitenote button{flex:none;font:inherit;font-weight:600;padding:4px 12px;border-radius:6px;' +
      'border:1px solid #9aa69f;background:transparent;color:inherit;cursor:pointer}' +
      '.tm-sitenote button:hover{background:rgba(0,0,0,.06)}' +
      '@media (prefers-color-scheme: dark){.tm-sitenote{background:rgba(32,36,34,.96);color:#ddd;border-color:#444}}' +
      '.body--dark .tm-sitenote{background:rgba(32,36,34,.96);color:#ddd;border-color:#444}' +
      // grugrutyp (Quasar) has its own theme switch: follow the app, not the OS
      '.body--light .tm-sitenote{background:rgba(250,250,247,.96);color:#333;border-color:#d9d9d2}' +
      '@media (max-width:520px){.tm-sitenote{font-size:12px;bottom:8px;left:8px;right:8px}}' +
      '@media print{.tm-sitenote{display:none}}';
    document.head.appendChild(css);

    var bar = document.createElement('div');
    bar.className = 'tm-sitenote';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Privacy notice');
    bar.innerHTML =
      '<span>This site uses only a login cookie and your own settings, stored in your ' +
      'browser. No tracking, no advertising. <a href="/privacy/">Details</a></span>' +
      '<button type="button">OK</button>';
    bar.querySelector('button').addEventListener('click', function () {
      try { localStorage.setItem(KEY, new Date().toISOString()); } catch (e) { /* ignore */ }
      bar.remove();
    });
    document.body.appendChild(bar);
  }

  if (document.body) show();
  else document.addEventListener('DOMContentLoaded', show);
})();
