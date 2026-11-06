// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The AI assistant in the receipts clip (scripts/promo_film.py): a chat panel
// laid over Huismus. Deliberately plain, "AI-assistent", in Huismus's colours:
// not the look of Claude, ChatGPT or any other app. What it shows the
// assistant doing, the script really does through Huismus's /mcp, with the
// tool titles Huismus gives them. Nothing animates by itself: the script sets
// every change, one frame at a time.
(() => {
  if (window.assistent) return;
  const style = document.createElement('style');
  style.textContent = `
    #ai { position: fixed; top: 0; right: 0; height: 810px; width: 470px; z-index: 2147483000;
          display: flex; flex-direction: column; background: #fbfaf8; color: #23201c;
          box-shadow: -18px 0 60px rgba(40, 30, 20, .18); border-left: 1px solid #e6e0d7;
          transform: translateX(105%); font-size: 16px; }
    #ai header { display: flex; align-items: center; gap: 10px; padding: 22px 24px;
                 border-bottom: 1px solid #ece6dd; font-weight: 600; font-size: 17px; }
    #ai header i { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center;
                   background: linear-gradient(135deg, #6c5ce7, #1f6fd1); color: #fff; font-style: normal; }
    #ai .log { flex: 1; overflow: hidden; padding: 22px 24px; display: flex; flex-direction: column;
                justify-content: flex-end; gap: 14px; }
    #ai .me { align-self: flex-end; max-width: 82%; padding: 11px 15px; border-radius: 18px 18px 4px 18px;
              background: #1f6fd1; color: #fff; }
    #ai .step { display: flex; align-items: center; gap: 10px; color: #6f685f; font-size: 15px; }
    #ai .step em { font-style: normal; display: grid; place-items: center; width: 22px; height: 22px;
                   border-radius: 50%; background: #e9f4ee; color: #2e9d5b; font-size: 13px; }
    #ai .step.busy em { background: none; border: 2.5px solid #d6d0c7; border-top-color: #1f6fd1; }
    #ai .ask { border: 1px solid #e0d9cf; border-radius: 16px; padding: 16px 18px; background: #fff; }
    #ai .ask small { display: block; color: #8b847b; font-size: 13px; margin-bottom: 4px; }
    #ai .ask b { display: block; margin-bottom: 8px; }
    #ai .ask dl { display: grid; grid-template-columns: auto 1fr; gap: 3px 14px; margin: 0 0 14px; font-size: 15px; }
    #ai .ask dt { color: #8b847b; }
    #ai .ask dd { margin: 0; }
    #ai .ask .knoppen { display: flex; gap: 10px; justify-content: flex-end; }
    #ai .ask button { font: inherit; font-size: 15px; font-weight: 600; padding: 9px 16px; border-radius: 10px;
                      border: 1px solid #d6d0c7; background: #fff; color: #23201c; }
    #ai .ask button.ja { background: #1f6fd1; border-color: #1f6fd1; color: #fff; }
    #ai .ask.klaar { opacity: .55; }
    #ai .ask.klaar .knoppen { display: none; }
    #ai .zegt { line-height: 1.45; }
    #ai footer { padding: 18px 24px 24px; border-top: 1px solid #ece6dd; }
    #ai .veld { min-height: 50px; padding: 13px 16px; border-radius: 14px; border: 1px solid #d6d0c7;
                background: #fff; color: #23201c; }
    #ai .veld:empty::before { content: 'Vraag iets…'; color: #a59e94; }
    #ai .veld.typt::after { content: ''; display: inline-block; width: 2px; height: 1.1em;
                            background: #1f6fd1; vertical-align: text-bottom; margin-left: 1px; }
  `;
  document.head.append(style);
  const panel = document.createElement('aside');
  panel.id = 'ai';
  panel.innerHTML = `<header><i>✦</i>AI-assistent</header><div class="log"></div>
    <footer><div class="veld"></div></footer>`;
  document.body.append(panel);
  const log = panel.querySelector('.log');
  const field = panel.querySelector('.veld');
  const add = (html) => { log.insertAdjacentHTML('beforeend', html); return log.lastElementChild; };

  window.assistent = {
    // 0 = out of sight on the right, 1 = fully in.
    slide(t) { panel.style.transform = `translateX(${(1 - t) * 105}%)`; },
    // null: nobody is typing, so no cursor either.
    typing(text) { field.textContent = text ?? ''; field.classList.toggle('typt', text !== null); },
    send() { add(`<div class="me"></div>`).textContent = field.textContent; this.typing(null); },
    step(title, busy) {
      const row = add(`<div class="step"><em></em><span></span></div>`);
      row.querySelector('span').textContent = `Huismus · ${title}`;
      this.done(row, !busy);
      return row;
    },
    done(row, done = true) { row.classList.toggle('busy', !done); row.querySelector('em').textContent = done ? '✓' : ''; },
    ask(title, facts) {
      const card = add(`<div class="ask"><small>Toestemming voor Huismus</small><b></b><dl></dl>
        <div class="knoppen"><button>Weigeren</button><button class="ja" id="toestaan">Toestaan</button></div></div>`);
      card.querySelector('b').textContent = title;
      for (const [term, value] of facts) {
        card.querySelector('dl').insertAdjacentHTML('beforeend', '<dt></dt><dd></dd>');
        card.querySelector('dl dt:last-of-type').textContent = term;
        card.querySelector('dl dd:last-of-type').textContent = value;
      }
      return card;
    },
    allowed(card) { card.classList.add('klaar'); },
    say(text) { add(`<div class="zegt"></div>`).textContent = text; },
  };
})();
