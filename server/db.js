// Blog storage: one SQLite file (Node's built-in driver, no native add-on to compile).
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const DATA_DIR = path.resolve(process.env.DATA_DIR || 'data');
mkdirSync(DATA_DIR, { recursive: true });

const db = new DatabaseSync(path.join(DATA_DIR, 'blog.db'));
db.exec(`
  PRAGMA journal_mode = WAL;
  CREATE TABLE IF NOT EXISTS posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    excerpt      TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    published    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    published_at TEXT
  );
  CREATE INDEX IF NOT EXISTS posts_published ON posts (published, published_at DESC);
`);

const q = {
  listPublished: db.prepare(`SELECT id, slug, title, excerpt, published, created_at, updated_at, published_at
    FROM posts WHERE published = 1 ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?`),
  listAll: db.prepare(`SELECT id, slug, title, excerpt, published, created_at, updated_at, published_at
    FROM posts ORDER BY COALESCE(published_at, updated_at) DESC, id DESC`),
  bySlug: db.prepare('SELECT * FROM posts WHERE slug = ?'),
  byId: db.prepare('SELECT * FROM posts WHERE id = ?'),
  insert: db.prepare(`INSERT INTO posts (slug, title, excerpt, body, published, created_at, updated_at, published_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)`),
  update: db.prepare(`UPDATE posts SET slug = ?, title = ?, excerpt = ?, body = ?, published = ?, updated_at = ?, published_at = ?
    WHERE id = ?`),
  remove: db.prepare('DELETE FROM posts WHERE id = ?'),
};

export function slugify(s) {
  return String(s).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);
}

// "my-post", then "my-post-2", "my-post-3"... skipping the post being edited
function freeSlug(wanted, selfId = null) {
  const base = slugify(wanted) || 'post';
  for (let n = 1; ; n++) {
    const slug = n === 1 ? base : `${base}-${n}`;
    const hit = q.bySlug.get(slug);
    if (!hit || hit.id === selfId) return slug;
  }
}

export const posts = {
  listPublished: (limit = 50, offset = 0) => q.listPublished.all(limit, offset),
  listAll: () => q.listAll.all(),
  bySlug: slug => q.bySlug.get(slug),
  byId: id => q.byId.get(id),

  create({ title, slug, excerpt = '', body = '', published = false }) {
    const now = new Date().toISOString();
    const info = q.insert.run(freeSlug(slug || title), title, excerpt, body, published ? 1 : 0, now, now, published ? now : null);
    return q.byId.get(Number(info.lastInsertRowid));
  },

  update(id, { title, slug, excerpt, body, published }) {
    const old = q.byId.get(id);
    if (!old) return null;
    const now = new Date().toISOString();
    const pub = published === undefined ? !!old.published : !!published;
    q.update.run(
      slug === undefined ? old.slug : freeSlug(slug || title || old.title, id),
      title ?? old.title, excerpt ?? old.excerpt, body ?? old.body, pub ? 1 : 0, now,
      pub ? (old.published_at || now) : null,   // first publish sets the date; unpublishing clears it
      id);
    return q.byId.get(id);
  },

  remove: id => q.remove.run(id).changes > 0,
};
