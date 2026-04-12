const importForm = document.querySelector('#import-form');
const filterForm = document.querySelector('#filter-form');
const myListFilterForm = document.querySelector('#my-list-filter-form');
const myListUpdateForm = document.querySelector('#my-list-update-form');
const historyFilterForm = document.querySelector('#history-filter-form');
const contactForm = document.querySelector('#contact-form');
const tagForm = document.querySelector('#tag-form');
const suppressionForm = document.querySelector('#suppression-form');
const adapterForm = document.querySelector('#adapter-form');
const googleKeyForm = document.querySelector('#google-key-form');

const importResult = document.querySelector('#import-result');
const contactResult = document.querySelector('#contact-result');
const tagResult = document.querySelector('#tag-result');
const suppressionResult = document.querySelector('#suppression-result');
const adapterResult = document.querySelector('#adapter-result');
const limitResult = document.querySelector('#limit-result');
const googleKeyStatus = document.querySelector('#google-key-status');
const myListAddResult = document.querySelector('#my-list-add-result');
const myListResult = document.querySelector('#my-list-result');
const historyResult = document.querySelector('#history-result');

const suppressionList = document.querySelector('#suppression-list');
const adapterList = document.querySelector('#adapter-list');
const auditList = document.querySelector('#audit-list');
const auditRefresh = document.querySelector('#audit-refresh');
const activityFeed = document.querySelector('#activity-feed');

const leadsTbody = document.querySelector('#lead-table tbody');
const myListTbody = document.querySelector('#my-list-table tbody');
const historyTbody = document.querySelector('#history-table tbody');

const categorySelect = document.querySelector('select[name="category"]');
const industrySelect = document.querySelector('select[name="industry"]');
const placeTypeSelect = document.querySelector('#place-type-select');
const placeTypeFilterInput = document.querySelector('#place-type-filter');
const importQueryInput = document.querySelector('#import-form input[name="query"]');
const myListStatusSelect = document.querySelector('#my-list-filter-form select[name="status"]');

const leadSelectAll = document.querySelector('#select-all');
const myListSelectAll = document.querySelector('#my-list-select-all');
const addToMyListBtn = document.querySelector('#add-to-my-list');
const myListSendBtn = document.querySelector('#my-list-send-btn');
const myListRemoveBtn = document.querySelector('#my-list-remove-btn');

const myListDefaultStatus = document.querySelector('#my-list-default-status');
const myListDefaultPriority = document.querySelector('#my-list-default-priority');

let currentItems = [];
let myListItems = [];
let placeTypeItems = [];

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    window.location.href = '/';
    return null;
  }
  return res;
}

async function loadUserBadge() {
  const res = await apiFetch('/api/auth/me');
  if (!res) return;
  const data = await res.json();
  const badge = document.querySelector('#gmail-badge');
  if (!badge) return;
  if (data.gmail_connected) {
    badge.textContent = '✉ Gmail 接続済み';
    badge.className = 'gmail-badge connected';
  } else {
    badge.textContent = '⚠ Gmail 未接続';
    badge.className = 'gmail-badge disconnected';
  }
}

function addActivity(text, who = 'system') {
  const el = document.createElement('div');
  el.className = `chat-item ${who}`;
  el.textContent = `[${new Date().toLocaleTimeString('ja-JP')}] ${text}`;
  activityFeed.prepend(el);
}

function switchView(viewName) {
  document.querySelectorAll('.menu-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.view === viewName);
  });
  document.querySelectorAll('.view').forEach((el) => {
    el.classList.toggle('active', el.id === `view-${viewName}`);
  });

  if (viewName === 'suppression') fetchSuppressions();
  if (viewName === 'settings') fetchGoogleKeyStatus();
  if (viewName === 'adapters') fetchAdapters();
  if (viewName === 'audit') fetchAuditLogs();
  if (viewName === 'my-list') fetchMyList();
  if (viewName === 'history') fetchContactLogs();
}

document.querySelector('#view-menu').addEventListener('click', (e) => {
  const btn = e.target.closest('.menu-item');
  if (!btn) return;
  switchView(btn.dataset.view);
});

function escapeHtml(str) {
  return String(str || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function renderOptions(select, items, selected) {
  if (!select) return;
  const base = '<option value="">すべて</option>';
  const options = items.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('');
  select.innerHTML = base + options;
  select.value = selected || '';
}

function renderLeadsTable(items) {
  leadsTbody.innerHTML = items
    .map(
      (item) => `
      <tr>
        <td><input type="checkbox" class="lead-check" value="${item.id}" /></td>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.effective_category || item.category)}</td>
        <td>${escapeHtml(item.effective_industry || item.industry)}</td>
        <td>${item.rating ?? ''}</td>
        <td>${item.user_ratings_total ?? ''}</td>
        <td>${item.website ? `<a href="${escapeHtml(item.website)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.website)}</a>` : ''}</td>
        <td>${escapeHtml(item.phone)}</td>
        <td>${escapeHtml(item.email)}${item.suppressed ? ' (停止中)' : ''}</td>
        <td>${escapeHtml(item.address)}</td>
      </tr>
    `,
    )
    .join('');
}

function renderMyListTable(items) {
  myListTbody.innerHTML = items
    .map(
      (item) => `
      <tr>
        <td><input type="checkbox" class="my-list-check" value="${item.id}" data-lead-id="${item.lead_id}" /></td>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.effective_category)}</td>
        <td>${escapeHtml(item.effective_industry)}</td>
        <td>${escapeHtml(item.status)}</td>
        <td>${escapeHtml(item.priority)}</td>
        <td>${escapeHtml(item.last_contacted_at || '')}</td>
        <td>${Number(item.contact_count || 0)}</td>
        <td>${escapeHtml(item.email)}</td>
        <td>${escapeHtml(item.address)}</td>
      </tr>
    `,
    )
    .join('');
}

function renderHistoryTable(items) {
  historyTbody.innerHTML = items
    .map(
      (item) => `
      <tr>
        <td>${escapeHtml(item.created_at)}</td>
        <td>${escapeHtml(item.lead_name)}</td>
        <td>${escapeHtml(item.channel)}</td>
        <td>${escapeHtml(item.status)}</td>
        <td>${escapeHtml(item.subject)}</td>
        <td>${escapeHtml(item.message || '').slice(0, 120)}</td>
      </tr>
    `,
    )
    .join('');
}

function getSelectedLeadIds() {
  return Array.from(document.querySelectorAll('.lead-check:checked')).map((el) => Number(el.value));
}

function getSelectedMyListItemIds() {
  return Array.from(document.querySelectorAll('.my-list-check:checked')).map((el) => Number(el.value));
}

function getSelectedMyListLeadIds() {
  return Array.from(document.querySelectorAll('.my-list-check:checked')).map((el) => Number(el.dataset.leadId));
}

async function fetchLeads() {
  const params = new URLSearchParams(new FormData(filterForm));
  const res = await apiFetch(`/api/leads?${params.toString()}`);
  if (!res) return;
  const data = await res.json();

  currentItems = data.items || [];
  renderLeadsTable(currentItems);
  renderOptions(categorySelect, data.filters.categories || [], filterForm.category.value);
  renderOptions(industrySelect, data.filters.industries || [], filterForm.industry.value);
  limitResult.textContent = `本日上限 ${data.send_limit.daily_limit}件 / email残 ${data.send_limit.email_remaining} / form残 ${data.send_limit.form_remaining}`;
}

async function fetchMyList() {
  const params = new URLSearchParams(new FormData(myListFilterForm));
  const res = await apiFetch(`/api/my-list?${params.toString()}`);
  if (!res) return;
  const data = await res.json();
  if (!res.ok) {
    myListResult.textContent = `エラー: ${data.detail || '取得失敗'}`;
    return;
  }

  myListItems = data.items || [];
  renderMyListTable(myListItems);
  renderOptions(myListStatusSelect, data.filters.statuses || [], myListFilterForm.status.value);
  myListResult.textContent = `${myListItems.length}件`;
}

async function fetchContactLogs() {
  const params = new URLSearchParams(new FormData(historyFilterForm));
  const res = await apiFetch(`/api/contact-logs?${params.toString()}`);
  if (!res) return;
  const data = await res.json();
  if (!res.ok) {
    historyResult.textContent = `エラー: ${data.detail || '取得失敗'}`;
    return;
  }

  const items = data.items || [];
  renderHistoryTable(items);
  historyResult.textContent = `${items.length}件表示中`;
}

async function addSelectedToMyList() {
  const lead_ids = getSelectedLeadIds();
  if (!lead_ids.length) {
    myListAddResult.textContent = '先に企業を選択してください';
    return;
  }

  const payload = {
    lead_ids,
    status: myListDefaultStatus?.value || 'new',
    priority: myListDefaultPriority?.value || 'medium',
    note: '',
  };

  const res = await apiFetch('/api/my-list', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    myListAddResult.textContent = `エラー: ${data.detail || '追加失敗'}`;
    return;
  }

  myListAddResult.textContent = `マイリスト追加: 新規${data.added}件 / 更新${data.updated}件`;
  addActivity(`マイリスト追加: 新規${data.added}件`, 'user');
  await fetchMyList();
}

async function updateSelectedMyListItems() {
  const itemIds = getSelectedMyListItemIds();
  if (!itemIds.length) {
    myListResult.textContent = '先にマイリスト項目を選択してください';
    return;
  }

  const formData = new FormData(myListUpdateForm);
  const payload = {};

  const status = String(formData.get('status') || '').trim();
  const priority = String(formData.get('priority') || '').trim();
  const note = String(formData.get('note') || '').trim();
  const ownerName = String(formData.get('owner_name') || '').trim();

  if (status) payload.status = status;
  if (priority) payload.priority = priority;
  if (note) payload.note = note;
  if (ownerName) payload.owner_name = ownerName;

  if (!Object.keys(payload).length) {
    myListResult.textContent = '更新項目を入力してください';
    return;
  }

  let okCount = 0;
  for (const itemId of itemIds) {
    const res = await apiFetch(`/api/my-list/${itemId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res) return;
    if (res.ok) okCount += 1;
  }

  myListResult.textContent = `更新完了: ${okCount}件`;
  addActivity(`マイリスト更新: ${okCount}件`, 'user');
  await fetchMyList();
}

async function removeSelectedMyListItems() {
  const itemIds = getSelectedMyListItemIds();
  if (!itemIds.length) {
    myListResult.textContent = '先にマイリスト項目を選択してください';
    return;
  }

  let removed = 0;
  for (const itemId of itemIds) {
    const res = await apiFetch(`/api/my-list/${itemId}`, { method: 'DELETE' });
    if (!res) return;
    if (res.ok) removed += 1;
  }

  myListResult.textContent = `削除完了: ${removed}件`;
  addActivity(`マイリスト削除: ${removed}件`, 'user');
  await fetchMyList();
}

async function sendMailToSelectedMyListItems() {
  const lead_ids = getSelectedMyListLeadIds();
  if (!lead_ids.length) {
    myListResult.textContent = '先にマイリスト項目を選択してください';
    return;
  }

  const subjectInput = document.querySelector('#contact-form input[name="subject"]');
  const bodyInput = document.querySelector('#contact-form textarea[name="body"]');
  const subject = String(subjectInput?.value || '').trim();
  const body = String(bodyInput?.value || '').trim();
  if (!subject || !body) {
    myListResult.textContent = '連絡実行画面の件名と本文を入力してください';
    return;
  }

  const res = await apiFetch('/api/contact/email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lead_ids, subject, body }),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    myListResult.textContent = `エラー: ${data.detail || '送信失敗'}`;
    return;
  }

  myListResult.textContent = `送信: ${data.sent}件 スキップ: ${data.skipped}件 制限: ${data.limited}件`;
  addActivity(`マイリストからメール送信: ${data.sent}件`, 'user');
  await fetchMyList();
  await fetchContactLogs();
  await fetchLeads();
}

async function fetchSuppressions() {
  const res = await apiFetch('/api/suppressions');
  if (!res) return;
  const data = await res.json();
  suppressionList.innerHTML = (data.items || [])
    .map((x) => `<div class="row">${escapeHtml(x.email)} | ${escapeHtml(x.reason)} | ${escapeHtml(x.created_at)}</div>`)
    .join('') || '<div class="row">未登録</div>';
}

async function fetchAdapters() {
  const res = await apiFetch('/api/form-adapters');
  if (!res) return;
  const data = await res.json();
  adapterList.innerHTML = (data.items || [])
    .map((x) => `<div class="row">${escapeHtml(x.domain)} ${escapeHtml(x.path)} | ${escapeHtml(x.name)} | enabled=${x.enabled}</div>`)
    .join('') || '<div class="row">未登録</div>';
}

async function fetchAuditLogs() {
  const res = await apiFetch('/api/audit-logs?limit=100');
  if (!res) return;
  const data = await res.json();
  auditList.innerHTML = (data.items || [])
    .map((x) => `<div class="row">${escapeHtml(x.created_at)} | ${escapeHtml(x.action)} | ${escapeHtml(x.target_type)}:${escapeHtml(x.target_id || '')}</div>`)
    .join('') || '<div class="row">ログなし</div>';
}

async function fetchGoogleKeyStatus() {
  const res = await apiFetch('/api/settings/google-maps-key');
  if (!res) return;
  const data = await res.json();
  if (!res.ok) {
    googleKeyStatus.textContent = `状態取得エラー: ${data.detail || 'unknown'}`;
    return;
  }
  if (!data.configured) {
    googleKeyStatus.textContent = '未設定です。APIキーを保存してください。';
    return;
  }
  googleKeyStatus.textContent = `設定済み: ${data.masked}`;
}

async function fetchPlaceTypes() {
  if (!placeTypeSelect) return;
  const res = await apiFetch('/api/place-types');
  if (!res) return;
  const data = await res.json();
  if (!res.ok) {
    addActivity(`業種プリセット取得失敗: ${data.detail || 'error'}`, 'system');
    return;
  }

  placeTypeItems = data.items || [];
  renderPlaceTypeOptions(placeTypeItems, '');
}

function renderPlaceTypeOptions(items, selectedValue = '') {
  if (!placeTypeSelect) return;

  const grouped = new Map();
  for (const item of items) {
    const industry = item.industry || '未分類';
    if (!grouped.has(industry)) grouped.set(industry, []);
    grouped.get(industry).push(item);
  }

  let html = '<option value="">すべて</option>';
  for (const [industry, groupedItems] of grouped.entries()) {
    const opts = groupedItems
      .map((item) => {
        const value = escapeHtml(item.value || '');
        const label = escapeHtml(item.label || item.value || '');
        const suffix = item.recommended ? ' ★' : '';
        return `<option value="${value}" data-label="${label}">${label}${suffix}</option>`;
      })
      .join('');
    html += `<optgroup label="${escapeHtml(industry)}">${opts}</optgroup>`;
  }

  placeTypeSelect.innerHTML = html;
  const exists = selectedValue && items.some((x) => x.value === selectedValue);
  placeTypeSelect.value = exists ? selectedValue : '';
}

function applyPlaceTypeFilter() {
  if (!placeTypeFilterInput || !placeTypeSelect) return;
  const selectedValue = placeTypeSelect.value;
  const keyword = placeTypeFilterInput.value.trim().toLowerCase();
  if (!keyword) {
    renderPlaceTypeOptions(placeTypeItems, selectedValue);
    return;
  }

  const filtered = placeTypeItems.filter((item) => {
    const label = String(item.label || '').toLowerCase();
    const value = String(item.value || '').toLowerCase();
    const industry = String(item.industry || '').toLowerCase();
    return label.includes(keyword) || value.includes(keyword) || industry.includes(keyword);
  });
  renderPlaceTypeOptions(filtered, selectedValue);
}

if (placeTypeSelect && importQueryInput) {
  placeTypeSelect.addEventListener('change', () => {
    if (importQueryInput.value.trim()) return;
    const selected = placeTypeSelect.selectedOptions?.[0];
    if (!selected || !selected.value) return;
    const label = selected.dataset.label || selected.textContent?.replace(' ★', '') || '';
    if (label) importQueryInput.value = label;
  });
}

if (placeTypeFilterInput) {
  placeTypeFilterInput.addEventListener('input', applyPlaceTypeFilter);
}

importForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  importResult.textContent = '取得中...';
  const payload = Object.fromEntries(new FormData(importForm).entries());
  payload.max_results = Number(payload.max_results || 20);

  const res = await apiFetch('/api/import/google-places', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    importResult.textContent = `エラー: ${data.detail || '取得に失敗しました'}`;
    addActivity(`取り込み失敗: ${data.detail || 'error'}`, 'system');
    return;
  }

  const selectedTypeLabel = placeTypeSelect?.selectedOptions?.[0]?.textContent || 'すべて';
  importResult.textContent = `取得完了: ${data.imported}件 (業種: ${selectedTypeLabel})`;
  addActivity(`取り込み完了: ${data.imported}件`, 'user');
  await fetchLeads();
});

filterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  await fetchLeads();
  addActivity(`一覧を更新: ${currentItems.length}件`, 'system');
});

myListFilterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  await fetchMyList();
});

historyFilterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  await fetchContactLogs();
});

addToMyListBtn?.addEventListener('click', addSelectedToMyList);
myListUpdateForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  await updateSelectedMyListItems();
});
myListRemoveBtn?.addEventListener('click', removeSelectedMyListItems);
myListSendBtn?.addEventListener('click', sendMailToSelectedMyListItems);

contactForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const lead_ids = getSelectedLeadIds();
  if (!lead_ids.length) {
    contactResult.textContent = '先に企業を選択してください';
    return;
  }

  const formData = new FormData(contactForm);
  const channel = formData.get('channel') || 'email';
  const endpoint = channel === 'form' ? '/api/contact/form' : '/api/contact/email';
  const payload = {
    lead_ids,
    subject: formData.get('subject'),
    body: formData.get('body'),
  };

  const res = await apiFetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    contactResult.textContent = `エラー: ${data.detail || '送信失敗'}`;
    addActivity(`${channel}送信失敗: ${data.detail || 'error'}`, 'system');
    return;
  }

  const via = data.via === 'gmail' ? 'Gmail送信' : data.via === 'dry_run' ? 'ドライラン(未送信)' : 'SMTP送信';
  contactResult.textContent = `送信: ${data.sent}件 スキップ: ${data.skipped}件 制限: ${data.limited}件 [${via}]`;
  addActivity(`${channel}送信: sent=${data.sent}, skipped=${data.skipped}`, 'user');
  await fetchLeads();
  await fetchMyList();
  await fetchContactLogs();
});

tagForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const lead_ids = getSelectedLeadIds();
  if (!lead_ids.length) {
    tagResult.textContent = '先に企業を選択してください';
    return;
  }

  const formData = new FormData(tagForm);
  const payload = {
    lead_ids,
    category: formData.get('category') || '',
    industry: formData.get('industry') || '',
    note: formData.get('note') || '',
  };

  const res = await apiFetch('/api/leads/tags/bulk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    tagResult.textContent = `エラー: ${data.detail || '更新失敗'}`;
    return;
  }

  tagResult.textContent = `更新: ${data.updated}件`;
  addActivity(`手動タグ更新: ${data.updated}件`, 'user');
  await fetchLeads();
  await fetchMyList();
});

suppressionForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(suppressionForm);
  const payload = {
    email: formData.get('email'),
    reason: formData.get('reason') || 'user_request',
  };

  const res = await apiFetch('/api/suppressions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    suppressionResult.textContent = `エラー: ${data.detail || '登録失敗'}`;
    return;
  }

  suppressionResult.textContent = `登録完了: ${data.email}`;
  addActivity(`配信停止を追加: ${data.email}`, 'user');
  suppressionForm.reset();
  await fetchSuppressions();
  await fetchLeads();
  await fetchMyList();
});

adapterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(adapterForm);
  const payload = {
    name: formData.get('name'),
    domain: formData.get('domain'),
    path: formData.get('path'),
    method: 'POST',
    payload_template: {
      name: '{{from_name}}',
      email: '{{from_email}}',
      subject: '{{subject}}',
      message: '{{body}}',
      company: '{{company_name}}',
    },
    enabled: true,
  };

  const res = await apiFetch('/api/form-adapters', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    adapterResult.textContent = `エラー: ${data.detail || '登録失敗'}`;
    return;
  }

  adapterResult.textContent = `更新完了: ${data.domain}`;
  addActivity(`アダプタ更新: ${data.domain}`, 'user');
  adapterForm.reset();
  await fetchAdapters();
});

googleKeyForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(googleKeyForm);
  const payload = { api_key: formData.get('api_key') };
  const res = await apiFetch('/api/settings/google-maps-key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    googleKeyStatus.textContent = `保存エラー: ${data.detail || 'unknown'}`;
    return;
  }

  googleKeyStatus.textContent = 'APIキーを保存しました。';
  addActivity('Google Maps APIキーを更新しました。', 'user');
  googleKeyForm.reset();
  await fetchGoogleKeyStatus();
});

auditRefresh?.addEventListener('click', fetchAuditLogs);

leadSelectAll?.addEventListener('change', (e) => {
  const checked = e.target.checked;
  document.querySelectorAll('.lead-check').forEach((el) => {
    el.checked = checked;
  });
});

myListSelectAll?.addEventListener('change', (e) => {
  const checked = e.target.checked;
  document.querySelectorAll('.my-list-check').forEach((el) => {
    el.checked = checked;
  });
});

loadUserBadge();
addActivity('ワークスペースを初期化しました。左メニューから操作を選択してください。', 'system');
fetchLeads();
fetchMyList();
fetchContactLogs();
fetchGoogleKeyStatus();
fetchPlaceTypes();
