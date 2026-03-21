type NoticeStatus = 'new' | 'watching' | 'applied' | 'ignored';
type NoticeCategory = 'school' | 'lab' | 'teacher';

type Overview = {
  total: number;
  official: number;
  experience: number;
  schoolCount: number;
  labCount: number;
  teacherCount: number;
  newCount: number;
  starred: number;
  deadlineSoon: number;
  actionable: number;
};

type SourceOption = {
  value: string;
  label: string;
};

type NoticeItem = {
  url: string;
  homepageUrl?: string;
  githubUrl?: string;
  title: string;
  entityName?: string;
  sourceName: string;
  school: string;
  college?: string;
  tier: string;
  category: NoticeCategory;
  sourceLevel?: string;
  contentKind: 'official' | 'experience';
  fitScore: number;
  deadlineText: string;
  parsedDeadline: string | null;
  daysLeft: number | null;
  firstSeenAt: string;
  status: NoticeStatus;
  starred: boolean;
  notes: string;
  summary: string;
  officialSummary?: string;
  githubSummary?: string;
  actionScore: number;
  actionable: boolean;
  level: 'high' | 'medium' | 'low';
};

type NoticesResponse = {
  items: NoticeItem[];
  total: number;
  options: {
    sources: SourceOption[];
  };
};

type ScanStatus = {
  running: boolean;
  startedAt?: string;
  finishedAt?: string;
  lastExitCode?: number;
  message?: string;
  log?: string;
};

type HighlightsResponse = {
  today: NoticeItem[];
  urgent: NoticeItem[];
  highFit: NoticeItem[];
};

type AssistantCommandResponse = {
  ok: boolean;
  reply: string;
  filters?: Partial<{
    kind: 'all' | 'official' | 'experience';
    category: 'all' | NoticeCategory;
    source: string;
    onlyActionable: boolean;
    sort: 'latest' | 'fit' | 'deadline';
  }>;
  matchedSources?: string[];
  scanned?: number;
  stderr?: string;
};

const state = {
  kind: 'all',
  status: 'all',
  category: 'all',
  source: 'all',
  sort: 'latest',
  q: '',
  onlyActionable: true,
};

let pendingScrollTarget: 'list' | NoticeCategory | null = null;

const overviewGrid = document.querySelector<HTMLDivElement>('#overviewGrid')!;
const highlightsGrid = document.querySelector<HTMLDivElement>('#highlightsGrid')!;
const noticeList = document.querySelector<HTMLDivElement>('#noticeList')!;
const resultCount = document.querySelector<HTMLSpanElement>('#resultCount')!;
const categoryFilter = document.querySelector<HTMLSelectElement>('#categoryFilter')!;
const sourceFilter = document.querySelector<HTMLSelectElement>('#sourceFilter')!;
const kindFilter = document.querySelector<HTMLSelectElement>('#kindFilter')!;
const statusFilter = document.querySelector<HTMLSelectElement>('#statusFilter')!;
const sortFilter = document.querySelector<HTMLSelectElement>('#sortFilter')!;
const onlyActionableFilter = document.querySelector<HTMLInputElement>('#onlyActionableFilter')!;
const queryInput = document.querySelector<HTMLInputElement>('#queryInput')!;
const scanStatusEl = document.querySelector<HTMLDivElement>('#scanStatus')!;
const scanLogEl = document.querySelector<HTMLPreElement>('#scanLog')!;
const configHintEl = document.querySelector<HTMLDivElement>('#configHint')!;
const scanButton = document.querySelector<HTMLButtonElement>('#scanButton')!;
const enrichButton = document.querySelector<HTMLButtonElement>('#enrichButton')!;
const refreshButton = document.querySelector<HTMLButtonElement>('#refreshButton')!;
const assistantInput = document.querySelector<HTMLTextAreaElement>('#assistantInput')!;
const assistantOutput = document.querySelector<HTMLDivElement>('#assistantOutput')!;
const assistantSubmitButton = document.querySelector<HTMLButtonElement>('#assistantSubmitButton')!;
const noticeTemplate = document.querySelector<HTMLTemplateElement>('#noticeTemplate')!;

function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function formatDateTime(value: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}-${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function formatDeadline(item: NoticeItem): string {
  if (!item.deadlineText) return item.contentKind === 'experience' ? '经验参考' : '未提取';
  if (typeof item.daysLeft === 'number') return `${item.deadlineText}（${item.daysLeft}天）`;
  return item.deadlineText;
}

function statusLabel(status: NoticeStatus): string {
  if (status === 'new') return '新发现';
  if (status === 'watching') return '跟进中';
  if (status === 'applied') return '已处理';
  return '忽略';
}

function kindLabel(kind: NoticeItem['contentKind']): string {
  return kind === 'official' ? '官方情报' : '经验参考';
}

function categoryLabel(category: NoticeCategory | 'all'): string {
  if (category === 'school') return '学院';
  if (category === 'lab') return '实验室';
  if (category === 'teacher') return '老师';
  return '全部';
}

function buildSummary(item: NoticeItem): string {
  const chunks: string[] = [];
  if (item.summary) chunks.push(item.summary);
  if (item.category === 'teacher' || item.category === 'lab') {
    if (item.school) chunks.push(`学校：${item.school}`);
    if (item.college) chunks.push(`院系：${item.college}`);
    if (item.sourceName) chunks.push(`来源目录：${item.sourceName}`);
  } else {
    if (item.school) chunks.push(`学校：${item.school}`);
    if (item.sourceName) chunks.push(`来源：${item.sourceName}`);
    if (item.parsedDeadline) chunks.push(`DDL：${item.parsedDeadline}`);
  }
  if (item.notes) chunks.push(`备注：${item.notes}`);
  chunks.push(item.actionable ? '高价值' : '低优先');
  return chunks.join(' · ');
}

function syncFilterControls(): void {
  kindFilter.value = state.kind;
  statusFilter.value = state.status;
  categoryFilter.value = state.category;
  sourceFilter.value = state.source;
  sortFilter.value = state.sort;
  queryInput.value = state.q;
  onlyActionableFilter.checked = state.onlyActionable;
}

function scrollToPendingTarget(): void {
  if (!pendingScrollTarget) return;
  if (pendingScrollTarget === 'list') {
    noticeList.scrollIntoView({ behavior: 'smooth', block: 'start' });
    pendingScrollTarget = null;
    return;
  }
  const section = noticeList.querySelector<HTMLElement>(`[data-category-section="${pendingScrollTarget}"]`);
  if (section) {
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    section.classList.add('section-flash');
    window.setTimeout(() => section.classList.remove('section-flash'), 1200);
  } else {
    noticeList.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  pendingScrollTarget = null;
}

async function applyQuickFilter(action: string): Promise<void> {
  state.kind = 'all';
  state.status = 'all';
  state.category = 'all';
  state.source = 'all';
  state.sort = 'latest';
  state.q = '';
  state.onlyActionable = false;
  pendingScrollTarget = 'list';

  if (action === 'official') state.kind = 'official';
  if (action === 'experience') state.kind = 'experience';
  if (action === 'school' || action === 'lab' || action === 'teacher') {
    state.category = action;
    pendingScrollTarget = action;
  }
  if (action === 'actionable') state.onlyActionable = true;
  if (action === 'deadline') state.sort = 'deadline';

  syncFilterControls();
  await loadNotices();
  scrollToPendingTarget();
}

function renderOverview(data: Overview): void {
  const cards: Array<{ label: string; value: string; action: string }> = [
    { label: '总记录', value: String(data.total), action: 'all' },
    { label: '官方情报', value: String(data.official), action: 'official' },
    { label: '经验参考', value: String(data.experience), action: 'experience' },
    { label: '学院', value: String(data.schoolCount), action: 'school' },
    { label: '实验室', value: String(data.labCount), action: 'lab' },
    { label: '老师', value: String(data.teacherCount), action: 'teacher' },
    { label: '高价值', value: String(data.actionable), action: 'actionable' },
    { label: '7天内DDL', value: String(data.deadlineSoon), action: 'deadline' },
  ];
  overviewGrid.innerHTML = cards.map((card) => `
    <button type="button" class="overview-card card overview-button" data-action="${escapeHtml(card.action)}">
      <div class="label">${escapeHtml(card.label)}</div>
      <div class="value">${escapeHtml(card.value)}</div>
    </button>
  `).join('');

  overviewGrid.querySelectorAll<HTMLButtonElement>('.overview-button').forEach((button) => {
    button.addEventListener('click', () => { void applyQuickFilter(button.dataset.action || 'all'); });
  });
}

function renderHighlights(data: HighlightsResponse): void {
  const sections: Array<[string, NoticeItem[], (item: NoticeItem) => string]> = [
    ['今日新增', data.today, (item) => `${categoryLabel(item.category)} · ${item.entityName || item.school || item.sourceName}`],
    ['临近 DDL', data.urgent, (item) => `${categoryLabel(item.category)} · ${formatDeadline(item)}`],
    ['高匹配', data.highFit, (item) => `${categoryLabel(item.category)} · 匹配度 ${item.fitScore}`],
  ];

  highlightsGrid.innerHTML = sections.map(([title, items, detail]) => {
    const inner = items.length
      ? `<ul class="highlight-list">${items.map((item) => `
          <li class="highlight-item">
            <a href="${escapeHtml(item.homepageUrl || item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>
            <div class="highlight-meta">${escapeHtml(detail(item))}</div>
          </li>`).join('')}</ul>`
      : '<div class="empty-state">暂无</div>';
    return `<section class="highlight-card card"><h2>${escapeHtml(title)}</h2>${inner}</section>`;
  }).join('');
}

function renderSourceOptions(options: SourceOption[]): void {
  const current = sourceFilter.value || 'all';
  sourceFilter.innerHTML = '<option value="all">全部</option>' + options
    .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
    .join('');
  sourceFilter.value = options.some((item) => item.value === current) ? current : 'all';
}

function buildNoticeCard(item: NoticeItem): HTMLElement {
  const node = noticeTemplate.content.firstElementChild!.cloneNode(true) as HTMLElement;
  const titleLink = node.querySelector<HTMLAnchorElement>('[data-role="titleLink"]')!;
  const kindBadge = node.querySelector<HTMLSpanElement>('[data-role="kindBadge"]')!;
  const categoryBadge = node.querySelector<HTMLSpanElement>('[data-role="categoryBadge"]')!;
  const tierBadge = node.querySelector<HTMLSpanElement>('[data-role="tierBadge"]')!;
  const statusBadge = node.querySelector<HTMLSpanElement>('[data-role="statusBadge"]')!;
  const metaLine = node.querySelector<HTMLParagraphElement>('[data-role="metaLine"]')!;
  const quickLinks = node.querySelector<HTMLDivElement>('[data-role="quickLinks"]')!;
  const fitScore = node.querySelector<HTMLElement>('[data-role="fitScore"]')!;
  const deadlineText = node.querySelector<HTMLElement>('[data-role="deadlineText"]')!;
  const firstSeen = node.querySelector<HTMLElement>('[data-role="firstSeen"]')!;
  const summary = node.querySelector<HTMLParagraphElement>('[data-role="summary"]')!;
  const starButton = node.querySelector<HTMLButtonElement>('[data-role="starButton"]')!;
  const statusSelect = node.querySelector<HTMLSelectElement>('[data-role="statusSelect"]')!;
  const notesInput = node.querySelector<HTMLTextAreaElement>('[data-role="notesInput"]')!;
  const saveButton = node.querySelector<HTMLButtonElement>('[data-role="saveButton"]')!;

  titleLink.href = item.homepageUrl || item.url;
  titleLink.textContent = item.title;
  kindBadge.textContent = kindLabel(item.contentKind);
  categoryBadge.textContent = categoryLabel(item.category);
  tierBadge.textContent = item.tier || '未分档';
  statusBadge.textContent = statusLabel(item.status);
  statusBadge.classList.add(`status-${item.status}`);
  metaLine.textContent = [item.school, item.college, item.sourceName].filter(Boolean).join(' · ') || '未识别来源';
  if (item.category === 'teacher' || item.category === 'lab') {
    const links: string[] = [];
    if (item.homepageUrl) links.push(`<a href="${escapeHtml(item.homepageUrl)}" target="_blank" rel="noreferrer">主页</a>`);
    if (item.githubUrl) links.push(`<a href="${escapeHtml(item.githubUrl)}" target="_blank" rel="noreferrer">GitHub</a>`);
    if (item.url && item.url !== item.homepageUrl) links.push(`<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">原始来源</a>`);
    quickLinks.innerHTML = links.join('<span class="dot">·</span>');
    quickLinks.hidden = links.length === 0;
  } else {
    quickLinks.hidden = true;
    quickLinks.innerHTML = '';
  }
  fitScore.textContent = String(item.fitScore);
  deadlineText.textContent = formatDeadline(item);
  firstSeen.textContent = formatDateTime(item.firstSeenAt);
  summary.textContent = buildSummary(item);
  statusSelect.value = item.status;
  notesInput.value = item.notes || '';
  starButton.textContent = item.starred ? '★' : '☆';
  starButton.classList.toggle('active', item.starred);

  starButton.addEventListener('click', async () => {
    await saveNoticeState(item.url, { starred: !item.starred });
    await loadAll();
  });
  saveButton.addEventListener('click', async () => {
    await saveNoticeState(item.url, { status: statusSelect.value as NoticeStatus, notes: notesInput.value });
    await loadAll();
  });

  return node;
}

function renderNotices(items: NoticeItem[]): void {
  resultCount.textContent = `共 ${items.length} 条`;
  noticeList.innerHTML = '';
  if (!items.length) {
    noticeList.innerHTML = '<div class="empty-state card">当前筛选条件下没有数据。你可以试试清空筛选，或者点一次“立即扫描”。</div>';
    return;
  }

  const groups: Array<[NoticeCategory, NoticeItem[]]> = [
    ['school', items.filter((item) => item.category === 'school')],
    ['lab', items.filter((item) => item.category === 'lab')],
    ['teacher', items.filter((item) => item.category === 'teacher')],
  ];

  const fragment = document.createDocumentFragment();
  for (const [category, groupItems] of groups) {
    if (!groupItems.length) continue;
    const section = document.createElement('section');
    section.className = 'category-section';
    section.dataset.categorySection = category;
    section.id = `section-${category}`;
    const head = document.createElement('div');
    head.className = 'category-head';
    head.innerHTML = `<h3 class="category-title">${escapeHtml(categoryLabel(category))}</h3><span class="muted">${groupItems.length} 条</span>`;
    section.appendChild(head);
    for (const item of groupItems) section.appendChild(buildNoticeCard(item));
    fragment.appendChild(section);
  }
  noticeList.appendChild(fragment);
}

async function saveNoticeState(url: string, payload: Partial<Pick<NoticeItem, 'status' | 'notes' | 'starred'>>): Promise<void> {
  try {
    await getJson('/api/notices/state', { method: 'POST', body: JSON.stringify({ url, ...payload }) });
  } catch (error) {
    window.alert(`保存失败：${String(error)}`);
  }
}

async function loadOverview(): Promise<void> {
  renderOverview(await getJson<Overview>('/api/overview'));
}

async function loadHighlights(): Promise<void> {
  renderHighlights(await getJson<HighlightsResponse>('/api/highlights'));
}

async function loadNotices(): Promise<void> {
  const params = new URLSearchParams({
    kind: state.kind,
    status: state.status,
    category: state.category,
    source: state.source,
    sort: state.sort,
    q: state.q,
    onlyActionable: state.onlyActionable ? '1' : '0',
  });
  const response = await getJson<NoticesResponse>(`/api/notices?${params.toString()}`);
  renderSourceOptions(response.options.sources);
  renderNotices(response.items);
}

async function loadScanStatus(): Promise<void> {
  const data = await getJson<ScanStatus>('/api/scan-status');
  const runningText = data.running
    ? `扫描状态：进行中（${data.startedAt ? formatDateTime(data.startedAt) : '刚刚启动'}）`
    : `扫描状态：空闲${data.finishedAt ? ` · 上次结束 ${formatDateTime(data.finishedAt)}` : ''}`;
  scanStatusEl.textContent = runningText;
  scanLogEl.textContent = data.log?.trim() || '暂无日志';
  configHintEl.textContent = data.message || '提示：若未完成 profile/targets 配置，先运行 setup_web.py。';
}

async function triggerScan(): Promise<void> {
  scanButton.disabled = true;
  scanButton.textContent = '扫描中...';
  try {
    await getJson('/api/scan', { method: 'POST', body: '{}' });
    await loadScanStatus();
    setTimeout(() => { void loadAll(); }, 1500);
  } catch (error) {
    window.alert(`启动扫描失败：${String(error)}`);
  } finally {
    scanButton.disabled = false;
    scanButton.textContent = '立即扫描';
  }
}

async function triggerEnrich(): Promise<void> {
  enrichButton.disabled = true;
  enrichButton.textContent = '提取中...';
  try {
    await getJson('/api/enrich', { method: 'POST', body: JSON.stringify({ limit: 24 }) });
    await loadAll();
  } catch (error) {
    window.alert(`提取摘要失败：${String(error)}`);
  } finally {
    enrichButton.disabled = false;
    enrichButton.textContent = '提取摘要';
  }
}

async function sendAssistantCommand(): Promise<void> {
  const message = assistantInput.value.trim();
  if (!message) {
    assistantOutput.textContent = '先输入一句话，比如：请帮我扫描上海交通大学的老师。';
    return;
  }
  assistantSubmitButton.disabled = true;
  assistantOutput.classList.add('busy');
  assistantOutput.textContent = '我正在帮你解析指令、执行扫描并刷新结果…';
  try {
    const response = await getJson<AssistantCommandResponse>('/api/assistant-command', {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
    if (response.filters) {
      if (response.filters.kind) state.kind = response.filters.kind;
      if (response.filters.category) state.category = response.filters.category;
      if (typeof response.filters.source === 'string') state.source = response.filters.source;
      if (typeof response.filters.onlyActionable === 'boolean') state.onlyActionable = response.filters.onlyActionable;
      if (response.filters.sort) state.sort = response.filters.sort;
      state.status = 'all';
      state.q = '';
      pendingScrollTarget = state.category === 'school' || state.category === 'lab' || state.category === 'teacher'
        ? state.category
        : 'list';
      syncFilterControls();
    }
    await loadAll();
    scrollToPendingTarget();
    const extra = response.matchedSources?.length ? `\n匹配来源：${response.matchedSources.join('；')}` : '';
    assistantOutput.textContent = `${response.reply || '已处理。'}${extra}`;
  } catch (error) {
    assistantOutput.textContent = `执行失败：${String(error)}`;
  } finally {
    assistantSubmitButton.disabled = false;
    assistantOutput.classList.remove('busy');
  }
}

async function loadAll(): Promise<void> {
  await Promise.all([loadOverview(), loadHighlights(), loadNotices(), loadScanStatus()]);
}

kindFilter?.addEventListener('change', () => { state.kind = kindFilter.value; pendingScrollTarget = 'list'; void loadNotices().then(scrollToPendingTarget); });
statusFilter?.addEventListener('change', () => { state.status = statusFilter.value; pendingScrollTarget = 'list'; void loadNotices().then(scrollToPendingTarget); });
categoryFilter?.addEventListener('change', () => {
  state.category = categoryFilter.value;
  pendingScrollTarget = (state.category === 'school' || state.category === 'lab' || state.category === 'teacher') ? state.category as NoticeCategory : 'list';
  void loadNotices().then(scrollToPendingTarget);
});
sourceFilter?.addEventListener('change', () => { state.source = sourceFilter.value; pendingScrollTarget = 'list'; void loadNotices().then(scrollToPendingTarget); });
sortFilter?.addEventListener('change', () => { state.sort = sortFilter.value; pendingScrollTarget = 'list'; void loadNotices().then(scrollToPendingTarget); });
onlyActionableFilter?.addEventListener('change', () => { state.onlyActionable = onlyActionableFilter.checked; pendingScrollTarget = 'list'; void loadNotices().then(scrollToPendingTarget); });
queryInput?.addEventListener('input', () => { state.q = queryInput.value.trim(); pendingScrollTarget = 'list'; void loadNotices().then(scrollToPendingTarget); });
scanButton?.addEventListener('click', () => { void triggerScan(); });
enrichButton?.addEventListener('click', () => { void triggerEnrich(); });
refreshButton?.addEventListener('click', () => { void loadAll(); });
assistantSubmitButton?.addEventListener('click', () => { void sendAssistantCommand(); });
assistantInput?.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault();
    void sendAssistantCommand();
  }
});

void loadAll();
setInterval(() => { void loadScanStatus(); }, 10000);
