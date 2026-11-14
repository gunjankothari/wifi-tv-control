/* TV Remote site: hero parallax, scroll reveal and the five section demos.
   Static, no dependencies. Motion is transform-only and is skipped under
   prefers-reduced-motion. */
(function () {
  'use strict';

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var clamp = function (v, lo, hi) { return Math.max(lo, Math.min(hi, v)); };
  var say = function (id, text) { var el = document.getElementById(id); if (el) el.textContent = text; };

  /* ---------- Parallax: one rAF-throttled scroll handler ---------- */
  var stage = $('.stage');
  var layers = $$('.stage .layer[data-speed]');
  var frames = $$('.demo-frame');
  var ticking = false;

  function parallax() {
    ticking = false;
    var vh = window.innerHeight;
    if (stage) {
      var r = stage.getBoundingClientRect();
      if (r.bottom > 0 && r.top < vh) {
        var y = window.scrollY;
        layers.forEach(function (l) {
          var speed = parseFloat(l.getAttribute('data-speed')) || 1;
          // How far the layer can move before its edge shows inside the stage.
          var room = Math.max((l.offsetHeight - stage.clientHeight) / 2, 40);
          var dy = clamp((1 - speed) * y * 0.25, -room, room);
          l.style.transform = 'translate3d(0,' + dy.toFixed(1) + 'px,0)';
        });
      }
    }
    frames.forEach(function (f) {
      var fr = f.getBoundingClientRect();
      if (fr.bottom < -100 || fr.top > vh + 100) return;
      var dy = clamp((fr.top + fr.height / 2 - vh / 2) * 0.1, -40, 40);
      f.style.transform = 'translate3d(0,' + dy.toFixed(1) + 'px,0)';
    });
  }

  function onScroll() {
    if (!ticking) { ticking = true; window.requestAnimationFrame(parallax); }
  }

  if (!reduce) {
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    parallax();
  }

  /* ---------- Remote demo ---------- */
  var TILES = [[112, 132], [362, 132], [612, 132], [112, 330], [362, 330], [612, 330]];
  var focusIdx = 3;
  var volume = 18;
  var toastTimer = 0;
  var tvFocus = $('#tv-focus');
  var tvToast = $('#tv-toast');

  function toast(text) {
    if (!tvToast) return;
    $('#tv-toast-text').textContent = text;
    tvToast.setAttribute('opacity', '1');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { tvToast.setAttribute('opacity', '0'); }, 1200);
  }

  function moveFocus(key) {
    var col = focusIdx % 3;
    if (key === 'left' && col > 0) focusIdx -= 1;
    else if (key === 'right' && col < 2) focusIdx += 1;
    else if (key === 'up' && focusIdx >= 3) focusIdx -= 3;
    else if (key === 'down' && focusIdx < 3) focusIdx += 3;
    var t = TILES[focusIdx];
    tvFocus.style.transform = 'translate(' + t[0] + 'px,' + t[1] + 'px)';
    say('remote-status', 'Pressed ' + key + '. Focus is on tile ' + (focusIdx + 1) + ' of 6.');
  }

  $$('.remote-demo .hs').forEach(function (b) {
    b.addEventListener('click', function () {
      var key = b.getAttribute('data-key');
      var app = b.getAttribute('data-app');
      if (app) {
        $('#tv-app').textContent = app;
        say('remote-status', 'Opened ' + app + ' on the TV.');
      } else if (key === 'volup' || key === 'voldown') {
        volume = clamp(volume + (key === 'volup' ? 1 : -1), 0, 100);
        toast('Vol ' + volume);
        say('remote-status', 'Volume ' + volume + '.');
      } else if (key === 'ok') {
        toast('OK');
        say('remote-status', 'Pressed OK on tile ' + (focusIdx + 1) + '.');
      } else if (key && tvFocus) {
        moveFocus(key);
      }
    });
  });

  /* ---------- Phone demo ---------- */
  var phone = $('#phone-screens');
  var pinBoxes = $$('#pin-boxes rect');
  var pinDots = $$('#pin-dots circle');
  var pinConnect = $('#pin-connect');
  var phoneTimers = [];

  function phoneLater(fn, ms) { phoneTimers.push(setTimeout(fn, ms)); }

  function setCursor(i) {
    pinBoxes.forEach(function (b, j) { b.setAttribute('stroke', j === i ? '#5b8cff' : 'none'); });
  }

  function phoneReset() {
    phoneTimers.forEach(clearTimeout);
    phoneTimers = [];
    phone.classList.remove('done');
    pinConnect.classList.remove('pulse');
    pinDots.forEach(function (d) { d.setAttribute('opacity', '0'); });
    setCursor(0);
  }

  function phoneFinish() {
    pinDots.forEach(function (d) { d.setAttribute('opacity', '1'); });
    setCursor(-1);
    phone.classList.add('done');
    say('phone-status', 'PIN accepted. The phone is now the remote.');
  }

  function phonePlay() {
    if (!phone) return;
    phoneReset();
    say('phone-status', 'The phone is entering the 6-digit PIN.');
    if (reduce) { phoneFinish(); return; }
    pinDots.forEach(function (d, i) {
      phoneLater(function () { d.setAttribute('opacity', '1'); setCursor(i + 1); }, 400 + i * 180);
    });
    var t = 400 + pinDots.length * 180 + 150;
    phoneLater(function () { pinConnect.classList.add('pulse'); }, t);
    phoneLater(phoneFinish, t + 1100);
  }

  var replay = $('#phone-replay');
  if (replay) replay.addEventListener('click', phonePlay);

  /* ---------- Rules demo ---------- */
  var rules = { kid: true, shorts: true, channels: false };
  var rulesTv = $('#rules-tv');
  var tvSvg = $('#tv-svg');

  if (rulesTv && tvSvg) {
    // Clone the remote demo's TV. Drop its defs and ids so nothing is duplicated;
    // the url(#tv-…) fills still resolve to the original, which stays rendered.
    var clone = tvSvg.cloneNode(true);
    var defs = $('defs', clone);
    if (defs) defs.parentNode.removeChild(defs);
    clone.removeAttribute('id');
    $$('[id]', clone).forEach(function (el) { el.removeAttribute('id'); });
    var cf = $('.tv-focus', clone);
    if (cf) cf.parentNode.removeChild(cf);
    clone.setAttribute('aria-label', 'A small TV preview showing which videos the rules block');
    rulesTv.innerHTML = '';
    rulesTv.appendChild(clone);
  }

  function renderRule(name) {
    var on = rules[name];
    var tg = $('.tg[data-rule="' + name + '"]');
    if (tg) {
      $('.trk', tg).setAttribute('fill', on ? 'url(#r-brand)' : '#262c3d');
      var knob = $('.knob', tg);
      knob.setAttribute('cx', on ? '31' : '13');
      knob.setAttribute('fill', on ? '#fff' : '#9aa3b8');
    }
    var btn = $('.row-btn[data-rule="' + name + '"]');
    if (btn) btn.setAttribute('aria-checked', on ? 'true' : 'false');
    if (rulesTv) {
      $$('.tv-blocked[data-rule="' + name + '"]', rulesTv).forEach(function (g) {
        g.setAttribute('opacity', on ? '1' : '0');
      });
    }
  }

  Object.keys(rules).forEach(renderRule);

  $$('.row-btn[data-rule]').forEach(function (b) {
    b.addEventListener('click', function () {
      var name = b.getAttribute('data-rule');
      rules[name] = !rules[name];
      renderRule(name);
      var label = b.getAttribute('aria-label');
      var msg = label + (rules[name] ? ' is on.' : ' is off.');
      if (name !== 'channels') msg += rules[name] ? ' A video on the TV is blocked.' : ' The video can play.';
      say('rules-status', msg);
    });
  });

  var range = $('#r-time');
  function renderTime() {
    var v = parseInt(range.value, 10) || 0;
    $('#r-time-text').textContent = v + ' of 120 min';
    $('#r-time-fill').setAttribute('width', (440 * v / 120).toFixed(1));
    range.setAttribute('aria-valuetext', v + ' of 120 minutes');
    var left = 120 - v;
    var chip = left > 0 ? 'Rules on · ' + left + ' min left' : 'Time is up · TV off';
    $$('.tv-chip').forEach(function (c) { c.textContent = chip; });
    return left;
  }
  if (range) {
    renderTime();
    range.addEventListener('input', renderTime);
    range.addEventListener('change', function () {
      var left = renderTime();
      say('rules-status', left > 0 ? left + ' minutes of screen time left today.' : 'Screen time is used up. The TV turns off.');
    });
  }

  /* ---------- History demo ---------- */
  var filtered = false;
  var allowed = false;
  var hAll = $('#h-all');
  var hBlocked = $('#h-blocked');
  var hAllow = $('#h-allow');

  function pill(id, on) {
    $('#' + id).setAttribute('fill', on ? 'url(#h-brand)' : '#1b2030');
    $('#' + id + '-t').setAttribute('fill', on ? '#fff' : '#9aa3b8');
  }

  function renderHistory() {
    pill('h-pill-all', !filtered);
    pill('h-pill-blk', filtered);
    hAll.setAttribute('aria-pressed', filtered ? 'false' : 'true');
    hBlocked.setAttribute('aria-pressed', filtered ? 'true' : 'false');
    $('#h-live').classList.toggle('hidden', filtered);
    $('#h-past').classList.toggle('hidden', filtered);
    $('#h-blk').style.transform = filtered ? 'translateY(-66px)' : '';
    hAllow.style.top = filtered ? '55.6%' : '69.4%';

    var green = '#3ccf91';
    var bg = $('#h-blk-bg');
    bg.setAttribute('fill', allowed ? green : '#ff5d6c');
    bg.setAttribute('stroke', allowed ? green : '#ff5d6c');
    $('#h-blk-dot').setAttribute('fill', allowed ? green : '#ff5d6c');
    var sub = $('#h-blk-sub');
    sub.textContent = allowed ? 'Allowed · plays next time · 19:26' : 'Blocked by Kid filter · 19:26';
    sub.setAttribute('fill', allowed ? green : '#ff8a95');
    $('#h-allow-t').textContent = allowed ? 'Undo' : 'Allow';
    hAllow.setAttribute('aria-label', (allowed ? 'Undo allow for ' : 'Allow ') + 'Scary zombie night 3');
    $('#h-count').textContent = allowed ? '2' : '3';
  }

  if (hAll && hBlocked && hAllow) {
    renderHistory();
    hAll.addEventListener('click', function () {
      filtered = false; renderHistory();
      say('history-status', 'Showing all videos.');
    });
    hBlocked.addEventListener('click', function () {
      filtered = true; renderHistory();
      say('history-status', 'Showing blocked videos only.');
    });
    hAllow.addEventListener('click', function () {
      allowed = !allowed; renderHistory();
      say('history-status', allowed
        ? 'Scary zombie night 3 is allowed and plays next time. 2 blocked today.'
        : 'Scary zombie night 3 is blocked again. 3 blocked today.');
    });
  }

  /* ---------- Platforms switch ---------- */
  var table = $('#plat-table');
  var segBtns = $$('.seg button[data-plat]');
  segBtns.forEach(function (b) {
    b.addEventListener('click', function () {
      var plat = b.getAttribute('data-plat');
      segBtns.forEach(function (o) { o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
      if (table) table.className = 'hl-' + plat;
    });
  });

  /* ---------- Reveal once, and start the phone demo when it is seen ---------- */
  var reveals = $$('.reveal');
  if (!('IntersectionObserver' in window)) {
    reveals.forEach(function (el) { el.classList.add('in'); });
    phonePlay();
    return;
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add('in');
      io.unobserve(e.target);
    });
  }, { threshold: 0.15 });
  reveals.forEach(function (el) { io.observe(el); });

  var phoneDemo = $('.phone-demo');
  if (phoneDemo) {
    var pio = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) { pio.disconnect(); phonePlay(); }
    }, { threshold: 0.5 });
    pio.observe(phoneDemo);
  }
})();
