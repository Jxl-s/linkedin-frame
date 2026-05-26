'use strict';

// Matches Python bot's apply_arc_text defaults
const ARC = {
  fontSize: 85,
  radius: 333,
  letterSpacing: 10,
  radiusOffset: 4,
  centerAngleDeg: 123.0,
  clockwise: true,
};

const LINKEDIN_GREEN = '#457032';
const GIF_WORKER = 'js/vendor/gif.worker.js';

// ── state ────────────────────────────────────────────────────────────────────

let alphaImage  = null;
let maskCache   = null; // cached alpha mask pixel data (read once, reused)
let sourceImage = null; // static image
let rawGifFrames = null; // decoded GIF frames: [{canvas, delay}]
let isGif = false;

let rafId = null;
let animTimer = null;
let animFrames = [];
let animIdx = 0;
let encodeVersion = 0;  // incremented each encode; stale results are dropped

// ── helpers ──────────────────────────────────────────────────────────────────

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Could not load: ${src}`));
    img.src = src;
  });
}

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function scheduleRender() {
  cancelAnimationFrame(rafId);
  rafId = requestAnimationFrame(render);
}

function setStatus(msg) {
  document.getElementById('status').textContent = msg;
}

function setDlState(state, href) {
  const dl    = document.getElementById('download-btn');
  const label = document.getElementById('dl-label');
  dl.classList.remove('encoding');
  dl.classList.add('visible');

  switch (state) {
    case 'png':
      label.textContent = 'Download PNG';
      dl.download = 'frame.png';
      if (href) dl.href = href;
      break;
    case 'encoding':
      label.textContent = 'Encoding GIF…';
      dl.classList.add('encoding');
      break;
    case 'gif':
      label.textContent = 'Download GIF';
      dl.download = 'frame.gif';
      dl.href = href;
      break;
  }
}

// ── alpha mask (read once, cached) ───────────────────────────────────────────

function getAlphaMask() {
  if (maskCache) return maskCache;
  const W = alphaImage.naturalWidth;
  const H = alphaImage.naturalHeight;
  const mc = document.createElement('canvas');
  mc.width = W;
  mc.height = H;
  const ctx = mc.getContext('2d');
  ctx.drawImage(alphaImage, 0, 0);
  maskCache = ctx.getImageData(0, 0, W, H).data;
  return maskCache;
}

// ── rendering ─────────────────────────────────────────────────────────────────

/**
 * Composite a colored ring using alpha.png as a mask.
 * Mirrors lib/frame.py :: apply_frame.
 */
function applyFrame(ctx, rgb) {
  const { width: W, height: H } = ctx.canvas;
  const [r, g, b] = rgb;
  const mask = getAlphaMask();

  const frameData = new ImageData(W, H);
  for (let i = 0; i < mask.length; i += 4) {
    frameData.data[i]     = r;
    frameData.data[i + 1] = g;
    frameData.data[i + 2] = b;
    frameData.data[i + 3] = mask[i]; // R channel of grayscale PNG = alpha
  }

  const fc = document.createElement('canvas');
  fc.width = W;
  fc.height = H;
  fc.getContext('2d').putImageData(frameData, 0, 0);
  ctx.drawImage(fc, 0, 0);
}

/**
 * Render text along a circular arc.
 * Mirrors lib/text.py :: apply_arc_text.
 */
function applyArcText(ctx, text) {
  if (!text) return;
  const { fontSize, radius, letterSpacing, radiusOffset, centerAngleDeg, clockwise } = ARC;
  const cx = ctx.canvas.width / 2;
  const cy = ctx.canvas.height / 2;
  const direction = clockwise ? -1 : 1;

  ctx.save();
  ctx.font = `bold ${fontSize}px Carlito`;
  ctx.fillStyle = '#ffffff';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  const chars = [...text];
  const widths = chars.map(ch => ctx.measureText(ch).width);
  const totalWidth = widths.reduce((a, b) => a + b, 0) + letterSpacing * Math.max(chars.length - 1, 0);
  const startRad = (centerAngleDeg * Math.PI) / 180 - direction * (totalWidth / radius) / 2;

  let arcPos = 0;
  for (let i = 0; i < chars.length; i++) {
    const cw = widths[i];
    const angleRad = startRad + direction * (arcPos + cw / 2) / radius;
    const rEff = radius + radiusOffset;
    ctx.save();
    ctx.translate(cx + rEff * Math.cos(angleRad), cy + rEff * Math.sin(angleRad));
    ctx.rotate(angleRad + direction * Math.PI / 2);
    ctx.fillText(chars[i], 0, 0);
    ctx.restore();
    arcPos += cw + letterSpacing;
  }

  ctx.restore();
}

// ── GIF decode ───────────────────────────────────────────────────────────────

/**
 * Decode an animated GIF into an array of fully-composited frame canvases.
 * Handles disposal methods 0/1 (keep), 2 (clear), 3 (restore to previous).
 * delay is in milliseconds.
 */
function decodeGif(arrayBuffer) {
  const reader = new GifReader(new Uint8Array(arrayBuffer)); // eslint-disable-line no-undef
  const W = reader.width;
  const H = reader.height;
  const n = reader.numFrames();

  const frames = [];
  let composited = new Uint8ClampedArray(W * H * 4); // starts transparent
  let savedPixels = null;

  for (let i = 0; i < n; i++) {
    const info = reader.frameInfo(i);

    // Save pre-blit state for disposal type 3
    if (info.disposal === 3) savedPixels = composited.slice();

    // Blit this frame's patch onto the composited buffer in-place
    reader.decodeAndBlitFrameRGBA(i, composited);

    // Snapshot the full composited image as a canvas
    const canvas = document.createElement('canvas');
    canvas.width = W;
    canvas.height = H;
    canvas.getContext('2d').putImageData(new ImageData(composited.slice(), W, H), 0, 0);

    frames.push({
      canvas,
      delay: Math.max(info.delay * 10, 20), // centiseconds → ms, floor at 20ms
    });

    // Apply disposal for next frame
    switch (info.disposal) {
      case 2: composited = new Uint8ClampedArray(W * H * 4); break; // clear
      case 3: composited = savedPixels; break;                       // restore
      // 0 or 1: keep composited as-is
    }
  }

  return { frames, width: W, height: H };
}

// ── GIF preview animation ────────────────────────────────────────────────────

function startAnimation(frames) {
  stopAnimation();
  const canvas = document.getElementById('preview-canvas');
  canvas.width  = alphaImage.naturalWidth;
  canvas.height = alphaImage.naturalHeight;
  animFrames = frames;
  animIdx = 0;
  tick();
}

function stopAnimation() {
  clearTimeout(animTimer);
  animTimer = null;
  animFrames = [];
}

function tick() {
  if (!animFrames.length) return;
  const { canvas: src, delay } = animFrames[animIdx];
  const canvas = document.getElementById('preview-canvas');
  canvas.getContext('2d').drawImage(src, 0, 0);
  animIdx = (animIdx + 1) % animFrames.length;
  animTimer = setTimeout(tick, delay);
}

// ── GIF encode ───────────────────────────────────────────────────────────────

function encodeGifFrames(processedFrames, W, H) {
  const myVersion = ++encodeVersion;

  return new Promise((resolve, reject) => {
    const gif = new GIF({ // eslint-disable-line no-undef
      workers: 2,
      quality: 10,
      width: W,
      height: H,
      workerScript: GIF_WORKER,
    });

    for (const { canvas, delay } of processedFrames) {
      // GIF has no full alpha — composite onto black, matching lib/process.py
      const flat = document.createElement('canvas');
      flat.width = W;
      flat.height = H;
      const ctx = flat.getContext('2d');
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, W, H);
      ctx.drawImage(canvas, 0, 0);
      gif.addFrame(flat, { delay, copy: true });
    }

    gif.on('finished', blob => {
      if (myVersion !== encodeVersion) return; // superseded by a newer render
      resolve(blob);
    });
    gif.on('error', reject);
    gif.render();
  });
}

// ── process GIF frames ───────────────────────────────────────────────────────

function processGifFrames(rgb, text, W, H) {
  return rawGifFrames.map(({ canvas, delay }) => {
    const out = document.createElement('canvas');
    out.width = W;
    out.height = H;
    const ctx = out.getContext('2d');
    ctx.drawImage(canvas, 0, 0, W, H); // scale source frame to output size
    applyFrame(ctx, rgb);
    applyArcText(ctx, text);
    return { canvas: out, delay };
  });
}

// ── render ───────────────────────────────────────────────────────────────────

function renderStatic() {
  if (!sourceImage) return;

  const rgb = hexToRgb(document.getElementById('color-hex').value);
  if (!rgb) { setStatus('Invalid color — use a hex code like #5865F2.'); return; }
  setStatus('');

  const W = alphaImage.naturalWidth;
  const H = alphaImage.naturalHeight;
  const canvas = document.getElementById('preview-canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  ctx.drawImage(sourceImage, 0, 0, W, H);
  applyFrame(ctx, rgb);
  applyArcText(ctx, document.getElementById('arc-text').value.trim());

  document.getElementById('drop-zone').classList.add('has-image');
  setDlState('png', canvas.toDataURL('image/png'));
}

function renderGif() {
  if (!rawGifFrames) return;

  const rgb = hexToRgb(document.getElementById('color-hex').value);
  if (!rgb) { setStatus('Invalid color — use a hex code like #5865F2.'); return; }
  setStatus('');

  const W = alphaImage.naturalWidth;
  const H = alphaImage.naturalHeight;
  const text = document.getElementById('arc-text').value.trim();

  const processed = processGifFrames(rgb, text, W, H);
  startAnimation(processed);
  document.getElementById('drop-zone').classList.add('has-image');
  setDlState('encoding');

  encodeGifFrames(processed, W, H).then(blob => {
    setDlState('gif', URL.createObjectURL(blob));
  }).catch(err => {
    console.error('[gif encode]', err);
    setStatus('GIF encoding failed.');
  });
}

function render() {
  if (isGif) renderGif();
  else renderStatic();
}

// ── init ─────────────────────────────────────────────────────────────────────

async function init() {
  try {
    alphaImage = await loadImage('assets/alpha.png');
  } catch {
    setStatus('Failed to load frame asset — serve the page from the repo root.');
    return;
  }

  // fonts.load() is more reliable than fonts.ready for custom fonts that haven't
  // been triggered by the DOM yet; ensures Carlito is canvas-ready on first render.
  try {
    await document.fonts.load(`bold ${ARC.fontSize}px Carlito`);
  } catch {
    await document.fonts.ready;
  }

  const dropZone    = document.getElementById('drop-zone');
  const fileInput   = document.getElementById('file-input');
  const colorPicker = document.getElementById('color-picker');
  const colorHex    = document.getElementById('color-hex');
  const arcText     = document.getElementById('arc-text');

  async function loadFile(file) {
    if (!file?.type.startsWith('image/')) {
      setStatus('Please upload an image file.');
      return;
    }

    stopAnimation();

    try {
      if (file.type === 'image/gif') {
        const buffer = await file.arrayBuffer();
        const { frames } = decodeGif(buffer);
        if (frames.length === 0) throw new Error('GIF has no frames');
        rawGifFrames = frames;
        sourceImage  = null;
        isGif        = true;
      } else {
        rawGifFrames = null;
        sourceImage  = await loadImage(URL.createObjectURL(file));
        isGif        = false;
      }
      setStatus('');
      render();
    } catch (err) {
      console.error('[loadFile]', err);
      setStatus('Could not read that image file.');
    }
  }

  fileInput.addEventListener('change', e => loadFile(e.target.files[0]));

  dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    loadFile(e.dataTransfer.files[0]);
  });

  // Static images: live updates on every keystroke / drag.
  // GIFs: update on blur (text) or change (color picker) — re-processing every
  //        frame on each keypress is too expensive.
  colorPicker.addEventListener('input', () => {
    colorHex.value = colorPicker.value;
    if (!isGif) render();
  });
  colorPicker.addEventListener('change', () => {
    if (isGif) renderGif();
  });

  colorHex.addEventListener('input', () => {
    const val = colorHex.value;
    if (/^#[0-9a-fA-F]{6}$/.test(val)) {
      colorPicker.value = val;
      if (!isGif) scheduleRender();
    }
  });
  colorHex.addEventListener('blur', () => {
    if (isGif && /^#[0-9a-fA-F]{6}$/.test(colorHex.value)) renderGif();
  });

  arcText.addEventListener('input', () => { if (!isGif) scheduleRender(); });
  arcText.addEventListener('blur',  () => { if (isGif) renderGif(); });

  document.getElementById('preset-btn').addEventListener('click', () => {
    colorHex.value    = LINKEDIN_GREEN;
    colorPicker.value = LINKEDIN_GREEN;
    arcText.value     = '#OPENTOWORK';
    render(); // deliberate action — update immediately regardless of type
  });
}

document.addEventListener('DOMContentLoaded', init);
