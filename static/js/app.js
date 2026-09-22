(() => {
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

  const filter = document.getElementById('studentFilter');
  if(filter) filter.addEventListener('input', () => {
    const q = filter.value.trim().toLowerCase();
    document.querySelectorAll('.student-row').forEach(row => { row.style.display = (row.dataset.search || '').includes(q) ? '' : 'none'; });
  });

  document.querySelectorAll('.flash').forEach(el => setTimeout(() => { el.style.opacity='0'; el.style.transform='translateY(-6px)'; setTimeout(()=>el.remove(),250); }, 4200));
})();
