# My AI Pro source code: static/index.html

The complete frontend (single file): chat UI, SSE streaming, markdown/KaTeX/code rendering, HTML/SVG previews, in-browser Python & JavaScript runners, paywall card with owner unlock, usage pill, settings dialog, owner billing dashboard.

This is the assistant's own source code, kept here so it can answer questions about how it works, explain any part of itself, and help its owner debug or extend it. Contains no secrets (passwords and API keys live in environment variables).

~~~~
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>My AI</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%235b5bd6'/%3E%3Cstop offset='1' stop-color='%238b5cf6'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='64' height='64' rx='16' fill='url(%23g)'/%3E%3Cpath d='M17 44l9-24 9 24M20.5 36h11M45 20v24' stroke='white' stroke-width='5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<!-- Maths (KaTeX) and code colouring (highlight.js) are stored inside the app, so they also work offline. -->
<link rel="stylesheet" href="static/vendor/katex/katex.min.css">
<link rel="stylesheet" href="static/vendor/highlight/atom-one-dark.min.css">
<script defer src="static/vendor/katex/katex.min.js"></script>
<script defer src="static/vendor/highlight/highlight.min.js"></script>
<style>
:root{
  --bg:#f6f7fb;--side:#eff1f8;--text:#1c1f33;--muted:#6a6f88;--border:#e2e5ef;
  --accent:#5b5bd6;--accent2:#8b5cf6;--accent-soft:#ecebff;--danger:#d14343;--warn:#a86a12;--ok:#23966a;
  --shadow:0 1px 2px rgba(16,24,40,.05),0 6px 18px rgba(16,24,40,.06);
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,Ubuntu,"Helvetica Neue",Arial,sans-serif;color:var(--text);background:var(--bg);-webkit-font-smoothing:antialiased}
button,input,select,textarea{font:inherit;color:inherit}
button{cursor:pointer}
[hidden]{display:none!important}
.app{display:grid;grid-template-columns:300px minmax(0,1fr);height:100vh;height:100dvh}

/* ---------- sidebar ---------- */
.sidebar{background:var(--side);border-right:1px solid var(--border);display:flex;flex-direction:column;gap:14px;padding:18px 14px 14px;min-height:0}
.brand{display:flex;align-items:center;gap:11px;padding:0 4px}
.logo{width:40px;height:40px;border-radius:12px;flex:none;display:grid;place-items:center;color:#fff;font-weight:700;font-size:15px;letter-spacing:.3px;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 6px 14px rgba(91,91,214,.35)}
.brand-text{min-width:0}
.brand-name{font-weight:700;font-size:16.5px;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.brand-sub{font-size:12.5px;color:var(--muted)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid var(--border);background:#fff;border-radius:10px;padding:9px 14px;font-weight:600;font-size:14px;transition:background .15s,border-color .15s}
.btn:hover{border-color:#c9cce0;background:#fafaff}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{background:#4b4bc4}
.btn.small{padding:6px 11px;font-size:13px;border-radius:8px}
.btn:disabled{opacity:.55;cursor:default}
.section-title{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);padding:2px 4px 0}
.count{background:#fff;border:1px solid var(--border);border-radius:99px;padding:0 8px;font-size:11.5px;letter-spacing:0;color:var(--text)}
.dropzone{display:block;border:1.5px dashed #c5c8de;border-radius:12px;padding:13px 12px;text-align:center;cursor:pointer;background:#fff;transition:.15s}
.dropzone:hover{border-color:var(--accent);background:var(--accent-soft)}
.dropzone svg{color:var(--accent)}
.dz-title{font-weight:700;font-size:14px;margin-top:2px}
.dz-hint{font-size:12px;color:var(--muted)}
.file-list{flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column;gap:6px;margin:0 -4px;padding:0 4px}
.file{display:flex;align-items:center;gap:10px;padding:8px 9px;border-radius:11px;background:#fff;border:1px solid var(--border)}
.badge{width:36px;height:36px;border-radius:9px;flex:none;display:grid;place-items:center;color:#fff;font-size:9.5px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;background:#8a8fa8}
.file-info{min-width:0;flex:1}
.file-name{font-size:13.5px;font-weight:600;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.file-meta{font-size:12px;color:var(--muted)}
.file-warn{font-size:12px;color:var(--warn);line-height:1.35;margin-top:2px}
.file-warn.err{color:var(--danger)}
.del{border:0;background:transparent;color:#9aa0b8;width:28px;height:28px;border-radius:8px;flex:none;display:grid;place-items:center;opacity:0;transition:.15s}
.file:hover .del,.del:focus-visible{opacity:1}
.del:hover{background:#fdecec;color:var(--danger)}
.file.uploading .badge{background:linear-gradient(135deg,var(--accent),var(--accent2));font-size:15px}
.progress{height:4px;border-radius:9px;background:#e7e8f3;overflow:hidden;margin-top:6px}
.progress>div{height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .2s}
.empty-files{font-size:13px;color:var(--muted);text-align:center;padding:10px 6px}
.sidebar-footer{display:flex;flex-direction:column;gap:8px;border-top:1px solid var(--border);padding-top:12px}
.status{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);padding:0 4px;min-width:0}
.status span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;background:#c2c5d6;flex:none}
.dot.ok{background:var(--ok);box-shadow:0 0 0 3px rgba(35,150,106,.15)}
.dot.warn{background:#e0a020;box-shadow:0 0 0 3px rgba(224,160,32,.18)}

/* ---------- main ---------- */
.main{display:flex;flex-direction:column;min-width:0;min-height:0}
.topbar{height:58px;flex:none;display:flex;align-items:center;gap:12px;padding:0 22px;border-bottom:1px solid var(--border);background:rgba(255,255,255,.85);backdrop-filter:saturate(1.4) blur(8px)}
.topbar .title{font-weight:700;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pill{font-size:12px;color:var(--muted);background:var(--bg);border:1px solid var(--border);border-radius:99px;padding:3px 10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:46%}
.spacer{flex:1}
.icon-btn{border:1px solid transparent;background:transparent;border-radius:9px;width:36px;height:36px;flex:none;display:grid;place-items:center;color:var(--muted)}
.icon-btn:hover{background:var(--bg);border-color:var(--border);color:var(--text)}
.menu{display:none}
.messages{flex:1;min-height:0;overflow-y:auto;padding:26px 22px 8px}
.thread{max-width:860px;margin:0 auto;display:flex;flex-direction:column;gap:20px}

/* ---------- welcome ---------- */
.welcome{max-width:680px;margin:6vh auto 0;text-align:center}
.welcome .logo{width:64px;height:64px;border-radius:18px;font-size:22px;margin:0 auto 16px}
.welcome h1{font-size:26px;line-height:1.25;margin:0 0 8px}
.welcome p{color:var(--muted);margin:0 0 22px}
.welcome .hint{font-size:13px;margin:16px 0 0}
.welcome .hint a{color:var(--accent);font-weight:600;cursor:pointer}
.suggestions{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;text-align:left}
.suggestion{border:1px solid var(--border);background:#fff;border-radius:12px;padding:12px 14px;box-shadow:var(--shadow);transition:.15s;text-align:left}
.suggestion:hover{border-color:var(--accent);transform:translateY(-1px)}
.suggestion b{display:block;font-size:13.5px;margin-bottom:2px}
.suggestion span{color:var(--muted);font-size:12.5px;line-height:1.45;display:block}
.suggestion .q{display:block;font-size:13.5px;font-weight:600;color:var(--text);line-height:1.45}

/* ---------- messages ---------- */
.msg{display:flex;gap:12px;min-width:0}
.msg.user{flex-direction:column;align-items:flex-end;gap:6px}
.msg.user .bubble{max-width:78%;background:var(--accent);color:#fff;padding:10px 15px;border-radius:18px 18px 5px 18px;white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:0 4px 12px rgba(91,91,214,.22)}
.bubble-atts{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end;max-width:78%}
.bubble-atts img{max-width:240px;max-height:180px;min-width:64px;min-height:64px;object-fit:contain;border-radius:12px;display:block;border:1px solid var(--border);background:#fff}
.bubble-file{background:#fff;border:1px solid var(--border);border-radius:10px;padding:4px 10px;font-size:12.5px;color:var(--text);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.avatar{width:32px;height:32px;border-radius:10px;flex:none;display:grid;place-items:center;color:#fff;font-size:12px;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--accent2));margin-top:2px}
.card{flex:1;min-width:0;background:#fff;border:1px solid var(--border);border-radius:5px 18px 18px 18px;padding:13px 17px;box-shadow:var(--shadow)}
.status-line{display:flex;align-items:center;gap:9px;font-size:13.5px;color:var(--muted);margin-bottom:6px}
.spinner{width:14px;height:14px;border:2px solid #d4d6ea;border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;flex:none}
@keyframes spin{to{transform:rotate(360deg)}}
.md{overflow-wrap:anywhere}
.md>*:first-child{margin-top:0}
.md>*:last-child{margin-bottom:0}
.md p{margin:0 0 .75em}
.md h1,.md h2,.md h3,.md h4,.md h5,.md h6{line-height:1.3;margin:1em 0 .45em}
.md h1{font-size:1.3em}.md h2{font-size:1.18em}.md h3{font-size:1.06em}.md h4,.md h5,.md h6{font-size:1em}
.md ul,.md ol{margin:.3em 0 .8em;padding-left:1.4em}
.md li{margin:.2em 0}
.md li>ul,.md li>ol{margin:.2em 0}
.md a{color:var(--accent)}
.md code{font-family:var(--mono);font-size:.88em;background:#f0f1f7;border-radius:5px;padding:.12em .38em}
.md pre{background:#1d1f2f;color:#e9e9f3;border-radius:11px;padding:12px 14px;overflow-x:auto;margin:.6em 0 .9em}
.md pre code{background:none;padding:0;color:inherit;font-size:.85em}
.md blockquote{margin:.6em 0 .9em;padding:.45em .9em;border-left:3px solid var(--accent);background:#f7f7fe;border-radius:0 10px 10px 0;color:#3f4460}
.md blockquote p{margin:.25em 0}
.md hr{border:0;border-top:1px solid var(--border);margin:1em 0}
.table-wrap{overflow-x:auto;margin:.5em 0 .9em}
.md table{border-collapse:collapse;font-size:.93em;min-width:50%}
.md th,.md td{border:1px solid var(--border);padding:6px 10px;text-align:left;vertical-align:top}
.md th{background:#f6f7fc;font-weight:650}
.cite{display:inline-block;font-size:.76em;font-weight:650;line-height:1.5;background:var(--accent-soft);color:#4a4ac2;border-radius:6px;padding:0 .45em;margin:0 .1em;vertical-align:.08em;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cursor::after{content:"";display:inline-block;width:7px;height:1.05em;background:var(--accent);margin-left:3px;vertical-align:-.15em;border-radius:2px;animation:caret 1s steps(1) infinite}
@keyframes caret{50%{opacity:0}}

/* code blocks */
.md .codeblock{margin:.6em 0 .9em;border-radius:11px;overflow:hidden;background:#1d1f2f;border:1px solid #2b2e45}
.code-head{display:flex;align-items:center;flex-wrap:wrap;gap:4px 8px;padding:4px 6px 4px 12px;background:#272a40;color:#b8bbd6;font-size:12px;line-height:1.4}
.code-lang{font-family:var(--mono);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;max-width:60%}
.code-actions{margin-left:auto;display:flex;flex-wrap:wrap;gap:2px}
.code-btn{border:0;background:transparent;color:#cfd1ea;font-size:12px;font-weight:600;padding:3px 9px;border-radius:6px;line-height:1.5}
.code-btn:hover{background:rgba(255,255,255,.1);color:#fff}
.code-btn.run{color:#86e3b5}
.code-btn:disabled{opacity:.35;cursor:default;background:transparent}
.md .codeblock pre{margin:0;border-radius:0;background:transparent;max-height:640px;overflow:auto}
.md .codeblock pre code.hljs{background:transparent;padding:0;color:#e6e6f0;display:inline;overflow:visible}
.code-out{border-top:1px solid #33375a;background:#14151f;color:#e4e4ef}
.out-head{display:flex;align-items:center;gap:8px;padding:4px 6px 4px 12px;color:#a3a7c9;font-size:12px}
.out-head .spinner{width:12px;height:12px;border-color:#3a3e60;border-top-color:#86e3b5}
.out-title{font-weight:700;color:#d6d8ee}
.out-status{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.out-head .code-actions{flex:none}
.md .code-out pre.out-text{margin:0;padding:6px 12px 10px;background:transparent;border-radius:0;white-space:pre-wrap;overflow-wrap:anywhere;max-height:380px;overflow:auto;font:12.5px/1.5 var(--mono);color:#e9e9f3}
.out-text:empty{display:none}
.out-text .err{color:#ff9e9e}
.out-text .res{color:#9fd8ff}
.out-imgs img{display:block;max-width:calc(100% - 24px);margin:4px 12px 12px;border-radius:8px;background:#fff}

/* maths */
.math-block{overflow-x:auto;overflow-y:hidden;margin:.4em 0 .9em;padding:2px 0}
.md .katex{font-size:1.07em}
.md .katex-display{margin:.3em 0}
.math-fallback{font-family:var(--mono)}

.error-box{margin-top:6px;background:#fdf1f1;border:1px solid #f4cccc;color:#a33232;border-radius:10px;padding:9px 12px;font-size:14px}
.notice{margin-top:10px;background:#fff8e8;border:1px solid #f1dcaa;color:#7a5410;border-radius:10px;padding:7px 8px 7px 12px;font-size:13.5px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.notice .btn{margin-left:auto}
.searched{font-size:12.5px;color:var(--muted);margin-top:12px;overflow-wrap:anywhere}
.sources{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:8px;padding-top:10px;border-top:1px dashed var(--border)}
.searched+.sources{margin-top:6px}
.sources-label{font-size:12px;font-weight:700;color:var(--muted);margin-right:2px}
.chip{border:1px solid var(--border);background:var(--bg);border-radius:99px;padding:3px 10px;font-size:12.5px;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:.15s}
.chip:hover,.chip.active{border-color:var(--accent);color:var(--accent);background:var(--accent-soft)}
.src-panel{margin-top:8px;background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:13.5px;max-height:260px;overflow-y:auto;color:#3d4260;overflow-wrap:anywhere}
.src-panel>b{display:block;margin-bottom:4px;color:var(--text)}
.src-panel a{color:var(--accent);font-weight:600}
.src-panel code{font-size:.9em;background:#e9eaf3;border-radius:4px;padding:0 .3em}
.msg-actions{display:flex;gap:4px;margin-top:8px}
.act{border:0;background:transparent;color:var(--muted);font-size:12.5px;padding:3px 8px;border-radius:7px}
.act:hover{background:var(--bg);color:var(--text)}
.typing{display:inline-flex;gap:5px;padding:6px 2px}
.typing span{width:7px;height:7px;border-radius:50%;background:#b9bcd3;animation:blink 1.2s infinite ease-in-out}
.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
@keyframes blink{0%,80%,100%{opacity:.3;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}

/* ---------- composer ---------- */
.composer{flex:none;padding:8px 22px 14px}
.banner{max-width:860px;margin:0 auto 8px;background:#fff8e8;border:1px solid #f1dcaa;color:#7a5410;border-radius:12px;padding:8px 10px 8px 12px;font-size:13.5px;display:flex;align-items:center;gap:10px}
.banner .btn{margin-left:auto;white-space:nowrap;flex:none}
.attach-row{max-width:860px;margin:0 auto 8px;display:flex;flex-wrap:wrap;gap:6px}
.att{display:inline-flex;align-items:center;gap:7px;background:#fff;border:1px solid var(--border);border-radius:10px;padding:4px 4px 4px 6px;font-size:12.5px;max-width:280px;box-shadow:var(--shadow)}
.att img{width:30px;height:30px;object-fit:cover;border-radius:6px;flex:none;border:1px solid var(--border);background:#fff}
.att .att-icon{width:30px;height:30px;border-radius:6px;background:var(--accent-soft);display:grid;place-items:center;flex:none;font-size:14px}
.att span.att-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.att button{border:0;background:transparent;color:var(--muted);width:24px;height:24px;border-radius:6px;display:grid;place-items:center;flex:none}
.att button:hover{background:#fdecec;color:var(--danger)}
.composer form{max-width:860px;margin:0 auto;display:flex;align-items:flex-end;gap:6px;background:#fff;border:1px solid var(--border);border-radius:18px;padding:8px 8px 8px 8px;box-shadow:var(--shadow);transition:border-color .15s,box-shadow .15s}
.composer form:focus-within{border-color:#b9b9f0;box-shadow:0 0 0 4px rgba(91,91,214,.1),var(--shadow)}
.composer.drag form{border-color:var(--accent);box-shadow:0 0 0 4px rgba(91,91,214,.18),var(--shadow)}
.clip{width:42px;height:42px;border-radius:13px;border:0;background:transparent;color:var(--muted);display:grid;place-items:center;flex:none}
.clip:hover{background:var(--bg);color:var(--accent)}
.composer textarea{flex:1;border:0;outline:0;resize:none;background:transparent;padding:9px 0;max-height:220px;line-height:1.5;min-width:0}
.send{width:42px;height:42px;border-radius:13px;border:0;background:var(--accent);color:#fff;display:grid;place-items:center;flex:none;transition:.15s}
.send:hover{background:#4b4bc4}
.send:disabled{background:#c9cae4;cursor:default}
.send.stop{background:#2d2f45}
.fineprint{max-width:860px;margin:7px auto 0;text-align:center;font-size:11.5px;color:#9a9eb5}

/* ---------- paywall & billing ---------- */
.paywall{border:1.5px solid #e4c98a;background:linear-gradient(180deg,#fffaf0,#fff);border-radius:14px;padding:14px 16px;margin:4px 0 10px;max-width:560px}
.paywall .pw-head{font-size:15px;font-weight:750;display:flex;gap:8px;align-items:center}
.paywall .pw-sub{color:var(--muted);font-size:13px;margin:6px 0 10px}
.pw-plan{display:flex;align-items:baseline;gap:10px;border:1px solid var(--border);background:#fff;border-radius:12px;padding:10px 14px;margin-bottom:10px}
.pw-plan b{font-size:15px}
.pw-price{margin-left:auto;font-size:22px;font-weight:800;color:#3f3fae}
.pw-price span{font-size:12.5px;font-weight:600;color:var(--muted)}
.pw-list{margin:0 0 12px;padding-left:18px;font-size:13.5px;color:#3c4160;display:flex;flex-direction:column;gap:3px}
.pw-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:8px}
.pw-row .input{flex:1;min-width:180px}
.pw-bank{background:#fff;border:1px solid var(--border);border-radius:10px;padding:9px 12px;font-size:13px;margin-top:10px;display:grid;grid-template-columns:auto 1fr;gap:2px 12px}
.pw-bank b{font-weight:650;color:var(--muted)}
.pw-bank code{font-family:var(--mono);font-size:12.5px}
.pw-status{font-size:12.5px;margin-top:9px;color:#4d5270;min-height:16px}
.pw-status.ok{color:#17694a}.pw-status.bad{color:#a33232}
.pw-note{font-size:12.5px;color:var(--muted);margin-top:8px}
.bgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.bgrid .field{margin:0}
@media (max-width:560px){.bgrid{grid-template-columns:1fr}}
.dash-tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0}
.dash-tbl td,.dash-tbl th{padding:4px 6px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
.dash-stats{display:flex;flex-wrap:wrap;gap:7px;margin:6px 0}
.dstat{background:var(--bg);border:1px solid var(--border);border-radius:9px;padding:5px 10px;font-size:12.5px}
.dstat b{font-size:14px}

/* ---------- other AIs (engines) ---------- */
.engine-strip{max-width:860px;margin:0 auto 8px;display:flex;gap:6px;overflow-x:auto;padding:2px 1px 4px;scrollbar-width:thin}
.engine-strip::-webkit-scrollbar{height:4px}
.engine-strip::-webkit-scrollbar-thumb{background:#d6d9e6;border-radius:4px}
.ebtn{flex:none;display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);background:#fff;border-radius:999px;padding:5px 12px 5px 10px;font-size:12.8px;font-weight:600;color:var(--muted);white-space:nowrap;transition:.14s}
.ebtn:hover{border-color:#b9b9f0;color:var(--accent)}
.ebtn.on{border-color:var(--accent);background:var(--accent-soft);color:#3f3fae}
.ebtn .ico{font-size:14px;line-height:1}
.ebtn .mdl{max-width:130px;overflow:hidden;text-overflow:ellipsis;font-weight:500;opacity:.8}
.ebtn.add{border-style:dashed}
.engine-badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:650;color:#4d5270;background:#eef0f8;border:1px solid var(--border);border-radius:999px;padding:2px 10px;margin-bottom:8px}
.engine-badge b{font-weight:700}
.engine-badge .mdl{font-weight:500;color:var(--muted)}
.voice-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:2px 0 10px;font-size:12.5px;color:var(--muted)}
.voice-row .vn{font-weight:650;color:#4d5270}
.voice-row audio{height:30px;max-width:100%}
.hintline{max-width:860px;margin:0 auto 8px;font-size:12.5px;color:var(--muted)}

/* ---------- connectors panel in settings ---------- */
.conn-intro{font-size:13px;color:var(--muted);background:var(--bg);border-radius:10px;padding:10px 12px;line-height:1.5}
.conn{border:1px solid var(--border);border-radius:12px;overflow:hidden}
.conn-head{display:flex;align-items:center;gap:10px;padding:11px 13px;cursor:pointer;background:#fff}
.conn-head:hover{background:#fafbff}
.conn.on>.conn-head{background:var(--accent-soft)}
.conn-ico{font-size:19px;flex:none;width:26px;text-align:center}
.conn-title{flex:1;min-width:0}
.conn-title b{display:block;font-size:14px;font-weight:650}
.conn-title small{display:block;color:var(--muted);font-size:12px;line-height:1.4;margin-top:1px}
.conn-dot{width:8px;height:8px;border-radius:50%;background:#d5d8e5;flex:none}
.conn-dot.ok{background:#37b57f}
.conn-dot.bad{background:#e08a3c}
.switch{position:relative;width:40px;height:23px;flex:none;border-radius:999px;background:#d5d8e5;border:0;transition:.16s;padding:0}
.switch::after{content:"";position:absolute;top:2.5px;left:3px;width:18px;height:18px;border-radius:50%;background:#fff;transition:.16s;box-shadow:0 1px 3px rgba(0,0,0,.25)}
.switch[aria-checked="true"]{background:var(--accent)}
.switch[aria-checked="true"]::after{left:19px}
.conn-body{padding:0 13px 13px;display:flex;flex-direction:column;gap:10px;border-top:1px solid var(--border)}
.conn-body .lbl{margin-bottom:4px}
.conn .row{flex-wrap:wrap}
.chipset{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}
.mchip{border:1px solid var(--border);background:#fff;border-radius:8px;padding:3px 9px;font-size:12px;color:var(--muted);font-family:var(--mono)}
.mchip:hover{border-color:var(--accent);color:var(--accent)}
.free-tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px}
.free-tbl td{padding:5px 6px;border-bottom:1px solid var(--border);vertical-align:top}
.free-tbl tr:last-child td{border-bottom:0}
.free-tbl .fname{font-weight:650;white-space:nowrap}
.free-tbl .ffree{color:var(--muted)}
.free-tbl button{white-space:nowrap}

/* ---------- overlays ---------- */
.drop-overlay{position:fixed;inset:0;z-index:50;background:rgba(91,91,214,.12);backdrop-filter:blur(2px);display:grid;place-items:center;pointer-events:none}
.drop-overlay>div{background:#fff;border:2px dashed var(--accent);border-radius:18px;padding:24px 34px;font-weight:700;font-size:18px;color:var(--accent);box-shadow:var(--shadow);text-align:center;max-width:90vw}
.drop-overlay small{display:block;font-weight:500;font-size:13.5px;color:var(--muted);margin-top:6px}
.drop-overlay .to-chat{display:none}
.drop-overlay.chat .to-chat{display:block}
.drop-overlay.chat .to-kb{display:none}
.modal{position:fixed;inset:0;z-index:60;background:rgba(20,22,40,.45);display:grid;place-items:center;padding:16px}
.dialog{background:#fff;border-radius:18px;width:min(620px,100%);max-height:calc(100dvh - 32px);display:flex;flex-direction:column;box-shadow:0 24px 60px rgba(16,24,40,.25)}
.dialog>header{display:flex;align-items:center;gap:8px;padding:14px 16px 14px 22px;border-bottom:1px solid var(--border)}
.dialog>header h2{font-size:17px;margin:0}
.dialog .content{padding:18px 22px;overflow-y:auto;display:flex;flex-direction:column;gap:18px}
.dialog>footer{display:flex;gap:8px;justify-content:flex-end;padding:14px 22px;border-top:1px solid var(--border)}
.preview-dialog{width:min(1180px,100%);height:calc(100dvh - 32px)}
.preview-dialog>header{padding:10px 12px 10px 20px}
.pv-note{font-size:12.5px;color:var(--muted)}
.preview-dialog iframe{flex:1;width:100%;border:0;background:#fff;border-radius:0 0 18px 18px}
.lbl{display:block;font-weight:650;font-size:13.5px;margin-bottom:6px}
.help{font-size:12.5px;color:var(--muted);margin-top:6px;line-height:1.45}
.help a{color:var(--accent);font-weight:600}
.input,.field select,.field textarea{width:100%;border:1px solid var(--border);border-radius:10px;padding:9px 11px;background:#fff;outline:0;transition:.15s}
.input:focus,.field select:focus,.field textarea:focus{border-color:#a9a9ee;box-shadow:0 0 0 3px rgba(91,91,214,.12)}
.field textarea{resize:vertical;min-height:92px;line-height:1.5}
.row{display:flex;gap:8px;align-items:center}
.row .input{flex:1;min-width:0}
.radios{display:flex;flex-direction:column;gap:7px}
.radio{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--border);border-radius:10px;padding:9px 12px;cursor:pointer;font-size:14px;font-weight:600}
.radio:has(input:checked){border-color:var(--accent);background:var(--accent-soft)}
.radio input{margin-top:4px;accent-color:var(--accent)}
.radio small{display:block;color:var(--muted);font-size:12.5px;font-weight:400}
details.adv summary{cursor:pointer;font-weight:650;font-size:13.5px;color:var(--muted)}
details.adv[open] summary{margin-bottom:14px}
.adv-inner{display:flex;flex-direction:column;gap:18px}
.test-result{font-size:13px;border-radius:9px;padding:8px 11px;line-height:1.45}
.test-result.ok{background:#eaf7f1;color:#17694a}
.test-result.bad{background:#fdf1f1;color:#a33232}
.test-result.info{background:var(--bg);color:#4d5270}
.toast{position:fixed;left:50%;bottom:112px;transform:translateX(-50%) translateY(20px);opacity:0;z-index:80;background:#1f2136;color:#fff;padding:10px 16px;border-radius:12px;font-size:14px;box-shadow:0 10px 30px rgba(0,0,0,.2);transition:.25s;pointer-events:none;max-width:min(560px,92vw);white-space:pre-line}
.toast.show{opacity:1;transform:translateX(-50%)}
.toast.error{background:#a33232}
.scrim{display:none}

@media (max-width:860px){
  .app{grid-template-columns:minmax(0,1fr)}
  .sidebar{position:fixed;z-index:40;top:0;bottom:0;left:0;width:min(300px,86vw);transform:translateX(-102%);transition:transform .22s ease;box-shadow:0 0 40px rgba(0,0,0,.15)}
  .sidebar.open{transform:none}
  .scrim.show{display:block;position:fixed;inset:0;z-index:35;background:rgba(20,22,40,.35)}
  .menu{display:grid}
  .topbar{padding:0 10px}
  .messages{padding:18px 12px 6px}
  .composer{padding:6px 10px 10px}
  .msg.user .bubble,.bubble-atts{max-width:88%}
  .del{opacity:1}
  .pill{display:none}
  .engine-strip{margin-bottom:6px}
  .welcome{margin-top:3vh}
  .card{padding:12px 13px}
  .preview-dialog{height:calc(100dvh - 16px)}
  .modal{padding:8px}
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar" id="sidebar">
    <div class="brand">
      <div class="logo" id="logo">AI</div>
      <div class="brand-text">
        <div class="brand-name" id="brandName">My AI</div>
        <div class="brand-sub">Code · Engineering · Your files</div>
      </div>
    </div>
    <button class="btn" id="newChatBtn" type="button">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
      New chat
    </button>
    <div class="section-title">Knowledge <span class="count" id="fileCount">0</span></div>
    <label class="dropzone" id="dropzone">
      <input type="file" id="fileInput" multiple hidden>
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></svg>
      <div class="dz-title">Add files</div>
      <div class="dz-hint">Click or drop: PDF, Word, Excel, PowerPoint, text, or a .zip</div>
    </label>
    <div class="file-list" id="fileList"></div>
    <div class="sidebar-footer">
      <div class="status"><span class="dot" id="statusDot"></span><span id="statusText">Loading…</span></div>
      <button class="btn" id="settingsBtn" type="button">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h9M19 6h1M4 12h3M13 12h7M4 18h11M21 18h-1"/><circle cx="16" cy="6" r="2.2"/><circle cx="10" cy="12" r="2.2"/><circle cx="18" cy="18" r="2.2"/></svg>
        Settings
      </button>
      <div id="creatorCredit" style="font-size:11px;opacity:.65;text-align:center">created by <b>Ruwayne</b></div>
    </div>
  </aside>
  <div class="scrim" id="scrim"></div>

  <main class="main">
    <header class="topbar">
      <button class="icon-btn menu" id="menuBtn" type="button" aria-label="Open menu">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
      </button>
      <div class="title" id="topTitle">My AI</div>
      <div class="pill" id="modelPill"></div>
      <div class="pill" id="usagePill" hidden title="Your free allowance"></div>
      <div class="spacer"></div>
      <button class="icon-btn" id="newChatTop" type="button" title="New chat" aria-label="New chat">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
      </button>
    </header>

    <div class="messages" id="messages"><div class="thread" id="thread"></div></div>

    <div class="composer" id="composer">
      <div class="banner" id="keyBanner" hidden>
        <span>🔌 <b>No AI connected yet.</b> Add a free API key to get answers, code and engineering help. Until then I can only search your files.</span>
        <button class="btn small primary" type="button" id="bannerBtn">Connect AI</button>
      </div>
      <div class="engine-strip" id="engineStrip" hidden></div>
      <div class="attach-row" id="attachRow" hidden></div>
      <form id="form" autocomplete="off">
        <button class="clip" id="attachBtn" type="button" title="Attach code, text files or pictures to your message" aria-label="Attach files">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.4 11.1l-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5"/></svg>
        </button>
        <input type="file" id="attachInput" multiple hidden>
        <textarea id="input" rows="1" placeholder="Ask anything: code, engineering, your files…"></textarea>
        <button class="send" id="sendBtn" type="submit" aria-label="Send"></button>
      </form>
      <div class="fineprint">AI can make mistakes. Test code before you rely on it, and have safety-critical designs checked by a qualified engineer.</div>
    </div>
  </main>
</div>

<div class="drop-overlay" id="dropOverlay" hidden><div>
  <span class="to-kb">Drop to add the files to your AI's knowledge<small>Or drop them on the message box to attach them to one message</small></span>
  <span class="to-chat">Drop to attach to your message<small>Code, text files and pictures</small></span>
</div></div>

<div class="modal" id="previewModal" hidden>
  <div class="dialog preview-dialog" role="dialog" aria-modal="true" aria-labelledby="previewTitle">
    <header>
      <h2 id="previewTitle">Preview</h2>
      <span class="pv-note">Runs in a safe sandbox</span>
      <div class="spacer"></div>
      <button class="btn small" type="button" id="pvReload">Reload</button>
      <button class="btn small" type="button" id="pvDownload">Download</button>
      <button class="icon-btn" type="button" data-close-preview aria-label="Close preview">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </header>
    <iframe id="previewFrame" title="Preview" sandbox="allow-scripts allow-forms allow-modals allow-popups allow-downloads"></iframe>
  </div>
</div>

<div class="modal" id="settingsModal" hidden>
  <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
    <header>
      <h2 id="settingsTitle">Settings</h2>
      <div class="spacer"></div>
      <button class="icon-btn" type="button" data-close aria-label="Close">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </header>
    <div class="content">
      <div class="field">
        <label class="lbl" for="cfgName">Your AI's name</label>
        <input class="input" id="cfgName" maxlength="60" placeholder="My AI">
      </div>
      <div class="field">
        <label class="lbl" for="cfgCreator">Created by (shown in the sidebar)</label>
        <input class="input" id="cfgCreator" maxlength="40" placeholder="Ruwayne">
      </div>
      <div class="field">
        <label class="lbl" for="cfgProvider">AI brain (provider)</label>
        <select id="cfgProvider"></select>
        <div class="help" id="providerHelp"></div>
      </div>
      <div class="field" id="keyField">
        <label class="lbl" for="cfgKey">API key</label>
        <div class="row">
          <input class="input" id="cfgKey" type="password" placeholder="Paste your key here" autocomplete="off" spellcheck="false">
          <button class="btn small" type="button" id="toggleKey">Show</button>
        </div>
        <div class="help" id="keyHelp"></div>
      </div>
      <div class="field">
        <label class="lbl" for="cfgModel">Model</label>
        <div class="row">
          <input class="input" id="cfgModel" placeholder="e.g. gemini-3.8-flash" spellcheck="false">
          <button class="btn small" type="button" id="loadModelsBtn">Load models</button>
        </div>
        <select id="modelSelect" hidden style="margin-top:8px"></select>
        <div class="help">Click “Load models” to see every model your key can use. Bigger models write better code for hard problems but are slower and may cost money.</div>
      </div>
      <div>
        <button class="btn small" type="button" id="testBtn">Test connection</button>
        <div class="test-result" id="testResult" hidden style="margin-top:10px"></div>
      </div>
      <div class="field">
        <span class="lbl">How should it answer?</span>
        <div class="radios">
          <label class="radio"><input type="radio" name="mode" value="files_first"><span>Everything: coding, engineering and general knowledge, plus my files<small>Recommended. Uses your files whenever they're relevant and its own expertise for everything else.</small></span></label>
          <label class="radio"><input type="radio" name="mode" value="files_only"><span>Only from my files<small>Strict: answers only from your files and says when they don't have the answer. Turns off coding and general help.</small></span></label>
        </div>
      </div>
      <div class="field">
        <label class="lbl" for="cfgInstructions">Extra instructions <span style="font-weight:400;color:var(--muted)">(optional)</span></label>
        <textarea id="cfgInstructions" placeholder="e.g. You are the assistant for Thabo's Plumbing in Cape Town. Be friendly and brief. Give prices in Rand. Answer in English or Afrikaans, whichever the customer uses."></textarea>
        <div class="help">Personality, tone, rules, language: tell your AI how to behave.</div>
      </div>
      <div class="field">
        <span class="lbl">Plans &amp; payments</span>
        <div class="help">Visitors get a free allowance; when it runs out they see a subscription
          offer. Card payments (Stripe or Paystack) pay out to your bank account; direct bank
          transfers you confirm yourself with one click. Keys entered here are stored on the
          server and never shown again.</div>
        <label class="radio" style="margin:10px 0"><input type="checkbox" id="billEnabled" style="margin-top:4px;accent-color:var(--accent)"><span>Ask for a subscription when the free allowance runs out</span></label>
        <div class="bgrid">
          <div class="field"><label class="lbl" for="billPrompts">Free questions per visitor</label><input class="input" id="billPrompts" type="number" min="0" max="100000"></div>
          <div class="field"><label class="lbl" for="billTokens">Free tokens per visitor</label><input class="input" id="billTokens" type="number" min="0" max="10000000" step="1000"></div>
          <div class="field"><label class="lbl" for="billWindow">Allowance resets</label><select id="billWindow"><option value="lifetime">Never (one free trial per visitor)</option><option value="monthly">Every 30 days</option></select></div>
          <div class="field"><label class="lbl" for="billPlan">Plan name</label><input class="input" id="billPlan" maxlength="40"></div>
          <div class="field"><label class="lbl" for="billPrice">Price</label><input class="input" id="billPrice" inputmode="decimal"></div>
          <div class="field"><label class="lbl" for="billCurrency">Currency</label><select id="billCurrency"><option>ZAR</option><option>USD</option><option>EUR</option><option>GBP</option><option>NAD</option><option>BWP</option></select></div>
          <div class="field"><label class="lbl" for="billInterval">Billed</label><select id="billInterval"><option value="month">Monthly</option><option value="year">Yearly</option><option value="week">Weekly</option></select></div>
        </div>
        <div class="radios" style="margin:10px 0">
          <label class="radio"><input type="checkbox" id="billManual"><span>Bank transfer / EFT<small>You confirm each payment in the owner dashboard below.</small></span></label>
          <label class="radio"><input type="checkbox" id="billStripe"><span>Card payments via Stripe<small>Subscriptions; Stripe pays out to your bank account.</small></span></label>
          <label class="radio"><input type="checkbox" id="billPaystack"><span>Card payments via Paystack<small>Works well in South Africa; pays out to your bank.</small></span></label>
        </div>
        <div class="bgrid">
          <div class="field"><label class="lbl" for="billBank">Bank</label><input class="input" id="billBank"></div>
          <div class="field"><label class="lbl" for="billAccName">Account name</label><input class="input" id="billAccName"></div>
          <div class="field"><label class="lbl" for="billAccNo">Account number</label><input class="input" id="billAccNo" spellcheck="false"></div>
          <div class="field"><label class="lbl" for="billBranch">Branch code</label><input class="input" id="billBranch" spellcheck="false"></div>
        </div>
        <div class="bgrid" style="margin-top:10px">
          <div class="field"><label class="lbl" for="billStripeKey">Stripe secret key</label><input class="input" id="billStripeKey" type="password" autocomplete="off" spellcheck="false" placeholder="saved — type to replace"></div>
          <div class="field"><label class="lbl" for="billStripeHook">Stripe webhook secret</label><input class="input" id="billStripeHook" type="password" autocomplete="off" spellcheck="false" placeholder="saved — type to replace"></div>
          <div class="field"><label class="lbl" for="billPaystackKey">Paystack secret key</label><input class="input" id="billPaystackKey" type="password" autocomplete="off" spellcheck="false" placeholder="saved — type to replace"></div>
        </div>
        <div class="field" style="margin-top:10px"><label class="lbl" for="billNote">Note shown on the paywall</label><input class="input" id="billNote" placeholder="e.g. WhatsApp the proof of payment to 082 …"></div>
        <div class="help">Stripe also needs a webhook: in your Stripe dashboard add
          <code>https://YOUR-ADDRESS/api/billing/webhook/stripe</code> (and
          <code>…/paystack</code> for Paystack) so payments switch on automatically.</div>
        <div class="row" style="margin-top:10px">
          <button class="btn small" type="button" id="billDashBtn">Owner dashboard</button>
          <span class="help" style="margin:0">visitors, payments waiting for confirmation, coupons, revenue</span>
        </div>
        <div id="billDash" hidden style="margin-top:10px"></div>
      </div>
      <div class="field">
        <span class="lbl">Connectors: other AIs it can use</span>
        <div class="conn-intro" id="connIntro"></div>
        <div id="connList" style="display:flex;flex-direction:column;gap:9px;margin-top:10px"></div>
        <label class="radio" style="margin-top:10px"><input type="checkbox" id="cfgVoice" style="margin-top:4px;accent-color:var(--accent)"><span>Play Open-LLM-VTuber's voice in the chat<small>Switch off if you only want its text answers.</small></span></label>
        <label class="radio" style="margin-top:10px"><input type="checkbox" id="cfgSkills" style="margin-top:4px;accent-color:var(--accent)"><span>Agent Skills module<small>17 built-in tools your AI uses automatically when helpful: calculator, live web search, weather, exchange rates, Wikipedia, dictionary, date &amp; time, timezones, unit converter, finance maths, JSON &amp; regex tools, QR codes, text tools, password audit and a secure random generator.</small></span></label>
        <div class="help">Keys you type here are saved on the server (config.json) and never shown again. You can also put them in the <b>.env</b> file instead. Everything is optional: your AI works fine with none of them.</div>
      </div>
      <details class="adv">
        <summary>Advanced</summary>
        <div class="adv-inner">
          <div class="field">
            <label class="lbl" for="cfgBaseUrl">Server address (base URL)</label>
            <input class="input" id="cfgBaseUrl" spellcheck="false">
            <div class="help">Filled in automatically when you choose a provider.</div>
          </div>
          <div class="field">
            <label class="lbl" for="cfgEffort">Thinking effort</label>
            <select id="cfgEffort">
              <option value="">Model default (recommended)</option>
              <option value="low">Low: faster answers</option>
              <option value="medium">Medium</option>
              <option value="high">High: best for hard coding and engineering problems (slower)</option>
            </select>
            <div class="help">How long the AI thinks before answering. Works with Gemini and OpenAI reasoning models; if you get an error, set it back to “Model default”.</div>
          </div>
          <div class="field">
            <label class="lbl" for="cfgContext">How much of your files the AI reads</label>
            <select id="cfgContext">
              <option value="15000">Small: about 2,500 words (fastest)</option>
              <option value="60000">Medium: about 10,000 words (recommended)</option>
              <option value="150000">Large: about 25,000 words</option>
              <option value="400000">Huge: about 65,000 words (slower, uses more quota)</option>
            </select>
            <div class="help">If all your files fit, the AI reads every one in full. If not, it searches them whenever a question needs them.</div>
          </div>
          <div class="field">
            <label class="lbl" for="cfgSuggestions">Starter questions <span style="font-weight:400;color:var(--muted)">(one per line, up to 6)</span></label>
            <textarea id="cfgSuggestions" style="min-height:80px" placeholder="Leave empty to use the standard ones"></textarea>
            <div class="help">Shown as buttons on the welcome screen.</div>
          </div>
          <div class="field">
            <label class="lbl" for="cfgHistory">Chat memory</label>
            <select id="cfgHistory">
              <option value="0">Don't remember earlier messages</option>
              <option value="6">Last 6 messages</option>
              <option value="10">Last 10 messages</option>
              <option value="20">Last 20 messages (recommended)</option>
              <option value="40">Last 40 messages (long coding sessions)</option>
            </select>
          </div>
        </div>
      </details>
    </div>
    <footer>
      <button class="btn" type="button" data-close>Cancel</button>
      <button class="btn primary" type="button" id="saveSettings">Save</button>
    </footer>
  </div>
</div>

<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
(function () {
  'use strict';

  /* ==MARKDOWN-START== (small, safe Markdown renderer with code colouring and maths) */
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function lib(name) {
    var g = typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : {});
    return g[name];
  }

  var LANG_ALIAS = {
    py: 'python', python3: 'python', py3: 'python', ipython: 'python', js: 'javascript', node: 'javascript',
    nodejs: 'javascript', mjs: 'javascript', cjs: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript',
    htm: 'html', xhtml: 'html', sh: 'bash', shell: 'bash', zsh: 'bash', console: 'bash', terminal: 'bash',
    ps: 'powershell', ps1: 'powershell', pwsh: 'powershell', 'c++': 'cpp', cc: 'cpp', cxx: 'cpp', hpp: 'cpp', h: 'c',
    'c#': 'csharp', cs: 'csharp', yml: 'yaml', md: 'markdown', rs: 'rust', rb: 'ruby', kt: 'kotlin', golang: 'go',
    ino: 'arduino', v: 'verilog', sv: 'verilog', systemverilog: 'verilog', vhd: 'vhdl', scad: 'openscad', tex: 'latex',
    m: 'matlab', octave: 'matlab', jl: 'julia', f90: 'fortran', f: 'fortran', nc: 'gcode', txt: 'plaintext', text: 'plaintext',
    plain: 'plaintext', output: 'plaintext', bat: 'dos', cmd: 'dos', batch: 'dos', vb: 'vbnet', asm: 'x86asm'
  };
  var EXT_FOR = {
    python: 'py', javascript: 'js', typescript: 'ts', html: 'html', css: 'css', scss: 'scss', json: 'json', bash: 'sh',
    powershell: 'ps1', dos: 'bat', c: 'c', cpp: 'cpp', csharp: 'cs', java: 'java', go: 'go', rust: 'rs', ruby: 'rb',
    php: 'php', sql: 'sql', yaml: 'yml', xml: 'xml', svg: 'svg', markdown: 'md', matlab: 'm', arduino: 'ino',
    verilog: 'v', vhdl: 'vhd', gcode: 'gcode', openscad: 'scad', latex: 'tex', kotlin: 'kt', swift: 'swift', r: 'r',
    julia: 'jl', fortran: 'f90', dart: 'dart', lua: 'lua', ini: 'ini', toml: 'toml', csv: 'csv', plaintext: 'txt'
  };
  var FILE_EXTS = 'py|js|mjs|cjs|ts|tsx|jsx|html?|css|scss|sass|less|json|ya?ml|toml|ini|cfg|conf|env|md|txt|csv|tsv|sql|sh|bash|zsh|ps1|bat|cmd|c|h|cpp|hpp|cc|cs|java|kt|kts|go|rs|rb|php|swift|dart|lua|r|m|jl|f90|v|sv|vhdl?|ino|gcode|nc|scad|tex|xml|svg|vue|svelte|gradle|properties|ipynb|asm|s';
  var FILE_RE = new RegExp('(?:^|[\\s*`#:(\\[])((?:[\\w.\\-]+[\\/\\\\])*[\\w.\\-]*[\\w-]\\.(?:' + FILE_EXTS + ')|Dockerfile|Makefile|Procfile)[*`:)\\]]*\\s*$', 'i');

  var hlCache = new Map(), mathCache = new Map();
  function highlight(code, lang, allowAuto) {
    var hljs = lib('hljs');
    if (!hljs || !code) return esc(code);
    var key = lang + '\u0000' + (allowAuto ? 1 : 0) + code, hit = hlCache.get(key);
    if (hit !== undefined) return hit;
    var out = null;
    try {
      if (lang && lang !== 'plaintext' && hljs.getLanguage(lang)) out = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
      else if (!lang && allowAuto && code.length < 20000) {
        var auto = hljs.highlightAuto(code);
        if (auto.relevance >= 6) out = auto.value;
      }
    } catch (e) { out = null; }
    if (out === null) out = esc(code);
    if (hlCache.size > 400) hlCache.clear();
    hlCache.set(key, out);
    return out;
  }
  function renderMath(tex, display) {
    var katex = lib('katex'), key = (display ? 'D' : 'I') + tex, hit = mathCache.get(key);
    if (hit !== undefined) return hit;
    var out;
    if (katex) {
      try { out = katex.renderToString(tex, { displayMode: display, throwOnError: false, strict: 'ignore', trust: false }); }
      catch (e) { out = null; }
    }
    if (!out) {
      if (!katex) return '<code class="math-fallback">' + esc(tex) + '</code>';  // not loaded yet: don't cache
      out = '<code class="math-fallback">' + esc(tex) + '</code>';
    }
    if (mathCache.size > 600) mathCache.clear();
    mathCache.set(key, out);
    return out;
  }

  function parseInfo(info) {
    var t = (String(info).trim().split(/[\s{]+/)[0] || ''), lang = t, file = '';
    var m = t.match(/^([\w+#-]+):(.+)$/);
    if (m) { lang = m[1]; file = m[2]; }
    else if (/\.[A-Za-z0-9]{1,8}$/.test(t) && !/^[\w+#-]+$/.test(t)) { file = t; lang = t.split('.').pop(); }
    var tm = String(info).match(/(?:title|file|filename|name)=["']?([^"'\s}]+)/i);
    if (tm) file = tm[1];
    lang = lang.toLowerCase();
    return { lang: LANG_ALIAS[lang] || lang, file: file };
  }

  function codeBlockHtml(code, info, prevLine, closed) {
    var p = parseInfo(info), lang = p.lang, file = p.file;
    if (!file && prevLine && prevLine.length <= 160) {
      var fm = prevLine.match(FILE_RE);
      if (fm) file = fm[1].replace(/^[\\/]+/, '');
    }
    if (!lang && file) { var ext = file.split('.').pop().toLowerCase(); lang = LANG_ALIAS[ext] || ext; }
    var isSvg = lang === 'svg' || ((lang === 'xml' || lang === 'html' || !lang) && /^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/i.test(code));
    var isHtml = !isSvg && (lang === 'html' || (!lang && /^\s*<(!doctype html|html[\s>])/i.test(code)));
    var kind = isSvg ? 'svg' : isHtml ? 'html' : lang === 'python' ? 'python' : lang === 'javascript' ? 'js' : '';
    var label = file || (lang && lang !== 'plaintext' ? lang : 'code');
    var off = closed ? '' : ' disabled';
    var btns = '';
    if (kind === 'python' || kind === 'js') btns += '<button type="button" class="code-btn run" data-code="run"' + off + ' title="Run this code in your browser">▶ Run</button>';
    if (kind === 'html' || kind === 'svg') btns += '<button type="button" class="code-btn run" data-code="preview"' + off + ' title="See the result">▶ Preview</button>';
    btns += '<button type="button" class="code-btn" data-code="copy" title="Copy the code">Copy</button>';
    btns += '<button type="button" class="code-btn" data-code="download"' + off + ' title="Save as a file">Download</button>';
    return '<div class="codeblock" data-kind="' + kind + '" data-lang="' + esc(isSvg ? 'svg' : lang) + '" data-file="' + esc(file) + '">' +
      '<div class="code-head"><span class="code-lang">' + esc(label) + '</span><span class="code-actions">' + btns + '</span></div>' +
      '<pre><code class="hljs">' + highlight(code, isSvg || isHtml ? 'xml' : lang, closed) + '</code></pre></div>';
  }

  function mdInline(text) {
    var codes = [], links = [], maths = [], escs = [];
    var s = String(text).replace(/`([^`\n]+)`/g, function (m, c) { codes.push(c); return '\u0001' + (codes.length - 1) + '\u0001'; });
    var keepMath = function (tex) { maths.push(renderMath(tex, false)); return '\u0004' + (maths.length - 1) + '\u0004'; };
    s = s.replace(/\\\((.+?)\\\)/g, function (m, t) { return keepMath(t); });
    s = s.replace(/\\\[(.+?)\\\]/g, function (m, t) { return keepMath(t); });
    s = s.replace(/\$\$([^$\n]+?)\$\$/g, function (m, t) { return keepMath(t); });
    s = s.replace(/(^|[^\\$\w])\$(?![\s$])([^$\n]*?[^\s\\$])\$(?![\w$])/g, function (m, pre, t) { return pre + keepMath(t); });
    s = s.replace(/\\([\\`*_{}\[\]()#+\-.!|~<>$])/g, function (m, ch) { escs.push(ch); return '\u0005' + (escs.length - 1) + '\u0005'; });
    s = esc(s);
    s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, function (m, label, url) {
      links.push('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + '</a>');
      return '\u0002' + (links.length - 1) + '\u0002';
    });
    s = s.replace(/(^|[\s(])(https?:\/\/[^\s<\u0001-\u0005]+[^\s<.,;:!?)\]'"\u0001-\u0005])/g, function (m, pre, url) {
      links.push('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + '</a>');
      return pre + '\u0002' + (links.length - 1) + '\u0002';
    });
    s = s.replace(/\*\*([^\n]+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__([^_\n]+?)__/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^\w*])\*([^*\s](?:[^*\n]*[^*\s])?)\*(?![\w*])/g, '$1<em>$2</em>');
    s = s.replace(/(^|[^\w])_([^_\s](?:[^_\n]*[^_\s])?)_(?!\w)/g, '$1<em>$2</em>');
    s = s.replace(/~~([^~\n]+?)~~/g, '<del>$1</del>');
    s = s.replace(/\[([^\[\]\n]{1,200}?\.(?:pdf|docx?|pptx?|xlsx?|xlsm|csv|tsv|txt|md|markdown|json|html?|xml|log|ya?ml|rst|tex)\b[^\[\]\n]{0,80})\](?!\()/gi, '<span class="cite">$1</span>');
    s = s.replace(/\u0002(\d+)\u0002/g, function (m, i) { return links[+i]; });
    s = s.replace(/\u0005(\d+)\u0005/g, function (m, i) { return esc(escs[+i]); });
    s = s.replace(/\u0004(\d+)\u0004/g, function (m, i) { return maths[+i]; });
    s = s.replace(/\u0001(\d+)\u0001/g, function (m, i) { return '<code>' + esc(codes[+i]) + '</code>'; });
    return s;
  }

  function mdList(items) {
    var html = '', stack = [];
    items.forEach(function (it) {
      var tag = it.ordered ? 'ol' : 'ul';
      while (stack.length && it.indent < stack[stack.length - 1].indent) html += '</li></' + stack.pop().tag + '>';
      if (!stack.length || it.indent > stack[stack.length - 1].indent) {
        html += '<' + tag + (it.ordered && it.start !== 1 ? ' start="' + it.start + '"' : '') + '>';
        stack.push({ indent: it.indent, tag: tag });
      } else {
        html += '</li>';
        if (stack[stack.length - 1].tag !== tag) {
          html += '</' + stack.pop().tag + '><' + tag + '>';
          stack.push({ indent: it.indent, tag: tag });
        }
      }
      html += '<li>' + it.text.split('\n').map(mdInline).join('<br>');
    });
    while (stack.length) html += '</li></' + stack.pop().tag + '>';
    return html;
  }

  var LIST_RE = /^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/;
  var HR_RE = /^\s*([-*_])(\s*\1){2,}\s*$/;
  var SEP_RE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

  function isBlockStart(l) {
    return /^\s*#{1,6}\s/.test(l) || /^\s*>/.test(l) || LIST_RE.test(l) || /^\s*\|/.test(l) ||
      /^\u0003\d+\u0003$/.test(l.trim()) || HR_RE.test(l);
  }

  function mdBlocks(src, blocks) {
    var lines = src.split('\n'), out = [], i = 0, m;
    while (i < lines.length) {
      var line = lines[i], t = line.trim();
      if (!t) { i++; continue; }
      if ((m = t.match(/^\u0003(\d+)\u0003$/))) { out.push(blocks[+m[1]]); i++; continue; }
      if ((m = line.match(/^\s*(#{1,6})\s+(.*?)\s*#*\s*$/))) {
        out.push('<h' + m[1].length + '>' + mdInline(m[2]) + '</h' + m[1].length + '>'); i++; continue;
      }
      if (HR_RE.test(line)) { out.push('<hr>'); i++; continue; }
      if (/^\s*>/.test(line)) {
        var quote = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) { quote.push(lines[i].replace(/^\s*>\s?/, '')); i++; }
        out.push('<blockquote>' + mdBlocks(quote.join('\n'), blocks) + '</blockquote>');
        continue;
      }
      if (/^\s*\|/.test(line) && i + 1 < lines.length && SEP_RE.test(lines[i + 1]) && lines[i + 1].indexOf('-') !== -1) {
        var cells = function (r) { return r.trim().replace(/^\|/, '').replace(/\|\s*$/, '').split('|').map(function (c) { return c.trim(); }); };
        var head = cells(line);
        var align = cells(lines[i + 1]).map(function (c) { return /^:-+:$/.test(c) ? 'center' : /-:$/.test(c) ? 'right' : ''; });
        var cell = function (tag, v, k) {
          return '<' + tag + (align[k] ? ' style="text-align:' + align[k] + '"' : '') + '>' + mdInline(v || '') + '</' + tag + '>';
        };
        i += 2;
        var rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(cells(lines[i])); i++; }
        out.push('<div class="table-wrap"><table><thead><tr>' +
          head.map(function (h, k) { return cell('th', h, k); }).join('') + '</tr></thead><tbody>' +
          rows.map(function (r) { return '<tr>' + head.map(function (_, k) { return cell('td', r[k], k); }).join('') + '</tr>'; }).join('') +
          '</tbody></table></div>');
        continue;
      }
      if (LIST_RE.test(line)) {
        var items = [];
        while (i < lines.length) {
          var l = lines[i], mm = l.match(LIST_RE);
          if (mm) {
            items.push({ indent: mm[1].replace(/\t/g, '    ').length, ordered: /\d/.test(mm[2]), start: parseInt(mm[2], 10) || 1, text: mm[3] });
            i++; continue;
          }
          if (l.trim() && /^\s{2,}/.test(l) && items.length && !/^\u0003/.test(l.trim())) {
            items[items.length - 1].text += '\n' + l.trim(); i++; continue;
          }
          if (!l.trim()) {
            var j = i + 1;
            while (j < lines.length && !lines[j].trim()) j++;
            if (j < lines.length && LIST_RE.test(lines[j])) { i = j; continue; }
          }
          break;
        }
        out.push(mdList(items));
        continue;
      }
      var para = [];
      while (i < lines.length && lines[i].trim() && !(para.length && isBlockStart(lines[i]))) { para.push(lines[i].trim()); i++; }
      out.push('<p>' + para.map(function (p) { return mdInline(p); }).join('<br>') + '</p>');
    }
    return out.join('');
  }

  // live = the answer is still arriving (unfinished code blocks can't be run yet)
  function renderMarkdown(src, live) {
    src = String(src || '').replace(/\r\n?/g, '\n').replace(/[\u0001-\u0005]/g, '');
    var blocks = [];
    var keep = function (html) { blocks.push(html); return '\u0003' + (blocks.length - 1) + '\u0003'; };
    src = src.replace(/(^|\n)([ \t]*)(`{3,})([^\n`]*)(?:\n([\s\S]*?))?(?:(\n[ \t]*\3`*[ \t]*)(?=\n|$)|$)/g,
      function (m, pre, indent, fence, info, code, close, offset, whole) {
        code = code || '';
        if (indent) code = code.replace(new RegExp('^[ \\t]{1,' + indent.length + '}', 'gm'), '');
        var before = whole.slice(Math.max(0, offset - 400), offset).split('\n'), prev = '';
        for (var k = before.length - 1; k >= 0; k--) { if (before[k].trim()) { prev = before[k].trim(); break; } }
        return pre + keep(codeBlockHtml(code, info, prev, !!close || !live));
      });
    var mathBlock = function (m, pre, tex) { return pre + keep('<div class="math-block">' + renderMath(tex.trim(), true) + '</div>'); };
    src = src.replace(/(^|\n)[ \t]*\$\$([\s\S]{1,6000}?)\$\$[ \t]*(?=\n|$)/g, mathBlock);
    src = src.replace(/(^|\n)[ \t]*\\\[([\s\S]{1,6000}?)\\\][ \t]*(?=\n|$)/g, mathBlock);
    return mdBlocks(src, blocks);
  }
  /* ==MARKDOWN-END== */

  /* ---------------------------------------------------------------- helpers */
  var $ = function (sel) { return document.querySelector(sel); };
  var each = function (list, fn) { Array.prototype.forEach.call(list, fn); };
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } }
  };
  var session = {
    get: function (k) { try { return sessionStorage.getItem(k) || ''; } catch (e) { return ''; } },
    set: function (k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* ignore */ } }
  };
  function initials(name) {
    var w = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!w.length || /^my ai$/i.test(w.join(' '))) return 'AI';
    return (w.length === 1 ? w[0].slice(0, 2) : w[0][0] + w[1][0]).toUpperCase();
  }
  function fmtSize(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return Math.round(b / 1024) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
  }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
  var toastTimer;
  function toast(msg, kind) {
    var t = $('#toast'), err = kind === 'error';
    t.textContent = msg;
    t.className = 'toast show' + (err ? ' error' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = 'toast' + (err ? ' error' : ''); }, err ? 6500 : 3200);
  }
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      var copied = false;
      return Promise.race([
        navigator.clipboard.writeText(text).then(function () { copied = true; }),
        new Promise(function (resolve) { setTimeout(resolve, 800); })
      ]).catch(function () { /* blocked: use the fallback */ }).then(function () { if (!copied) fallbackCopy(text); });
    }
    fallbackCopy(text);
    return Promise.resolve();
  }
  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) { /* ignore */ }
    ta.remove();
  }
  function flash(btn, text) {
    var old = btn.getAttribute('data-label') || btn.textContent;
    btn.setAttribute('data-label', old);
    btn.textContent = text;
    setTimeout(function () { btn.textContent = old; }, 1500);
  }
  function downloadText(name, text, type) {
    var url = URL.createObjectURL(new Blob([text], { type: (type || 'text/plain') + ';charset=utf-8' }));
    var a = document.createElement('a');
    a.href = url; a.download = name; a.style.display = 'none';
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 1500);
  }
  function fence(text, lang) {
    var f = '```';
    while (text.indexOf(f) !== -1) f += '`';
    return f + (lang || '') + '\n' + text + '\n' + f;
  }
  function langFromName(name) {
    var ext = String(name || '').split('.').pop().toLowerCase();
    return LANG_ALIAS[ext] || (EXT_FOR[ext] ? ext : (/^[a-z0-9]{1,10}$/.test(ext) ? ext : ''));
  }

  var SEND_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
  var STOP_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2.5"/></svg>';
  var X_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  var BADGE = { pdf: '#e5484d', docx: '#2f6fed', pptx: '#e8590c', xlsx: '#1f9d55', xlsm: '#1f9d55', csv: '#0f9b8e', tsv: '#0f9b8e',
    txt: '#6b7088', md: '#4b5563', markdown: '#4b5563', json: '#b7791f', html: '#8b5cf6', htm: '#8b5cf6' };

  /* ------------------------------------------------------------------ state */
  var S = { status: null, files: [], chat: store.get('myai.chat', []), streaming: false, controller: null, stick: true, attachments: [], engine: 'auto', ready: [] };

  function visitorId() {
    var v = store.get('myai.visitor', '');
    if (!v) {
      v = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : 'v-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      store.set('myai.visitor', v);
    }
    return v;
  }

  function api(path, opts, retried) {
    opts = opts || {};
    var headers = Object.assign({}, opts.headers || {});
    headers['X-Visitor'] = visitorId();
    var pw = session.get('myai.admin');
    if (pw) headers['X-Admin-Password'] = pw;
    var ek = engineKeys();
    if (Object.keys(ek).length) headers['X-Engine-Keys'] = JSON.stringify(ek);
    return fetch(path, Object.assign({}, opts, { headers: headers })).then(function (res) {
      if (res.status === 401 && !retried) {
        var p = window.prompt('This AI is protected. Enter the admin password:');
        if (p) { session.set('myai.admin', p); return api(path, opts, true); }
      }
      return res.json().catch(function () { return null; }).then(function (data) {
        if (!res.ok) throw new Error((data && data.detail) || ('Error ' + res.status));
        return data;
      });
    });
  }

  function keys() { return store.get('myai.keys', {}); }
  function getKey(provider) {
    var p = provider || (S.status && S.status.config.provider);
    return String(keys()[p] || '').trim();
  }
  function setKey(provider, value) {
    var k = keys();
    if (value) k[provider] = value; else delete k[provider];
    store.set('myai.keys', k);
  }
  /* ------------------------------------------------- free allowance & paywall */
  function refreshUsage() {
    return api('api/usage').then(function (u) {
      S.usage = u;
      var pill = $('#usagePill');
      if (!pill) return;
      if (!u.enabled && !u.admin) { pill.hidden = true; return; }
      pill.hidden = false;
      if (u.admin) { pill.textContent = u.owner_lifetime ? '\ud83d\udc51 Owner \u00b7 lifetime' : ' Owner'; pill.title = 'Owner account \u2014 activated for life. No limits, no paywall, ever.'; }
      else if (u.subscribed) {
        pill.textContent = '⭐ ' + (u.plan || 'Plus');
        pill.title = u.sub_until ? 'Subscribed until ' + new Date(u.sub_until * 1000).toDateString() : 'Subscribed';
      } else if (u.left_prompts !== null) {
        pill.textContent = 'Free · ' + u.left_prompts + ' question' + (u.left_prompts === 1 ? '' : 's') + ' left';
        pill.title = u.free_prompts + ' free questions and about ' +
          Math.round(u.free_tokens / 1000) + 'k free tokens per visitor';
      } else { pill.textContent = 'Free'; }
    }).catch(function () { /* offline: keep the old numbers */ });
  }

  function cur(sym) { return ({ ZAR: 'R', USD: '$', EUR: '€', GBP: '£' })[sym] || (sym + ' '); }

  function paywallHtml(q) {
    var per = q.interval === 'year' ? '/year' : q.interval === 'week' ? '/week' : '/month';
    var h = '<div class="paywall"><div class="pw-head">🔒 Your free allowance is used up</div>' +
      '<p class="pw-sub">You asked ' + q.prompts_used + ' free question' + (q.prompts_used === 1 ? '' : 's') +
      (q.reason === 'tokens' ? ' and reached the free token limit' : '') +
      '. Continue with ' + esc(q.plan || 'the subscription') + ':</p>' +
      '<div class="pw-plan"><b>' + esc(q.plan || 'Subscription') + '</b>' +
      '<span class="pw-price">' + cur(q.currency) + esc(q.price) + '<span>' + per + '</span></span></div>' +
      '<ul class="pw-list"><li>Unlimited questions - coding, engineering, cybersecurity</li>' +
      '<li>Every connected AI engine and your files</li>' +
      '<li>Voice answers, code runner and previews included</li></ul>';
    if (q.providers && (q.providers.stripe || q.providers.paystack)) {
      h += '<div class="pw-row"><input class="input" data-pw="email" type="email" ' +
        'placeholder="your@email.com (for the receipt)">' +
        (q.providers.stripe ? '<button class="btn small primary" type="button" data-pw="stripe">Pay by card</button>' : '') +
        (q.providers.paystack ? '<button class="btn small primary" type="button" data-pw="paystack">Pay with Paystack</button>' : '') +
        '</div>';
    }
    if (q.providers && q.providers.manual) {
      h += '<div class="pw-row"><button class="btn small" type="button" data-pw="manual">' +
        (q.bank && q.bank.account_number ? 'Pay by bank transfer (EFT)' : 'Get payment details') +
        '</button></div><div data-pw="bankbox"></div>';
    }
    h += '<div class="pw-row"><input class="input" data-pw="coupon" placeholder="Coupon code">' +
      '<button class="btn small" type="button" data-pw="coupon-go">Redeem</button>' +
      '<button class="btn small" type="button" data-pw="refresh">I\'m subscribed - check again</button></div>' +
      '<div class="pw-row"><input class="input" data-pw="owner" type="password" ' +
      'placeholder="Owner? Enter your admin password">' +
      '<button class="btn small" type="button" data-pw="owner-go">Unlock as owner</button></div>' +
      (q.pay_note ? '<div class="pw-note">' + esc(q.pay_note) + '</div>' : '') +
      '<div class="pw-status" data-pw="status"></div></div>';
    return h;
  }

  function pwStatus(card, msg, kind) {
    var el = card.querySelector('[data-pw="status"]');
    if (el) { el.textContent = msg; el.className = 'pw-status ' + (kind || ''); }
  }

  function bindPaywall(card, q) {
    each(card.querySelectorAll('[data-pw]'), function (el) {
      if (el.tagName !== 'BUTTON') return;
      el.addEventListener('click', function () {
        var kind = el.getAttribute('data-pw'), status = card.querySelector('[data-pw="status"]');
        if (kind === 'stripe' || kind === 'paystack') {
          var email = (card.querySelector('[data-pw="email"]') || {}).value || '';
          pwStatus(card, 'Opening the secure payment page…');
          api('api/billing/checkout', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: kind, email: email.trim() })
          }).then(function (d) {
            window.open(d.url, '_blank', 'noopener');
            pwStatus(card, 'Finish the payment in the new tab, then press “I\'m subscribed - check again”.', 'ok');
          }).catch(function (e) { pwStatus(card, e.message, 'bad'); });
        } else if (kind === 'manual') {
          pwStatus(card, 'Fetching your payment reference…');
          api('api/billing/paid', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(function (d) {
              var box = card.querySelector('[data-pw="bankbox"]');
              if (box) {
                box.innerHTML = '<div class="pw-bank">' +
                  '<b>Bank</b><span>' + esc(d.bank.bank || '-') + '</span>' +
                  '<b>Account name</b><span>' + esc(d.bank.account_name || '-') + '</span>' +
                  '<b>Account number</b><code>' + esc(d.bank.account_number || '-') + '</code>' +
                  '<b>Branch</b><code>' + esc(d.bank.branch || '-') + '</code>' +
                  '<b>Amount</b><span>' + cur(d.currency) + esc(d.amount) + '</span>' +
                  '<b>Reference</b><code>' + esc(d.ref) + '</code></div>' +
                  '<div class="pw-note">Use the reference exactly as shown so the owner can match ' +
                  'your payment. It is confirmed by hand - usually within a day.</div>';
              }
              pwStatus(card, 'Now press “I\'m subscribed - check again” after you\'ve paid.', 'ok');
            }).catch(function (e) { pwStatus(card, e.message, 'bad'); });
        } else if (kind === 'coupon-go') {
          var code = (card.querySelector('[data-pw="coupon"]') || {}).value || '';
          api('api/billing/coupon', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code }) })
            .then(function (d) {
              pwStatus(card, 'Code accepted - unlocked for ' + d.days + ' days. Ask away!', 'ok');
              refreshUsage().then(function () { renderThread(); });
            }).catch(function (e) { pwStatus(card, e.message, 'bad'); });
        } else if (kind === 'refresh') {
          pwStatus(card, 'Checking…');
          refreshUsage().then(function () {
            if (S.usage && S.usage.subscribed) { renderThread(); toast('Subscription active ✓ Welcome back!'); }
            else pwStatus(card, 'No active subscription found yet for this browser.', 'bad');
          });
        } else if (kind === 'owner-go') {
          var pwv = ((card.querySelector('[data-pw="owner"]') || {}).value || '').trim();
          if (!pwv) { pwStatus(card, 'Type your admin password first.', 'bad'); return; }
          pwStatus(card, 'Checking…');
          session.set('myai.admin', pwv);
          refreshUsage().then(function () {
            if (S.usage && S.usage.admin) {
              renderThread();
              toast('👑 Owner unlocked - activated for life on this device.');
            } else {
              session.set('myai.admin', '');
              pwStatus(card, 'That password was not accepted. Check caps lock and try again.', 'bad');
            }
          });
        }
      });
    });
  }

  /* ---------------------------------------------------- owner billing dashboard */
  function loadDashboard() {
    var box = $('#billDash');
    if (!box) return;
    box.hidden = false;
    box.innerHTML = '<div class="help">Loading…</div>';
    api('api/billing/admin').then(function (d) {
      var h = '<div class="dash-stats">' +
        '<span class="dstat"><b>' + d.visitors + '</b> visitors (' + d.new_today + ' new today)</span>' +
        '<span class="dstat"><b>' + d.prompts + '</b> questions (' + d.prompts_today + ' today)</span>' +
        '<span class="dstat"><b>' + Math.round((d.tokens || 0) / 1000) + 'k</b> tokens</span>' +
        '<span class="dstat"><b>' + d.blocked_prompts + '</b> hit the paywall</span>' +
        '<span class="dstat"><b>' + d.active_subs + '</b> active subscriptions</span>' +
        (d.revenue || []).map(function (r) {
          return '<span class="dstat"><b>' + cur(r.currency) + r.total + '</b> earned (' + r.payments + ' paid)</span>';
        }).join('') + '</div>';
      h += '<div class="lbl" style="margin-top:8px">Payments waiting for confirmation</div>';
      if (!(d.pending || []).length) h += '<div class="help">Nothing waiting.</div>';
      else {
        h += '<table class="dash-tbl"><tr><th>Visitor</th><th>Amount</th><th>Reference</th><th>When</th><th></th></tr>' +
          d.pending.map(function (p) {
            return '<tr><td><code>' + esc(p.visitor_id.slice(0, 10)) + '</code></td><td>' +
              cur(p.currency) + esc(p.amount) + '</td><td><code>' + esc(p.ref) + '</code></td><td>' +
              new Date(p.created * 1000).toLocaleDateString() + '</td><td>' +
              '<button class="btn small" type="button" data-appr="' + esc(p.id) + '">Approve</button> ' +
              '<button class="btn small" type="button" data-rej="' + esc(p.id) + '">Reject</button></td></tr>';
          }).join('') + '</table>';
      }
      h += '<div class="lbl" style="margin-top:10px">Coupons</div>' +
        '<div class="row"><input class="input" id="cpDays" type="number" value="30" min="1" style="max-width:90px" title="Days free">' +
        '<input class="input" id="cpCode" placeholder="code (blank = random)" style="max-width:160px">' +
        '<input class="input" id="cpUses" type="number" value="1" min="0" style="max-width:80px" title="Max uses, 0 = unlimited">' +
        '<button class="btn small" type="button" id="cpMake">Create</button></div>';
      if ((d.coupons || []).length) {
        h += '<table class="dash-tbl"><tr><th>Code</th><th>Days</th><th>Used</th></tr>' + d.coupons.map(function (cp) {
          return '<tr><td><code>' + esc(cp.code) + '</code></td><td>' + cp.days + '</td><td>' + cp.uses +
            (cp.max_uses ? '/' + cp.max_uses : '') + '</td></tr>';
        }).join('') + '</table>';
      }
      h += '<div class="lbl" style="margin-top:10px">Give someone access</div>' +
        '<div class="row"><input class="input" id="grVisitor" placeholder="visitor id (from the table above)">' +
        '<input class="input" id="grDays" type="number" value="30" min="1" style="max-width:90px">' +
        '<button class="btn small" type="button" id="grGo">Grant days</button></div>';
      box.innerHTML = h;
      each(box.querySelectorAll('[data-appr]'), function (b) {
        b.addEventListener('click', function () {
          api('api/billing/admin/approve', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payment_id: b.getAttribute('data-appr') }) })
            .then(function () { toast('Approved - the visitor is subscribed.'); loadDashboard(); })
            .catch(function (e) { toast(e.message, 'error'); });
        });
      });
      each(box.querySelectorAll('[data-rej]'), function (b) {
        b.addEventListener('click', function () {
          api('api/billing/admin/reject', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payment_id: b.getAttribute('data-rej') }) })
            .then(function () { toast('Rejected.'); loadDashboard(); })
            .catch(function (e) { toast(e.message, 'error'); });
        });
      });
      var make = box.querySelector('#cpMake');
      if (make) make.addEventListener('click', function () {
        api('api/billing/admin/coupon', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ days: Number(box.querySelector('#cpDays').value) || 30,
            code: box.querySelector('#cpCode').value.trim(),
            max_uses: Number(box.querySelector('#cpUses').value) || 0 }) })
          .then(function (cp) { toast('Coupon ' + cp.code + ' created (' + cp.days + ' days).'); loadDashboard(); })
          .catch(function (e) { toast(e.message, 'error'); });
      });
      var gr = box.querySelector('#grGo');
      if (gr) gr.addEventListener('click', function () {
        api('api/billing/admin/grant', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ visitor: box.querySelector('#grVisitor').value.trim(),
            days: Number(box.querySelector('#grDays').value) || 30 }) })
          .then(function () { toast('Granted.'); loadDashboard(); })
          .catch(function (e) { toast(e.message, 'error'); });
      });
    }).catch(function (e) { box.innerHTML = '<div class="test-result bad">' + esc(e.message) + '</div>'; });
  }

  /* ------------------------------------------- other AIs (connectors / engines) */
  function engineSpecs() { return (S.status && S.status.engines) || {}; }
  function engineCfgs() { return (S.status && S.status.config && S.status.config.engines) || {}; }
  function engineOrder() { return (S.status && S.status.engine_order) || []; }
  function engineKeys() {
    var k = store.get('myai.enginekeys', {}), out = {};
    Object.keys(k).forEach(function (id) { if (k[id]) out[id] = k[id]; });
    return out;
  }
  function getEngineKey(id) { return String(store.get('myai.enginekeys', {})[id] || '').trim(); }
  function setEngineKey(id, value) {
    var k = store.get('myai.enginekeys', {});
    if (value) k[id] = value; else delete k[id];
    store.set('myai.enginekeys', k);
  }
  function engineReady(id) {
    var c = engineCfgs()[id];
    if (!c || !c.enabled || !c.url) return false;
    var spec = engineSpecs()[id] || {};
    if (spec.kind === 'openai' && !c.model) return false;
    if (spec.kind === 'dify' && !c.has_key && !getEngineKey(id)) return false;
    return true;
  }
  function refreshEngines() {
    S.ready = engineOrder().filter(function (id) { return id !== 'main' && engineReady(id); });
    renderEngineStrip();
  }
  function engineLabel(id) {
    var spec = engineSpecs()[id] || {};
    return (spec.icon || '🔌') + ' ' + (spec.short || id);
  }

  function renderEngineStrip() {
    var strip = $('#engineStrip');
    if (!strip) return;
    var specs = engineSpecs();
    var items = [{ id: 'auto', label: '✨ Auto', title: 'Pick the best AI for each question automatically' },
                 { id: 'main', label: '🧠 My AI', title: 'Your AI itself: its own brain, your files, coding, engineering and cybersecurity' }];
    engineOrder().forEach(function (id) {
      if (id === 'main') return;
      if (!engineReady(id)) return;
      var c = engineCfgs()[id] || {};
      items.push({ id: id, label: engineLabel(id) + (c.model ? ' · ' + c.model : ''),
                   title: (specs[id] || {}).blurb || '' });
    });
    var extras = engineOrder().filter(function (id) { return id !== 'main' && !engineReady(id); }).length;
    items.push({ id: '__add', label: '⚙ ' + (extras ? 'Connect more (' + extras + ')' : 'Connectors'),
                 title: 'Open Settings → Connectors' });

    strip.innerHTML = items.map(function (it) {
      return '<button class="ebtn' + (S.engine === it.id ? ' on' : '') + (it.id === '__add' ? ' add' : '') +
        '" type="button" data-e="' + esc(it.id) + '" title="' + esc(it.title) + '">' + esc(it.label) + '</button>';
    }).join('');
    strip.hidden = false;
    each(strip.querySelectorAll('.ebtn'), function (b) {
      b.addEventListener('click', function () {
        var id = b.getAttribute('data-e');
        if (id === '__add') { openSettings('connectors'); return; }
        S.engine = id;
        renderEngineStrip();
        toast(id === 'auto' ? 'I’ll pick the best AI for each question.'
          : id === 'main' ? 'I’ll answer everything myself.'
          : 'Next answers come from ' + ((engineSpecs()[id] || {}).label || id) + '.');
      });
    });
  }

  /* Voice replies from Open-LLM-VTuber: play them one after another. */
  var voiceQueue = Promise.resolve();
  function b64ToBlob(b64, mime) {
    var bin = atob(b64), len = bin.length, bytes = new Uint8Array(len);
    for (var i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime || 'audio/wav' });
  }
  function playVoice(b64, mime) {
    if (!b64) return;
    voiceQueue = voiceQueue.then(function () {
      return new Promise(function (done) {
        try {
          var url = URL.createObjectURL(b64ToBlob(b64, mime));
          var a = new Audio(url);
          a.addEventListener('ended', function () { URL.revokeObjectURL(url); done(); });
          a.addEventListener('error', function () { URL.revokeObjectURL(url); done(); });
          a.play().catch(function () { URL.revokeObjectURL(url); done(); });
        } catch (e) { done(); }
      });
    });
  }
  function voiceRow(text) {
    return '<div class="voice-row"><span class="vn">🔊 Voice reply</span>' +
      (text ? '<span>' + esc(text) + '</span>' : '') + '</div>';
  }

  /* -------------------------------------------------- connectors in Settings */
  var MODEL_SUGGESTIONS = {
    ollama: ['llama3.2', 'qwen2.5', 'mistral', 'phi3'],
    orca: ['orca-mini', 'orca-mini:3b', 'orca-mini:7b', 'orca-mini:13b'],
    free: ['openrouter/auto', 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b', 'meta-llama/llama-3.3-70b-instruct:free'],
    custom2: []
  };

  function renderConnectors() {
    var list = $('#connList');
    if (!list || !S.status) return;
    var specs = engineSpecs(), cfgs = engineCfgs();
    var intro = $('#connIntro');
    if (intro) {
      intro.innerHTML = 'Your AI answers by itself. You can also connect other AIs and it will hand work to them — ' +
        'automatically when the question fits, or whenever you click their button above the message box. ' +
        '<b>' + S.ready.length + '</b> connected right now.';
    }
    var ids = engineOrder().filter(function (id) { return id !== 'main'; });
    list.innerHTML = ids.map(function (id) {
      var spec = specs[id] || {}, c = cfgs[id] || { enabled: false, url: '', model: '', has_key: false, extra: {} };
      var kind = spec.kind;
      var needKey = kind !== 'vtuber';
      var noKey = kind === 'ollama' || kind === 'vtuber';
      var models = MODEL_SUGGESTIONS[id] || [];
      var body = '';
      body += '<div class="field"><label class="lbl" for="eurl-' + id + '">Address</label>' +
        '<input class="input" id="eurl-' + id + '" data-e="' + id + '" data-f="url" spellcheck="false" ' +
        'placeholder="' + esc(spec.url_hint || 'http://127.0.0.1') + '" value="' + esc(c.url || '') + '"></div>';
      if (kind !== 'vtuber') {
        body += '<div class="field"><label class="lbl" for="emodel-' + id + '">' +
          (kind === 'openhands' ? 'Agent (model)' : 'Model') + '</label>' +
          '<input class="input" id="emodel-' + id + '" data-e="' + id + '" data-f="model" spellcheck="false" ' +
          'placeholder="' + esc(kind === 'openhands' ? 'openhands_myprofile' : (models[0] || 'model name')) + '" value="' + esc(c.model || '') + '">' +
          (models.length ? '<div class="chipset">' + models.map(function (m) {
            return '<button class="mchip" type="button" data-m="' + esc(m) + '" data-e="' + id + '">' + esc(m) + '</button>';
          }).join('') + '</div>' : '') + '</div>';
      }
      var ollamaish = spec.profile === 'ollama' || spec.profile === 'orca';
      if (needKey && !noKey) {
        body += '<div class="field"><label class="lbl" for="ekey-' + id + '">API key' +
          (ollamaish ? ' <span style="font-weight:400;color:var(--muted)">(optional — Ollama doesn’t need one)</span>' : '') +
          (c.has_key ? ' <span style="font-weight:400;color:var(--ok)">· saved ✓</span>' : '') + '</label>' +
          '<div class="row"><input class="input" id="ekey-' + id + '" data-e="' + id + '" data-f="key" type="password" ' +
          'autocomplete="off" spellcheck="false" placeholder="' + (c.has_key ? 'Saved. Type a new one to replace it.' : 'Paste the key') + '">' +
          '<button class="btn small" type="button" data-clearkey="' + id + '">Clear</button></div></div>';
      }
      if (id === 'dify') {
        body += '<div class="field"><label class="lbl" for="euser-dify">Dify user id</label>' +
          '<input class="input" id="euser-dify" data-e="dify" data-f="extra.user" value="' +
          esc((c.extra && c.extra.user) || 'my-ai') + '">' +
          '<div class="help">Any name; Dify uses it to keep conversations apart.</div></div>';
      }
      body += '<div class="row"><button class="btn small" type="button" data-test="' + id + '">Test</button>' +
        (spec.url_hint ? '<span class="help" style="margin:0">default: <code>' + esc(spec.url_hint) + '</code></span>' : '') +
        (spec.docs ? '<a class="help" style="margin:0" href="' + esc(spec.docs) + '" target="_blank" rel="noopener">docs ↗</a>' : '') +
        '</div><div class="test-result" id="etest-' + id + '" hidden></div>';

      return '<div class="conn' + (c.enabled ? ' on' : '') + '" data-c="' + id + '">' +
        '<div class="conn-head" data-head="' + id + '">' +
        '<span class="conn-ico">' + (spec.icon || '🔌') + '</span>' +
        '<span class="conn-title"><b>' + esc(spec.label || id) + '</b><small>' + esc(spec.blurb || '') + '</small></span>' +
        '<span class="conn-dot" id="edot-' + id + '"></span>' +
        '<button class="switch" type="button" role="switch" aria-checked="' + (c.enabled ? 'true' : 'false') +
        '" data-toggle="' + id + '" aria-label="Switch on ' + esc(spec.short || id) + '"></button>' +
        '</div>' +
        (c.enabled ? '<div class="conn-body">' + body + '</div>' : '') +
        '</div>';
    }).join('');

    // free providers helper table
    var fp = (S.status && S.status.free_providers) || [];
    if (fp.length) {
      var tbl = document.createElement('div');
      tbl.className = 'conn';
      tbl.innerHTML = '<div class="conn-head"><span class="conn-ico">🆓</span>' +
        '<span class="conn-title"><b>Where to get a free key</b><small>Paste the address and model into the connector above.</small></span></div>' +
        '<div class="conn-body"><table class="free-tbl"><tbody>' + fp.map(function (f, i) {
          return '<tr><td class="fname">' + esc(f.name) + '</td><td class="ffree">' + esc(f.free || '') + '</td>' +
            '<td><button class="btn small" type="button" data-free="' + i + '">Use</button>' +
            (f.key_url ? ' <a class="help" href="' + esc(f.key_url) + '" target="_blank" rel="noopener" style="margin:0">key ↗</a>' : '') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
      list.appendChild(tbl);
      each(tbl.querySelectorAll('[data-free]'), function (b) {
        b.addEventListener('click', function () {
          var f = fp[+b.getAttribute('data-free')];
          var target = f.base_url.indexOf('11434') !== -1 ? 'orca' : 'free';
          setConnField(target, 'url', f.base_url);
          if (f.model) setConnField(target, 'model', f.model);
          var card = list.querySelector('[data-c="' + target + '"]');
          if (card && !card.classList.contains('on')) toggleConn(target, true);
          toast(f.name + ' filled into ' + ((specs[target] || {}).short || target) + '. Add your key and press Test.');
        });
      });
    }

    each(list.querySelectorAll('[data-toggle]'), function (b) {
      b.addEventListener('click', function (e) {
        e.stopPropagation();
        toggleConn(b.getAttribute('data-toggle'), b.getAttribute('aria-checked') !== 'true');
      });
    });
    each(list.querySelectorAll('[data-head]'), function (h) {
      h.addEventListener('click', function (e) {
        if (e.target.closest('[data-toggle]')) return;
        var id = h.getAttribute('data-head');
        var c = engineCfgs()[id] || {};
        toggleConn(id, !c.enabled);
      });
    });
    each(list.querySelectorAll('[data-m]'), function (b) {
      b.addEventListener('click', function () { setConnField(b.getAttribute('data-e'), 'model', b.getAttribute('data-m')); });
    });
    each(list.querySelectorAll('[data-test]'), function (b) {
      b.addEventListener('click', function () { testConn(b.getAttribute('data-test')); });
    });
    each(list.querySelectorAll('[data-clearkey]'), function (b) {
      b.addEventListener('click', function () {
        var id = b.getAttribute('data-clearkey');
        setEngineKey(id, '');
        var input = list.querySelector('#ekey-' + id);
        if (input) { input.value = ''; input.placeholder = 'Paste the key'; }
        connDraft[id] = connDraft[id] || {};
        connDraft[id].key = '';
        connDraft[id].clear_key = true;
        toast('Key for ' + ((specs[id] || {}).short || id) + ' will be removed when you Save.');
      });
    });
  }

  var connDraft = {};     // unsaved connector edits, per engine

  function setConnField(id, field, value) {
    var input = document.querySelector('#connList [data-e="' + id + '"][data-f="' + field + '"]');
    if (input) { input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); }
    connDraft[id] = connDraft[id] || {};
    connDraft[id][field] = value;
  }

  function toggleConn(id, on) {
    connDraft[id] = connDraft[id] || {};
    connDraft[id].enabled = on;
    var cfgs = engineCfgs();
    cfgs[id] = Object.assign({}, cfgs[id], connDraft[id]);
    renderConnectors();
    refreshEngines();
  }

  function collectConns() {
    var out = {};
    each(document.querySelectorAll('#connList [data-e][data-f]'), function (el) {
      var id = el.getAttribute('data-e'), f = el.getAttribute('data-f'), v = (el.value || '').trim();
      out[id] = out[id] || {};
      if (f.indexOf('extra.') === 0) {
        out[id].extra = out[id].extra || {};
        out[id].extra[f.slice(6)] = v;
      } else if (f === 'key') {
        if (v) { out[id].key = v; setEngineKey(id, v); }
        else if (connDraft[id] && connDraft[id].clear_key) { out[id].key = ''; out[id].clear_key = true; }
      } else {
        out[id][f] = v;
      }
    });
    Object.keys(connDraft).forEach(function (id) {
      out[id] = Object.assign({}, connDraft[id], out[id] || {});
      if (out[id].key === '' && !out[id].clear_key) delete out[id].key;
      delete out[id].clear_key;
    });
    return out;
  }

  function testConn(id) {
    var box = document.getElementById('etest-' + id), dot = document.getElementById('edot-' + id);
    if (!box) return;
    var input = document.querySelector('#connList [data-e="' + id + '"][data-f="url"]');
    var model = document.querySelector('#connList [data-e="' + id + '"][data-f="model"]');
    var keyEl = document.querySelector('#connList [data-e="' + id + '"][data-f="key"]');
    box.hidden = false;
    box.className = 'test-result info';
    box.textContent = 'Testing…';
    var headers = { 'Content-Type': 'application/json' };
    if (keyEl && keyEl.value.trim()) headers['X-Key-' + id] = keyEl.value.trim();
    else if (getEngineKey(id)) headers['X-Key-' + id] = getEngineKey(id);
    api('api/engines/check', {
      method: 'POST', headers: headers,
      body: JSON.stringify({ engine: id, url: input ? input.value.trim() : '', model: model ? model.value.trim() : '' })
    }).then(function (d) {
      box.className = 'test-result ' + (d.ok ? 'ok' : 'bad');
      box.textContent = (d.ok ? '✓ ' : '✗ ') + (d.detail || '');
      if (dot) dot.className = 'conn-dot ' + (d.ok ? 'ok' : 'bad');
      if (d.ok && d.models && d.models.length && model) {
        var have = d.models.indexOf(model.value.trim()) !== -1;
        if (!have) { model.value = d.models[0]; setConnField(id, 'model', d.models[0]); }
      }
    }).catch(function (e) {
      box.className = 'test-result bad';
      box.textContent = '✗ ' + e.message;
      if (dot) dot.className = 'conn-dot bad';
    });
  }

  function aiName() { return (S.status && S.status.config.name) || 'My AI'; }
  function aiConnected() {
    if (!S.status) return false;
    var c = S.status.config;
    return !!(c.model && c.base_url && (getKey() || S.status.server_key || c.provider === 'ollama'));
  }

  /* ----------------------------------------------------------------- status */
  function setStatus(kind, text) { $('#statusDot').className = 'dot ' + kind; $('#statusText').textContent = text; }

  function refreshStatus() {
    return api('api/status').then(function (st) {
      S.status = st;
      var c = st.config, ok = aiConnected();
      document.title = c.name || 'My AI';
      var cr = $('#creatorCredit');
      if (cr) { cr.textContent = 'created by '; var cb = document.createElement('b'); cb.textContent = c.creator || 'Ruwayne'; cr.appendChild(cb); }
      $('#brandName').textContent = c.name;
      $('#topTitle').textContent = c.name;
      $('#logo').textContent = initials(c.name);
      setStatus(ok ? 'ok' : 'warn', ok ? 'Connected · ' + c.model : 'Search-only · no AI connected');
      $('#modelPill').textContent = ok ? c.model : 'Search-only mode';
      $('#keyBanner').hidden = ok;
      refreshEngines();
    }).catch(function () { setStatus('warn', 'Server not reachable'); });
  }

  /* ------------------------------------------------------------------ files */
  function refreshFiles() {
    return api('api/files').then(function (d) {
      var before = JSON.stringify(S.files);
      S.files = d.files || [];
      if (JSON.stringify(S.files) !== before) {
        renderFiles();
        if (!S.chat.length) renderThread();
      }
    }).catch(function () { /* offline: keep the old list */ });
  }

  function renderFiles() {
    var list = $('#fileList'), uploading = list.querySelector('.file.uploading');
    $('#fileCount').textContent = S.files.length;
    list.innerHTML = '';
    if (uploading) list.appendChild(uploading);
    if (!S.files.length && !uploading) {
      list.innerHTML = '<div class="empty-files">No files yet. Add documents you want your AI to know.</div>';
      return;
    }
    S.files.forEach(function (f) {
      var meta = [];
      if (f.pages && f.unit) meta.push(plural(f.pages, f.unit));
      if (f.chunks) meta.push(plural(f.chunks, 'passage'));
      meta.push(fmtSize(f.size));
      var note = f.error || f.warning;
      var el = document.createElement('div');
      el.className = 'file';
      el.innerHTML =
        '<div class="badge" style="background:' + (BADGE[f.kind] || '#8a8fa8') + '">' + esc((f.kind || 'file').slice(0, 4)) + '</div>' +
        '<div class="file-info"><div class="file-name" title="' + esc(f.name) + '">' + esc(f.name) + '</div>' +
        '<div class="file-meta">' + esc(meta.join(' · ')) + '</div>' +
        (note ? '<div class="file-warn' + (f.error ? ' err' : '') + '">⚠ ' + esc(note) + '</div>' : '') + '</div>' +
        '<button class="del" type="button" title="Remove file" aria-label="Remove ' + esc(f.name) + '">' + X_ICON + '</button>';
      el.querySelector('.del').addEventListener('click', function () { removeFile(f.name); });
      list.appendChild(el);
    });
  }

  function removeFile(name) {
    if (!window.confirm('Remove “' + name + '” from your AI\'s knowledge?')) return;
    api('api/files/' + encodeURIComponent(name), { method: 'DELETE' }).then(function (d) {
      S.files = d.files || [];
      renderFiles();
      if (!S.chat.length) renderThread();
      toast('Removed ' + name);
      refreshStatus();
    }).catch(function (e) { toast(e.message, 'error'); });
  }

  function showUploadRow(text, pct) {
    var list = $('#fileList'), row = list.querySelector('.file.uploading');
    if (!row) {
      row = document.createElement('div');
      row.className = 'file uploading';
      row.innerHTML = '<div class="badge">⇪</div><div class="file-info"><div class="file-name"></div><div class="progress"><div></div></div></div>';
      var empty = list.querySelector('.empty-files');
      if (empty) empty.remove();
      list.insertBefore(row, list.firstChild);
    }
    row.querySelector('.file-name').textContent = text;
    row.querySelector('.progress > div').style.width = (pct || 0) + '%';
  }
  function hideUploadRow() { var row = $('#fileList .file.uploading'); if (row) row.remove(); }

  function upload(fileList) {
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;
    var fd = new FormData();
    files.forEach(function (f) { fd.append('files', f, f.name); });
    showUploadRow('Uploading ' + plural(files.length, 'file') + '…', 2);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', 'api/upload');
    var pw = session.get('myai.admin');
    if (pw) xhr.setRequestHeader('X-Admin-Password', pw);
    xhr.upload.onprogress = function (e) {
      if (!e.lengthComputable) return;
      var pct = Math.round(e.loaded / e.total * 100);
      showUploadRow(pct < 100 ? 'Uploading… ' + pct + '%' : 'Reading your files…', Math.max(pct, 2));
    };
    xhr.onload = function () {
      hideUploadRow();
      if (xhr.status === 401) {
        var p = window.prompt('This AI is protected. Enter the admin password:');
        if (p) { session.set('myai.admin', p); upload(files); }
        return;
      }
      var data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
      if (xhr.status >= 400) { toast(data.detail || 'Upload failed (error ' + xhr.status + ')', 'error'); renderFiles(); return; }
      S.files = data.files || S.files;
      renderFiles();
      if (!S.chat.length) renderThread();
      var saved = data.saved || [], dups = data.duplicates || [], skipped = data.skipped || [], errors = data.errors || [];
      var problems = (data.files || []).filter(function (f) { return saved.indexOf(f.name) !== -1 && (f.warning || f.error); });
      var parts = [];
      if (saved.length) parts.push('Added ' + plural(saved.length, 'file') + ' ✓');
      if (dups.length) parts.push(plural(dups.length, 'file') + (dups.length === 1 ? ' was' : ' were') + ' already there');
      if (skipped.length) parts.push(skipped.length + ' unsupported skipped');
      var msg = parts.join(' · ') || 'Nothing new to add.';
      if (errors.length) toast(errors.join('\n') + (parts.length ? '\n' + msg : ''), 'error');
      else if (problems.length) toast(msg + '\n' + plural(problems.length, 'file') + ' had a problem. See the ⚠ note in the list.', 'error');
      else toast(saved.length ? msg + ' Your AI can use them now.' : msg);
      refreshStatus();
    };
    xhr.onerror = function () { hideUploadRow(); renderFiles(); toast('Upload failed. Check your connection.', 'error'); };
    xhr.send(fd);
  }

  /* ------------------------------------------------- attachments (one message) */
  var IMG_TYPE = /^image\/(png|jpeg|webp|gif)$/;
  var TEXT_MAX = 400000;
  function imageToDataUrl(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file), img = new Image();
      img.onload = function () {
        var w = img.naturalWidth, h = img.naturalHeight, scale = Math.min(1, 2000 / Math.max(w, h, 1));
        if (scale === 1 && file.size <= 1.5 * 1024 * 1024 && file.type !== 'image/gif') {
          URL.revokeObjectURL(url);
          var fr = new FileReader();
          fr.onload = function () { resolve(fr.result); };
          fr.onerror = reject;
          fr.readAsDataURL(file);
          return;
        }
        var c = document.createElement('canvas');
        c.width = Math.max(1, Math.round(w * scale)); c.height = Math.max(1, Math.round(h * scale));
        var g = c.getContext('2d');
        g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
        g.drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL('image/jpeg', 0.88));
      };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('unreadable picture')); };
      img.src = url;
    });
  }

  function addAttachments(fileList) {
    Array.prototype.slice.call(fileList || []).forEach(function (f) {
      var name = f.name || (IMG_TYPE.test(f.type) ? 'pasted-picture.png' : 'file.txt');
      if (IMG_TYPE.test(f.type)) {
        if (S.attachments.filter(function (a) { return a.kind === 'image'; }).length >= 6) { toast('You can attach up to 6 pictures per message.', 'error'); return; }
        imageToDataUrl(f).then(function (url) {
          S.attachments.push({ kind: 'image', name: name, dataUrl: url });
          renderAttachments();
        }).catch(function () { toast('Couldn\u2019t read the picture “' + name + '”.', 'error'); });
        return;
      }
      if (/\.(pdf|docx?|xlsx?|xlsm|pptx?|odt|ods|odp|zip|rar|7z|gz|exe|dll|bin|iso|mp3|mp4|mov|avi|mkv|wav|heic|heif|tiff?|bmp|psd)$/i.test(name) || f.size > 5 * 1024 * 1024) {
        toast('“' + name + '” can\u2019t be attached to a message. Attach code, text files or pictures (PNG, JPG). PDF, Word, Excel and PowerPoint files go into Knowledge on the left.', 'error');
        return;
      }
      f.text().then(function (txt) {
        if (txt.indexOf('\u0000') !== -1) { toast('“' + name + '” isn\u2019t a text file, so it can\u2019t be attached.', 'error'); return; }
        if (txt.length > TEXT_MAX) {
          txt = txt.slice(0, TEXT_MAX) + '\n…(file shortened)';
          toast('“' + name + '” is very long, so only the first part was attached.');
        }
        S.attachments.push({ kind: 'text', name: name, text: txt });
        renderAttachments();
      }).catch(function () { toast('Couldn\u2019t read “' + name + '”.', 'error'); });
    });
  }

  function renderAttachments() {
    var row = $('#attachRow');
    row.hidden = !S.attachments.length;
    row.innerHTML = S.attachments.map(function (a, i) {
      var icon = a.kind === 'image' ? '<img src="' + esc(a.dataUrl) + '" alt="">' : '<span class="att-icon">📄</span>';
      return '<span class="att" title="' + esc(a.name) + '">' + icon + '<span class="att-name">' + esc(a.name) + '</span>' +
        '<button type="button" data-rm="' + i + '" aria-label="Remove ' + esc(a.name) + '">' + X_ICON + '</button></span>';
    }).join('');
    updateSendState();
  }

  // What the AI receives for a user message: the text plus any attached files.
  function userContent(m) {
    var parts = [m.content || ''];
    (m.attachments || []).forEach(function (a) {
      if (a.kind === 'text') parts.push('Attached file “' + a.name + '”:\n' + fence(a.text || '(the content is no longer available)', langFromName(a.name)));
      else if (!a.dataUrl) parts.push('(A picture “' + a.name + '” was attached earlier.)');
    });
    return parts.filter(Boolean).join('\n\n');
  }

  /* ------------------------------------------------------------------- chat */
  function scrollToBottom(force) {
    var m = $('#messages');
    if (force || S.stick) m.scrollTop = m.scrollHeight;
  }

  var DEFAULT_SUGG = [
    ['Code', 'Write a Python script that renames the photos in a folder by the date they were taken', false],
    ['Web page', 'Build a stylish one-page website for a coffee shop as a single HTML file', false],
    ['Engineering', 'Size a simply supported steel beam for a 6 m span carrying 12 kN/m', false],
    ['Your files', 'Give me a short summary of my files', true]
  ];

  function welcomeEl() {
    var name = aiName(), hasFiles = S.files.some(function (f) { return f.chunks > 0; });
    var el = document.createElement('div');
    el.className = 'welcome';
    var custom = (S.status && S.status.config.suggestions) || [];
    var sugg = custom.length ? custom.map(function (q) { return [null, q]; })
      : DEFAULT_SUGG.filter(function (s) { return hasFiles || !s[2]; });
    var intro = hasFiles
      ? 'Ask me anything. I write and fix code, solve engineering problems, and know your files.'
      : 'Ask me anything. I write and fix code and solve engineering problems.';
    el.innerHTML = '<div class="logo">' + esc(initials(name)) + '</div><h1>Hi, I\u2019m ' + esc(name) + '</h1><p>' + esc(intro) + '</p>' +
      '<div class="suggestions">' + sugg.map(function (s) {
        return '<button class="suggestion" type="button" data-q="' + esc(s[1]) + '">' +
          (s[0] ? '<b>' + esc(s[0]) + '</b><span>' + esc(s[1]) + '</span>' : '<span class="q">' + esc(s[1]) + '</span>') + '</button>';
      }).join('') + '</div>' +
      (hasFiles ? '' : '<p class="hint">Want me to know your own documents? <a data-add>Add files</a> on the left.</p>');
    each(el.querySelectorAll('.suggestion'), function (b) {
      b.addEventListener('click', function () { send(b.getAttribute('data-q')); });
    });
    var add = el.querySelector('[data-add]');
    if (add) add.addEventListener('click', function () { $('#fileInput').click(); });
    return el;
  }

  function messageEl(m) {
    var el = document.createElement('div');
    if (m.role === 'user') {
      el.className = 'msg user';
      var atts = (m.attachments || []).map(function (a) {
        if (a.kind === 'image' && a.dataUrl && /^data:image\//.test(a.dataUrl)) return '<img src="' + esc(a.dataUrl) + '" alt="' + esc(a.name) + '">';
        return '<span class="bubble-file" title="' + esc(a.name) + '">' + (a.kind === 'image' ? '🖼 ' : '📄 ') + esc(a.name) + '</span>';
      }).join('');
      el.innerHTML = (atts ? '<div class="bubble-atts">' + atts + '</div>' : '') +
        (m.content ? '<div class="bubble">' + esc(m.content) + '</div>' : '');
      return el;
    }
    el.className = 'msg assistant';
    el.innerHTML = '<div class="avatar">' + esc(initials(aiName())) + '</div><div class="card">' +
      '<div class="status-line" hidden><span class="spinner"></span><span class="status-text"></span></div>' +
      '<div class="md"></div><div class="extra"></div></div>';
    fillAssistant(el, m, false);
    return el;
  }

  function isLastMessage(m) { return S.chat[S.chat.length - 1] === m; }

  function visibleSources(m) {
    var list = m.sources || [];
    if (!m.verify || !m.content) return list;
    // Keyword matches are only shown when the answer actually used them.
    var low = m.content.toLowerCase();
    return list.filter(function (s) {
      return (s.file && low.indexOf(s.file.toLowerCase()) !== -1) ||
        (s.label && s.label.length > 3 && low.indexOf(s.label.toLowerCase()) !== -1);
    });
  }

  function fillAssistant(el, m, live) {
    var md = el.querySelector('.md'), extra = el.querySelector('.extra'), st = el.querySelector('.status-line');
    st.hidden = !(live && m.status);
    if (live && m.status) st.querySelector('.status-text').textContent = m.status;
    if (live && !m.content) {
      md.innerHTML = m.status ? '' : '<div class="typing"><span></span><span></span><span></span></div>';
    } else {
      md.innerHTML = renderMarkdown(m.content || '', live);
      if (live) {
        var node = md.lastElementChild;
        while (node && node.lastElementChild && !/^(P|LI|H\d|TD|PRE)$/.test(node.tagName)) node = node.lastElementChild;
        if (node) node.classList.add('cursor');
      }
    }
    if (live) { extra.innerHTML = ''; return; }

    var html = '', sources = visibleSources(m), last = isLastMessage(m) && !S.streaming;
    if (m.quota && !(S.usage && (S.usage.subscribed || S.usage.admin))) html += paywallHtml(m.quota);
    if (m.engine && m.engine !== 'main') {
      html += '<div class="engine-badge"><span>' + esc(m.engineIcon || '🔌') + '</span>' +
        '<b>' + esc(m.engineLabel || m.engine) + '</b>' +
        (m.engineModel ? '<span class="mdl">· ' + esc(m.engineModel) + '</span>' : '') +
        '<span class="mdl">answered this</span></div>';
    }
    if (m.voices && m.voices.length) html += voiceRow(m.voices.length === 1 ? m.voices[0].text : '');
    if (m.error) html += '<div class="error-box">⚠ ' + esc(m.error) + '</div>';
    if (m.cut && last) html += '<div class="notice"><span>✂ The answer was cut off because it got very long.</span><button class="btn small" type="button" data-act="continue">Continue</button></div>';
    if (m.searches && m.searches.length) {
      html += '<div class="searched">🔎 Searched your files for: ' + m.searches.map(function (q) { return '“' + esc(q) + '”'; }).join(', ') + '</div>';
    }
    if (sources.length) {
      var labels = sources.map(function (s) { return s.location || s.label || ''; }), seenLabel = {};
      labels.forEach(function (l) { seenLabel[l] = (seenLabel[l] || 0) + 1; });
      html += '<div class="sources"><span class="sources-label">Sources</span>' + sources.map(function (s, k) {
        var where = labels[k];
        if (where && seenLabel[where] > 1) {
          var by = String(s.passage || '').match(/\]\(https?:\/\/[^\/\s)]+\/([^\/\s)?#]+)\//);
          if (by) where += ' (' + by[1] + ')';
        }
        return '<button class="chip" type="button" data-k="' + k + '" title="' + esc(s.snippet || '') + '">📄 ' +
          esc(s.file) + (where ? ' · ' + esc(where) : '') + '</button>';
      }).join('') + '</div><div class="src-panel" hidden></div>';
    }
    var acts = '';
    if (m.content) acts += '<button class="act" type="button" data-act="copy">Copy</button>';
    if (last) acts += '<button class="act" type="button" data-act="retry" title="Ask again for a new answer">↻ Retry</button>';
    if (acts) html += '<div class="msg-actions">' + acts + '</div>';
    extra.innerHTML = html;

    var pw = extra.querySelector('.paywall');
    if (pw && m.quota) bindPaywall(pw, m.quota);
    var panel = extra.querySelector('.src-panel');
    var chips = extra.querySelectorAll('.chip');
    each(chips, function (chip) {
      chip.addEventListener('click', function () {
        var s = sources[+chip.getAttribute('data-k')], wasActive = chip.classList.contains('active');
        each(chips, function (c) { c.classList.remove('active'); });
        if (wasActive) { panel.hidden = true; return; }
        chip.classList.add('active');
        panel.innerHTML = '<b>' + esc(s.file) + (s.location ? ' · ' + esc(s.location) : '') + '</b>' +
          String(s.passage || s.snippet || '').split('\n').map(mdInline).join('<br>');
        panel.hidden = false;
      });
    });
    var copy = extra.querySelector('[data-act="copy"]');
    if (copy) copy.addEventListener('click', function () { copyText(m.content).then(function () { flash(copy, 'Copied ✓'); }); });
    var retryBtn = extra.querySelector('[data-act="retry"]');
    if (retryBtn) retryBtn.addEventListener('click', retry);
    var cont = extra.querySelector('[data-act="continue"]');
    if (cont) cont.addEventListener('click', function () { send('Continue exactly where you stopped. Don\u2019t repeat what you already wrote.'); });
  }

  function renderThread() {
    var thread = $('#thread');
    thread.innerHTML = '';
    if (!S.chat.length) { thread.appendChild(welcomeEl()); return; }
    S.chat.forEach(function (m) { thread.appendChild(messageEl(m)); });
    scrollToBottom(true);
  }

  function saveChat() {
    var slim = S.chat.slice(-100).map(function (m) {
      var c = Object.assign({}, m);
      delete c.status;
      if (c.quota) { c.content = c.content || '🔒 Your free allowance had been used here - subscription options were shown.'; delete c.quota; }
      if (c.voices) c.voices = c.voices.map(function (v) { return { text: v.text || '' }; });
      if (m.attachments) {
        c.attachments = m.attachments.map(function (a) {
          if (a.kind === 'image') return { kind: 'image', name: a.name };   // pictures are too big to keep
          if (a.text && a.text.length > 60000) return { kind: 'text', name: a.name, text: a.text.slice(0, 60000) + '\n…(shortened)' };
          return a;
        });
      }
      return c;
    });
    if (!store.set('myai.chat', slim)) store.set('myai.chat', slim.slice(-20));
  }

  function setStreaming(on) {
    S.streaming = on;
    var b = $('#sendBtn');
    b.classList.toggle('stop', on);
    b.innerHTML = on ? STOP_ICON : SEND_ICON;
    b.setAttribute('aria-label', on ? 'Stop' : 'Send');
    updateSendState();
  }
  function updateSendState() { $('#sendBtn').disabled = !S.streaming && !$('#input').value.trim() && !S.attachments.length; }
  function autoGrow() {
    var t = $('#input');
    t.style.height = 'auto';
    t.style.height = Math.min(t.scrollHeight, 220) + 'px';
    updateSendState();
  }

  // Only the newest answer offers "Retry" and "Continue".
  function clearLastActions() {
    each($('#thread').querySelectorAll('[data-act="retry"], .notice'), function (n) { n.remove(); });
  }

  function send(text) {
    text = String(text || '').trim();
    var atts = S.attachments.slice();
    if ((!text && !atts.length) || S.streaming) return;
    closeSidebar();
    $('#input').value = '';
    S.attachments = [];
    renderAttachments();
    autoGrow();
    var userMsg = { role: 'user', content: text };
    if (atts.length) userMsg.attachments = atts;
    clearLastActions();
    S.chat.push(userMsg);
    var thread = $('#thread');
    if (thread.querySelector('.welcome')) thread.innerHTML = '';
    thread.appendChild(messageEl(userMsg));
    ask(S.engine);
  }

  function retry() {
    if (S.streaming) return;
    var last = S.chat[S.chat.length - 1];
    if (!last || last.role !== 'assistant') return;
    S.chat.pop();
    var thread = $('#thread');
    if (thread.lastElementChild) thread.lastElementChild.remove();
    ask(last.engine === 'main' ? S.engine : (last.requestedEngine || S.engine));
  }

  function apiHistory(upto) {
    var msgs = S.chat.slice(0, upto).filter(function (m) {
      return (m.content || (m.attachments && m.attachments.length)) && !m.error;
    }).slice(-60);
    var pictures = 3, out = [];
    for (var i = msgs.length - 1; i >= 0; i--) {
      var m = msgs[i], item = { role: m.role, content: m.role === 'user' ? userContent(m) : m.content };
      if (m.role === 'user' && pictures > 0) {
        var imgs = (m.attachments || []).filter(function (a) { return a.kind === 'image' && a.dataUrl; }).map(function (a) { return a.dataUrl; });
        if (imgs.length) { item.images = imgs; pictures--; }
      }
      out.unshift(item);
    }
    return out;
  }

  function ask(engineId) {
    var reply = { role: 'assistant', content: '', sources: [], error: '', engine: engineId || 'auto',
                  requestedEngine: engineId || 'auto' };
    S.chat.push(reply);
    var el = messageEl(reply);
    $('#thread').appendChild(el);
    fillAssistant(el, reply, true);
    S.stick = true;
    scrollToBottom(true);
    setStreaming(true);

    var controller = window.AbortController ? new AbortController() : null;
    S.controller = controller;
    var frame = 0;
    var paint = function () { frame = 0; fillAssistant(el, reply, true); scrollToBottom(); };
    var schedule = function () { if (!frame) frame = requestAnimationFrame(paint); };
    var history = apiHistory(-1);

    function handle(ev) {
      if (ev.type === 'delta') { reply.content += ev.text; reply.status = ''; schedule(); }
      else if (ev.type === 'status') { reply.status = ev.text; schedule(); }
      else if (ev.type === 'sources') {
        reply.sources = ev.sources || [];
        reply.verify = !!ev.verify;
        if (ev.searches) reply.searches = ev.searches;
      }
      else if (ev.type === 'notice') { if (ev.kind === 'length') reply.cut = true; }
      else if (ev.type === 'engine') {
        reply.engine = ev.engine; reply.engineLabel = ev.label; reply.engineIcon = ev.icon;
        reply.engineModel = ev.model || ''; schedule();
      }
      else if (ev.type === 'audio') {
        reply.voices = reply.voices || [];
        reply.voices.push({ text: ev.text || '' });
        playVoice(ev.audio, ev.mime);
        schedule();
      }
      else if (ev.type === 'quota') { reply.quota = ev; schedule(); }
      else if (ev.type === 'error') reply.error = ev.message;
    }

    var chatHeaders = { 'Content-Type': 'application/json', 'X-API-Key': getKey(), 'X-Visitor': visitorId() };
    var ownerPw = session.get('myai.admin');
    if (ownerPw) chatHeaders['X-Admin-Password'] = ownerPw;
    fetch('api/chat', {
      method: 'POST',
      headers: chatHeaders,
      body: JSON.stringify({ messages: history, engine: engineId === 'auto' ? 'auto' : (engineId || 'auto') }),
      signal: controller ? controller.signal : undefined
    }).then(function (res) {
      var vid = res.headers && res.headers.get('x-visitor-id');
      if (vid && vid !== visitorId()) store.set('myai.visitor', vid);
      if (!res.ok || !res.body) {
        return res.json().catch(function () { return {}; }).then(function (d) {
          throw new Error(d.detail || (res.status === 413 ? 'That message is too big. Try smaller pictures or files.' : 'Error ' + res.status));
        });
      }
      var reader = res.body.getReader(), decoder = new TextDecoder(), buf = '';
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) return;
          buf += decoder.decode(r.value, { stream: true });
          var idx;
          while ((idx = buf.indexOf('\n\n')) !== -1) {
            var raw = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            var data = raw.split('\n').filter(function (l) { return l.indexOf('data:') === 0; })
              .map(function (l) { return l.slice(5).replace(/^ /, ''); }).join('\n');
            if (!data) continue;
            try { handle(JSON.parse(data)); } catch (e) { /* ignore broken line */ }
          }
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      if (err && err.name === 'AbortError') reply.content += (reply.content ? '\n\n' : '') + '_(stopped)_';
      else reply.error = (err && err.message) || String(err);
    }).then(function () {
      if (frame) cancelAnimationFrame(frame);
      delete reply.status;
      S.controller = null;
      setStreaming(false);
      refreshUsage();
      fillAssistant(el, reply, false);
      saveChat();
      scrollToBottom();
    });
  }

  function newChat() {
    if (S.controller) S.controller.abort();
    S.chat = [];
    store.set('myai.chat', []);
    renderThread();
    closeSidebar();
    if (window.innerWidth > 860) $('#input').focus();
  }

  /* ------------------------------------------------- code blocks: run & preview */
  var PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/';
  var PY_HARNESS = [
    'import builtins, io, os, sys, base64, warnings',
    'from pyodide.code import eval_code_async',
    'os.environ["MPLBACKEND"] = "AGG"',
    'warnings.filterwarnings("ignore", message=".*non-interactive.*")',
    'warnings.filterwarnings("ignore", message=".*FigureCanvasAgg.*")',
    'def __myai_input(prompt=""):',
    '    raise RuntimeError("input() doesn\'t work when code runs in the chat. Put the values directly in the code instead.")',
    'builtins.input = __myai_input',
    'async def __myai_run(code):',
    '    # every run starts fresh; the value of a last bare expression is shown like in Python',
    '    ns = {"__name__": "__main__", "__builtins__": builtins}',
    '    result = await eval_code_async(code, ns, filename="<exec>")',
    '    return None if result is None else repr(result)',
    'def __myai_figures():',
    '    if "matplotlib.pyplot" not in sys.modules:',
    '        return []',
    '    import matplotlib.pyplot as plt',
    '    images = []',
    '    for num in plt.get_fignums()[:8]:',
    '        buf = io.BytesIO()',
    '        with warnings.catch_warnings():',
    '            warnings.simplefilter("ignore")',
    '            plt.figure(num).savefig(buf, format="png", dpi=110, bbox_inches="tight")',
    '        images.append(base64.b64encode(buf.getvalue()).decode("ascii"))',
    '    plt.close("all")',
    '    return images'
  ].join('\n');

  function pyWorkerSource() {
    return [
      // Pyodide 314+ only runs in module workers, loaded with import().
      'var PY = null, BOOT = null, HARNESS = ' + JSON.stringify(PY_HARNESS) + ';',
      'function boot() {',
      '  if (!BOOT) {',
      '    BOOT = import(' + JSON.stringify(PYODIDE + 'pyodide.mjs') + ')',
      '      .then(function (m) { return m.loadPyodide({ indexURL: ' + JSON.stringify(PYODIDE) + ' }); })',
      '      .then(function (py) { py.runPython(HARNESS, { filename: "<myai>" }); PY = py; return py; })',
      '      .catch(function (e) { BOOT = null; throw e; });',
      '  }',
      '  return BOOT;',
      '}',
      'self.onmessage = async function (e) {',
      '  var id = e.data.id, code = e.data.code;',
      '  function post(type, extra) { var m = { id: id, type: type }; for (var k in extra) m[k] = extra[k]; self.postMessage(m); }',
      '  try {',
      '    if (!PY) post("status", { text: "Loading Python (the first time takes a few seconds)…" });',
      '    var py = await boot();',
      '    py.setStdout({ batched: function (s) { post("out", { text: s + "\\n" }); } });',
      '    py.setStderr({ batched: function (s) { post("err", { text: s + "\\n" }); } });',
      '    post("status", { text: "Loading packages…" });',
      '    await py.loadPackagesFromImports(code, { messageCallback: function () {}, errorCallback: function (m) { post("err", { text: m + "\\n" }); } });',
      '    post("status", { text: "Running…", running: true });',
      '    var run = py.globals.get("__myai_run"), result, failure = null;',
      '    try { result = await run(code); } catch (x) { failure = x; } finally { run.destroy(); }',
      '    try { var figs = py.runPython("__myai_figures()"); post("images", { images: figs.toJs() }); figs.destroy(); } catch (x) {}',
      '    if (failure) throw failure;',
      '    post("done", { result: typeof result === "string" ? result : "" });',
      '  } catch (err) { post("error", { text: String((err && err.message) || err) }); }',
      '};'
    ].join('\n');
  }

  var JS_WORKER = [
    'function fmt(v) {',
    '  if (typeof v === "string") return v;',
    '  if (v instanceof Error) return v.stack || String(v);',
    '  if (typeof v === "function" || typeof v === "symbol" || typeof v === "bigint") return String(v);',
    '  try { var s = JSON.stringify(v, null, 2); return s === undefined ? String(v) : s; } catch (e) { return String(v); }',
    '}',
    'function send(type, args) { self.postMessage({ type: type, text: Array.prototype.map.call(args, fmt).join(" ") + "\\n" }); }',
    'console.log = console.info = console.debug = console.table = function () { send("out", arguments); };',
    'console.warn = console.error = function () { send("err", arguments); };',
    'self.onmessage = async function (e) {',
    '  try {',
    '    var AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;',
    '    var result = await new AsyncFunction(e.data.code)();',
    '    self.postMessage({ type: "done", result: result === undefined ? "" : fmt(result) });',
    '  } catch (err) { self.postMessage({ type: "error", text: (err && err.stack) ? String(err.stack) : String(err) }); }',
    '};'
  ].join('\n');

  var runner = { py: null, pyReady: false, jobs: {}, seq: 0 };

  function workerFrom(src, module) {
    return new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })), module ? { type: 'module' } : undefined);
  }

  function getPyWorker() {
    if (!runner.py) {
      runner.py = workerFrom(pyWorkerSource(), true);
      runner.py.onmessage = function (e) { var job = runner.jobs[e.data.id]; if (job) onRunMessage(job, e.data); };
      runner.py.onerror = function (e) {
        e.preventDefault();
        Object.keys(runner.jobs).forEach(function (id) {
          var job = runner.jobs[id];
          if (job.kind === 'python') onRunMessage(job, { type: 'error', text: e.message || 'Python stopped unexpectedly.' });
        });
      };
    }
    return runner.py;
  }

  function cleanTraceback(t) {
    var lines = String(t).split('\n'), out = [];
    for (var i = 0; i < lines.length; i++) {
      if (/^\s*File "(\/lib\/python[^"]*|<frozen [^"]*|<myai>)"/.test(lines[i])) {
        while (i + 1 < lines.length && !/^\s*File "/.test(lines[i + 1]) && /^\s{4,}\S/.test(lines[i + 1])) i++;
        continue;
      }
      out.push(lines[i]);
    }
    return out.join('\n').replace(/\n{3,}/g, '\n\n').trim();
  }

  function ensureOutput(block) {
    var out = block.querySelector('.code-out');
    if (!out) {
      out = document.createElement('div');
      out.className = 'code-out';
      out.innerHTML = '<div class="out-head"><span class="spinner"></span><span class="out-title">Output</span><span class="out-status"></span>' +
        '<span class="code-actions"><button type="button" class="code-btn" data-out="stop">Stop</button>' +
        '<button type="button" class="code-btn" data-out="send" title="Put the output in the message box so you can ask about it">Send to chat</button>' +
        '<button type="button" class="code-btn" data-out="close" aria-label="Close output">✕</button></span></div>' +
        '<pre class="out-text"></pre><div class="out-imgs"></div>';
      block.appendChild(out);
    }
    out.hidden = false;
    return out;
  }

  function outAppend(job, text, cls) {
    if (!text) return;
    if (job.size > 200000) {
      if (!job.capped) { job.capped = true; outAppend2(job, '\n…(output cut: too long)\n', 'err'); }
      return;
    }
    job.size += text.length;
    outAppend2(job, text, cls);
  }
  function outAppend2(job, text, cls) {
    var pre = job.out.querySelector('.out-text'), span = document.createElement('span');
    if (cls) span.className = cls;
    span.textContent = text;
    pre.appendChild(span);
    job.plain += text;
    pre.scrollTop = pre.scrollHeight;
  }
  function setRunState(job, text, running) {
    if (runner.jobs[job.id] !== job && running) return;
    job.out.querySelector('.out-status').textContent = text;
    job.out.querySelector('.spinner').hidden = !running;
    job.out.querySelector('[data-out="stop"]').hidden = !running;
  }
  function finishJob(job, text) {
    clearTimeout(job.timer);
    delete runner.jobs[job.id];
    job.done = true;
    setRunState(job, text, false);
  }

  function onRunMessage(job, m) {
    if (job.done) { if (m.type === 'out' || m.type === 'err') outAppend(job, m.text, m.type === 'err' ? 'err' : ''); return; }
    if (m.type === 'status') {
      setRunState(job, m.text, true);
      if (m.running) {
        runner.pyReady = true;
        clearTimeout(job.timer);
        job.started = Date.now();
        job.timer = setTimeout(function () { stopJob(job, 'Stopped: it ran for more than 2 minutes.'); }, 120000);
      }
    } else if (m.type === 'out') outAppend(job, m.text, '');
    else if (m.type === 'err') outAppend(job, m.text, 'err');
    else if (m.type === 'images') {
      (m.images || []).forEach(function (b64) {
        var img = document.createElement('img');
        img.src = 'data:image/png;base64,' + b64;
        img.alt = 'Plot';
        job.out.querySelector('.out-imgs').appendChild(img);
        job.images++;
      });
    } else if (m.type === 'done') {
      if (m.result) outAppend(job, m.result + '\n', 'res');
      var secs = ((Date.now() - job.started) / 1000).toFixed(1);
      finishJob(job, (job.plain || job.images ? 'Finished' : 'Finished (no output)') + ' in ' + secs + ' s');
    } else if (m.type === 'error') {
      var msg = m.text || 'Error';
      if (job.kind === 'python') {
        msg = cleanTraceback(msg);
        if (/importScripts|NetworkError|Failed to fetch|dynamically imported module|load script/i.test(msg)) {
          msg = 'Couldn\u2019t load Python. Running Python needs an internet connection (it downloads from cdn.jsdelivr.net the first time).';
        }
      }
      outAppend(job, (job.plain && !/\n$/.test(job.plain) ? '\n' : '') + msg + '\n', 'err');
      finishJob(job, 'Error');
    }
  }

  function stopJob(job, why) {
    if (job.done) return;
    if (job.kind === 'python') {
      if (runner.py) runner.py.terminate();
      runner.py = null;
      runner.pyReady = false;
      Object.keys(runner.jobs).forEach(function (id) {
        var other = runner.jobs[id];
        if (other !== job && other.kind === 'python') { outAppend(other, '\nStopped.\n', 'err'); finishJob(other, 'Stopped'); }
      });
    } else if (job.worker) job.worker.terminate();
    outAppend(job, (job.plain && !/\n$/.test(job.plain) ? '\n' : '') + (why || 'Stopped.') + '\n', 'err');
    finishJob(job, 'Stopped');
  }

  function runCode(block, code) {
    var kind = block.getAttribute('data-kind'), out = ensureOutput(block);
    if (out.job && !out.job.done) stopJob(out.job, 'Stopped (started again).');
    out.querySelector('.out-text').innerHTML = '';
    out.querySelector('.out-imgs').innerHTML = '';
    var job = { id: ++runner.seq, out: out, kind: kind === 'python' ? 'python' : 'js', plain: '', size: 0, images: 0, started: Date.now() };
    out.job = job;
    runner.jobs[job.id] = job;
    setRunState(job, 'Starting…', true);
    if (job.kind === 'python') {
      getPyWorker().postMessage({ id: job.id, code: code });
      job.timer = setTimeout(function () { stopJob(job, 'Stopped: Python took too long to load. Check your internet connection.'); }, 240000);
    } else {
      var w = workerFrom(JS_WORKER);
      job.worker = w;
      w.onmessage = function (e) { onRunMessage(job, e.data); };
      w.onerror = function (e) { e.preventDefault(); onRunMessage(job, { type: 'error', text: e.message || 'Error' }); };
      setRunState(job, 'Running…', true);
      w.postMessage({ code: code });
      job.timer = setTimeout(function () {
        if (!job.done) stopJob(job, 'Stopped: it ran for more than 20 seconds.');
        w.terminate();
      }, 20000);
    }
    var pre = out.querySelector('.out-text');
    setTimeout(function () { if (pre.getBoundingClientRect().top > window.innerHeight) out.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }, 50);
  }

  // Previews run in a sandboxed frame: they can't see your keys, chats or this page.
  var STORAGE_SHIM = '<script>(function(){function mk(){var d={};return{getItem:function(k){k=String(k);return Object.prototype.hasOwnProperty.call(d,k)?d[k]:null},setItem:function(k,v){d[String(k)]=String(v)},removeItem:function(k){delete d[String(k)]},clear:function(){d={}},key:function(i){return Object.keys(d)[i]||null},get length(){return Object.keys(d).length}}}["localStorage","sessionStorage"].forEach(function(n){try{window[n].getItem("x")}catch(e){try{Object.defineProperty(window,n,{value:mk(),configurable:true})}catch(e2){}}})})();<\/script>';
  var preview = { doc: '', code: '', name: 'page.html' };
  function previewDoc(code, kind) {
    if (kind === 'svg') {
      return '<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{margin:0;min-height:100%;background:#fff}body{display:grid;place-items:center;min-height:100vh}svg{max-width:100%;height:auto}</style></head><body>' + code + '</body></html>';
    }
    var m = code.match(/<head[^>]*>/i) || code.match(/<html[^>]*>/i) || code.match(/<!doctype[^>]*>/i);
    if (m) { var at = m.index + m[0].length; return code.slice(0, at) + STORAGE_SHIM + code.slice(at); }
    return STORAGE_SHIM + code;
  }
  function openPreview(code, kind, name) {
    preview.code = code;
    preview.doc = previewDoc(code, kind);
    preview.name = name || (kind === 'svg' ? 'drawing.svg' : 'page.html');
    $('#previewTitle').textContent = 'Preview' + (name ? ' · ' + name : '');
    $('#previewModal').hidden = false;
    $('#previewFrame').srcdoc = preview.doc;
  }
  function closePreview() {
    if ($('#previewModal').hidden) return;
    $('#previewModal').hidden = true;
    $('#previewFrame').srcdoc = '';
  }

  function blockFileName(block) {
    var file = block.getAttribute('data-file');
    if (file) return file.split(/[\\/]/).pop();
    var lang = block.getAttribute('data-lang');
    var ext = EXT_FOR[lang] || (lang && /^[a-z0-9]{1,8}$/.test(lang) ? lang : 'txt');
    return (lang === 'html' ? 'index' : lang === 'svg' ? 'drawing' : 'code') + '.' + ext;
  }

  $('#thread').addEventListener('click', function (e) {
    var btn = e.target.closest('[data-code], [data-out]');
    if (!btn || btn.disabled) return;
    var block = btn.closest('.codeblock');
    if (!block) return;
    var code = block.querySelector('pre code').textContent;
    var act = btn.getAttribute('data-code'), outAct = btn.getAttribute('data-out');
    if (act === 'copy') copyText(code).then(function () { flash(btn, 'Copied ✓'); });
    else if (act === 'download') downloadText(blockFileName(block), code);
    else if (act === 'preview') openPreview(code, block.getAttribute('data-kind'), block.getAttribute('data-file'));
    else if (act === 'run') runCode(block, code);
    else if (outAct) {
      var out = block.querySelector('.code-out'), job = out && out.job;
      if (outAct === 'stop' && job) stopJob(job);
      else if (outAct === 'close' && out) { if (job && !job.done) stopJob(job); out.hidden = true; }
      else if (outAct === 'send' && job) {
        var text = job.plain.trim() || '(no text output)';
        if (text.length > 6000) text = text.slice(0, 3000) + '\n…\n' + text.slice(-3000);
        var input = $('#input');
        input.value = (input.value ? input.value.replace(/\s+$/, '') + '\n\n' : '') + 'I ran the code. This is the output:\n' + fence(text, 'text') + '\n';
        autoGrow();
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
      }
    }
  });

  /* --------------------------------------------------------------- settings */
  function showTest(kind, msg) {
    var t = $('#testResult');
    t.className = 'test-result ' + kind;
    t.textContent = msg;
    t.hidden = false;
  }

  function setSelect(sel, value, labelFn) {
    value = String(value);
    var exists = Array.prototype.some.call(sel.options, function (o) { return o.value === value; });
    if (!exists) {
      var o = document.createElement('option');
      o.value = value; o.textContent = labelFn(value);
      sel.appendChild(o);
    }
    sel.value = value;
  }

  var PROVIDER_HELP = {
    gemini: 'Free, no credit card needed. On the free plan Google may use your conversations to improve its products.',
    openai: 'Paid per use. Create a key in your OpenAI account.',
    openrouter: 'One key for models from many companies, some of them free.',
    groq: 'Very fast open-source models, with a free plan.',
    ollama: 'Runs on your own computer, offline and free. Install Ollama, download a model (for example “ollama pull qwen3”), then click Load models. No key needed.',
    custom: 'Any service that speaks the OpenAI API.'
  };

  function updateProviderHelp() {
    var id = $('#cfgProvider').value, p = S.status.providers[id] || {};
    $('#providerHelp').textContent = PROVIDER_HELP[id] || '';
    var parts = [];
    if (p.key_url && id !== 'ollama') parts.push('<a href="' + esc(p.key_url) + '" target="_blank" rel="noopener">Get your ' + (id === 'gemini' || id === 'groq' ? 'free ' : '') + 'key here ↗</a>');
    if (id === 'ollama') parts.push('<a href="' + esc(p.key_url) + '" target="_blank" rel="noopener">Download Ollama ↗</a>');
    parts.push(esc('Saved only in this browser' + (S.status.server_key ? '. A key is also set on the server, so you can leave this empty.' : '.')));
    $('#keyHelp').innerHTML = parts.join(' · ');
    $('#keyField').hidden = id === 'ollama';
  }

  function openSettings(focus) {
    if (!S.status) { toast('Still connecting to the server…'); return; }
    var c = S.status.config, P = S.status.providers;
    $('#cfgName').value = c.name || '';
    if ($('#cfgCreator')) $('#cfgCreator').value = c.creator || 'Ruwayne';
    var sel = $('#cfgProvider');
    sel.innerHTML = Object.keys(P).map(function (id) { return '<option value="' + id + '">' + esc(P[id].label) + '</option>'; }).join('');
    sel.value = P[c.provider] ? c.provider : 'custom';
    $('#cfgBaseUrl').value = c.base_url || '';
    $('#cfgModel').value = c.model || '';
    $('#cfgKey').value = getKey(sel.value);
    $('#cfgKey').type = 'password';
    $('#toggleKey').textContent = 'Show';
    each(document.querySelectorAll('input[name=mode]'), function (r) { r.checked = r.value === c.answer_mode; });
    $('#cfgInstructions').value = c.instructions || '';
    $('#cfgSuggestions').value = (c.suggestions || []).join('\n');
    $('#cfgEffort').value = c.reasoning_effort || '';
    setSelect($('#cfgContext'), c.context_chars, function (v) { return 'Custom: ' + Number(v).toLocaleString() + ' characters'; });
    setSelect($('#cfgHistory'), c.history_messages, function (v) { return 'Last ' + v + ' messages'; });
    $('#modelSelect').hidden = true;
    $('#testResult').hidden = true;
    connDraft = {};
    if ($('#cfgVoice')) $('#cfgVoice').checked = c.vtuber_audio !== false;
    if ($('#cfgSkills')) $('#cfgSkills').checked = c.skills_enabled !== false;
    var B = c.billing || {};
    var BP = B.providers || {}, BB = B.bank || {};
    if ($('#billEnabled')) $('#billEnabled').checked = B.enabled !== false;
    setVal('#billPrompts', B.free_prompts === undefined ? 15 : B.free_prompts);
    setVal('#billTokens', B.free_tokens === undefined ? 120000 : B.free_tokens);
    setVal('#billWindow', B.window || 'lifetime');
    setVal('#billPlan', B.plan_name || 'My AI Plus');
    setVal('#billPrice', B.price || '49');
    setVal('#billCurrency', B.currency || 'ZAR');
    setVal('#billInterval', B.interval || 'month');
    if ($('#billManual')) $('#billManual').checked = !!BP.manual;
    if ($('#billStripe')) $('#billStripe').checked = !!BP.stripe;
    if ($('#billPaystack')) $('#billPaystack').checked = !!BP.paystack;
    setVal('#billBank', BB.bank || ''); setVal('#billAccName', BB.account_name || '');
    setVal('#billAccNo', BB.account_number || ''); setVal('#billBranch', BB.branch || '');
    setVal('#billNote', B.pay_note || '');
    each(['#billStripeKey', '#billStripeHook', '#billPaystackKey'], function (i) { setVal(i, ''); });
    if ($('#billDash')) { $('#billDash').hidden = true; $('#billDash').innerHTML = ''; }
    renderConnectors();
    updateProviderHelp();
    $('#settingsModal').hidden = false;
    closeSidebar();
    if (focus === 'connectors') {
      var adv = document.querySelector('details.adv');
      setTimeout(function () {
        var box = $('#connList');
        if (box) box.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 60);
    } else {
      setTimeout(function () { (getKey(sel.value) || sel.value === 'ollama' ? $('#cfgName') : $('#cfgKey')).focus(); }, 30);
    }
  }
  function closeSettings() { $('#settingsModal').hidden = true; }

  function setVal(sel, v) { var el = $(sel); if (el) el.value = v; }

  function verCmp(a, b) {
    var x = a.split('.').map(Number), y = b.split('.').map(Number);
    for (var i = 0; i < Math.max(x.length, y.length); i++) {
      var d = (x[i] || 0) - (y[i] || 0);
      if (d) return d;
    }
    return 0;
  }
  function pickModel(list, provider) {
    if (provider === 'gemini') {
      var flash = list.filter(function (m) { return /^gemini-\d+(\.\d+)?-flash$/.test(m); })
        .sort(function (a, b) { return verCmp(b.split('-')[1], a.split('-')[1]); });
      if (flash.length) return flash[0];
      var anyFlash = list.filter(function (m) { return /^gemini-.*flash/.test(m) && !/preview|exp|lite/.test(m); });
      if (anyFlash.length) return anyFlash.sort().reverse()[0];
    }
    return list[0];
  }

  function loadModels(quiet) {
    var btn = $('#loadModelsBtn');
    btn.disabled = true; btn.textContent = 'Loading…';
    return api('api/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': $('#cfgKey').value.trim() },
      body: JSON.stringify({ base_url: $('#cfgBaseUrl').value.trim(), provider: $('#cfgProvider').value })
    }).then(function (d) {
      var models = d.models || [], sel = $('#modelSelect'), cur = $('#cfgModel').value.trim();
      sel.innerHTML = '<option value="">Choose a model (' + models.length + ' found)</option>' + models.map(function (m) {
        return '<option value="' + esc(m) + '"' + (m === cur ? ' selected' : '') + '>' + esc(m) + '</option>';
      }).join('');
      sel.hidden = !models.length;
      if (models.length && models.indexOf(cur) === -1) {
        var pick = pickModel(models, $('#cfgProvider').value);
        $('#cfgModel').value = pick;
        sel.value = pick;
        showTest('info', (cur ? '“' + cur + '” isn\u2019t available with this key, so I picked “' + pick + '”.' : 'Picked “' + pick + '”.') +
          ' You can choose another one from the list.');
      } else if (!quiet) {
        showTest('ok', '✓ Found ' + plural(models.length, 'model') + '.');
      }
      return models;
    }).catch(function (e) {
      if (!quiet) showTest('bad', e.message);
      return null;
    }).then(function (r) {
      btn.disabled = false; btn.textContent = 'Load models';
      return r;
    });
  }

  function testConnection() {
    var id = $('#cfgProvider').value;
    if (id !== 'ollama' && !$('#cfgKey').value.trim() && !S.status.server_key) { showTest('bad', 'Paste your API key first.'); return; }
    showTest('info', 'Testing…');
    loadModels(false).then(function (models) {
      if (!models) return;
      var model = $('#cfgModel').value.trim();
      if (models.indexOf(model) !== -1) showTest('ok', '✓ Connected! “' + model + '” is ready. Click Save.');
      else if (model) showTest('info', 'Your key works, but “' + model + '” isn\u2019t in your list of models. Choose one above.');
    });
  }

  function saveSettings() {
    var id = $('#cfgProvider').value, checked = document.querySelector('input[name=mode]:checked');
    var body = {
      name: $('#cfgName').value.trim() || 'My AI',
      creator: ($('#cfgCreator') ? $('#cfgCreator').value.trim() : '') || 'Ruwayne',
      provider: id,
      base_url: $('#cfgBaseUrl').value.trim(),
      model: $('#cfgModel').value.trim(),
      answer_mode: checked ? checked.value : 'files_first',
      instructions: $('#cfgInstructions').value,
      reasoning_effort: $('#cfgEffort').value,
      context_chars: Number($('#cfgContext').value),
      history_messages: Number($('#cfgHistory').value),
      suggestions: $('#cfgSuggestions').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean).slice(0, 6),
      engines: collectConns(),
      vtuber_audio: $('#cfgVoice') ? $('#cfgVoice').checked : true,
      skills_enabled: $('#cfgSkills') ? $('#cfgSkills').checked : true,
      billing: {
        enabled: $('#billEnabled').checked,
        free_prompts: Number($('#billPrompts').value) || 0,
        free_tokens: Number($('#billTokens').value) || 0,
        window: $('#billWindow').value,
        plan_name: $('#billPlan').value.trim() || 'My AI Plus',
        price: $('#billPrice').value.trim() || '49',
        currency: $('#billCurrency').value,
        interval: $('#billInterval').value,
        providers: { manual: $('#billManual').checked, stripe: $('#billStripe').checked,
                     paystack: $('#billPaystack').checked },
        stripe_secret: $('#billStripeKey').value.trim(),
        stripe_webhook_secret: $('#billStripeHook').value.trim(),
        paystack_secret: $('#billPaystackKey').value.trim(),
        bank: { bank: $('#billBank').value.trim(), account_name: $('#billAccName').value.trim(),
                account_number: $('#billAccNo').value.trim(), branch: $('#billBranch').value.trim() },
        pay_note: $('#billNote').value.trim()
      }
    };
    var btn = $('#saveSettings');
    btn.disabled = true;
    api('api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function () {
        if (id !== 'ollama') setKey(id, $('#cfgKey').value.trim());
        connDraft = {};
        closeSettings();
        return refreshStatus();
      })
      .then(function () {
        if (!S.streaming) renderThread();
        toast(aiConnected() ? 'Saved ✓ Your AI is connected.' : 'Saved ✓');
      })
      .catch(function (e) { showTest('bad', e.message); })
      .then(function () { btn.disabled = false; });
  }

  /* ------------------------------------------------------------ sidebar UI */
  function openSidebar() { $('#sidebar').classList.add('open'); $('#scrim').classList.add('show'); }
  function closeSidebar() { $('#sidebar').classList.remove('open'); $('#scrim').classList.remove('show'); }

  /* ----------------------------------------------------------------- events */
  $('#form').addEventListener('submit', function (e) {
    e.preventDefault();
    if (S.streaming) { if (S.controller) S.controller.abort(); return; }
    send($('#input').value);
  });
  $('#input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (!S.streaming) send($('#input').value);
    }
  });
  $('#input').addEventListener('input', autoGrow);
  $('#input').addEventListener('paste', function (e) {
    var files = e.clipboardData && e.clipboardData.files;
    if (!files || !files.length) return;
    var pics = Array.prototype.filter.call(files, function (f) { return IMG_TYPE.test(f.type); });
    if (pics.length) { e.preventDefault(); addAttachments(pics); }
  });
  $('#attachBtn').addEventListener('click', function () { $('#attachInput').click(); });
  $('#attachInput').addEventListener('change', function (e) { addAttachments(e.target.files); e.target.value = ''; });
  $('#attachRow').addEventListener('click', function (e) {
    var b = e.target.closest('[data-rm]');
    if (b) { S.attachments.splice(+b.getAttribute('data-rm'), 1); renderAttachments(); }
  });
  $('#messages').addEventListener('scroll', function () {
    var m = $('#messages');
    S.stick = m.scrollHeight - m.scrollTop - m.clientHeight < 140;
  });
  $('#newChatBtn').addEventListener('click', newChat);
  $('#newChatTop').addEventListener('click', newChat);
  $('#settingsBtn').addEventListener('click', openSettings);
  $('#bannerBtn').addEventListener('click', openSettings);
  $('#menuBtn').addEventListener('click', openSidebar);
  $('#scrim').addEventListener('click', closeSidebar);
  $('#fileInput').addEventListener('change', function (e) { upload(e.target.files); e.target.value = ''; });

  var dashBtn = $('#billDashBtn');
  if (dashBtn) dashBtn.addEventListener('click', loadDashboard);

  $('#cfgProvider').addEventListener('change', function () {
    var id = $('#cfgProvider').value, p = S.status.providers[id];
    if (id !== 'custom') $('#cfgBaseUrl').value = p.base_url;
    $('#cfgModel').value = p.model || '';
    $('#cfgKey').value = getKey(id);
    $('#modelSelect').hidden = true;
    $('#testResult').hidden = true;
    updateProviderHelp();
    if (!p.model && ($('#cfgKey').value || id === 'ollama')) loadModels(true);
  });
  $('#modelSelect').addEventListener('change', function (e) { if (e.target.value) $('#cfgModel').value = e.target.value; });
  $('#loadModelsBtn').addEventListener('click', function () { loadModels(false); });
  $('#testBtn').addEventListener('click', testConnection);
  $('#saveSettings').addEventListener('click', saveSettings);
  $('#toggleKey').addEventListener('click', function () {
    var k = $('#cfgKey'), show = k.type === 'password';
    k.type = show ? 'text' : 'password';
    $('#toggleKey').textContent = show ? 'Hide' : 'Show';
  });
  each(document.querySelectorAll('[data-close]'), function (b) { b.addEventListener('click', closeSettings); });
  $('#settingsModal').addEventListener('mousedown', function (e) { if (e.target === e.currentTarget) closeSettings(); });
  each(document.querySelectorAll('[data-close-preview]'), function (b) { b.addEventListener('click', closePreview); });
  $('#previewModal').addEventListener('mousedown', function (e) { if (e.target === e.currentTarget) closePreview(); });
  $('#pvReload').addEventListener('click', function () {
    var f = $('#previewFrame');
    f.srcdoc = '';
    setTimeout(function () { f.srcdoc = preview.doc; }, 30);
  });
  $('#pvDownload').addEventListener('click', function () {
    downloadText(preview.name.split(/[\\/]/).pop(), preview.code, /\.svg$/i.test(preview.name) ? 'image/svg+xml' : 'text/html');
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closePreview(); closeSettings(); closeSidebar(); }
  });

  // Drag & drop: on the message box = attach to the message; anywhere else = add to knowledge
  var dragDepth = 0;
  function hasFiles(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') !== -1; }
  function overComposer(e) { return !!(e.target && e.target.closest && e.target.closest('.composer')); }
  window.addEventListener('dragenter', function (e) { if (!hasFiles(e)) return; e.preventDefault(); dragDepth++; $('#dropOverlay').hidden = false; });
  window.addEventListener('dragover', function (e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    var chat = overComposer(e);
    $('#dropOverlay').classList.toggle('chat', chat);
    $('#composer').classList.toggle('drag', chat);
  });
  window.addEventListener('dragleave', function (e) {
    if (!hasFiles(e)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) { $('#dropOverlay').hidden = true; $('#composer').classList.remove('drag'); }
  });
  window.addEventListener('drop', function (e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth = 0;
    $('#dropOverlay').hidden = true;
    $('#composer').classList.remove('drag');
    if (overComposer(e)) addAttachments(e.dataTransfer.files);
    else upload(e.dataTransfer.files);
  });

  /* ------------------------------------------------------------------- start */
  function start() {
    setStreaming(false);
    Promise.all([refreshStatus(), refreshFiles(), refreshUsage()]).then(function () {
      renderFiles();
      renderThread();
      if (window.innerWidth > 860) $('#input').focus();
    });
    // Pick up files that were copied straight into the knowledge folder.
    setInterval(function () { if (!document.hidden && !S.streaming) refreshFiles(); }, 15000);
  }
  // Wait for the maths and code-colouring scripts (they load with "defer").
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
</script>
</body>
</html>
~~~~
