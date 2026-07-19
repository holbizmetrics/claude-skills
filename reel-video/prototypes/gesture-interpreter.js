/**
 * gesture-interpreter.js — slim runtime that walks a reel-video.skill YAML script
 * and emits a GSAP timeline. Goal: feed video-mock.yaml and reproduce the
 * animation that video-mock.html hand-codes.
 *
 * Scope: demo-only. Implements just the gestures used by video-mock.yaml:
 *   PLACE / CONNECT / ANNOTATE
 * plus camera moves, transitions (hold-from-previous, morph-from-previous),
 * stage swaps, and content-type 'notification' materialization.
 *
 * Structural axes wired so far:
 *   motion_blur (DESIGN.md item 14) — applied on PLACE; helper ready for
 *   replication onto MOVE / FRAME / HANDOFF when those handlers land.
 *   style cascade (DESIGN.md item 13) — plumbing only: resolveStyle helper
 *   exposed on GestureInterpreter; body.dataset.style carries the global
 *   resolved value at run start. Hand-drawn rendering engine (rough.js)
 *   pending — lights up alongside item 11's bracket / ellipse / underline.
 *   ANNOTATE shape kinds (DESIGN.md items 11a + 11b):
 *     11a — array target → group-bracket (drawGroupBracket).
 *     11b — single target with kind ∈ {bracket, ellipse, underline,
 *           elbow-arrow} → point-attached shape (drawEllipse,
 *           drawUnderline, drawElbowArrow + drawGroupBracket on single).
 *   Span resolution (target: {element, span}) is 11c — not yet wired.
 *   Hand-drawn engine (rough.js) for the shapes is the engine half of #13.
 *
 * NOT in scope (yet): edge-tts sentence boundaries, the full 33-primitive
 * gesture vocabulary, headless capture, build.py integration. Those land
 * once this proves the grammar holds.
 *
 * Depends on: window.gsap, js-yaml (window.jsyaml).
 */
(function () {
  'use strict';

  // ── Helpers ────────────────────────────────────────────────────────────

  function sentenceCount(text) {
    if (!text) return 0;
    return text.split(/(?<=[.!?])\s+/).filter(s => s.trim()).length;
  }

  function firstSentence(text) {
    if (!text) return '';
    return text.split(/(?<=[.!?])\s+/)[0] || text;
  }

  // Camera enum → GSAP target props on the active stage
  function cameraTarget(cam) {
    const map = {
      'zoom-in':  { scale: 2.6, y: -180 },
      'zoom-out': { scale: 1,   y: 0 },
      'static':   { scale: 1,   y: 0 },
      'hold':     null,   // null = inherit; no animation
    };
    return map[cam] !== undefined ? map[cam] : null;
  }

  // Resolve a stage selector by name. Convention: stage 'crt' → '#stage', stage 'phone' → '#stage-2'.
  function stageSelector(stageName) {
    const map = { crt: '#stage', phone: '#stage-2' };
    return map[stageName] || '#stage';
  }

  // Find a referent value in the DOM. 'stage' is special; otherwise treat as id.
  function resolveRef(ref, currentStage) {
    if (ref === 'stage') return currentStage;
    return '#' + ref;
  }

  // Map an icon id like "icon-settings" to its line/junction selectors.
  function iconLineSelector(iconId) {
    return '#line-' + iconId.replace(/^icon-/, '');
  }
  function iconJunctionSelector(iconId) {
    return '#junc-' + iconId.replace(/^icon-/, '');
  }

  // Highlight a chapter_nav item by its data-chapter value. Pass null to clear.
  function setChapterActive(name) {
    document.querySelectorAll('.chapter-nav .item').forEach(el => {
      el.classList.toggle('active', name != null && el.dataset.chapter === name);
    });
  }

  // Style cascade (DESIGN.md item 13, n=2-derived global axis).
  // Resolver walks: per-primitive override → top-level spec.style → 'clean'.
  // Per-primitive overrides always win. v0.2 ships plumbing only; the
  // hand-drawn rendering engine lights up alongside item 11's shapes.
  function resolveStyle(spec, primitiveStyle) {
    if (primitiveStyle) return primitiveStyle;
    if (spec && spec.style) return spec.style;
    return 'clean';
  }

  // motion_blur (DESIGN.md item 14, n=2-derived structural axis).
  // Cuts across PLACE / MOVE / FRAME / HANDOFF — anywhere with transit motion.
  // Forms: false | true | <int> | { px, decay }.
  function resolveMotionBlur(mb) {
    if (mb == null || mb === false) return null;
    if (mb === true) return { px: 8, decay: true };
    if (typeof mb === 'number') return { px: mb, decay: true };
    if (typeof mb === 'object') {
      return { px: (mb.px != null ? mb.px : 8), decay: mb.decay !== false };
    }
    return null;
  }

  // Apply a motion-blur tween over [offset, offset+duration].
  // decay:true  → 0 → px → 0 (peak at midpoint)
  // decay:false → hold px through transit, snap to 0 at end
  function applyMotionBlur(tl, sel, offset, motionBlur, duration) {
    const cfg = resolveMotionBlur(motionBlur);
    if (!cfg) return;
    if (cfg.decay) {
      const half = duration / 2;
      tl.fromTo(sel,
        { filter: 'blur(0px)' },
        { filter: 'blur(' + cfg.px + 'px)', duration: half, ease: 'power1.in' },
        offset);
      tl.to(sel,
        { filter: 'blur(0px)', duration: half, ease: 'power1.out' },
        offset + half);
    } else {
      tl.set(sel, { filter: 'blur(' + cfg.px + 'px)' }, offset);
      tl.set(sel, { filter: 'blur(0px)' }, offset + duration);
    }
  }

  // ── ANNOTATE primitives (DESIGN.md item 11a — group-bracket) ─────────

  // Compute union bbox in frame-space coords for a list of element ids.
  // Uses the data-tx / data-ty + computed CSS width/height convention that
  // PLACE-positioned elements follow (top:50%; left:50% + xPercent/yPercent
  // -50 + x:tx; y:ty). If element lacks data-tx/ty, it's skipped.
  // Constraint: bbox is computed at build time using resting positions, so
  // it does not follow elements that move during the scene (MOVE etc.) —
  // v0.2 limitation; revisit when MOVE handler lands.
  function computeFrameBBox(ids) {
    const frame = document.querySelector('.frame');
    if (!frame) return null;
    const fcs = window.getComputedStyle(frame);
    const frameW = parseFloat(fcs.width);
    const frameH = parseFloat(fcs.height);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    ids.forEach(id => {
      const el = document.querySelector('#' + id);
      if (!el || el.dataset.tx == null) return;
      const tx = parseFloat(el.dataset.tx) || 0;
      const ty = parseFloat(el.dataset.ty) || 0;
      const cs = window.getComputedStyle(el);
      const w = parseFloat(cs.width);
      const h = parseFloat(cs.height);
      const cx = frameW / 2 + tx;
      const cy = frameH / 2 + ty;
      const lx = cx - w / 2, ly = cy - h / 2;
      const rx = cx + w / 2, ry = cy + h / 2;
      if (lx < minX) minX = lx;
      if (ly < minY) minY = ly;
      if (rx > maxX) maxX = rx;
      if (ry > maxY) maxY = ry;
    });
    if (!isFinite(minX)) return null;
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  // Lazily inject an SVG overlay sized to the frame's natural dimensions.
  // Used by ANNOTATE primitives that need to draw shapes (brackets etc.).
  function ensureOverlaySvg() {
    let svg = document.querySelector('#annotate-overlay');
    if (svg) return svg;
    const frame = document.querySelector('.frame');
    if (!frame) return null;
    const fcs = window.getComputedStyle(frame);
    const w = parseFloat(fcs.width);
    const h = parseFloat(fcs.height);
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('id', 'annotate-overlay');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.position = 'absolute';
    svg.style.inset = '0';
    svg.style.width = '100%';
    svg.style.height = '100%';
    svg.style.pointerEvents = 'none';
    svg.style.zIndex = '50';
    frame.appendChild(svg);
    return svg;
  }

  // Draw a square bracket above (or below/left/right of) a bbox, with an
  // optional label. Returns { path, length, label } so the caller can
  // animate stroke-dashoffset reveal + label fade-in.
  function drawGroupBracket(svg, bbox, opts) {
    opts = opts || {};
    const side    = opts.side        || 'top';
    const gap     = opts.gap         || 30;
    const tipLen  = opts.tipLen      || 30;
    const stroke  = opts.color       || '#1a1a1a';
    const sw      = opts.strokeWidth || 5;
    const fontSz  = opts.fontSize    || 36;

    let pathD;
    if (side === 'top') {
      const y = bbox.y - gap, tipY = y + tipLen;
      const x1 = bbox.x, x2 = bbox.x + bbox.w;
      pathD = 'M ' + x1 + ' ' + tipY + ' L ' + x1 + ' ' + y +
              ' L ' + x2 + ' ' + y + ' L ' + x2 + ' ' + tipY;
    } else if (side === 'bottom') {
      const y = bbox.y + bbox.h + gap, tipY = y - tipLen;
      const x1 = bbox.x, x2 = bbox.x + bbox.w;
      pathD = 'M ' + x1 + ' ' + tipY + ' L ' + x1 + ' ' + y +
              ' L ' + x2 + ' ' + y + ' L ' + x2 + ' ' + tipY;
    } else if (side === 'left') {
      const x = bbox.x - gap, tipX = x + tipLen;
      const y1 = bbox.y, y2 = bbox.y + bbox.h;
      pathD = 'M ' + tipX + ' ' + y1 + ' L ' + x + ' ' + y1 +
              ' L ' + x + ' ' + y2 + ' L ' + tipX + ' ' + y2;
    } else { // right
      const x = bbox.x + bbox.w + gap, tipX = x - tipLen;
      const y1 = bbox.y, y2 = bbox.y + bbox.h;
      pathD = 'M ' + tipX + ' ' + y1 + ' L ' + x + ' ' + y1 +
              ' L ' + x + ' ' + y2 + ' L ' + tipX + ' ' + y2;
    }

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', pathD);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', stroke);
    path.setAttribute('stroke-width', sw);
    path.setAttribute('stroke-linecap', 'square');
    path.setAttribute('stroke-linejoin', 'miter');
    svg.appendChild(path);
    const len = path.getTotalLength();
    path.style.strokeDasharray = len;
    path.style.strokeDashoffset = len;

    let labelEl = null;
    if (opts.label) {
      labelEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      let lx, ly, anchor = 'middle';
      if (side === 'top') {
        lx = bbox.x + bbox.w / 2;
        ly = bbox.y - gap - 18;
      } else if (side === 'bottom') {
        lx = bbox.x + bbox.w / 2;
        ly = bbox.y + bbox.h + gap + fontSz + 4;
      } else if (side === 'left') {
        lx = bbox.x - gap - 14;
        ly = bbox.y + bbox.h / 2 + fontSz / 3;
        anchor = 'end';
      } else {
        lx = bbox.x + bbox.w + gap + 14;
        ly = bbox.y + bbox.h / 2 + fontSz / 3;
        anchor = 'start';
      }
      labelEl.setAttribute('x', lx);
      labelEl.setAttribute('y', ly);
      labelEl.setAttribute('text-anchor', anchor);
      labelEl.setAttribute('font-size', fontSz);
      labelEl.setAttribute('font-family',
        '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif');
      labelEl.setAttribute('font-weight', '600');
      labelEl.setAttribute('fill', stroke);
      labelEl.style.opacity = '0';
      labelEl.textContent = opts.label;
      svg.appendChild(labelEl);
    }
    return { path: path, length: len, label: labelEl };
  }

  // Draw an ellipse around a bbox with optional label above. Returns the
  // same shape as drawGroupBracket so the caller animates uniformly.
  function drawEllipse(svg, bbox, opts) {
    opts = opts || {};
    const stroke   = opts.color       || '#1a1a1a';
    const sw       = opts.strokeWidth || 5;
    const padding  = opts.padding     || 24;
    const fontSz   = opts.fontSize    || 32;

    const cx = bbox.x + bbox.w / 2;
    const cy = bbox.y + bbox.h / 2;
    const rx = bbox.w / 2 + padding;
    const ry = bbox.h / 2 + padding;

    const ellipse = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
    ellipse.setAttribute('cx', cx);
    ellipse.setAttribute('cy', cy);
    ellipse.setAttribute('rx', rx);
    ellipse.setAttribute('ry', ry);
    ellipse.setAttribute('fill', 'none');
    ellipse.setAttribute('stroke', stroke);
    ellipse.setAttribute('stroke-width', sw);
    svg.appendChild(ellipse);
    // Ramanujan approximation for ellipse circumference
    const h = Math.pow(rx - ry, 2) / Math.pow(rx + ry, 2);
    const C = Math.PI * (rx + ry) * (1 + (3 * h) / (10 + Math.sqrt(4 - 3 * h)));
    ellipse.style.strokeDasharray = C;
    ellipse.style.strokeDashoffset = C;

    let labelEl = null;
    if (opts.label) {
      labelEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      labelEl.setAttribute('x', cx);
      labelEl.setAttribute('y', cy - ry - 18);
      labelEl.setAttribute('text-anchor', 'middle');
      labelEl.setAttribute('font-size', fontSz);
      labelEl.setAttribute('font-family',
        '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif');
      labelEl.setAttribute('font-weight', '600');
      labelEl.setAttribute('fill', stroke);
      labelEl.style.opacity = '0';
      labelEl.textContent = opts.label;
      svg.appendChild(labelEl);
    }
    return { path: ellipse, length: C, label: labelEl };
  }

  // Draw an underline beneath the bbox. Optional label below the line.
  function drawUnderline(svg, bbox, opts) {
    opts = opts || {};
    const stroke = opts.color       || '#1a1a1a';
    const sw     = opts.strokeWidth || 5;
    const gap    = opts.gap         || 14;
    const fontSz = opts.fontSize    || 28;

    const x1 = bbox.x;
    const x2 = bbox.x + bbox.w;
    const y  = bbox.y + bbox.h + gap;

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y);
    line.setAttribute('stroke', stroke);
    line.setAttribute('stroke-width', sw);
    line.setAttribute('stroke-linecap', 'round');
    svg.appendChild(line);
    const len = bbox.w;
    line.style.strokeDasharray = len;
    line.style.strokeDashoffset = len;

    let labelEl = null;
    if (opts.label) {
      labelEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      labelEl.setAttribute('x', bbox.x + bbox.w / 2);
      labelEl.setAttribute('y', y + fontSz + 6);
      labelEl.setAttribute('text-anchor', 'middle');
      labelEl.setAttribute('font-size', fontSz);
      labelEl.setAttribute('font-family',
        '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif');
      labelEl.setAttribute('font-weight', '500');
      labelEl.setAttribute('fill', stroke);
      labelEl.style.opacity = '0';
      labelEl.textContent = opts.label;
      svg.appendChild(labelEl);
    }
    return { path: line, length: len, label: labelEl };
  }

  // Draw an elbow-arrow callout: a label sits at offset from the target,
  // a horizontal-first bent line connects label edge to target's edge,
  // terminating in a small arrowhead. opts.labelOffset = {x, y} is the
  // label-center offset from target-center in frame pixels.
  //
  // Anchoring: edge-midpoint with vertical-bias heuristic. If |offset.y|
  // > |offset.x| * 0.7, tip lands on top/bottom edge midpoint; otherwise
  // on side edge midpoint. Lands on a straight bbox edge, sidestepping
  // border-radius rounding that would leave a corner-exact tip stranded
  // in background pixels.
  function drawElbowArrow(svg, bbox, opts) {
    opts = opts || {};
    const stroke = opts.color       || '#1a1a1a';
    const sw     = opts.strokeWidth || 5;
    const fontSz = opts.fontSize    || 32;
    const offset = opts.labelOffset || { x: 240, y: -220 };

    const tcx = bbox.x + bbox.w / 2;
    const tcy = bbox.y + bbox.h / 2;
    const lx  = tcx + offset.x;
    const ly  = tcy + offset.y;

    let targetX, targetY;
    if (Math.abs(offset.y) > Math.abs(offset.x) * 0.7) {
      // Vertical-dominant: top/bottom edge midpoint
      targetX = tcx;
      targetY = offset.y > 0 ? bbox.y + bbox.h : bbox.y;
    } else {
      // Horizontal-dominant: side edge midpoint
      targetX = offset.x > 0 ? bbox.x + bbox.w : bbox.x;
      targetY = tcy;
    }

    // Horizontal-first elbow: leaves label horizontally toward target_x,
    // then turns vertically toward target edge
    const elbowX = targetX;
    const elbowY = ly;
    const labelEdgeX = offset.x > 0 ? lx - 20 : lx + 20;

    const pathD =
      'M ' + labelEdgeX + ' ' + ly +
      ' L ' + elbowX + ' ' + elbowY +
      ' L ' + targetX + ' ' + targetY;

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', pathD);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', stroke);
    path.setAttribute('stroke-width', sw);
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'miter');
    svg.appendChild(path);
    const len = path.getTotalLength();
    path.style.strokeDasharray = len;
    path.style.strokeDashoffset = len;

    // Arrowhead at target; orientation derived from last segment direction.
    // For horizontal-dominant offsets the vertical segment can be degenerate
    // (elbow Y = target Y); fall back to horizontal-segment direction then.
    let dx = targetX - elbowX;
    let dy = targetY - elbowY;
    if (dx === 0 && dy === 0) {
      dx = elbowX - labelEdgeX;
      dy = 0;
    }
    const ang = Math.atan2(dy, dx);
    const ahLen = 18;
    const ahAng = 0.45;
    const ah1x = targetX - ahLen * Math.cos(ang - ahAng);
    const ah1y = targetY - ahLen * Math.sin(ang - ahAng);
    const ah2x = targetX - ahLen * Math.cos(ang + ahAng);
    const ah2y = targetY - ahLen * Math.sin(ang + ahAng);
    const arrowhead = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    arrowhead.setAttribute('d',
      'M ' + ah1x + ' ' + ah1y +
      ' L ' + targetX + ' ' + targetY +
      ' L ' + ah2x + ' ' + ah2y);
    arrowhead.setAttribute('fill', 'none');
    arrowhead.setAttribute('stroke', stroke);
    arrowhead.setAttribute('stroke-width', sw);
    arrowhead.setAttribute('stroke-linecap', 'round');
    arrowhead.setAttribute('stroke-linejoin', 'round');
    arrowhead.style.opacity = '0';
    svg.appendChild(arrowhead);

    let labelEl = null;
    if (opts.label) {
      labelEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      labelEl.setAttribute('x', lx);
      labelEl.setAttribute('y', ly + fontSz / 3);
      labelEl.setAttribute('text-anchor', offset.x > 0 ? 'start' : 'end');
      labelEl.setAttribute('font-size', fontSz);
      labelEl.setAttribute('font-family',
        '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif');
      labelEl.setAttribute('font-weight', '600');
      labelEl.setAttribute('fill', stroke);
      labelEl.style.opacity = '0';
      labelEl.textContent = opts.label;
      svg.appendChild(labelEl);
    }
    return { path: path, length: len, label: labelEl, arrowhead: arrowhead };
  }

  // ── Reset (initial state) ─────────────────────────────────────────────

  function resetState(spec) {
    // Style cascade: tag the body with the global resolved style so CSS
    // hooks (and later the rough.js engine) can key off body[data-style].
    document.body.dataset.style = resolveStyle(spec, null);

    // Clear any previously-injected annotate overlay paths so replay
    // builds don't stack shapes on top of prior runs.
    const annotateOverlay = document.querySelector('#annotate-overlay');
    if (annotateOverlay) annotateOverlay.innerHTML = '';

    // Stage 1 — start zoomed-in close-up
    gsap.set('#stage', {
      xPercent: -50, yPercent: -50,
      x: 0, y: -180,
      scale: 2.6, opacity: 1,
      filter: 'blur(0px)'
    });

    // Stage 2 — start off-screen below
    gsap.set('#stage-2', {
      xPercent: -50, yPercent: -50,
      x: 0, y: 1500,
      scale: 0.85, opacity: 0
    });

    // Icons — pin to their offset positions, hidden + scaled down
    document.querySelectorAll('.icon').forEach((el) => {
      const tx = parseFloat(el.dataset.tx);
      const ty = parseFloat(el.dataset.ty);
      gsap.set(el, {
        xPercent: -50, yPercent: -50,
        x: tx, y: ty,
        scale: 0.5, opacity: 0
      });
    });

    // Connection lines — fully un-drawn
    gsap.set('.connections path', { strokeDashoffset: 1200 });
    gsap.set('.junction', { opacity: 0 });

    // Notification card + annotation — hidden initially
    gsap.set('#notif-card', { opacity: 0, y: 16 });
    gsap.set('#annotation', { opacity: 0 });
    gsap.set('#arrow-path', { strokeDashoffset: 400 });
    gsap.set('#arrowhead', { opacity: 0 });

    // Replay button — hidden until end
    const replay = document.querySelector('#replay');
    if (replay) gsap.set(replay, { opacity: 0 });

    // Initial caption from first scene
    const captions = document.querySelector('#captions');
    if (captions && spec.scenes[0]) {
      captions.textContent = firstSentence(spec.scenes[0].narration);
    }

    // Initial chapter highlight from first scene's chapter (if specified)
    if (spec.scenes[0] && spec.scenes[0].chapter) {
      setChapterActive(spec.scenes[0].chapter);
    } else {
      setChapterActive(null);
    }
  }

  // ── Gesture handlers ──────────────────────────────────────────────────

  const handlers = {

    PLACE(params, ctx) {
      const targets = params.elements
        ? params.elements
        : (params.element ? [params.element] : []);
      if (!targets.length) return;

      const reveal   = params.reveal   || 'all-at-once';
      const duration = params.duration || 0.5;
      const easing   = params.easing   || 'back.out(1.5)';
      const stagger  = params.stagger  || 0.9;
      const delay    = params.delay    || 0;

      targets.forEach((t, i) => {
        // chapter_nav is already visible in DOM; skip animation for v0.1
        if (t === 'chapter_nav') return;

        const sel = '#' + t;
        const offset = (reveal === 'per-step' || reveal === 'per-sentence')
          ? ctx.sceneStart + delay + i * stagger
          : ctx.sceneStart + delay;

        if (params.from) {
          // Transit-style entrance: pre-position at offset, travel to resting.
          // Resting (tx, ty) read from data-attrs set up in the DOM.
          const el = document.querySelector(sel);
          if (!el) return;
          const tx = parseFloat(el.dataset.tx) || 0;
          const ty = parseFloat(el.dataset.ty) || 0;
          ctx.tl.set(sel, {
            x: tx + (params.from.x || 0),
            y: ty + (params.from.y || 0),
            opacity: 1, scale: 1
          }, offset);
          ctx.tl.to(sel, {
            x: tx, y: ty,
            duration, ease: easing
          }, offset);
          applyMotionBlur(ctx.tl, sel, offset, params.motion_blur, duration);
        } else if (t === 'notif-card') {
          // Notification card — uses y-offset reveal instead of scale
          ctx.tl.to(sel, {
            opacity: 1, y: 0,
            duration, ease: easing
          }, offset);
          applyMotionBlur(ctx.tl, sel, offset, params.motion_blur, duration);
        } else {
          ctx.tl.to(sel, {
            opacity: 1, scale: 1,
            duration, ease: easing
          }, offset);
          applyMotionBlur(ctx.tl, sel, offset, params.motion_blur, duration);
        }
      });
    },

    CONNECT(params, ctx) {
      const targets = Array.isArray(params.to) ? params.to : [params.to];
      const reveal   = params.reveal   || 'all-at-once';
      const duration = params.duration || 0.7;
      const easing   = params.easing   || 'power2.out';
      const stagger  = params.stagger  || 0.9;
      const delay    = params.delay    || 0;

      targets.forEach((t, i) => {
        const lineSel = iconLineSelector(t);
        const juncSel = iconJunctionSelector(t);
        const offset = (reveal === 'per-step' || reveal === 'per-sentence')
          ? ctx.sceneStart + delay + i * stagger
          : ctx.sceneStart + delay;

        ctx.tl.to(lineSel, {
          strokeDashoffset: 0,
          duration, ease: easing
        }, offset);

        // Junction dot pops mid-line-draw
        ctx.tl.to(juncSel, {
          opacity: 1, duration: 0.2
        }, offset + duration * 0.6);
      });
    },

    ANNOTATE(params, ctx) {
      const annDur = params.duration || 0.7;
      const easing = params.easing   || 'power2.out';
      const delay  = params.delay    || 0;
      const offset = ctx.sceneStart + delay;

      // Shape dispatch (DESIGN.md items 11a + 11b):
      //   array target  → bracket (default kind for arrays — group-bracket)
      //   single target with kind ∈ {bracket, ellipse, underline, elbow-arrow}
      //                 → point-attached shapes (11b)
      //   anything else → fall through to legacy arrow ANNOTATE (#annotation/
      //                   #arrow-path/#arrowhead pre-staged in DOM)
      const isArrayTarget = Array.isArray(params.target);
      const kind = params.kind || (isArrayTarget ? 'bracket' : 'arrow');
      const isShape = (kind === 'bracket' || kind === 'ellipse' ||
                       kind === 'underline' || kind === 'elbow-arrow');

      if (isShape) {
        const ids = isArrayTarget ? params.target
                                  : (params.target ? [params.target] : []);
        if (!ids.length) {
          console.warn('[gesture-interpreter] ANNOTATE kind: ' + kind +
            ' requires a target.');
          return;
        }
        const bbox = computeFrameBBox(ids);
        if (!bbox) {
          console.warn('[gesture-interpreter] ANNOTATE ' + kind +
            ': no resolvable targets in ' + JSON.stringify(params.target));
          return;
        }
        const svg = ensureOverlaySvg();
        if (!svg) return;
        const opts = params.options || {};
        const drawerOpts = {
          side:         opts.side || 'top',
          label:        params.label || opts.label,
          color:        opts.color,
          gap:          opts.gap,
          tipLen:       opts.tipLen,
          padding:      opts.padding,
          labelOffset:  opts.labelOffset,
          strokeWidth:  opts.strokeWidth,
          fontSize:     opts.fontSize
        };

        let drawn;
        if (kind === 'bracket')          drawn = drawGroupBracket(svg, bbox, drawerOpts);
        else if (kind === 'ellipse')     drawn = drawEllipse(svg, bbox, drawerOpts);
        else if (kind === 'underline')   drawn = drawUnderline(svg, bbox, drawerOpts);
        else if (kind === 'elbow-arrow') drawn = drawElbowArrow(svg, bbox, drawerOpts);
        if (!drawn || !drawn.path) return;

        ctx.tl.to(drawn.path, {
          strokeDashoffset: 0,
          duration: annDur,
          ease: easing
        }, offset);
        if (drawn.label) {
          ctx.tl.to(drawn.label, {
            opacity: 1, duration: 0.3
          }, offset + annDur * 0.7);
        }
        if (drawn.arrowhead) {
          ctx.tl.to(drawn.arrowhead, {
            opacity: 1, duration: 0.15
          }, offset + annDur * 0.85);
        }
        return;
      }

      // Legacy point-attached arrow ANNOTATE (kind: arrow with pre-existing
      // #annotation / #arrow-path / #arrowhead in DOM, e.g. video-mock).
      ctx.tl.to('#annotation', { opacity: 1, duration: 0.3 }, offset);
      ctx.tl.to('#arrow-path', {
        strokeDashoffset: 0,
        duration: annDur,
        ease: easing
      }, offset + 0.1);
      ctx.tl.to('#arrowhead', {
        opacity: 1, duration: 0.15
      }, offset + 0.1 + annDur * 0.85);
    },
  };

  // ── Scene processing ──────────────────────────────────────────────────

  function processScene(scene, ctx) {
    const captions = document.querySelector('#captions');
    const sceneStart = ctx.cursor;

    // Caption + chapter highlight swap at scene entry
    if (scene.narration && captions) {
      const text = firstSentence(scene.narration);
      ctx.tl.call(() => { captions.textContent = text; }, null, sceneStart);
    }
    if (scene.chapter) {
      ctx.tl.call(() => { setChapterActive(scene.chapter); }, null, sceneStart);
    }

    // Determine current stage selector for this scene
    const currentStageSel = stageSelector(scene.stage);
    const ctxLocal = { tl: ctx.tl, scene, sceneStart, currentStage: currentStageSel };

    // Transition-in handling (relative to scene start)
    let transitionConsumed = 0;
    if (scene.transition_in === 'morph-from-previous') {
      const tDur = scene.transition_duration || 1.5;
      const tEase = scene.transition_easing || 'power2.inOut';

      // Find the previous stage selector (the one we're morphing OUT of)
      const prevStageSel = ctx.previousStage || '#stage';
      const newStageSel  = currentStageSel;

      // Stage 1 morphs out: slide up, scale down, blur, fade
      ctx.tl.to(prevStageSel, {
        y: '-=900',
        scale: 0.55,
        opacity: 0.18,
        filter: 'blur(10px)',
        duration: tDur,
        ease: tEase
      }, sceneStart);

      // Stage 2 morphs in: rise from below, scale up, fade in
      ctx.tl.to(newStageSel, {
        y: 0,
        scale: 1,
        opacity: 1,
        duration: tDur,
        ease: tEase
      }, sceneStart);

      transitionConsumed = tDur;
    }
    // 'hold-from-previous' = no transition, scene starts in previous final state. No-op.

    // Camera moves (within the scene, after any transition)
    let cameraConsumed = 0;
    if (scene.camera) {
      // Validity rule for camera.start: hold (SKILL.md "Camera shape" section).
      // hold only carries meaning with hold-from-previous or morph-from-previous;
      // with any other transition_in, warn and fall back to static.
      if (scene.camera.start === 'hold') {
        const inheriting = scene.transition_in === 'hold-from-previous'
                        || scene.transition_in === 'morph-from-previous';
        if (!inheriting) {
          console.warn('[gesture-interpreter] Scene "' + (scene.id || '<anonymous>') +
            '": camera.start: hold is undefined with transition_in: ' +
            (scene.transition_in || 'cut (default)') +
            '. Falling back to static.');
          ctx.tl.set(currentStageSel, cameraTarget('static'),
            sceneStart + transitionConsumed);
        }
      }

      const startState = cameraTarget(scene.camera.start);
      const endState   = cameraTarget(scene.camera.end);
      const camDur     = typeof scene.camera.duration === 'number'
                         ? scene.camera.duration : 2.5;
      const camEase    = scene.camera.easing || 'power2.inOut';

      if (endState && (scene.camera.end !== 'hold')) {
        ctx.tl.to(currentStageSel, {
          ...endState,
          duration: camDur,
          ease: camEase
        }, sceneStart + transitionConsumed);
      }
      cameraConsumed = camDur;
    }

    // Overlays (gesture invocations) — anchored at scene start (or after transition)
    if (scene.overlays) {
      scene.overlays.forEach(overlay => {
        const handler = handlers[overlay.gesture];
        if (handler) {
          handler(overlay, {
            ...ctxLocal,
            sceneStart: sceneStart + transitionConsumed
          });
        } else {
          console.warn('[gesture-interpreter] Unknown gesture:', overlay.gesture);
        }
      });
    }

    // Pause (silent beat)
    let pauseConsumed = 0;
    if (typeof scene.pause === 'number') {
      pauseConsumed = scene.pause;
    }

    // Explicit scene duration takes precedence
    let sceneDuration;
    if (typeof scene.duration === 'number') {
      sceneDuration = scene.duration;
    } else {
      // Otherwise take max of consumed components
      sceneDuration = Math.max(transitionConsumed + cameraConsumed, pauseConsumed, 0.5);
    }

    // Advance the cursor
    ctx.cursor = sceneStart + sceneDuration;
    ctx.previousStage = currentStageSel;
  }

  // ── Main runner ───────────────────────────────────────────────────────

  function runFromYAML(yamlText) {
    const spec = jsyaml.load(yamlText);
    runFromSpec(spec);
  }

  function runFromSpec(spec) {
    function build() {
      resetState(spec);

      const tl = gsap.timeline({ defaults: { ease: 'power2.inOut' } });
      const ctx = { tl, cursor: 0, previousStage: null };

      spec.scenes.forEach(scene => processScene(scene, ctx));

      // Final replay button
      const replay = document.querySelector('#replay');
      if (replay) {
        tl.to(replay, { opacity: 1, duration: 0.4 }, ctx.cursor + 0.2);
      }
    }

    build();

    const replay = document.querySelector('#replay');
    if (replay) replay.addEventListener('click', build);
  }

  // ── Public API ────────────────────────────────────────────────────────

  window.GestureInterpreter = {
    run: runFromYAML,
    runSpec: runFromSpec,
    resolveStyle: resolveStyle
  };

})();
