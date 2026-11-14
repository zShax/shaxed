// One admin, one password (ADMIN_PASSWORD). The session is a signed, expiring cookie: nothing stored server-side.
import { createHmac, createHash, timingSafeEqual, randomBytes } from 'node:crypto';

const COOKIE = 'shaxed_admin';
const MAX_AGE_S = 60 * 60 * 24 * 7;
const PASSWORD = process.env.ADMIN_PASSWORD || '';
// Without SESSION_SECRET the key changes on every restart, which only means the admin has to sign in again.
const SECRET = process.env.SESSION_SECRET || randomBytes(32).toString('hex');

export const adminEnabled = PASSWORD.length >= 8;

const sign = v => createHmac('sha256', SECRET).update(v).digest('base64url');
const sha = v => createHash('sha256').update(v).digest();
const same = (a, b) => { const x = Buffer.from(a), y = Buffer.from(b); return x.length === y.length && timingSafeEqual(x, y); };

function readCookie(req, name) {
  for (const part of (req.headers.cookie || '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return '';
}

export function isAdmin(req) {
  const [exp, mac] = readCookie(req, COOKIE).split('.');
  return !!exp && !!mac && same(mac, sign(exp)) && Number(exp) > Date.now();
}

export function requireAdmin(req, res, next) {
  if (isAdmin(req)) return next();
  res.status(401).json({ error: 'Sign in first.' });
}

// 5 wrong passwords per address per 15 minutes
const tries = new Map();
const WINDOW_MS = 15 * 60 * 1000, MAX_TRIES = 5;

export function login(req, res) {
  if (!adminEnabled) return res.status(503).json({ error: 'Admin is off. Set ADMIN_PASSWORD (8+ characters) and restart.' });
  const ip = req.ip, now = Date.now();
  const t = tries.get(ip);
  if (t && now - t.first > WINDOW_MS) tries.delete(ip);
  if ((tries.get(ip)?.count || 0) >= MAX_TRIES) return res.status(429).json({ error: 'Too many attempts. Try again in 15 minutes.' });

  const given = typeof req.body?.password === 'string' ? req.body.password : '';
  if (!timingSafeEqual(sha(given), sha(PASSWORD))) {
    const cur = tries.get(ip) || { first: now, count: 0 };
    cur.count++; tries.set(ip, cur);
    return res.status(401).json({ error: 'Wrong password.' });
  }
  tries.delete(ip);
  const exp = String(now + MAX_AGE_S * 1000);
  res.setHeader('Set-Cookie', `${COOKIE}=${exp}.${sign(exp)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${MAX_AGE_S}${req.secure ? '; Secure' : ''}`);
  res.json({ ok: true });
}

export function logout(req, res) {
  res.setHeader('Set-Cookie', `${COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0`);
  res.json({ ok: true });
}
