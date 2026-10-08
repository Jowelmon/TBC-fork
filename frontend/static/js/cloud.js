// cloud.js - The AI's on-screen presence: a small cloud with a face.
//
// It floats over every screen and can be dragged anywhere (mouse, touch or
// arrow keys); its position is remembered. Its expression shows what the AI
// is doing, and clicking it says so in words:
//   online   smiling            Tencent Cloud ADP is answering
//   ready    calm, blinking     offline models in use, or ADP not yet called
//   thinking eyes up, dots      a model call is in progress
//   alert    worried            the AI second opinion disagrees with the rules
//   offline  asleep, grey       the AI is unavailable (the reason is shown)
// It is decoration with a job: it never acts, it only reports.

const FACES = {
  online:   { eyes: 'open',  mouth: 'M-9 6 Q0 14 9 6',   tint: '#DCEBFF' },
  ready:    { eyes: 'open',  mouth: 'M-7 8 Q0 11 7 8',   tint: '#E6EEFB' },
  thinking: { eyes: 'up',    mouth: 'M-5 9 L5 9',        tint: '#E4E6FF' },
  alert:    { eyes: 'wide',  mouth: 'M-7 11 Q0 5 7 11',  tint: '#FFEFCF' },
  offline:  { eyes: 'shut',  mouth: 'M-4 9 Q0 11 4 9',   tint: '#E2E5EA' },
};

// The cloud outline, centred on (0, 0), about 100 x 64 units.
const CLOUD_PATH = 'M-38 26 Q-52 26 -52 12 Q-52 -2 -38 -2 Q-36 -22 -16 -22 Q-6 -36 10 -30 '
  + 'Q26 -38 34 -20 Q52 -20 52 0 Q56 16 42 26 Z';

function eyes(kind) {
  if (kind === 'shut') {
    return '<path d="M-17 -2 Q-12 2 -7 -2 M7 -2 Q12 2 17 -2" class="cf-line"/>';
  }
  const dy = kind === 'up' ? -4 : 0;
  const r = kind === 'wide' ? 4.2 : 3.4;
  const brows = kind === 'wide'
    ? '<path d="M-17 -8 L-8 -12 M8 -12 L17 -8" class="cf-line"/>' : '';
  return `${brows}<g class="cf-eyes"><ellipse cx="-12" cy="${-2 + dy}" rx="${r}" ry="${r + 0.8}" class="cf-eye"/>`
    + `<ellipse cx="12" cy="${-2 + dy}" rx="${r}" ry="${r + 0.8}" class="cf-eye"/></g>`;
}

// SVG markup for a cloud face. Reused small inside cards.
export function cloudSvg(state = 'ready', size = 72) {
  const f = FACES[state] || FACES.ready;
  const extra = state === 'thinking'
    ? '<g class="cf-dots"><circle cx="38" cy="-30" r="3"/><circle cx="46" cy="-38" r="2.4"/><circle cx="52" cy="-45" r="1.8"/></g>'
    : state === 'offline' ? '<text x="30" y="-28" class="cf-zzz">z</text><text x="40" y="-38" class="cf-zzz cf-zzz2">z</text>'
    : state === 'alert' ? '<text x="40" y="-24" class="cf-bang">!</text>' : '';
  return `<svg class="cloud-svg cloud--${state}" width="${size}" height="${Math.round(size * 0.78)}" viewBox="-58 -50 116 90" aria-hidden="true" focusable="false">
    <path d="${CLOUD_PATH}" class="cf-body" style="fill:${f.tint}"/>
    ${eyes(f.eyes)}
    <ellipse cx="-22" cy="7" rx="5" ry="3" class="cf-cheek"/><ellipse cx="22" cy="7" rx="5" ry="3" class="cf-cheek"/>
    <path d="${f.mouth}" class="cf-line"/>
    ${extra}
  </svg>`;
}

const MESSAGES = {
  online: 'Tencent Cloud ADP is answering. I draft knowledge and give second opinions; people decide.',
  ready: 'Ready. I draft expert knowledge and give an advisory second opinion; I never approve anything.',
  thinking: 'Thinking…',
  alert: 'My second opinion disagrees with the rule-based diagnosis on this case. The AOM still decides.',
  offline: 'The AI model is unavailable right now. Diagnosis carries on without me.',
};

let el, bubble, state = 'ready', base = 'ready', note = '', busy = 0;

function render() {
  if (!el) return;
  el.querySelector('.cloud-face').innerHTML = cloudSvg(state, 104);
  el.setAttribute('aria-label', `AI assistant: ${MESSAGES[state].replace('…', '')} Press Enter for details; arrow keys move me.`);
  if (!bubble.hidden) bubble.textContent = note && state !== 'thinking' ? `${MESSAGES[state]} ${note}` : MESSAGES[state];
}

function place(x, y) {
  const w = el.offsetWidth || 90, h = el.offsetHeight || 70;
  // Never over the top bar: the role badge and theme controls live there.
  const top = (document.getElementById('topbar')?.getBoundingClientRect().bottom || 0) + 8;
  const nx = Math.min(Math.max(8, x), window.innerWidth - w - 8);
  const ny = Math.min(Math.max(top, y), window.innerHeight - h - 8);
  el.style.left = `${nx}px`; el.style.top = `${ny}px`;
  el.style.right = 'auto'; el.style.bottom = 'auto';
  // On the left half the speech bubble opens to the right, staying on screen.
  el.classList.toggle('cloud-left', nx + w / 2 < window.innerWidth / 2);
  return [nx, ny];
}

// Default home: in the navigation rail, above its footer, so the cloud never
// covers a card. Falls back to the CSS corner when the rail is too narrow.
function dock() {
  const rail = document.getElementById('nav-rail')?.getBoundingClientRect();
  const foot = document.getElementById('kb-footer')?.getBoundingClientRect();
  const w = el.offsetWidth || 90, h = el.offsetHeight || 70;
  if (!rail || !foot || rail.width < w + 16) {
    el.style.left = el.style.top = '';
    el.style.right = el.style.bottom = '';
    el.classList.remove('cloud-left');
    return;
  }
  place(rail.left + (rail.width - w) / 2, foot.top - h - 16);
}

function save() {
  try { localStorage.setItem('tbc_cloud_pos', JSON.stringify([parseInt(el.style.left, 10), parseInt(el.style.top, 10)])); } catch (_) { /* not remembered */ }
}

export function initCloud() {
  el = document.createElement('div');
  el.id = 'ai-cloud';
  el.tabIndex = 0;
  el.setAttribute('role', 'button');
  el.innerHTML = '<div class="cloud-face"></div>';
  bubble = document.createElement('div');
  bubble.className = 'cloud-bubble';
  bubble.hidden = true;
  bubble.setAttribute('role', 'status');
  el.appendChild(bubble);
  document.body.appendChild(el);
  render();

  let saved = null;
  try { saved = JSON.parse(localStorage.getItem('tbc_cloud_pos') || 'null'); } catch (_) { /* fresh start */ }
  const moved = Array.isArray(saved) && saved.length === 2 && saved.every(Number.isFinite);
  if (moved) place(saved[0], saved[1]); else requestAnimationFrame(dock);

  // Drag with mouse or touch; a press without movement is a click.
  let start = null;
  el.addEventListener('pointerdown', e => {
    const r = el.getBoundingClientRect();
    start = { x: e.clientX, y: e.clientY, dx: e.clientX - r.left, dy: e.clientY - r.top, moved: false };
    el.setPointerCapture(e.pointerId);
  });
  el.addEventListener('pointermove', e => {
    if (!start) return;
    if (Math.abs(e.clientX - start.x) + Math.abs(e.clientY - start.y) > 4) start.moved = true;
    if (start.moved) { el.classList.add('dragging'); place(e.clientX - start.dx, e.clientY - start.dy); }
  });
  el.addEventListener('pointerup', () => {
    if (!start) return;
    if (start.moved) save(); else toggleBubble();
    el.classList.remove('dragging');
    start = null;
  });
  el.addEventListener('keydown', e => {
    const step = e.shiftKey ? 40 : 12;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[e.key]) {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      place(r.left + moves[e.key][0], r.top + moves[e.key][1]);
      save();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault(); toggleBubble();
    } else if (e.key === 'Escape') {
      bubble.hidden = true;
    }
  });
  // Keep the cloud on screen when the window changes size: re-dock it unless
  // the user has put it somewhere themselves.
  window.addEventListener('resize', () => {
    let remembered = false;
    try { remembered = !!localStorage.getItem('tbc_cloud_pos'); } catch (_) { /* treat as not moved */ }
    if (remembered && el.style.left) {
      place(parseInt(el.style.left, 10), parseInt(el.style.top, 10));
    } else {
      dock();
    }
  });
}

function toggleBubble() {
  bubble.hidden = !bubble.hidden;
  render();
}

// Base state from /system/info: online | ready | offline.
export function setCloudStatus(next, message = '') {
  base = next; note = message;
  if (!busy) { state = base; render(); }
}

// A short-lived mood on top of the base state, e.g. on a screen showing a
// disagreement. Cleared by passing null.
export function setCloudMood(mood) {
  if (busy) return;
  state = mood || base;
  render();
}

// Wrap a model call: the cloud thinks while it runs.
export async function cloudThinking(promise) {
  busy += 1; state = 'thinking'; render();
  try { return await promise; }
  finally { busy -= 1; if (!busy) { state = base; render(); } }
}
