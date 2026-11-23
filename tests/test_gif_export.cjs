const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appSource = fs.readFileSync(path.join(__dirname, '../js/app.js'), 'utf8');

for (const [width, height] of [[128, 128], [320, 320], [320, 180], [180, 320], [321, 180], [1024, 1024]]) {
  test(`${width} × ${height} images export a centered square without stretching`, async () => {
    const encoders = [];
    const draws = [];
    const pngExports = [];
    function makeCanvas() {
      const canvas = {
        getContext: () => ({
          canvas,
          fillRect() {},
          drawImage: (...args) => draws.push(args),
        }),
        toDataURL: () => {
          pngExports.push([canvas.width, canvas.height]);
          return 'data:image/png;base64,';
        },
      };
      return canvas;
    }
    const previewCanvas = makeCanvas();
    const context = vm.createContext({
      Blob,
      URL: { createObjectURL: () => 'blob:test' },
      document: {
        addEventListener() {},
        getElementById: id => id === 'preview-canvas' ? previewCanvas : { value: '#457032', classList: { add() {} } },
        createElement: makeCanvas,
      },
      GIF: class {
        constructor(options) {
          this.options = options;
          this.frames = [];
          this.handlers = {};
          encoders.push(this);
        }
        addFrame(canvas, options) { this.frames.push({ canvas, options }); }
        on(event, callback) { this.handlers[event] = callback; }
        render() { this.handlers.finished(new Blob()); }
      },
    });
    vm.runInContext(appSource, context);
    vm.runInContext(`
      alphaImage = { naturalWidth: 800, naturalHeight: 800 };
      rawGifFrames = [40, 120].map(delay => ({ canvas: { width: ${width}, height: ${height} }, delay }));
      applyFrame = () => {};
      applyArcText = () => {};
      startAnimation = () => {};
      setStatus = () => {};
      setDlState = () => {};
      renderGif();
      sourceImage = { naturalWidth: ${width}, naturalHeight: ${height} };
      renderStatic();
    `, context);
    await Promise.resolve();

    const encoder = encoders[0];
    const size = Math.min(width, height);
    assert.equal(encoder.options.width, size);
    assert.equal(encoder.options.height, size);
    assert.deepEqual(encoder.frames.map(frame => frame.options.delay), [40, 120]);
    for (const frame of encoder.frames) {
      assert.equal(frame.canvas.width, size);
      assert.equal(frame.canvas.height, size);
    }
    const crop = [(width - size) / 2, (height - size) / 2, size, size, 0, 0, 800, 800];
    for (const index of [0, 1, 4]) {
      assert.deepEqual(draws[index].slice(1), crop);
    }
    for (const index of [2, 3, 5]) {
      assert.deepEqual(draws[index].slice(1), [0, 0, size, size]);
    }
    assert.deepEqual(pngExports, [[size, size]]);
  });
}
