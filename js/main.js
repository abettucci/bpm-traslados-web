/* =========================================
   BPM Traslados — Main Logic
   ========================================= */

let activeFilter = 'todos';

// ---- Hamburger menu ----
function initHamburger() {
  const btn = document.getElementById('hamburger-btn');
  const menu = document.getElementById('navbar-mobile');
  if (!btn || !menu) return;

  btn.addEventListener('click', () => {
    btn.classList.toggle('open');
    menu.classList.toggle('open');
  });

  // Close on link click
  menu.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      btn.classList.remove('open');
      menu.classList.remove('open');
    });
  });
}

// ---- Active nav link ----
function setActiveNavLink() {
  const path = window.location.pathname;
  document.querySelectorAll('.navbar-links a, .navbar-mobile a').forEach(a => {
    a.classList.remove('active');
    const href = a.getAttribute('href') || '';
    if (
      (href === 'index.html' || href === '/' || href === '' || href === '../index.html') && (path.endsWith('index.html') || path.endsWith('/') || path.endsWith('bpm-traslados-web/'))
    ) {
      a.classList.add('active');
    } else if (href.includes('como-reservar') && path.includes('como-reservar')) {
      a.classList.add('active');
    } else if (href.includes('preguntas-frecuentes') && path.includes('preguntas-frecuentes')) {
      a.classList.add('active');
    } else if (href.includes('resenas') && path.includes('resenas')) {
      a.classList.add('active');
    }
  });
}

// ---- Badge HTML ----
function badgeHTML(event) {
  const map = {
    avail: { cls: 'badge-avail', label: event.badgeLabel },
    few:   { cls: 'badge-few',   label: event.badgeLabel },
    sold:  { cls: 'badge-sold',  label: event.badgeLabel },
    pre:   { cls: 'badge-pre',   label: event.badgeLabel },
  };
  const b = map[event.badge] || map.avail;
  return `<span class="card-badge ${b.cls}"><span class="badge-dot"></span>${b.label}</span>`;
}

// ---- Render single card ----
function renderCard(event) {
  const isSold = event.badge === 'sold';
  const waLink = buildWhatsAppLink(event);
  const priceDisplay = event.price
    ? `<span class="card-price">$${event.price.toLocaleString('es-AR')}</span>`
    : `<span class="card-price consultar">Consultar</span>`;

  return `
    <article class="event-card genre-${event.genre}">
      <div class="card-image">
        <span class="card-image-icon">${event.icon}</span>
        ${badgeHTML(event)}
      </div>
      <div class="card-body">
        <span class="card-genre-tag">${event.genreLabel}</span>
        <h3 class="card-title">${event.subtitle ? `<small style="display:block;font-size:0.72rem;font-weight:500;color:var(--text-faint);margin-bottom:2px;">${event.subtitle}</small>` : ''}${event.title}</h3>
        <p class="card-venue">📍 ${event.venue} · ${event.city}</p>
        <div class="card-meta">
          <span class="card-date">🗓 ${event.dateDisplay} · ${event.time}h</span>
          ${priceDisplay}
        </div>
      </div>
      <div class="card-footer">
        ${isSold
          ? `<button class="btn-reservar sold" disabled>Agotado</button>`
          : `<a href="${waLink}" target="_blank" rel="noopener" class="btn-reservar available">
               <span>RESERVAR</span>
               <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.091.538 4.058 1.479 5.777L0 24l6.395-1.479A11.947 11.947 0 0 0 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.853 0-3.607-.49-5.126-1.348l-.368-.211-3.795.877.896-3.704-.229-.378A9.962 9.962 0 0 1 2 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/></svg>
             </a>`
        }
      </div>
    </article>
  `;
}

// ---- Render grid ----
function renderGrid(filter) {
  const grid = document.getElementById('events-grid');
  const countEl = document.getElementById('events-count');
  if (!grid) return;

  const filtered = filter === 'todos'
    ? EVENTS
    : EVENTS.filter(e => e.genre === filter);

  if (countEl) countEl.textContent = `${filtered.length} eventos`;

  if (filtered.length === 0) {
    grid.innerHTML = `<div class="no-events">No hay eventos en esta categoría por ahora.</div>`;
    return;
  }

  grid.innerHTML = filtered.map(renderCard).join('');
}

// ---- Filter pills ----
function initFilters() {
  document.querySelectorAll('.filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      activeFilter = pill.dataset.filter;
      renderGrid(activeFilter);
    });
  });
}

// ---- FAQ accordion ----
function initFAQ() {
  document.querySelectorAll('.faq-question').forEach(btn => {
    btn.addEventListener('click', () => {
      const item = btn.closest('.faq-item');
      const isOpen = item.classList.contains('open');

      // Close all
      document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));

      // Toggle clicked
      if (!isOpen) item.classList.add('open');
    });
  });
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  initHamburger();
  setActiveNavLink();
  renderGrid('todos');
  initFilters();
  initFAQ();
});