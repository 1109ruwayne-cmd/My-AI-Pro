/* My AI Pro verify-embed: drop-in verification badge for any website.
   Usage: <script src="https://HOST/static/verify-embed.js" data-code="ABC123"></script>
   Renders a badge that links to the live verification page. No cookies, no tracking. */
(function () {
  var s = document.currentScript;
  if (!s) { var all = document.getElementsByTagName('script'); s = all[all.length - 1]; }
  var code = s.getAttribute('data-code') || '';
  if (!code) return;
  var base = s.getAttribute('data-base');
  if (!base) { base = (s.src || '').split('/static/verify-embed.js')[0] || ''; }
  base = base.replace(/\/+$/, '');
  var url = base + '/verify/' + encodeURIComponent(code.toUpperCase());
  var a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.setAttribute('aria-label', 'Verify credential ' + code.toUpperCase());
  a.innerHTML = '<span class="ve-check">&#10003;</span> Verified credential <b>' + code.toUpperCase() + '</b><span class="ve-by">My AI Pro Registry</span>';
  a.className = 've-badge';
  var css = document.createElement('style');
  css.textContent = '.ve-badge{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:10px;' +
    'background:#12122a;border:1px solid #2c2c54;color:#dfe0ff;font:600 12px/1.4 system-ui,sans-serif;text-decoration:none}' +
    '.ve-badge .ve-check{color:#4fe0a5;font-weight:800}.ve-badge b{font-weight:800;color:#fff}' +
    '.ve-badge .ve-by{font-weight:400;font-size:10px;color:#9a9fc4;border-left:1px solid #2c2c54;padding-left:6px;margin-left:2px}';
  document.head.appendChild(css);
  (s.parentNode || document.body).insertBefore(a, s.nextSibling || null);
})();
