// Blog admin: sign in, list posts, write and publish. Talks to /api.
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
