import express from 'express';
import compression from 'compression';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { posts } from './db.js';
import { isAdmin, requireAdmin, login, logout, adminEnabled } from './auth.js';
import * as render from './render.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT) || 3000;
const PROD = process.env.NODE_ENV === 'production';

const app = express();
app.disable('x-powered-by');
app.set('trust proxy', 1);          // behind nginx: real client address and https detection
app.use(compression());
app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  next();
});

/* ---------------------------------------------------------------- static */
const longCache = { maxAge: PROD ? '365d' : 0, immutable: PROD };
const shortCache = { maxAge: PROD ? '1h' : 0 };
const nm = (...p) => path.join(ROOT, 'node_modules', ...p);
app.use('/fonts/archivo', express.static(nm('@fontsource-variable', 'archivo', 'files'), longCache));
app.use('/fonts/bodoni', express.static(nm('@fontsource-variable', 'bodoni-moda', 'files'), longCache));
app.use('/vendor/three/build', express.static(nm('three', 'build'), longCache));
app.use('/vendor/three/addons', express.static(nm('three', 'examples', 'jsm'), longCache));
// only the two figurines on the site are public; other models in the folder stay private
app.use('/models', (req, res, next) => (/^\/(marius|toma)-hero\.glb$/.test(req.path) ? next() : res.status(404).end()),
  express.static(path.join(ROOT, 'public', 'models'), shortCache));
app.use(express.static(path.join(ROOT, 'public'), { ...shortCache, index: false }));

/* ----------------------------------------------------------------- pages */
const html = (res, body, status = 200) => res.status(status).type('html').send(body);

app.get('/', (req, res) => html(res, render.home(posts.listPublished(3))));
app.get('/blog', (req, res) => html(res, render.blogIndex(posts.listPublished(200))));
app.get('/blog/feed.xml', (req, res) => res.type('application/rss+xml').send(render.feed(posts.listPublished(30))));
app.get('/blog/:slug', (req, res, next) => {
  const p = posts.bySlug(req.params.slug);
  if (!p) return next();
  if (!p.published) {              // drafts: visible to the signed-in admin only
    if (!isAdmin(req)) return next();
    res.setHeader('Cache-Control', 'no-store');
    return html(res, render.blogPost(p, { draft: true }));
  }
  html(res, render.blogPost(p));
});
app.get('/admin', (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  html(res, render.admin({ signedIn: isAdmin(req), enabled: adminEnabled }));
});
app.get('/healthz', (req, res) => res.json({ ok: true }));

/* ------------------------------------------------------------------- API */
// Public:  GET /api/posts, GET /api/posts/:slug
// Admin:   POST /api/login, POST /api/logout, GET /api/admin/posts[/:id], POST /api/posts, PUT|DELETE /api/posts/:id, POST /api/preview
const api = express.Router();
api.use(express.json({ limit: '2mb' }));
api.use((req, res, next) => { res.setHeader('Cache-Control', 'no-store'); next(); });
// Writes must be JSON. A plain cross-site form cannot send that, which (with the SameSite=Strict cookie) shuts out CSRF.
api.use((req, res, next) => (req.method === 'GET' || /^application\/json\b/i.test(req.get('content-type') || '')
  ? next() : res.status(415).json({ error: 'Send JSON.' })));

const withHtml = p => ({ ...p, published: !!p.published, html: render.markdown(p.body) });
const brief = p => ({ ...p, published: !!p.published });

function readPost(body, { partial = false } = {}) {
  const out = {}, str = (k, max) => { if (typeof body?.[k] === 'string') out[k] = body[k].trim().slice(0, max); };
  str('title', 200); str('slug', 80); str('excerpt', 400);
  if (typeof body?.body === 'string') out.body = body.body.slice(0, 500_000);
  if (typeof body?.published === 'boolean') out.published = body.published;
  if (!partial && !out.title) return { error: 'A post needs a title.' };
  if (out.title === '') return { error: 'A post needs a title.' };
  return { value: out };
}

api.post('/login', login);
api.post('/logout', logout);

api.get('/posts', (req, res) => res.json({ posts: posts.listPublished(100).map(brief) }));
api.get('/posts/:slug', (req, res) => {
  const p = posts.bySlug(req.params.slug);
  if (!p || !p.published) return res.status(404).json({ error: 'No post at this address.' });
  res.json({ post: withHtml(p) });
});

api.get('/admin/posts', requireAdmin, (req, res) => res.json({ posts: posts.listAll().map(brief) }));
api.get('/admin/posts/:id', requireAdmin, (req, res) => {
  const p = posts.byId(Number(req.params.id));
  if (!p) return res.status(404).json({ error: 'This post no longer exists.' });
  res.json({ post: withHtml(p) });
});
api.post('/posts', requireAdmin, (req, res) => {
  const { value, error } = readPost(req.body);
  if (error) return res.status(400).json({ error });
  res.status(201).json({ post: brief(posts.create(value)) });
});
api.put('/posts/:id', requireAdmin, (req, res) => {
  const { value, error } = readPost(req.body, { partial: true });
  if (error) return res.status(400).json({ error });
  const p = posts.update(Number(req.params.id), value);
  if (!p) return res.status(404).json({ error: 'This post no longer exists.' });
  res.json({ post: brief(p) });
});
api.delete('/posts/:id', requireAdmin, (req, res) => {
  if (!posts.remove(Number(req.params.id))) return res.status(404).json({ error: 'This post no longer exists.' });
  res.json({ ok: true });
});
api.post('/preview', requireAdmin, (req, res) => res.json({ html: render.markdown(req.body?.body) }));
api.use((req, res) => res.status(404).json({ error: 'No such endpoint.' }));
app.use('/api', api);

/* ---------------------------------------------------------------- errors */
app.use((req, res) => html(res, render.notFound(), 404));
app.use((err, req, res, next) => {
  const status = err.status || err.statusCode || 500;
  if (status >= 500) console.error(err);
  if (req.path.startsWith('/api/')) return res.status(status).json({ error: status === 400 ? 'That request is not valid JSON.' : 'Something broke on the server.' });
  res.status(status).type('text').send('Something broke on the server.');
});

const server = app.listen(PORT, () => {
  console.log(`shaxed site on http://localhost:${PORT}${adminEnabled ? '' : '  (admin off: ADMIN_PASSWORD not set)'}`);
});
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => server.close(() => process.exit(0)));
