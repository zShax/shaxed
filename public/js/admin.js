// Admin: sign in, write and publish posts, edit the CV. Talks to /api.
import { CV_SCHEMA } from './cv-schema.js';
const $ = s => document.querySelector(s);

async function api(method, url, data) {
  const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: data ? JSON.stringify(data) : undefined });
  const json = await r.json().catch(() => ({}));
  if (r.status === 401 && url !== '/api/login') { location.reload(); throw new Error('Your session ended. Sign in again.'); }
  if (!r.ok) throw new Error(json.error || `The server answered ${r.status}.`);
  return json;
}
const say = (el, text, bad = false) => { el.textContent = text; el.classList.toggle('bad', bad); };

/* ---------------------------------------------------------------- sign in */
const loginForm = $('#login');
if (loginForm) {
  loginForm.addEventListener('submit', async e => {
    e.preventDefault();
    const msg = loginForm.querySelector('.form-msg');
    try { await api('POST', '/api/login', { password: loginForm.password.value }); location.reload(); }
    catch (err) { say(msg, err.message, true); }
  });
}

/* ------------------------------------------------------------------ posts */
const list = $('#post-list');
if (list) {
  const editor = $('#editor'), f = editor.elements, listMsg = $('#list-msg'), msg = editor.querySelector('.form-msg');
  const preview = $('#preview'), del = $('#delete');
  let editing = null;                // id of the post in the editor, null for a new one
  let dirty = false;

  const day = iso => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  async function refresh() {
    try {
      const { posts } = await api('GET', '/api/admin/posts');
      list.textContent = '';
      if (!posts.length) { say(listMsg, 'No posts yet. Write the first one.'); return; }
      say(listMsg, '');
      for (const p of posts) {
        const li = document.createElement('li');
        const open = Object.assign(document.createElement('button'), { type: 'button', className: 'link t', textContent: p.title });
        open.onclick = () => edit(p.id);
        const state = Object.assign(document.createElement('span'), { className: 's' + (p.published ? ' live-flag' : ''),
          textContent: p.published ? `Published ${day(p.published_at)}` : `Draft, edited ${day(p.updated_at)}` });
        const view = Object.assign(document.createElement('a'), { href: `/blog/${p.slug}`, textContent: p.published ? 'View' : 'View draft', className: 's' });
        li.append(open, state, view); list.append(li);
      }
    } catch (err) { say(listMsg, err.message, true); }
  }

  function show(post) {
    editing = post ? post.id : null;
    $('#editor-title').textContent = post ? 'Edit post' : 'New post';
    f.title.value = post?.title || ''; f.slug.value = post?.slug || ''; f.excerpt.value = post?.excerpt || '';
    f.body.value = post?.body || ''; f.published.checked = !!post?.published;
    preview.innerHTML = post?.html || '';      // already sanitized by the server
    del.hidden = !post; dirty = false; say(msg, '');
    editor.hidden = false; editor.scrollIntoView({ block: 'start' }); f.title.focus();
  }
  async function edit(id) {
    if (dirty && !confirm('Discard the changes you have not saved?')) return;
    try { show((await api('GET', `/api/admin/posts/${id}`)).post); } catch (err) { say(listMsg, err.message, true); }
  }

  $('#new').onclick = () => { if (!dirty || confirm('Discard the changes you have not saved?')) show(null); };
  $('#cancel').onclick = () => { if (!dirty || confirm('Discard the changes you have not saved?')) { editor.hidden = true; dirty = false; } };
  $('#logout').onclick = async () => { await api('POST', '/api/logout', {}); location.reload(); };

  editor.addEventListener('input', () => { dirty = true; });
  addEventListener('beforeunload', e => { if (dirty) e.preventDefault(); });

  let timer;
  f.body.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try { preview.innerHTML = (await api('POST', '/api/preview', { body: f.body.value })).html; } catch { /* keep the last preview */ }
    }, 350);
  });

  editor.addEventListener('submit', async e => {
    e.preventDefault();
    const data = { title: f.title.value, slug: f.slug.value, excerpt: f.excerpt.value, body: f.body.value, published: f.published.checked };
    try {
      const { post } = editing ? await api('PUT', `/api/posts/${editing}`, data) : await api('POST', '/api/posts', data);
      editing = post.id; f.slug.value = post.slug; del.hidden = false; dirty = false;
      $('#editor-title').textContent = 'Edit post';
      say(msg, post.published ? 'Saved and published.' : 'Saved as a draft.');
      refresh();
    } catch (err) { say(msg, err.message, true); }
  });

  del.onclick = async () => {
    if (!editing || !confirm(`Delete "${f.title.value}"? This cannot be undone.`)) return;
    try { await api('DELETE', `/api/posts/${editing}`); editor.hidden = true; dirty = false; refresh(); }
    catch (err) { say(msg, err.message, true); }
  };

  refresh();
}

/* ------------------------------------------------------------------- tabs */
const tabs = document.querySelectorAll('[data-tab]');
if (tabs.length) {
  const pick = () => {
    const want = location.hash === '#cv' ? 'cv' : 'posts';
    for (const a of tabs) a.toggleAttribute('aria-current', a.dataset.tab === want);
    $('#tab-posts').hidden = want !== 'posts';
    $('#tab-cv').hidden = want !== 'cv';
  };
  addEventListener('hashchange', pick); pick();
}

/* --------------------------------------------------------------------- CV */
// The form is built from CV_SCHEMA; read() walks the same schema back into an object.
const cvForm = $('#cv-form');
if (cvForm) {
  const box = $('#cv-fields'), msg = cvForm.querySelector('.form-msg'), meta = $('#cv-meta');
  let saved = null, cvDirty = false;
  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
  const grow = ta => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 2 + 'px'; };

  // One input for a leaf field. Returns { node, read }.
  function leaf(f, v) {
    const multi = f.type === 'long' || f.type === 'lines';
    const input = multi ? el('textarea', { rows: f.type === 'lines' ? 4 : 2 }) : el('input', { type: f.type === 'url' ? 'url' : 'text' });
    input.value = f.type === 'lines' ? (v || []).join('\n') : (v ?? '');
    if (multi) { input.addEventListener('input', () => grow(input)); requestAnimationFrame(() => grow(input)); }
    const label = el('label', {}, f.label, ...(f.hint ? [' ', el('span', { className: 'hint', textContent: f.hint })] : []), input);
    return { node: label, read: () => (f.type === 'lines' ? input.value.split('\n').map(x => x.trim()).filter(Boolean) : input.value) };
  }

  function group(fields, v) {
    const parts = fields.map(f => [f.key, field(f, v?.[f.key])]);
    return { nodes: parts.map(([, p]) => p.node), read: () => Object.fromEntries(parts.map(([k, p]) => [k, p.read()])) };
  }

  function list(f, items) {
    const rows = [], ol = el('ol', { className: 'cv-items' });
    const blank = () => Object.fromEntries(f.fields.map(x => [x.key, x.type === 'lines' ? [] : '']));
    function add(v, focus = false) {
      const g = group(f.fields, v);
      const title = el('span', { className: 'cv-item-title' });
      const head = el('div', { className: 'cv-item-head' }, title);
      const li = el('li', {}, head, el('div', { className: 'cv-item-body' }, ...g.nodes));
      const row = { li, read: g.read };
      const name = () => { title.textContent = g.read()[f.item] || 'New entry'; };
      li.addEventListener('input', name); name();
      const btn = (text, label, fn) => head.append(el('button', { type: 'button', className: 'quiet small', textContent: text, title: label, ariaLabel: label, onclick: () => { fn(); cvDirty = true; } }));
      const move = d => { const i = rows.indexOf(row), j = i + d; if (j < 0 || j >= rows.length) return;
        rows.splice(i, 1); rows.splice(j, 0, row); rows.forEach(r => ol.append(r.li)); li.querySelector('button')?.focus(); };
      btn('↑', 'Move up', () => move(-1));
      btn('↓', 'Move down', () => move(1));
      btn('Remove', 'Remove this entry', () => { if (confirm(`Remove "${title.textContent}"?`)) { rows.splice(rows.indexOf(row), 1); li.remove(); } });
      rows.push(row); ol.append(li);
      if (focus) li.querySelector('input,textarea')?.focus();
    }
    (items || []).forEach(v => add(v));
    const more = el('button', { type: 'button', className: 'quiet small', textContent: `Add to ${f.label.toLowerCase()}`, onclick: () => { add(blank(), true); cvDirty = true; } });
    return { node: el('div', { className: 'cv-list' }, el('p', { className: 'label', textContent: f.label }), ol, more), read: () => rows.map(r => r.read()) };
  }

  function field(f, v) {
    if (f.type === 'list') return list(f, v);
    if (f.type === 'object') { const g = group(f.fields, v); return { node: el('div', { className: 'cv-group' }, ...g.nodes), read: g.read }; }
    return leaf(f, v);
  }

  let readAll = () => ({});
  function draw(cv) {
    box.textContent = '';
    const parts = CV_SCHEMA.map(s => {
      const p = s.type === 'object' || s.type === 'list' ? field(s, cv[s.key]) : leaf({ ...s, label: '' }, cv[s.key]);
      const sec = el('fieldset', { className: 'cv-section' }, el('legend', { textContent: s.label }),
        ...(s.hint && s.type === 'lines' ? [el('p', { className: 'hint', textContent: s.hint })] : []), p.node);
      box.append(sec);
      return [s.key, p];
    });
    readAll = () => Object.fromEntries(parts.map(([k, p]) => [k, p.read()]));
    cvDirty = false;
  }
  const stamp = r => { meta.textContent = r.updated_at ? `Last saved ${new Date(r.updated_at).toLocaleString('en-GB')}.` : 'Showing the defaults from server/cv.js. Nothing saved here yet.'; };
  const load = r => { saved = r.cv; draw(saved); stamp(r); };

  cvForm.addEventListener('input', () => { cvDirty = true; });
  addEventListener('beforeunload', e => { if (cvDirty) e.preventDefault(); });

  cvForm.addEventListener('submit', async e => {
    e.preventDefault();
    try { load(await api('PUT', '/api/admin/cv', { cv: readAll() })); say(msg, 'Saved. The home page shows it now.'); }
    catch (err) { say(msg, err.message, true); }
  });
  $('#cv-undo').onclick = () => { if (saved && (!cvDirty || confirm('Throw away the changes you have not saved?'))) { draw(saved); say(msg, ''); } };
  $('#cv-reset').onclick = async () => {
    if (!confirm('Drop every CV edit made here and go back to the text in server/cv.js?')) return;
    try { load(await api('DELETE', '/api/admin/cv', {})); say(msg, 'Back to the defaults from cv.js.'); }
    catch (err) { say(msg, err.message, true); }
  };

  api('GET', '/api/admin/cv').then(load).catch(err => say(msg, err.message, true));
}
