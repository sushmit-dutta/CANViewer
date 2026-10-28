/**
 * Browser-side interactions: signal/frame drag-and-drop, frame resize, cursor
 * readout panel dragging, and the "." cursor shortcut.
 *
 * Events reach Dash by writing to dcc.Store components with
 * dash_clientside.set_props:
 *   drop-store         {sigs: [...], fid}            signals dropped on a frame
 *   reorder-store      {from, to}                    frame dragged onto another
 *   resize-store       {fid, height}                 frame resize finished
 *   cursor-key-store   {x}                           "." pressed over a plot
 *
 * Markup contract (see sidebar.py / cards.py):
 *   [data-signal="name"]            draggable single signal
 *   [data-signals='["a","b"]']      draggable group of signals
 *   [data-frame-card]               frame card: drop target for signals and frames
 *   [data-frame-drag]               frame reorder grip
 *   .frame-resize-handle            resize grip at the bottom of a card
 *   .cursor-drag-handle / .cursor-float-panel[data-panel-key]
 */
(function () {
    'use strict';

    var MIN_FRAME_HEIGHT = 200;
    var MAX_FRAME_HEIGHT = 4000;

    function send(id, data) {
        window.dash_clientside.set_props(id, { data: Object.assign({ t: Date.now() }, data) });
    }

    // ── Dash clientside callback: theme, cursor mode, last hovered x ─────────
    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        canviewer: {
            sync: function (theme, hoverList, cursorMode) {
                document.documentElement.setAttribute('data-theme', theme || 'dark');
                document.body.dataset.cursorMode = cursorMode ? 'true' : 'false';
                var triggered = window.dash_clientside.callback_context.triggered || [];
                for (var i = 0; i < triggered.length; i++) {
                    var v = triggered[i].value;
                    if (v && v.points && v.points.length) {
                        window._canviewerLastHoverX = v.points[0].x;
                        break;
                    }
                }
                return theme;
            },
        },
    });

    // ── "." drops a cursor at the last hovered x ─────────────────────────────
    document.addEventListener('keydown', function (e) {
        if (e.key !== '.' || document.body.dataset.cursorMode !== 'true') return;
        var tag = (document.activeElement || {}).tagName || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        if (window._canviewerLastHoverX) send('cursor-key-store', { x: window._canviewerLastHoverX });
    });

    // ── Keep Plotly sized to its container (frame resize, window, sidebar) ───
    var pending = new WeakSet();
    var observer = new ResizeObserver(function (entries) {
        entries.forEach(function (entry) {
            var host = entry.target;
            if (pending.has(host)) return;
            pending.add(host);
            requestAnimationFrame(function () {
                pending.delete(host);
                var gd = host.querySelector('.js-plotly-plot');
                // Skip detached/collapsed plots: Plotly throws on them.
                if (!gd || !window.Plotly || !gd.isConnected || host.clientHeight < 20) return;
                try { window.Plotly.Plots.resize(gd); } catch (_) { /* mid re-render */ }
            });
        });
    });
    var observed = new WeakSet();

    // ── Cursor panel positions survive re-renders ────────────────────────────
    var panelPos = {};

    function applyPanelPositions() {
        document.querySelectorAll('.cursor-float-panel[data-panel-key]').forEach(function (p) {
            var pos = panelPos[p.dataset.panelKey];
            if (pos && p.dataset.placed !== '1') {
                p.style.right = 'auto';
                p.style.left = pos.left + 'px';
                p.style.top = pos.top + 'px';
                p.dataset.placed = '1';
            }
        });
    }

    function scan() {
        document.querySelectorAll('.frame-plot').forEach(function (el) {
            if (!observed.has(el)) { observed.add(el); observer.observe(el); }
        });
        applyPanelPositions();
    }
    new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });

    // ── Pointer interactions: frame resize and cursor panel move ─────────────
    var resize = null;  // {card, handle, startY, startH, pointerId}
    var move = null;    // {panel, dx, dy}

    document.addEventListener('pointerdown', function (e) {
        var handle = e.target.closest && e.target.closest('.frame-resize-handle');
        if (handle) {
            var card = handle.closest('[data-frame-card]');
            if (!card) return;
            resize = { card: card, handle: handle, startY: e.clientY, startH: card.offsetHeight };
            handle.setPointerCapture(e.pointerId);
            handle.classList.add('is-dragging');
            document.body.style.userSelect = 'none';
            e.preventDefault();
            return;
        }
        var grip = e.target.closest && e.target.closest('.cursor-drag-handle');
        var panel = grip && grip.closest('.cursor-float-panel');
        if (!panel || !panel.offsetParent) return;
        var parent = panel.offsetParent.getBoundingClientRect();
        var rect = panel.getBoundingClientRect();
        panel.style.right = 'auto';
        panel.style.left = (rect.left - parent.left) + 'px';
        panel.style.top = (rect.top - parent.top) + 'px';
        move = { panel: panel, dx: e.clientX - rect.left, dy: e.clientY - rect.top, parent: parent };
        grip.setPointerCapture(e.pointerId);
        e.preventDefault();
    });

    document.addEventListener('pointermove', function (e) {
        if (resize) {
            var h = resize.startH + (e.clientY - resize.startY);
            resize.card.style.height = Math.max(MIN_FRAME_HEIGHT, Math.min(MAX_FRAME_HEIGHT, h)) + 'px';
        } else if (move) {
            var left = e.clientX - move.parent.left - move.dx;
            var top = e.clientY - move.parent.top - move.dy;
            move.panel.style.left = left + 'px';
            move.panel.style.top = top + 'px';
            move.panel.dataset.placed = '1';
            if (move.panel.dataset.panelKey) {
                panelPos[move.panel.dataset.panelKey] = { left: left, top: top };
            }
        }
    });

    function endPointer() {
        if (resize) {
            resize.handle.classList.remove('is-dragging');
            document.body.style.userSelect = '';
            var fid = resize.card.getAttribute('data-frame-card');
            if (fid) send('resize-store', { fid: fid, height: Math.round(resize.card.offsetHeight) });
            resize = null;
        }
        move = null;
    }
    document.addEventListener('pointerup', endPointer);
    document.addEventListener('pointercancel', endPointer);

    // ── HTML5 drag-and-drop: signals into frames, frames onto frames ─────────
    var dragSignals = null;  // string[] being dragged from the sidebar
    var dragFrame = null;    // frame id being reordered

    function clearHighlights() {
        document.querySelectorAll('.drop-target, .reorder-target').forEach(function (el) {
            el.classList.remove('drop-target', 'reorder-target');
        });
    }

    document.addEventListener('dragstart', function (e) {
        dragSignals = dragFrame = null;
        var frameGrip = e.target.closest('[data-frame-drag]');
        var group = e.target.closest('[data-signals]');
        var single = e.target.closest('[data-signal]');
        if (frameGrip) {
            dragFrame = frameGrip.getAttribute('data-frame-drag');
            e.dataTransfer.effectAllowed = 'move';
        } else if (group) {
            try { dragSignals = JSON.parse(group.getAttribute('data-signals')); } catch (_) { dragSignals = null; }
            if (dragSignals && !dragSignals.length) dragSignals = null;
            e.dataTransfer.effectAllowed = 'copy';
        } else if (single) {
            dragSignals = [single.getAttribute('data-signal')];
            e.dataTransfer.effectAllowed = 'copy';
        }
        // Firefox refuses to start a drag without data.
        if (e.dataTransfer && (dragSignals || dragFrame)) e.dataTransfer.setData('text/plain', 'canviewer');
    });

    document.addEventListener('dragend', function () {
        dragSignals = dragFrame = null;
        clearHighlights();
    });

    function dropZone(e) {
        if (!dragFrame && !dragSignals) return null;
        var card = e.target.closest('[data-frame-card]');
        if (dragFrame && card && card.getAttribute('data-frame-card') === dragFrame) return null;
        return card;
    }

    document.addEventListener('dragover', function (e) {
        var zone = dropZone(e);
        if (!zone) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = dragFrame ? 'move' : 'copy';
        if (!zone.classList.contains(dragFrame ? 'reorder-target' : 'drop-target')) {
            clearHighlights();
            zone.classList.add(dragFrame ? 'reorder-target' : 'drop-target');
        }
    });

    document.addEventListener('drop', function (e) {
        var zone = dropZone(e);
        if (!zone) return;
        e.preventDefault();
        if (dragFrame) {
            send('reorder-store', { from: dragFrame, to: zone.getAttribute('data-frame-card') });
        } else {
            send('drop-store', { sigs: dragSignals, fid: zone.getAttribute('data-frame-card') });
        }
        dragSignals = dragFrame = null;
        clearHighlights();
    });
}());
