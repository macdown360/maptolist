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
const exportResult = document.querySelector('#export-result');
const contactFormsResult = document.querySelector('#contact-forms-result');

const suppressionList = document.querySelector('#suppression-list');
const adapterList = document.querySelector('#adapter-list');
const auditList = document.querySelector('#audit-list');
const auditRefresh = document.querySelector('#audit-refresh');
const activityFeed = document.querySelector('#activity-feed');

const leadsTbody = document.querySelector('#lead-table tbody');
const leadsThead = document.querySelector('#lead-table thead');
const myListTbody = document.querySelector('#my-list-table tbody');
const historyTbody = document.querySelector('#history-table tbody');
const contactFormsTbody = document.querySelector('#contact-forms-table tbody');

const categorySelect = document.querySelector('select[name="category"]');
const industrySelect = document.querySelector('select[name="industry"]');
const prefectureSelect = document.querySelector('select[name="prefecture"]');
const citySelect = document.querySelector('select[name="city"]');
const placeTypeSelect = document.querySelector('#place-type-select');
const placeTypeFilterInput = document.querySelector('#place-type-filter');
const importQueryInput = document.querySelector('#import-form input[name="query"]');
const myListStatusSelect = document.querySelector('#my-list-filter-form select[name="status"]');
const myListPriorityFilterSelect = document.querySelector('#my-list-filter-form select[name="priority"]');
const historyTimeline = document.querySelector('#history-timeline');
const leadNameSuggestionList = document.querySelector('#lead-name-suggestions');
const historyRangeButtons = document.querySelectorAll('.history-range-btn');
const myListStatusTabs = document.querySelectorAll('.status-tab');
const historySummary = document.querySelector('#history-summary');
const toast = document.querySelector('#toast');

const timelineMessageMap = new Map();

const leadSelectAll = document.querySelector('#select-all');
const exportCsvBtn = document.querySelector('#export-csv-btn');
const exportExcelBtn = document.querySelector('#export-excel-btn');
const discoverContactFormsBtn = document.querySelector('#discover-contact-forms-btn');
const myListSelectAll = document.querySelector('#my-list-select-all');
const addToMyListBtn = document.querySelector('#add-to-my-list');
const myListSendBtn = document.querySelector('#my-list-send-btn');
const myListRemoveBtn = document.querySelector('#my-list-remove-btn');

const myListDefaultStatus = document.querySelector('#my-list-default-status');
const myListDefaultPriority = document.querySelector('#my-list-default-priority');

let currentItems = [];
let myListItems = [];
let placeTypeItems = [];
let leadSortBy = 'updated_at';
let leadSortDir = 'desc';
let leadPreviewSourceItems = [];
let leadFetchController = null;
let leadFetchRequestSeq = 0;
let leadFilterAutoSearchTimerId = null;
const MAPS_KEY_STORAGE_KEY = 'maptolist.google_maps_api_key.v2';
const LEADS_CACHE_STORAGE_KEY = 'maptolist.leads_cache.v2';
const LEADS_FILTER_STORAGE_KEY = 'maptolist.leads_filter.v2';
const CONTACT_FORMS_CACHE_STORAGE_KEY = 'maptolist.contact_forms_cache.v2';
const BROWSER_CLIENT_ID_STORAGE_KEY = 'maptolist.browser_client_id.v1';
const API_BASE_URL = String(window.__API_BASE_URL || '').trim().replace(/\/$/, '');
const IS_GITHUB_PAGES = window.location.hostname.endsWith('github.io');
const IS_PLACEHOLDER_API_BASE_URL = API_BASE_URL === 'https://YOUR-BACKEND-URL';

const STATUS_LABELS = {
  new: '未対応',
  contacted: '連絡済み',
  nurturing: '育成中',
  closed: 'クローズ',
  excluded: '除外',
};

const PRIORITY_LABELS = {
  high: '高',
  medium: '中',
  low: '低',
};

const CHANNEL_LABELS = {
  email: 'メール',
  form: 'フォーム',
};

const LOG_STATUS_LABELS = {
  sent: '送信済み',
  dry_run: 'ドライラン',
  skipped: 'スキップ',
  failed: '失敗',
  suppressed: '配信停止',
  daily_limit: '日次上限',
  no_adapter: 'アダプタなし',
};

const CATEGORY_LABELS = {
  Establishment: '施設・事業所',
};

function toStatusLabel(value) {
  return STATUS_LABELS[value] || value || '';
}

function toPriorityLabel(value) {
  return PRIORITY_LABELS[value] || value || '';
}

function toChannelLabel(value) {
  return CHANNEL_LABELS[value] || value || '';
}

function toLogStatusLabel(value) {
  return LOG_STATUS_LABELS[value] || value || '';
}

function toCategoryLabel(value) {
  return CATEGORY_LABELS[value] || value || '';
}

function getStoredMapsApiKey() {
  try {
    return String(window.localStorage.getItem(MAPS_KEY_STORAGE_KEY) || '').trim();
  } catch {
    return '';
  }
}

function setStoredMapsApiKey(value) {
  try {
    if (value) {
      window.localStorage.setItem(MAPS_KEY_STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(MAPS_KEY_STORAGE_KEY);
    }
  } catch {
    // noop
  }
}

function getScopedStorageKey(key) {
  return `${key}.${getBrowserClientId()}`;
}

function getStoredJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(getScopedStorageKey(key));
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function setStoredJson(key, value) {
  try {
    window.localStorage.setItem(getScopedStorageKey(key), JSON.stringify(value));
  } catch {
    // noop
  }
}

function maskApiKey(key) {
  if (!key) return '';
  return key.length >= 10 ? `${key.slice(0, 6)}...${key.slice(-4)}` : 'configured';
}

function getBrowserClientId() {
  try {
    const existing = String(window.localStorage.getItem(BROWSER_CLIENT_ID_STORAGE_KEY) || '').trim();
    if (existing) return existing;
    const nextId = window.crypto?.randomUUID?.() || `browser-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    window.localStorage.setItem(BROWSER_CLIENT_ID_STORAGE_KEY, nextId);
    return nextId;
  } catch {
    return `browser-${Date.now()}`;
  }
}

async function apiFetch(url, options = {}) {
  if (IS_GITHUB_PAGES && !API_BASE_URL) {
    throw new Error('PAGES_API_BASE_URL が未設定です。GitHub Actions Variables に本番API URLを設定してください。');
  }

  if (IS_PLACEHOLDER_API_BASE_URL) {
    throw new Error('PAGES_API_BASE_URL が未設定です。GitHub Actions Variables に本番API URLを設定してください。');
  }

  let requestUrl = String(url || '');
  if (API_BASE_URL && requestUrl.startsWith('/')) {
    requestUrl = `${API_BASE_URL}${requestUrl}`;
  }

  const requestHeaders = new Headers(options.headers || {});
  requestHeaders.set('X-Browser-Client-Id', getBrowserClientId());

  const requestOptions = {
    credentials: API_BASE_URL ? 'include' : 'same-origin',
    ...options,
    headers: requestHeaders,
  };

  let res;
  try {
    res = await fetch(requestUrl, requestOptions);
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    throw new Error(`API接続に失敗しました: ${reason}`);
  }

  if (res.status === 401) {
    window.location.href = API_BASE_URL ? `${API_BASE_URL}/` : '/';
    return null;
  }
  return res;
}

async function loadUserBadge() {
  return undefined;
}

function addActivity(text, who = 'system') {
  if (!activityFeed) return;
  const el = document.createElement('div');
  el.className = `chat-item ${who}`;
  el.textContent = `[${new Date().toLocaleTimeString('ja-JP')}] ${text}`;
  activityFeed.prepend(el);
}

function showToast(message, kind = 'info') {
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast show ${kind}`;
  window.clearTimeout(showToast.timerId);
  showToast.timerId = window.setTimeout(() => {
    toast.className = 'toast';
  }, 2200);
}

function setBusyStatusWithCat(target, message) {
  if (!target) return;
  target.innerHTML = `
    <span class="status-with-cat">
      <span>${escapeHtml(message)}</span>
      <span class="loading-cat" aria-hidden="true">
        <span class="loading-cat-body"></span>
        <span class="loading-cat-ear loading-cat-ear-left"></span>
        <span class="loading-cat-ear loading-cat-ear-right"></span>
        <span class="loading-cat-tail"></span>
      </span>
    </span>
  `;
}

function switchView(viewName) {
  document.querySelectorAll('.menu-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.view === viewName);
  });
  document.querySelectorAll('.view').forEach((el) => {
    el.classList.toggle('active', el.id === `view-${viewName}`);
  });

  if (viewName === 'suppression') fetchSuppressions();
  if (viewName === 'adapters') fetchAdapters();
  if (viewName === 'audit') fetchAuditLogs();
  if (viewName === 'my-list') fetchMyList();
  if (viewName === 'history') fetchContactLogs();
  if (viewName === 'contact-forms') fetchContactForms();
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

function renderOptions(select, items, selected, labelFormatter = (v) => v) {
  if (!select) return;
  const values = Array.from(new Set((items || []).filter((v) => String(v || '').trim() !== '')));
  const selectedValue = String(selected || '').trim();
  if (selectedValue && !values.includes(selectedValue)) {
    values.unshift(selectedValue);
  }

  const base = '<option value="">すべて</option>';
  const options = values
    .map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(labelFormatter(v))}</option>`)
    .join('');
  select.innerHTML = base + options;
  select.value = selectedValue;
}

function getNormalizedLeadFilters() {
  if (!filterForm) {
    return {
      q: '',
      prefecture: '',
      city: '',
      category: '',
      industry: '',
    };
  }

  const formData = new FormData(filterForm);
  return {
    q: String(formData.get('q') || '').trim(),
    prefecture: String(formData.get('prefecture') || '').trim(),
    city: String(formData.get('city') || '').trim(),
    category: String(formData.get('category') || '').trim(),
    industry: String(formData.get('industry') || '').trim(),
  };
}

function mergeLeadItems(existingItems = [], incomingItems = []) {
  const merged = new Map();
  for (const item of existingItems || []) {
    const key = String(item.place_id || item.id || '');
    if (key) merged.set(key, item);
  }
  for (const item of incomingItems || []) {
    const key = String(item.place_id || item.id || '');
    if (!key) continue;
    merged.set(key, { ...(merged.get(key) || {}), ...item });
  }
  return Array.from(merged.values());
}

function mergeContactFormItems(existingItems = [], incomingItems = []) {
  const merged = new Map();
  for (const item of existingItems || []) {
    const key = String(item.lead_id || item.form_url || item.website || '');
    if (key) merged.set(key, item);
  }
  for (const item of incomingItems || []) {
    const key = String(item.lead_id || item.form_url || item.website || '');
    if (!key) continue;
    merged.set(key, { ...(merged.get(key) || {}), ...item });
  }
  return Array.from(merged.values()).sort((a, b) => String(b.checked_at || '').localeCompare(String(a.checked_at || '')));
}

function persistLeadListState(items = currentItems) {
  const safeItems = Array.isArray(items) ? items : [];
  setStoredJson(LEADS_CACHE_STORAGE_KEY, {
    items: safeItems,
    sortBy: leadSortBy,
    sortDir: leadSortDir,
    savedAt: new Date().toISOString(),
  });

  if (!filterForm) return;
  const normalizedFilters = getNormalizedLeadFilters();
  setStoredJson(LEADS_FILTER_STORAGE_KEY, {
    q: normalizedFilters.q,
    prefecture: normalizedFilters.prefecture,
    city: normalizedFilters.city,
    category: normalizedFilters.category,
    industry: normalizedFilters.industry,
    sortBy: leadSortBy,
    sortDir: leadSortDir,
  });
}

function getStoredContactFormItems() {
  const cached = getStoredJson(CONTACT_FORMS_CACHE_STORAGE_KEY, {});
  return Array.isArray(cached.items) ? cached.items : [];
}

function persistContactFormsState(items = []) {
  const safeItems = Array.isArray(items) ? items : [];
  setStoredJson(CONTACT_FORMS_CACHE_STORAGE_KEY, {
    items: safeItems,
    savedAt: new Date().toISOString(),
  });
}

function hydrateLeadListState() {
  if (filterForm) {
    const filters = getStoredJson(LEADS_FILTER_STORAGE_KEY, {});
    const qInput = filterForm.querySelector('input[name="q"]');
    const prefectureInput = filterForm.querySelector('select[name="prefecture"]');
    const cityInput = filterForm.querySelector('select[name="city"]');
    const categoryInput = filterForm.querySelector('select[name="category"]');
    const industryInput = filterForm.querySelector('select[name="industry"]');

    if (qInput && typeof filters.q === 'string') qInput.value = filters.q;
    if (prefectureInput && typeof filters.prefecture === 'string') prefectureInput.value = filters.prefecture;
    if (cityInput && typeof filters.city === 'string') cityInput.value = filters.city;
    if (categoryInput && typeof filters.category === 'string') categoryInput.value = filters.category;
    if (industryInput && typeof filters.industry === 'string') industryInput.value = filters.industry;
    if (typeof filters.sortBy === 'string' && filters.sortBy) leadSortBy = filters.sortBy;
    if (typeof filters.sortDir === 'string' && filters.sortDir) leadSortDir = filters.sortDir;
  }

  const cached = getStoredJson(LEADS_CACHE_STORAGE_KEY, {});
  const cachedItems = Array.isArray(cached.items) ? cached.items : [];
  if (!cachedItems.length) return;

  currentItems = sortLeadItemsClientSide(cachedItems, leadSortBy, leadSortDir);
  renderLeadsTable(currentItems);
  updateLeadSortIndicators();
}

function cleanAddressValue(value) {
  return String(value || '')
    .replace(/^日本[、\s]*/u, '')
    .replace(/^Japan[،,\s]*/iu, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function formatLeadAddress(item) {
  if (item && (item.postal_code || item.prefecture || item.city || item.address_detail)) {
    const postal = item.postal_code ? `〒${String(item.postal_code).trim()} ` : '';
    const prefecture = String(item.prefecture || '').trim();
    const city = String(item.city || '').trim();
    const detail = String(item.address_detail || '').trim();
    const combined = `${postal}${prefecture}${city}${detail}`.trim();
    if (combined) return combined;
  }

  return cleanAddressValue(item?.address || '');
}

function renderLeadsTable(items) {
  if (!Array.isArray(items) || !items.length) {
    leadsTbody.innerHTML = `
      <tr>
        <td colspan="12" class="muted">該当する取得結果はありません。業種・業界の条件を見直してください。</td>
      </tr>
    `;
    return;
  }

  leadsTbody.innerHTML = items
    .map(
      (item) => `
      <tr>
        <td><input type="checkbox" class="lead-check" value="${item.id}" /></td>
        <td>${escapeHtml(formatLeadAddress(item))}</td>
        <td>${escapeHtml(item.prefecture || '')}</td>
        <td>${escapeHtml(item.city || '')}</td>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(toCategoryLabel(item.effective_category || item.category))}</td>
        <td>${escapeHtml(item.effective_industry || item.industry)}</td>
        <td>${item.rating ?? ''}</td>
        <td>${item.user_ratings_total ?? ''}</td>
        <td>${item.website ? `<a href="${escapeHtml(item.website)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.website)}</a>` : ''}</td>
        <td>${escapeHtml(item.phone)}</td>
      </tr>
    `,
    )
    .join('');
}

function updateLeadSortIndicators() {
  if (!leadsThead) return;

  leadsThead.querySelectorAll('th.sortable').forEach((th) => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    const thSort = String(th.dataset.sort || '');
    if (thSort && thSort === leadSortBy) {
      th.classList.add(leadSortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
    }
  });
}

function compareNullable(a, b, direction) {
  const dir = direction === 'asc' ? 1 : -1;
  const av = a ?? '';
  const bv = b ?? '';

  if (typeof av === 'number' || typeof bv === 'number') {
    const an = Number(av || 0);
    const bn = Number(bv || 0);
    if (an === bn) return 0;
    return an > bn ? dir : -dir;
  }

  const as = String(av).toLowerCase();
  const bs = String(bv).toLowerCase();
  if (as === bs) return 0;
  return as > bs ? dir : -dir;
}

function sortLeadItemsClientSide(items, sortBy, sortDir) {
  const keyMap = {
    updated_at: ['updated_at'],
    address: ['address', 'prefecture', 'city', 'address_detail', 'name'],
    prefecture: ['prefecture', 'city', 'address_detail', 'name'],
    city: ['city', 'prefecture', 'address_detail', 'name'],
    name: ['name'],
    category: ['effective_category', 'name'],
    industry: ['effective_industry', 'name'],
    rating: ['rating', 'user_ratings_total', 'name'],
    user_ratings_total: ['user_ratings_total', 'rating', 'name'],
  };

  const keys = keyMap[sortBy];
  if (!keys) return items;

  return [...items].sort((a, b) => {
    for (const key of keys) {
      const primary = compareNullable(a[key], b[key], sortDir);
      if (primary !== 0) return primary;
    }
    return compareNullable(a.updated_at, b.updated_at, 'desc');
  });
}

function applyLeadFiltersClientSide(items, filters = {}) {
  const q = String(filters.q || '').trim().toLowerCase();
  const prefecture = String(filters.prefecture || '').trim();
  const city = String(filters.city || '').trim();
  const category = String(filters.category || '').trim();
  const industry = String(filters.industry || '').trim();

  return (Array.isArray(items) ? items : []).filter((item) => {
    const effectivePrefecture = String(item?.prefecture || '').trim();
    const effectiveCity = String(item?.city || '').trim();
    const effectiveCategory = String(item?.effective_category || item?.category || '').trim();
    const effectiveIndustry = String(item?.effective_industry || item?.industry || '').trim();

    if (prefecture && effectivePrefecture !== prefecture) return false;
    if (city && effectiveCity !== city) return false;
    if (category && effectiveCategory !== category) return false;
    if (industry && effectiveIndustry !== industry) return false;

    if (!q) return true;

    const haystack = [
      item?.name,
      item?.address,
      item?.website,
      item?.prefecture,
      item?.city,
      item?.address_detail,
    ]
      .map((v) => String(v || '').toLowerCase())
      .join(' ');
    return haystack.includes(q);
  });
}

function renderLeadPreviewFromLocal() {
  const normalizedFilters = getNormalizedLeadFilters();
  const baseItems = leadPreviewSourceItems.length ? leadPreviewSourceItems : currentItems;
  const previewItems = sortLeadItemsClientSide(applyLeadFiltersClientSide(baseItems, normalizedFilters), leadSortBy, leadSortDir);

  currentItems = previewItems;
  renderLeadsTable(currentItems);
  updateLeadSortIndicators();
  persistLeadListState(currentItems);

  if (exportResult) {
    exportResult.textContent = `${currentItems.length}件表示中`;
  }
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
        <td><span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(toStatusLabel(item.status))}</span></td>
        <td><span class="priority-badge priority-${escapeHtml(item.priority)}">${escapeHtml(toPriorityLabel(item.priority))}</span></td>
        <td>${escapeHtml(item.last_contacted_at || '')}</td>
        <td>${Number(item.contact_count || 0)}</td>
        <td>${escapeHtml(item.address)}</td>
      </tr>
    `,
    )
    .join('');
}

function renderHistoryTable(items) {
  const keyword = String(historyFilterForm?.querySelector('input[name="q"]')?.value || '').trim();
  historyTbody.innerHTML = items
    .map(
      (item) => `
      <tr>
        <td>${escapeHtml(item.created_at)}</td>
        <td>${highlightText(item.lead_name, keyword)}</td>
        <td>${escapeHtml(item.lead_email || '')}</td>
        <td>${escapeHtml(toChannelLabel(item.channel))}</td>
        <td>${escapeHtml(toLogStatusLabel(item.status))}</td>
        <td>${highlightText(item.subject || '', keyword)}</td>
        <td>${highlightText((item.message || '').slice(0, 120), keyword)}</td>
        <td><button type="button" class="ghost show-timeline-btn" data-lead-id="${item.lead_id}" data-lead-name="${escapeHtml(item.lead_name)}">詳細</button></td>
      </tr>
    `,
    )
    .join('');
}

function highlightText(text, keyword) {
  const source = String(text || '');
  const key = String(keyword || '').trim();
  if (!key) return escapeHtml(source);

  const escapedKeyword = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`(${escapedKeyword})`, 'ig');
  const parts = source.split(re);
  return parts
    .map((part) => {
      if (!part) return '';
      if (part.toLowerCase() === key.toLowerCase()) {
        return `<mark>${escapeHtml(part)}</mark>`;
      }
      return escapeHtml(part);
    })
    .join('');
}

function renderTimeline(leadName, items) {
  if (!historyTimeline) return;
  const keyword = String(historyFilterForm?.querySelector('input[name="q"]')?.value || '').trim();
  timelineMessageMap.clear();
  if (!items.length) {
    historyTimeline.innerHTML = `<div class="row">${escapeHtml(leadName)} の履歴はありません。</div>`;
    return;
  }
  historyTimeline.innerHTML = items
    .map(
      (x) => {
        timelineMessageMap.set(String(x.id), String(x.message || ''));
        return `<div class="row timeline-row">
          <div>${escapeHtml(x.created_at)} | ${escapeHtml(toChannelLabel(x.channel))} | ${escapeHtml(toLogStatusLabel(x.status))} | ${highlightText(x.subject || '', keyword)}</div>
          <details class="timeline-message">
            <summary>本文を表示</summary>
            <pre>${highlightText(x.message || '', keyword)}</pre>
            <button type="button" class="ghost copy-message-btn" data-log-id="${x.id}">本文をコピー</button>
          </details>
        </div>`;
      },
    )
    .join('');
}

function renderHistorySummary(items) {
  if (!historySummary) return;
  const total = items.length;
  const statusCounts = {};
  const channelCounts = {};
  for (const item of items) {
    const key = String(item.status || 'unknown');
    statusCounts[key] = (statusCounts[key] || 0) + 1;
    const channel = String(item.channel || 'unknown');
    channelCounts[channel] = (channelCounts[channel] || 0) + 1;
  }

  const statusBadges = Object.entries(statusCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([status, count]) => `<span class="summary-badge">${escapeHtml(toLogStatusLabel(status))}: ${count}</span>`)
    .join('');

  const channelBadges = Object.entries(channelCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([channel, count]) => `<span class="summary-badge channel">${escapeHtml(toChannelLabel(channel))}: ${count}</span>`)
    .join('');

  historySummary.innerHTML = `<span class="summary-total">合計 ${total} 件</span>${statusBadges}${channelBadges}`;
}

function persistMyListFilterToUrl(formParams) {
  const url = new URL(window.location.href);
  const mapping = {
    q: 'ml_q',
    status: 'ml_status',
    priority: 'ml_priority',
    sort_by: 'ml_sort_by',
    sort_dir: 'ml_sort_dir',
  };

  Object.entries(mapping).forEach(([formKey, queryKey]) => {
    const value = String(formParams.get(formKey) || '').trim();
    if (value) {
      url.searchParams.set(queryKey, value);
    } else {
      url.searchParams.delete(queryKey);
    }
  });

  const query = url.searchParams.toString();
  const nextUrl = query ? `${url.pathname}?${query}` : url.pathname;
  window.history.replaceState({}, '', nextUrl);
}

function hydrateMyListFilterFromUrl() {
  if (!myListFilterForm) return;
  const params = new URLSearchParams(window.location.search);
  const mapping = {
    ml_q: 'q',
    ml_status: 'status',
    ml_priority: 'priority',
    ml_sort_by: 'sort_by',
    ml_sort_dir: 'sort_dir',
  };

  Object.entries(mapping).forEach(([queryKey, formKey]) => {
    const value = params.get(queryKey);
    if (value === null) return;
    const field = myListFilterForm.querySelector(`[name="${formKey}"]`);
    if (field) {
      field.value = value;
    }
  });
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

function formatDateInput(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

async function applyHistoryRange(range) {
  const fromInput = historyFilterForm?.querySelector('input[name="from_date"]');
  const toInput = historyFilterForm?.querySelector('input[name="to_date"]');
  if (!fromInput || !toInput) return;

  const today = new Date();
  const to = formatDateInput(today);

  if (range === 'today') {
    fromInput.value = to;
    toInput.value = to;
  } else if (range === '7d' || range === '30d') {
    const days = range === '7d' ? 6 : 29;
    const from = new Date(today);
    from.setDate(today.getDate() - days);
    fromInput.value = formatDateInput(from);
    toInput.value = to;
  } else {
    fromInput.value = '';
    toInput.value = '';
  }

  await fetchContactLogs();
}

function formatDateOnly(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  const datePart = text.includes('T') ? text.split('T')[0] : text;
  return datePart.replaceAll('-', '/');
}

function shortenText(value, maxLength = 48) {
  const text = String(value || '').trim();
  if (!text || text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}…`;
}

function formatUrlLabel(value) {
  const url = String(value || '').trim();
  if (!url) return '';
  try {
    const parsed = new URL(url);
    const combined = `${parsed.hostname}${parsed.pathname === '/' ? '' : parsed.pathname}`;
    return shortenText(combined, 52);
  } catch {
    return shortenText(url, 52);
  }
}

function isValidEmailValue(value) {
  const text = String(value || '').trim();
  if (!text) return false;
  return /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(text);
}

function looksLikeIsoDateValue(value) {
  const text = String(value || '').trim();
  if (!text) return false;
  return /^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$/.test(text);
}

function normalizeContactDiscoveryItem(item) {
  const src = item || {};
  const emailRaw = String(src.email || '').trim();
  const checkedAtRaw = String(src.checked_at || '').trim();

  if (isValidEmailValue(emailRaw)) {
    return {
      ...src,
      email: emailRaw,
      checked_at: checkedAtRaw,
    };
  }

  const fallbackCheckedAt = !checkedAtRaw && looksLikeIsoDateValue(emailRaw) ? emailRaw : checkedAtRaw;
  return {
    ...src,
    email: '',
    checked_at: fallbackCheckedAt,
  };
}

function hydrateContactFormsState() {
  const items = getStoredContactFormItems();
  if (!items.length) return;
  renderContactFormsTable(items);
  if (contactFormsResult) {
    contactFormsResult.textContent = `${items.length}件の問い合わせフォーム・メールアドレス情報を保持中`;
  }
}

function renderContactFormsTable(items) {
  if (!contactFormsTbody) return;
  if (!Array.isArray(items) || !items.length) {
    contactFormsTbody.innerHTML = `
      <tr>
        <td colspan="5" class="muted">まだ問い合わせフォームURL・メールアドレスはありません。取得結果一覧で企業を選択して探索してください。</td>
      </tr>
    `;
    return;
  }

  const normalizedItems = items.map(normalizeContactDiscoveryItem);

  contactFormsTbody.innerHTML = normalizedItems
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.lead_name || '名称未設定')}</td>
          <td>
            ${item.website ? `<a class="table-link" href="${escapeHtml(item.website)}" target="_blank" rel="noopener noreferrer">公式サイトを開く</a><div class="mini-url">${escapeHtml(formatUrlLabel(item.website))}</div>` : '<span class="muted">-</span>'}
          </td>
          <td>
            ${item.form_url ? `<a class="table-link form-link open-form-link" href="${escapeHtml(item.form_url)}" data-form-url="${escapeHtml(item.form_url)}" data-lead-name="${escapeHtml(item.lead_name || '')}" data-website="${escapeHtml(item.website || '')}" target="_blank" rel="noopener noreferrer">フォームを開く</a><div class="mini-url">${escapeHtml(formatUrlLabel(item.form_url))}</div>` : '<span class="muted">-</span>'}
          </td>
          <td>
            ${item.email ? `<a class="table-link" href="mailto:${escapeHtml(item.email)}">${escapeHtml(item.email)}</a>` : '<span class="muted">-</span>'}
          </td>
          <td class="date-cell">${escapeHtml(formatDateOnly(item.checked_at || ''))}</td>
        </tr>
      `,
    )
    .join('');
}

function getSelectedLeadIds() {
  return Array.from(document.querySelectorAll('.lead-check:checked'))
    .map((el) => Number(el.value))
    .filter((n) => Number.isInteger(n) && n > 0);
}

function getSelectedLeadItems() {
  const selected = new Set(getSelectedLeadIds());
  if (!selected.size) return [];
  return currentItems.filter((item) => selected.has(Number(item.id)));
}

function exportRowsFromLeadItems(items) {
  return items.map((item) => ({
    id: item.id,
    name: item.name || '',
    address: formatLeadAddress(item),
    prefecture: item.prefecture || '',
    city: item.city || '',
    category: toCategoryLabel(item.effective_category || item.category || ''),
    industry: item.effective_industry || item.industry || '',
    rating: item.rating ?? '',
    user_ratings_total: item.user_ratings_total ?? '',
    website: item.website || '',
    phone: item.phone || '',
    email: item.email || '',
    updated_at: item.updated_at || '',
  }));
}

function downloadTextAsFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function escapeCsvCell(value) {
  const str = String(value ?? '');
  if (/[",\r\n]/.test(str)) {
    return `"${str.replaceAll('"', '""')}"`;
  }
  return str;
}

function exportSelectedLeadsAsCsv() {
  const selectedItems = getSelectedLeadItems();
  if (!selectedItems.length) {
    const msg = '出力対象の企業をチェックしてください';
    if (exportResult) exportResult.textContent = msg;
    showToast(msg, 'error');
    return;
  }

  const rows = exportRowsFromLeadItems(selectedItems);
  const headers = ['ID', '企業・団体名', '住所', '都道府県', '市区町村', '業種', '業界', '評価', '評価件数', 'Web', '電話', 'メール', '更新日時'];
  const lines = [headers.join(',')];
  for (const row of rows) {
    lines.push([
      row.id,
      row.name,
      row.address,
      row.prefecture,
      row.city,
      row.category,
      row.industry,
      row.rating,
      row.user_ratings_total,
      row.website,
      row.phone,
      row.email,
      row.updated_at,
    ].map(escapeCsvCell).join(','));
  }

  const csvContent = `\ufeff${lines.join('\r\n')}`;
  downloadTextAsFile(csvContent, `map-to-list-leads-${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv;charset=utf-8;');

  const msg = `${rows.length}件をCSV出力しました`;
  if (exportResult) exportResult.textContent = msg;
  addActivity(msg, 'user');
  showToast('CSVをダウンロードしました', 'success');
}

function exportSelectedLeadsAsExcel() {
  const selectedItems = getSelectedLeadItems();
  if (!selectedItems.length) {
    const msg = '出力対象の企業をチェックしてください';
    if (exportResult) exportResult.textContent = msg;
    showToast(msg, 'error');
    return;
  }

  if (!window.XLSX) {
    const msg = 'Excel出力ライブラリの読み込みに失敗しました。ページを再読み込みしてください';
    if (exportResult) exportResult.textContent = msg;
    showToast(msg, 'error');
    return;
  }

  const rows = exportRowsFromLeadItems(selectedItems);
  const excelRows = rows.map((row) => ({
    ID: row.id,
    '企業・団体名': row.name,
    '住所': row.address,
    '都道府県': row.prefecture,
    '市区町村': row.city,
    '業種': row.category,
    '業界': row.industry,
    '評価': row.rating,
    '評価件数': row.user_ratings_total,
    'Web': row.website,
    '電話': row.phone,
    'メール': row.email,
    '更新日時': row.updated_at,
  }));

  const worksheet = window.XLSX.utils.json_to_sheet(excelRows);
  worksheet['!cols'] = [
    { wch: 10 },
    { wch: 28 },
    { wch: 36 },
    { wch: 12 },
    { wch: 16 },
    { wch: 14 },
    { wch: 18 },
    { wch: 8 },
    { wch: 10 },
    { wch: 28 },
    { wch: 18 },
    { wch: 28 },
    { wch: 20 },
  ];

  const workbook = window.XLSX.utils.book_new();
  window.XLSX.utils.book_append_sheet(workbook, worksheet, 'Leads');
  window.XLSX.writeFile(workbook, `map-to-list-leads-${new Date().toISOString().slice(0, 10)}.xlsx`, {
    compression: true,
  });

  const msg = `${rows.length}件をExcel出力しました`;
  if (exportResult) exportResult.textContent = msg;
  addActivity(msg, 'user');
  showToast('Excelをダウンロードしました', 'success');
}

function getSelectedMyListItemIds() {
  return Array.from(document.querySelectorAll('.my-list-check:checked')).map((el) => Number(el.value));
}

function getSelectedMyListLeadIds() {
  return Array.from(document.querySelectorAll('.my-list-check:checked')).map((el) => Number(el.dataset.leadId));
}

async function fetchLeads() {
  if (!filterForm) return;

  if (leadFetchController) {
    leadFetchController.abort();
  }
  const controller = new AbortController();
  leadFetchController = controller;
  const requestSeq = ++leadFetchRequestSeq;

  const normalizedFilters = getNormalizedLeadFilters();
  const params = new URLSearchParams();
  if (normalizedFilters.q) params.set('q', normalizedFilters.q);
  if (normalizedFilters.prefecture) params.set('prefecture', normalizedFilters.prefecture);
  if (normalizedFilters.city) params.set('city', normalizedFilters.city);
  if (normalizedFilters.category) params.set('category', normalizedFilters.category);
  if (normalizedFilters.industry) params.set('industry', normalizedFilters.industry);
  params.set('sort_by', leadSortBy);
  params.set('sort_dir', leadSortDir);

  let res;
  let data;
  try {
    res = await apiFetch(`/api/leads?${params.toString()}`, { signal: controller.signal });
    if (!res) return;
    data = await res.json();
  } catch (err) {
    const errName = err instanceof Error ? err.name : '';
    if (errName === 'AbortError') {
      return;
    }

    const fallback = getStoredJson(LEADS_CACHE_STORAGE_KEY, {});
    const cachedItems = Array.isArray(fallback.items) ? fallback.items : [];
    if (cachedItems.length) {
      currentItems = sortLeadItemsClientSide(cachedItems, leadSortBy, leadSortDir);
      renderLeadsTable(currentItems);
      updateLeadSortIndicators();
      addActivity('通信エラーのため前回取得した一覧を表示しています', 'system');
      showToast('前回取得した一覧を表示しています', 'info');
      return;
    }
    throw err;
  } finally {
    if (leadFetchController === controller) {
      leadFetchController = null;
    }
  }

  if (!res.ok) {
    addActivity(`一覧取得エラー: ${data.detail || 'unknown'}`, 'system');
    return;
  }

  if (requestSeq !== leadFetchRequestSeq) {
    return;
  }

  const serverItems = Array.isArray(data.items) ? data.items : [];
  if (!normalizedFilters.q && !normalizedFilters.prefecture && !normalizedFilters.city && !normalizedFilters.category && !normalizedFilters.industry) {
    leadPreviewSourceItems = serverItems;
  } else if (!leadPreviewSourceItems.length) {
    leadPreviewSourceItems = serverItems;
  }

  currentItems = sortLeadItemsClientSide(serverItems, leadSortBy, leadSortDir);
  if (data.sort) {
    leadSortBy = data.sort.sort_by || leadSortBy;
    leadSortDir = data.sort.sort_dir || leadSortDir;
    currentItems = sortLeadItemsClientSide(currentItems, leadSortBy, leadSortDir);
  }

  const selectedPrefecture = String(filterForm.querySelector('select[name="prefecture"]')?.value || '');
  const selectedCity = String(filterForm.querySelector('select[name="city"]')?.value || '');
  const selectedCategory = String(filterForm.querySelector('select[name="category"]')?.value || '');
  const selectedIndustry = String(filterForm.querySelector('select[name="industry"]')?.value || '');

  console.log('[DEBUG] filters from API:', JSON.stringify(data.filters));
  renderLeadsTable(currentItems);
  renderOptions(prefectureSelect, data.filters.prefectures || [], selectedPrefecture);
  renderOptions(citySelect, data.filters.cities || [], selectedCity);
  renderOptions(categorySelect, data.filters.categories || [], selectedCategory, toCategoryLabel);
  renderOptions(industrySelect, data.filters.industries || [], selectedIndustry);
  updateLeadSortIndicators();
  persistLeadListState(currentItems);

  if (exportResult) {
    exportResult.textContent = `${currentItems.length}件表示中`;
  }

  if (limitResult) {
    limitResult.textContent = `本日上限 ${data.send_limit.daily_limit}件 / email残 ${data.send_limit.email_remaining} / form残 ${data.send_limit.form_remaining}`;
  }

}

function scheduleLeadFilterAutoSearch(sourceLabel) {
  renderLeadPreviewFromLocal();

  if (leadFilterAutoSearchTimerId) {
    window.clearTimeout(leadFilterAutoSearchTimerId);
  }

  leadFilterAutoSearchTimerId = window.setTimeout(async () => {
    await fetchLeads();
    addActivity(`${sourceLabel}で再検索: ${currentItems.length}件`, 'system');
  }, 120);
}

async function fetchMyList() {
  if (!myListFilterForm) return;
  const params = new URLSearchParams(new FormData(myListFilterForm));
  persistMyListFilterToUrl(params);
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
  renderOptions(myListPriorityFilterSelect, data.filters.priorities || [], myListFilterForm.priority.value);
  myListResult.textContent = `${myListItems.length}件`;

  const selectedStatus = String(myListFilterForm.status.value || '');
  myListStatusTabs.forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.status === selectedStatus);
  });
}

async function fetchLeadNameSuggestions() {
  const res = await apiFetch('/api/leads/names?limit=500');
  if (!res) return;
  const data = await res.json();
  if (!res.ok || !leadNameSuggestionList) return;
  leadNameSuggestionList.innerHTML = (data.items || [])
    .map((name) => `<option value="${escapeHtml(name)}"></option>`)
    .join('');
}

async function fetchContactLogs() {
  if (!historyFilterForm) return;
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
  renderHistorySummary(items);
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
    const detail = data.detail;
    const errMsg = Array.isArray(detail)
      ? detail.map((e) => (e && e.msg ? `${e.loc ? e.loc.join('.') + ': ' : ''}${e.msg}` : JSON.stringify(e))).join(' / ')
      : (detail || '追加失敗');
    myListAddResult.textContent = `エラー: ${errMsg}`;
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

async function fetchContactForms() {
  if (!contactFormsTbody) return;

  let res;
  let data;
  try {
    res = await apiFetch('/api/contact-forms');
    if (!res) return;
    data = await res.json();
  } catch (_err) {
    const cachedItems = getStoredContactFormItems();
    if (cachedItems.length) {
      renderContactFormsTable(cachedItems);
      if (contactFormsResult) contactFormsResult.textContent = `${cachedItems.length}件の問い合わせフォーム・メールアドレス情報を保持中`;
      return;
    }
    if (contactFormsResult) contactFormsResult.textContent = '問い合わせフォーム・メールアドレス情報を取得できませんでした';
    return;
  }

  if (!res.ok) {
    const cachedItems = getStoredContactFormItems();
    if (cachedItems.length) {
      renderContactFormsTable(cachedItems);
      if (contactFormsResult) contactFormsResult.textContent = `${cachedItems.length}件の問い合わせフォーム・メールアドレス情報を保持中`;
      return;
    }
    if (contactFormsResult) contactFormsResult.textContent = `エラー: ${data.detail || '取得失敗'}`;
    return;
  }

  const serverItems = Array.isArray(data.items) ? data.items : [];
  const items = mergeContactFormItems([], serverItems).map(normalizeContactDiscoveryItem);
  renderContactFormsTable(items);
  persistContactFormsState(items);
  if (contactFormsResult) contactFormsResult.textContent = `${items.length}件の問い合わせフォーム・メールアドレス情報を表示中`;
}

async function discoverSelectedContactForms() {
  const lead_ids = getSelectedLeadIds();
  if (!lead_ids.length) {
    const msg = '先に企業を選択してください';
    if (exportResult) exportResult.textContent = msg;
    showToast(msg, 'error');
    return;
  }

  setBusyStatusWithCat(exportResult, '問い合わせフォーム・メールアドレスを探索中...');

  const res = await apiFetch('/api/contact-forms/discover', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lead_ids }),
  });
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    if (exportResult) exportResult.textContent = `エラー: ${data.detail || '探索失敗'}`;
    showToast('問い合わせフォーム・メールアドレス探索に失敗しました', 'error');
    return;
  }

  const foundItems = Array.isArray(data.items) ? data.items : [];
  const mergedItems = mergeContactFormItems(getStoredContactFormItems(), foundItems).map(normalizeContactDiscoveryItem);
  persistContactFormsState(mergedItems);

  const msg = `探索完了: ${data.found}件 / 対象${data.checked}件`;
  if (exportResult) exportResult.textContent = msg;
  addActivity(`問い合わせフォーム・メールアドレス探索: ${data.found}件見つかりました`, 'user');
  showToast(data.found ? '問い合わせフォーム・メールアドレス情報を取得しました' : '問い合わせフォーム・メールアドレス情報は見つかりませんでした', data.found ? 'success' : 'info');
  switchView('contact-forms');
  await fetchContactForms();
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
  const key = getStoredMapsApiKey();
  if (!key) {
    googleKeyStatus.textContent = '未設定です。このブラウザにAPIキーを保存してください。';
    return;
  }
  googleKeyStatus.textContent = `設定済み(ブラウザ保存): ${maskApiKey(key)}`;
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

  const maxResultsRaw = importForm.querySelector('input[name="max_results"]')?.value ?? '';
  const maxResultsNum = Number(maxResultsRaw);
  if (maxResultsRaw.trim() === '' || !Number.isInteger(maxResultsNum) || isNaN(maxResultsNum)) {
    importResult.textContent = 'エラー: 取得件数には数値を入力してください。';
    return;
  }
  if (maxResultsNum < 1 || maxResultsNum > 50) {
    importResult.textContent = 'エラー: 取得件数は1〜50の範囲で入力してください。';
    return;
  }

  setBusyStatusWithCat(importResult, '取得中...');
  const payload = Object.fromEntries(new FormData(importForm).entries());
  payload.max_results = maxResultsNum;

  let res;
  try {
    res = await apiFetch('/api/import/google-places', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    importResult.textContent = `エラー: ${err instanceof Error ? err.message : String(err)}`;
    return;
  }
  if (!res) return;
  const data = await res.json();

  if (!res.ok) {
    importResult.textContent = `エラー: ${data.detail || '取得に失敗しました'}`;
    addActivity(`取り込み失敗: ${data.detail || 'error'}`, 'system');
    return;
  }

  const selectedTypeLabel = placeTypeSelect?.selectedOptions?.[0]?.textContent || 'すべて';
  importResult.textContent = `取得完了: ${data.imported}件 / 新規追加: ${data.added || 0}件 / 更新: ${data.updated || 0}件 (業種: ${selectedTypeLabel})`;
  addActivity(`取り込み完了: 新規${data.added || 0}件 / 更新${data.updated || 0}件`, 'user');

  const incomingItems = Array.isArray(data.items) ? data.items : [];
  if (incomingItems.length) {
    currentItems = sortLeadItemsClientSide(mergeLeadItems(currentItems, incomingItems), leadSortBy, leadSortDir);
    renderLeadsTable(currentItems);
    persistLeadListState(currentItems);
  }

  if (filterForm) {
    filterForm.reset();
  }
  leadSortBy = 'updated_at';
  leadSortDir = 'desc';
  switchView('leads');
  await fetchLeads();
  showToast('前回結果を残したまま一覧へ追加しました', 'success');
});

filterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  await fetchLeads();
  addActivity(`一覧を更新: ${currentItems.length}件`, 'system');
});

prefectureSelect?.addEventListener('change', async () => {
  scheduleLeadFilterAutoSearch('都道府県');
});

citySelect?.addEventListener('change', async () => {
  scheduleLeadFilterAutoSearch('市区町村');
});

categorySelect?.addEventListener('change', async () => {
  scheduleLeadFilterAutoSearch('業種');
});

industrySelect?.addEventListener('change', async () => {
  scheduleLeadFilterAutoSearch('業界');
});

if (filterForm) {
  // ソートは列ヘッダクリックでのみ操作する。
}

leadsThead?.addEventListener('click', (e) => {
  const target = e.target;
  if (!(target instanceof Element)) return;

  const th = target.closest('th.sortable');
  if (!th) return;

  const nextSortBy = String(th.dataset.sort || '').trim();
  if (!nextSortBy) return;

  if (leadSortBy === nextSortBy) {
    leadSortDir = leadSortDir === 'asc' ? 'desc' : 'asc';
  } else {
    leadSortBy = nextSortBy;
    leadSortDir = 'asc';
  }

  currentItems = sortLeadItemsClientSide(currentItems, leadSortBy, leadSortDir);
  renderLeadsTable(currentItems);
  updateLeadSortIndicators();
  persistLeadListState(currentItems);
  addActivity(`並び替え: ${leadSortBy} ${leadSortDir}`, 'system');
});

myListFilterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  await fetchMyList();
});

historyFilterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  await fetchContactLogs();
});

historyRangeButtons.forEach((btn) => {
  btn.addEventListener('click', async () => {
    const range = btn.dataset.range || 'clear';
    await applyHistoryRange(range);
  });
});

myListStatusTabs.forEach((tab) => {
  tab.addEventListener('click', async () => {
    const status = tab.dataset.status || '';
    if (!myListFilterForm) return;
    const statusInput = myListFilterForm.querySelector('select[name="status"]');
    if (!statusInput) return;
    statusInput.value = status;
    await fetchMyList();
  });
});

historyTbody?.addEventListener('click', async (e) => {
  const btn = e.target.closest('.show-timeline-btn');
  if (!btn) return;
  const leadId = Number(btn.dataset.leadId || 0);
  const leadName = String(btn.dataset.leadName || '企業');
  if (!leadId) return;

  const res = await apiFetch(`/api/leads/${leadId}/timeline?limit=50`);
  if (!res) return;
  const data = await res.json();
  if (!res.ok) {
    if (historyTimeline) historyTimeline.innerHTML = `<div class="row">エラー: ${escapeHtml(data.detail || '取得失敗')}</div>`;
    return;
  }
  renderTimeline(leadName, data.items || []);
});

historyTimeline?.addEventListener('click', async (e) => {
  const btn = e.target.closest('.copy-message-btn');
  if (!btn) return;
  const logId = String(btn.dataset.logId || '');
  const message = timelineMessageMap.get(logId) || '';
  if (!message) {
    addActivity('コピー対象の本文が見つかりませんでした。', 'system');
    return;
  }
  try {
    await copyTextToClipboard(message);
    addActivity('本文をクリップボードにコピーしました。', 'user');
    showToast('本文をコピーしました', 'success');
  } catch (err) {
    addActivity(`コピーに失敗しました: ${String(err)}`, 'system');
    showToast('コピーに失敗しました', 'error');
  }
});

contactFormsTbody?.addEventListener('click', (e) => {
  const target = e.target;
  if (!(target instanceof Element)) return;

  const link = target.closest('.open-form-link');
  if (!link) return;

  const formUrl = String(link.getAttribute('href') || '').trim();
  const leadName = String(link.dataset.leadName || '').trim();

  showToast('フォームを新しいタブで開いています', 'info');
  addActivity(`問い合わせフォームを開きました: ${leadName || formUrl}`, 'user');
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

auditRefresh?.addEventListener('click', fetchAuditLogs);

leadSelectAll?.addEventListener('change', (e) => {
  const checked = e.target.checked;
  document.querySelectorAll('.lead-check').forEach((el) => {
    el.checked = checked;
  });
});

exportCsvBtn?.addEventListener('click', exportSelectedLeadsAsCsv);
exportExcelBtn?.addEventListener('click', exportSelectedLeadsAsExcel);
discoverContactFormsBtn?.addEventListener('click', discoverSelectedContactForms);

myListSelectAll?.addEventListener('change', (e) => {
  const checked = e.target.checked;
  document.querySelectorAll('.my-list-check').forEach((el) => {
    el.checked = checked;
  });
});

hydrateMyListFilterFromUrl();
hydrateLeadListState();
hydrateContactFormsState();
loadUserBadge();
fetchLeads();
fetchPlaceTypes();
fetchMyList();
fetchContactLogs();
fetchLeadNameSuggestions();
fetchAdapters();
fetchSuppressions();
fetchAuditLogs();
