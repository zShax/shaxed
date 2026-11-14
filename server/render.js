// HTML for every page. Plain template strings; esc() everything that is not already HTML.
import { marked } from 'marked';
import sanitizeHtml from 'sanitize-html';
import * as cv from './cv.js';

const SITE_URL = (process.env.SITE_URL || '').replace(/\/+$/, '');

// Links that leave the site open in a new tab.
const leaves = href => /^https?:///i.test(href || '') && !(SITE_URL && String(href).startsWith(SITE_URL));
const out = href => (leaves(href) ? ' target="_blank" rel="noopener"' : '');

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function markdown(md) {
  return sanitizeHtml(marked.parse(String(md ?? ''), { gfm: true }), {
    allowedTags: [...sanitizeHtml.defaults.allowedTags, 'img', 'h1', 'h2', 'del', 'figure', 'figcaption'],
    allowedAttributes: { ...sanitizeHtml.defaults.allowedAttributes, a: ['href', 'name', 'target', 'rel'], img: ['src', 'alt', 'title', 'width', 'height', 'loading'], code: ['class'] },
    allowedSchemes: ['http', 'https', 'mailto'],
    transformTags: {
      img: (tagName, attribs) => ({ tagName, attribs: { ...attribs, loading: 'lazy' } }),
      a: (tagName, { target, rel, ...attribs }) => ({ tagName, attribs: leaves(attribs.href) ? { ...attribs, target: '_blank', rel: 'noopener' } : attribs }),
    },
  });
}

const fmtDate = iso => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Europe/Bucharest' });
const isoDay = iso => String(iso).slice(0, 10);

function layout({ title, description = '', path = '/', body, head = '', bodyClass = '', noindex = false }) {
  const canonical = SITE_URL ? `<link rel="canonical" href="${esc(SITE_URL + path)}">` : '';
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
${noindex ? '<meta name="robots" content="noindex">' : canonical}
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:type" content="website">
<link rel="alternate" type="application/rss+xml" title="Marius Toma: blog" href="/blog/feed.xml">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preload" href="/fonts/archivo/archivo-latin-wdth-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/css/site.css">
${head}
</head>
<body class="${esc(bodyClass)}">
<a class="skip" href="#main">Skip to content</a>
${body}
</body>
</html>`;
}

const plainHeader = `<header class="bar">
  <a class="bar-name" href="/">Marius Toma</a>
  <nav aria-label="Main"><a href="/#experience">Experience</a><a href="/#projects">Projects</a><a href="/blog">Blog</a><a href="/#contact">Contact</a></nav>
</header>`;

const contactFooter = `<footer class="contact" id="contact">
  <div class="wrap">
    <h2>Get in touch</h2>
    <p class="contact-mail"><a href="mailto:${esc(cv.person.email)}">${esc(cv.person.email)}</a></p>
    <ul class="contact-links">
      ${cv.person.links.map(l => `<li><span>${esc(l.label)}</span> <a href="${esc(l.href)}"${out(l.href)}>${esc(l.text)}</a></li>`).join('\n      ')}
      <li><span>Based in</span> ${esc(cv.person.location)}</li>
    </ul>
  </div>
</footer>`;

const postRow = p => `<li>
        <time datetime="${isoDay(p.published_at)}">${fmtDate(p.published_at)}</time>
        <div>
          <h3><a href="/blog/${esc(p.slug)}">${esc(p.title)}</a></h3>
          ${p.excerpt ? `<p>${esc(p.excerpt)}</p>` : ''}
        </div>
      </li>`;

/* ------------------------------------------------------------------ home */
export function home(latestPosts) {
  const description = 'Marius Toma, full-stack web developer and founder in Arad, Romania. CV, live projects and blog.';
  const head = `<link rel="preload" href="/fonts/bodoni/bodoni-moda-latin-opsz-normal.woff2" as="font" type="font/woff2" crossorigin>
<script type="importmap">{"imports":{"three":"/vendor/three/build/three.module.min.js","three/addons/":"/vendor/three/addons/"}}</script>
<script type="module" src="/js/hero.js"></script>`;

  const body = `<header class="hero" id="top">
  <nav class="hero-nav" aria-label="Main">
    <a class="hero-nav-name" href="#top">Marius Toma</a>
    <span class="hero-nav-links"><a class="wide-only" href="#experience">Experience</a><a href="#projects">Projects</a><a href="/blog">Blog</a><a href="#contact">Contact</a></span>
  </nav>
  <h1 class="hero-name"><span class="name-marius">Marius</span> <span class="name-toma">Toma</span></h1>
  <div class="hero-blurbs">
    <p class="blurb-marius">${esc(cv.hero.marius)}</p>
    <p class="blurb-toma">${esc(cv.hero.toma)}</p>
    <p class="hero-hint" id="hero-hint" aria-hidden="true"><span>Drag a figure to push it around</span></p>
  </div>
  <canvas id="figures" aria-hidden="true"></canvas>
  <p class="sr-only">Two 3D figurines of the same person stand side by side: Marius in a blue blazer, bow tie and round glasses, and Toma in a white graphic tee, black shorts and flame-print sneakers. Marius gestures as if giving a speech; Toma runs, jumps and climbs.</p>
</header>

<main id="main">
  <section class="profile">
    <div class="wrap">
      <p class="lead">${esc(cv.profile[0])}</p>
      <p>${esc(cv.profile[1])}</p>
    </div>
  </section>

  <section class="block" id="experience">
    <div class="wrap">
      <h2>Experience</h2>
      <ol class="timeline">
        ${cv.experience.map(e => `<li>
          <p class="when">${esc(e.when)}</p>
          <div>
            <h3>${esc(e.role)}</h3>
            <p class="org">${esc(e.org)}${e.note ? `<span>, ${esc(e.note)}</span>` : ''}</p>
            <ul>${e.points.map(p => `<li>${esc(p)}</li>`).join('')}</ul>
            ${e.tech ? `<p class="tech">Worked with ${esc(e.tech)}.</p>` : ''}
          </div>
        </li>`).join('\n        ')}
      </ol>
    </div>
  </section>

  <section class="built" id="projects">
    <div class="wrap">
      <h2>Things I built</h2>
      <p class="built-intro">Four of them are live. Open one.</p>
      <ul class="live">
        ${cv.liveProjects.map(p => `<li><a href="${esc(p.href)}"${out(p.href)}>
          <span class="live-domain">${esc(p.domain)}</span>
          <span class="live-text"><strong>${esc(p.name)}</strong> ${esc(p.what)}</span>
        </a></li>`).join('\n        ')}
      </ul>
      <h3>Running inside companies</h3>
      <dl class="private">
        ${cv.privateProjects.map(p => `<div><dt>${esc(p.name)}</dt><dd>${esc(p.what)}</dd></div>`).join('\n        ')}
      </dl>
    </div>
  </section>

  <section class="block" id="background">
    <div class="wrap">
      <h2>Education</h2>
      <dl class="rows">
        ${cv.education.map(e => `<div><dt>${esc(e.what)}</dt><dd>${esc(e.where)}<span>${esc(e.when)}</span></dd></div>`).join('\n        ')}
      </dl>

      <h2>Skills</h2>
      <dl class="rows">
        ${cv.skills.map(s => `<div><dt>${esc(s.group)}</dt><dd>${esc(s.items)}</dd></div>`).join('\n        ')}
        <div><dt>Languages</dt><dd>${cv.languages.map(l => `${esc(l.name)} (${esc(l.level)})`).join(', ')}</dd></div>
      </dl>

      <h2>Activities and awards</h2>
      <dl class="rows">
        ${cv.awards.map(a => `<div><dt>${esc(a.what)}</dt><dd>${esc(a.detail)}</dd></div>`).join('\n        ')}
        <div><dt>Interests</dt><dd>${esc(cv.interests)}</dd></div>
      </dl>
    </div>
  </section>

  <section class="block" id="blog">
    <div class="wrap">
      <h2>Blog</h2>
      ${latestPosts.length
        ? `<ol class="posts">\n      ${latestPosts.map(postRow).join('\n      ')}\n      </ol>\n      <p class="more"><a href="/blog">All posts</a></p>`
        : '<p class="empty">Nothing published yet. The first post is on its way.</p>'}
    </div>
  </section>
</main>

${contactFooter}`;
  return layout({ title: 'Marius Toma, full-stack web developer', description, path: '/', body, head, bodyClass: 'home' });
}

/* ------------------------------------------------------------------ blog */
export function blogIndex(list) {
  const body = `${plainHeader}
<main id="main" class="page">
  <div class="wrap">
    <h1>Blog</h1>
    ${list.length ? `<ol class="posts">\n      ${list.map(postRow).join('\n      ')}\n    </ol>` : '<p class="empty">Nothing published yet. The first post is on its way.</p>'}
  </div>
</main>
${contactFooter}`;
  return layout({ title: 'Blog, Marius Toma', description: 'Notes on building software, automation and running a small software company.', path: '/blog', body });
}

export function blogPost(p, { draft = false } = {}) {
  const body = `${plainHeader}
<main id="main" class="page">
  <article class="wrap post">
    ${draft ? '<p class="draft-flag">Draft. Only you can see this page.</p>' : ''}
    <p class="post-meta">${p.published_at ? `<time datetime="${isoDay(p.published_at)}">${fmtDate(p.published_at)}</time>` : 'Not published'}</p>
    <h1>${esc(p.title)}</h1>
    ${p.excerpt ? `<p class="post-lead">${esc(p.excerpt)}</p>` : ''}
    <div class="prose">${markdown(p.body)}</div>
    <p class="more"><a href="/blog">All posts</a></p>
  </article>
</main>
${contactFooter}`;
  return layout({ title: `${p.title}, Marius Toma`, description: p.excerpt, path: `/blog/${p.slug}`, body, noindex: draft });
}

export function feed(list) {
  const base = SITE_URL || '';
  return `<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<title>Marius Toma: blog</title>
<link>${esc(base)}/blog</link>
<description>Notes on building software, automation and running a small software company.</description>
${list.map(p => `<item><title>${esc(p.title)}</title><link>${esc(base)}/blog/${esc(p.slug)}</link><guid>${esc(base)}/blog/${esc(p.slug)}</guid><pubDate>${new Date(p.published_at).toUTCString()}</pubDate><description>${esc(p.excerpt)}</description></item>`).join('\n')}
</channel></rss>`;
}

/* ----------------------------------------------------------------- admin */
export function admin({ signedIn, enabled }) {
  const body = `${plainHeader}
<main id="main" class="page admin" data-signed-in="${signedIn ? '1' : ''}">
  <div class="wrap">
    ${!enabled ? `<h1>Admin is off</h1>
    <p>Set <code>ADMIN_PASSWORD</code> (8 or more characters) in the server's environment, then restart it.</p>`
    : !signedIn ? `<h1>Sign in</h1>
    <form id="login" class="stack narrow">
      <label>Password <input type="password" name="password" autocomplete="current-password" required></label>
      <button type="submit">Sign in</button>
      <p class="form-msg" role="alert"></p>
    </form>`
    : `<div class="admin-head">
      <h1>Posts</h1>
      <span><button type="button" id="new">New post</button> <button type="button" id="logout" class="quiet">Sign out</button></span>
    </div>
    <p class="form-msg" id="list-msg" role="alert"></p>
    <ul id="post-list" class="admin-list"></ul>

    <form id="editor" class="stack" hidden>
      <h2 id="editor-title">New post</h2>
      <label>Title <input name="title" required maxlength="200"></label>
      <label>Address <span class="hint">/blog/…  Leave empty to make it from the title.</span> <input name="slug" maxlength="80" pattern="[a-z0-9\\-]*"></label>
      <label>Summary <span class="hint">One or two sentences. Shown in lists and in search results.</span> <textarea name="excerpt" rows="2" maxlength="400"></textarea></label>
      <div class="split">
        <label>Text <span class="hint">Markdown</span> <textarea name="body" rows="22" spellcheck="true"></textarea></label>
        <div><p class="label">Preview</p><div class="prose preview" id="preview"></div></div>
      </div>
      <label class="check"><input type="checkbox" name="published"> Published</label>
      <div class="actions">
        <button type="submit">Save post</button>
        <button type="button" id="cancel" class="quiet">Close</button>
        <button type="button" id="delete" class="danger" hidden>Delete post</button>
      </div>
      <p class="form-msg" role="alert"></p>
    </form>`}
  </div>
</main>
<script type="module" src="/js/admin.js"></script>`;
  return layout({ title: 'Admin, Marius Toma', path: '/admin', body, noindex: true });
}

export function notFound() {
  const body = `${plainHeader}
<main id="main" class="page">
  <div class="wrap">
    <h1>Page not found</h1>
    <p>Nothing lives at this address. Go back to the <a href="/">home page</a> or the <a href="/blog">blog</a>.</p>
  </div>
</main>`;
  return layout({ title: 'Page not found, Marius Toma', body, noindex: true });
}
