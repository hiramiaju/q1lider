(() => {
  const html = document.documentElement;
  const themeMeta = document.querySelector('meta[name="theme-color"]');

  const refreshThemeControls = () => {
    const dark = html.dataset.theme === 'dark';
    document.querySelectorAll('[data-theme-toggle], [data-login-theme-toggle]').forEach(button => {
      button.classList.toggle('isDark', dark);
      button.setAttribute('aria-label', dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');
      button.setAttribute('title', dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');
      const label = button.querySelector('.themeLabel');
      if (label) label.textContent = dark ? 'Claro' : 'Oscuro';
    });
    if (themeMeta) themeMeta.setAttribute('content', dark ? '#0f1020' : '#2D0B91');
  };

  const applyTheme = (theme, persistServer = false) => {
    const normalized = theme === 'dark' ? 'dark' : 'light';
    html.dataset.theme = normalized;
    refreshThemeControls();

    const userId = html.dataset.userId || '';
    if (userId) {
      try { localStorage.setItem(`q1lider-theme:${userId}`, normalized); } catch (_) {}
      if (persistServer) {
        fetch('/preferencias/tema', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({theme: normalized})
        }).catch(() => {});
      }
    } else {
      try { localStorage.setItem('q1lider-login-theme', normalized); } catch (_) {}
    }
  };

  document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
    applyTheme(html.dataset.theme === 'dark' ? 'light' : 'dark', true);
  }));
  document.querySelectorAll('[data-login-theme-toggle]').forEach(button => button.addEventListener('click', () => {
    applyTheme(html.dataset.theme === 'dark' ? 'light' : 'dark', false);
  }));
  refreshThemeControls();

  const sidebar = document.getElementById('sidebar');
  const backdrop = document.querySelector('.drawerBackdrop');
  const closeDrawer = () => { sidebar?.classList.remove('open'); backdrop?.classList.remove('open'); };
  document.querySelectorAll('[data-open-drawer]').forEach(b => b.addEventListener('click', () => {sidebar?.classList.add('open'); backdrop?.classList.add('open');}));
  document.querySelectorAll('[data-close-drawer]').forEach(b => b.addEventListener('click', closeDrawer));

  const openModal = id => document.getElementById(id)?.classList.add('open');
  const closeModal = el => el?.classList.remove('open');
  document.querySelectorAll('[data-modal-open]').forEach(b => b.addEventListener('click', () => openModal(b.dataset.modalOpen)));
  document.querySelectorAll('[data-modal-close]').forEach(b => b.addEventListener('click', () => closeModal(b.closest('.overlay'))));
  document.querySelectorAll('.overlay').forEach(o => o.addEventListener('mousedown', e => { if(e.target === o) closeModal(o); }));

  document.querySelectorAll('.day[data-date]').forEach(d => d.addEventListener('dblclick', () => {
    const input = document.querySelector('#newEvent input[name="date"]'); if(input) input.value = d.dataset.date || '';
    openModal('newEvent');
  }));

  document.querySelectorAll('.event-detail').forEach(btn => btn.addEventListener('click', () => {
    try {
      const e = JSON.parse(btn.dataset.event || '{}');
      const $ = id => document.getElementById(id);
      $('detailTitle').textContent = e.title || '';
      const imageBox = $('detailImage');
      if (imageBox) imageBox.innerHTML = e.imageName ? `<img src="/uploads/${encodeURIComponent(e.imageName)}" alt="Imagen de la actividad">` : '';
      $('detailDescription').textContent = e.description || 'Sin descripción.';
      $('detailDate').textContent = e.date || '';
      $('detailTime').textContent = `${e.startTime || ''} – ${e.endTime || ''}`;
      $('detailPlace').textContent = e.place || 'Sin definir';
      $('detailStatus').textContent = e.status || 'pending';
      $('detailBadge').innerHTML = `<span class="badge ${e.type === 'official' ? 'official':'personal'}">${e.type === 'official' ? '+Q1LÍDER':'Personal'}</span>`;
      openModal('eventDetail');
    } catch(_) {}
  }));

  document.querySelectorAll('.user-edit').forEach(btn => btn.addEventListener('click', () => {
    try {
      const u = JSON.parse(btn.dataset.user || '{}');
      document.getElementById('euName').value = u.name || '';
      document.getElementById('euLast').value = u.lastName || '';
      document.getElementById('euEmail').value = u.email || '';
      document.getElementById('euRole').value = u.role || 'participant';
      document.getElementById('euStatus').value = u.status || 'active';
      document.getElementById('editUserForm').action = `/users/${u.id}/update`;
      openModal('editUser');
    } catch(_) {}
  }));

  document.querySelectorAll('.note-edit').forEach(btn => btn.addEventListener('click', () => {
    try {
      const note = JSON.parse(btn.dataset.note || '{}');
      const form = document.getElementById('editPersonalNoteForm');
      const text = document.getElementById('spnText');
      if (!form || !text || !note.id) return;
      text.value = note.text || '';
      form.action = `/notes/${encodeURIComponent(note.id)}/update`;
      openModal('editPersonalNote');
      setTimeout(() => text.focus(), 30);
    } catch(_) {}
  }));

  document.querySelectorAll('.personal-event-edit').forEach(btn => btn.addEventListener('click', () => {
    try {
      const e = JSON.parse(btn.dataset.event || '{}');
      const form = document.getElementById('editPersonalEventForm');
      if (!form || !e.id) return;
      const set = (id, value) => { const el = document.getElementById(id); if (el) el.value = value ?? ''; };
      set('speTitle', e.title);
      set('speDescription', e.description);
      set('speDate', e.date);
      set('spePriority', e.priority || 'medium');
      set('speStart', e.startTime || '09:00');
      set('speEnd', e.endTime || '10:00');
      set('spePlace', e.place);
      set('speStatus', e.status || 'pending');
      form.action = `/events/${encodeURIComponent(e.id)}/update`;
      openModal('editPersonalEvent');
    } catch(_) {}
  }));

  const filter = document.getElementById('studentFilter');
  if(filter) filter.addEventListener('input', () => {
    const q = filter.value.trim().toLowerCase();
    document.querySelectorAll('.student-row').forEach(row => { row.style.display = (row.dataset.search || '').includes(q) ? '' : 'none'; });
  });

  document.querySelectorAll('.flash').forEach(el => setTimeout(() => { el.style.opacity='0'; el.style.transform='translateY(-6px)'; setTimeout(()=>el.remove(),250); }, 4200));
})();
