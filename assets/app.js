// Поведение страниц: подсказки по одной, проверка ответа, фильтры, высота интерактива.
(function () {
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // Оглавление на телефоне
  const mb = document.querySelector('.menu-btn');
  if (mb) mb.addEventListener('click', () => document.body.classList.toggle('side-open'));

  // Задача-история: открыть следующий пункт, когда текущий решён или открыто его решение
  const unlockNext = qa => {
    const part = qa.closest(".part"); if (!part) return;
    const next = part.nextElementSibling;
    if (next && next.hidden) { next.hidden = false; const note = part.querySelector(".unlock-note"); if (note) note.hidden = true; }
  };

  // Лестница подсказок — отдельно для каждого вопроса (задачи или пункта)
  $$(".qa").forEach(qa => {
    const hints = $$(".hint", qa), sol = qa.querySelector(".solution");
    const nextBtn = qa.querySelector(".next-hint"), solBtn = qa.querySelector(".show-solution");
    let shown = 0;
    if (nextBtn) nextBtn.addEventListener("click", () => {
      if (shown < hints.length) hints[shown++].hidden = false;
      if (shown < hints.length) nextBtn.textContent = "Подсказка " + (shown + 1);
      else nextBtn.hidden = true;
    });
    if (solBtn) solBtn.addEventListener("click", () => {
      if (!solBtn.dataset.confirm && shown < hints.length) {
        solBtn.dataset.confirm = "1";
        solBtn.textContent = "Точно показать? Сначала попробуй подсказки";
        return;
      }
      hints.forEach(h => h.hidden = false); if (nextBtn) nextBtn.hidden = true;
      sol.hidden = false; solBtn.hidden = true;
      unlockNext(qa);
    });
  });

  // Проверка ответа: каждое поле отдельно
  // Число из ответа ученика: понимает запятую, минус «−», запись 3e6, 3·10^6, 3×10⁶, 3*10^-7
  const SUP = { "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-" };
  const num = s => {
    let t = String(s).trim().replace(/\s/g, "").replace(",", ".").replace(/[−–]/g, "-").replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]/g, c => SUP[c]);
    t = t.replace(/^([-+]?[\d.]+)[·×*xх]10\^?([-+]?\d+)$/, "$1e$2").replace(/^([-+]?)10\^([-+]?\d+)$/, "$11e$2");
    return /^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(t) ? parseFloat(t) : NaN;
  };
  const letters = s => [...new Set((String(s).toLowerCase().match(/[а-яёa-z]/g) || []))].sort().join(",");
  const checkField = f => {
    const input = f.querySelector("input"), type = f.dataset.type, val = f.dataset.value, tol = f.dataset.tol;
    if (!input.value.trim()) return null;
    if (type === "number") {
      const x = num(input.value), v = num(val);
      if (isNaN(x)) return false;
      let d = 1e-9;
      if (/%$/.test(tol)) d = Math.abs(v) * parseFloat(tol) / 100;
      else if (tol !== "" && !isNaN(num(tol))) d = Math.max(num(tol), 1e-9);
      return Math.abs(x - v) <= d + 1e-9;
    }
    if (type === "estimate") {
      // оценка: засчитываем, если отличается от эталона не больше чем в N раз (tolerance: x3)
      const x = num(input.value), v = num(val), n = parseFloat(String(tol).replace(/^x/, "")) || 3;
      if (isNaN(x) || x <= 0) return false;
      return Math.max(x / v, v / x) <= n + 1e-9;
    }
    if (type === "choice") return letters(input.value) === letters(val);
    return input.value.trim().toLowerCase() === String(val).trim().toLowerCase();
  };
  $$(".p-check").forEach(form => form.addEventListener("submit", e => {
    e.preventDefault();
    const fields = $$(".field", form), res = fields.map(checkField), out = form.querySelector(".verdict");
    fields.forEach((f, i) => { const m = f.querySelector(".mark"); m.textContent = res[i] === null ? "" : res[i] ? "✓" : "✗"; m.className = "mark " + (res[i] ? "ok" : "no"); });
    const ok = res.every(r => r === true), empty = res.some(r => r === null);
    out.textContent = ok ? "✓ Верно!" : empty ? (fields.length > 1 ? "Заполни все поля" : "Введи ответ") :
      fields.length > 1 ? "Верно " + res.filter(r => r).length + " из " + fields.length + ". Попробуй подсказку" : "✗ Пока нет. Попробуй подсказку";
    out.className = "verdict " + (ok ? "ok" : "no");
    if (ok) unlockNext(form.closest(".qa"));
  }));

  // Показать все пункты задачи-истории (для проверки и повторения)
  $$(".reveal-all").forEach(b => b.addEventListener("click", () => {
    const card = b.closest(".problem");
    $$(".part", card).forEach(p => p.hidden = false); $$(".unlock-note", card).forEach(n => n.hidden = true);
    b.hidden = true;
  }));

  // Фильтр задач по уровню
  $$('.problems .filter').forEach(f => f.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    $$('button', f).forEach(x => x.classList.toggle('on', x === b));
    const lv = b.dataset.level;
    $$('.problem').forEach(p => p.hidden = lv === 'story' ? !p.classList.contains('story-problem') : lv !== 'all' && p.dataset.level !== lv);
  }));

  // Фильтр курса по классу на главной
  $$('.grades').forEach(f => f.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    $$('button', f).forEach(x => x.classList.toggle('on', x === b));
    const g = b.dataset.grade;
    $$('.topics li').forEach(li => li.hidden = g !== 'all' && !li.dataset.grades.split(',').includes(g));
    $$('.chap').forEach(c => { const items = $$('.topics li', c); c.hidden = items.length > 0 && items.every(li => li.hidden) || (g !== 'all' && !items.length); });
    $$('.sec').forEach(s => { const cs = $$('.chap', s); s.hidden = g !== 'all' && (!cs.length || cs.every(c => c.hidden)); });
  }));

  // Высота встроенного интерактива
  addEventListener('message', e => {
    if (!e.data || e.data.type !== 'interactive-height') return;
    $$('.interactive iframe').forEach(f => { if (f.contentWindow === e.source) f.style.height = Math.ceil(e.data.h) + 'px'; });
  });
})();
