"""Статическая разметка главного дашборда (стиль заказчика); данные — через GET /api/dashboard-stats."""

from sdocs_mcp.ui_nav import inject_top_nav
from sdocs_mcp.ui_paths import normalize_ui_base_path

_DASHBOARD_HTML_RAW = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MCP метрики — дашборд</title>
  <script>const __UI_BASE="{{UI_BASE_PATH}}";</script>
  <style>
{{TOPNAV_STYLES}}
    nav.sdocs-mcp-topnav { border-color: var(--border-light); background: var(--bg-card-light); }
    nav.sdocs-mcp-topnav a:not(.is-active) { color: var(--accent-green); }
    nav.sdocs-mcp-topnav a.is-active { color: var(--text-primary); }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    :root {
      --bg-primary: #020304;
      --bg-card: #080b10;
      --bg-card-light: #0D0F16;
      --border-color: #171b23;
      --border-light: #1A1E28;
      --text-primary: #eef3ff;
      --text-secondary: #8D99AB;
      --text-muted: #5A6675;
      --accent-green: #10b981;
      --accent-gold: #f0b90b;
      --accent-green-glow: #10b98130;
      --legend-bg: #05080E;
      --legend-header: #0A0D14;
    }
    body.light {
      --bg-primary: #f5f7fc;
      --bg-card: #ffffff;
      --bg-card-light: #f8f9fe;
      --border-color: #e2e8f0;
      --border-light: #e2edf2;
      --text-primary: #1a202c;
      --text-secondary: #4a5568;
      --text-muted: #718096;
      --accent-green: #059669;
      --accent-gold: #b45309;
      --accent-green-glow: #05966920;
      --legend-bg: #f1f5f9;
      --legend-header: #e2e8f0;
    }
    body {
      background: var(--bg-primary);
      font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      color: var(--text-primary);
      padding: 32px 40px;
      transition: background 0.2s, color 0.2s;
    }
    .mono { font-family: ui-monospace, "Cascadia Code", Consolas, monospace; }
    .dashboard { max-width: 1600px; margin: 0 auto; }
    .luxury-header {
      display: flex; justify-content: space-between; align-items: flex-end;
      margin-bottom: 32px; border-bottom: 1px solid var(--border-color);
      padding-bottom: 20px; flex-wrap: wrap; gap: 20px;
    }
    .brand h1 { font-size: 24px; font-weight: 500; letter-spacing: -0.3px; color: var(--text-primary); }
    .brand h1 span {
      font-family: ui-monospace, monospace; font-size: 12px;
      background: color-mix(in srgb, var(--accent-green) 20%, transparent);
      padding: 2px 10px; border-radius: 20px; color: var(--accent-green); margin-left: 12px;
    }
    @supports not (background: color-mix(in srgb, white 50%, black)) {
      .brand h1 span { background: rgba(16, 185, 129, 0.15); }
    }
    .savings-corner { text-align: right; }
    .savings-row { display: flex; align-items: baseline; gap: 20px; justify-content: flex-end; flex-wrap: wrap; }
    .savings-item { display: flex; flex-direction: column; align-items: flex-end; }
    .savings-hours { font-size: 28px; font-weight: 700; font-family: ui-monospace, monospace; color: var(--accent-green); letter-spacing: -1px; }
    .savings-money { font-size: 28px; font-weight: 600; font-family: ui-monospace, monospace; color: var(--accent-gold); }
    .savings-rate { font-size: 13px; font-weight: 500; color: var(--text-primary); }
    .savings-label { font-size: 10px; color: var(--text-secondary); letter-spacing: 0.2px; margin-top: 2px; }
    .savings-divider { width: 1px; height: 32px; background: var(--border-color); opacity: 0.4; }
    .grid-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; margin-bottom: 36px; }
    .card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 28px; overflow: hidden; }
    .card-header-section {
      padding: 20px 24px 8px 24px; border-bottom: 1px solid var(--border-color);
      display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
    }
    .card-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 16px; }
    .period-control { display: flex; align-items: center; gap: 12px; background: var(--bg-card-light); padding: 5px 12px; border-radius: 40px; }
    .period-btn {
      background: none; border: none; color: var(--text-secondary); font-size: 12px;
      padding: 4px 12px; border-radius: 30px; cursor: pointer; transition: 0.2s;
    }
    .period-btn.active { background: color-mix(in srgb, var(--accent-green) 20%, transparent); color: var(--accent-green); }
    @supports not (background: color-mix(in srgb, white 50%, black)) {
      .period-btn.active { background: rgba(16, 185, 129, 0.15); }
    }
    .reset-btn {
      background: var(--border-light); border: none; color: var(--text-primary);
      padding: 5px 14px; border-radius: 30px; font-size: 11px; cursor: pointer;
      display: flex; align-items: center; gap: 6px;
    }
    .metrics-container { padding: 20px 24px; }
    .metric-row { display: flex; gap: 28px; margin-bottom: 24px; flex-wrap: wrap; }
    .metric-item { flex: 1; min-width: 140px; }
    .metric-number { font-size: 36px; font-weight: 700; font-family: ui-monospace, monospace; }
    .metric-number.positive { color: var(--accent-green); text-shadow: 0 0 4px var(--accent-green-glow); }
    .metric-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
    .metric-note { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
    .legend-block { background: var(--legend-bg); border-radius: 20px; border: 0.5px solid var(--border-light); margin: 0 24px 24px 24px; overflow: hidden; }
    .legend-header { background: var(--legend-header); padding: 12px 18px; border-bottom: 0.5px solid var(--border-light); font-size: 11px; font-weight: 500; letter-spacing: 0.5px; color: var(--text-secondary); }
    .legend-body { padding: 18px; }
    .legend-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
    .scenario-card { background: var(--bg-card); border-radius: 16px; padding: 12px 14px; border: 0.5px solid var(--border-light); }
    .formula-row { grid-column: span 2; background: var(--bg-card); border-radius: 16px; padding: 14px; margin-top: 8px; }
    .dynamic-note { grid-column: span 2; display: flex; justify-content: space-between; font-size: 11px; color: var(--text-secondary); padding-top: 12px; border-top: 0.5px dashed var(--border-light); margin-top: 8px; flex-wrap: wrap; gap: 12px; }
    .servers-list { display: flex; flex-direction: column; gap: 14px; padding: 20px; }
    .server-item { background: var(--bg-card-light); border-radius: 20px; border: 0.5px solid var(--border-light); transition: 0.2s; }
    .server-header { display: flex; justify-content: space-between; padding: 14px 18px; align-items: center; }
    .status-led { width: 8px; height: 8px; border-radius: 8px; display: inline-block; margin-right: 8px; }
    .led-online { background: var(--accent-green); box-shadow: 0 0 4px var(--accent-green); }
    .led-degraded { background: #f97316; }
    .led-offline { background: #6b7280; }
    .toggle-mcp { background: var(--bg-card); padding: 3px 10px; border-radius: 30px; cursor: pointer; font-size: 10px; display: flex; gap: 8px; align-items: center; }
    .toggle-switch { width: 30px; height: 16px; background: #2d313e; border-radius: 30px; position: relative; transition: 0.2s; }
    .toggle-switch.active { background: var(--accent-green); }
    .toggle-switch .knob { width: 10px; height: 10px; background: white; border-radius: 10px; position: absolute; top: 3px; left: 3px; }
    .toggle-switch.active .knob { left: 17px; }
    .server-metrics { display: flex; gap: 16px; padding: 10px 18px; border-top: 0.5px solid var(--border-light); border-bottom: 0.5px solid var(--border-light); font-size: 11px; flex-wrap: wrap; }
    .server-footer { padding: 10px 18px; font-size: 10px; color: var(--text-secondary); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
    .dashboard-footer { margin-top: 40px; display: flex; justify-content: space-between; align-items: center; padding-top: 20px; border-top: 0.5px solid var(--border-light); font-size: 11px; color: var(--text-muted); flex-wrap: wrap; gap: 12px; }
    .theme-switch { display: flex; align-items: center; gap: 8px; background: var(--bg-card-light); padding: 4px 12px; border-radius: 40px; cursor: pointer; }
    .theme-switch .toggle-track { width: 36px; height: 18px; background: var(--border-light); border-radius: 30px; position: relative; transition: 0.2s; }
    .theme-switch .toggle-track .toggle-thumb { width: 14px; height: 14px; background: var(--text-primary); border-radius: 14px; position: absolute; top: 2px; left: 2px; transition: 0.2s; }
    body.light .theme-switch .toggle-track .toggle-thumb { left: 20px; }
    .src-banner { font-size: 11px; color: var(--text-muted); margin-top: 8px; max-width: 42rem; line-height: 1.45; }
    @media (max-width: 1100px) { .grid-2col { grid-template-columns: 1fr; } body { padding: 20px; } }
  </style>
</head>
<body>
<div class="dashboard">
  {{TOPNAV}}
  <div class="luxury-header">
    <div class="brand">
      <h1>SDocsMCP · метрики <span>sdocs-mcp telemetry</span></h1>
      <div style="font-size:13px; margin-top:6px; color: var(--text-muted);">Живые проверки бэкендов и счётчики UI · ROI по методике заказчика (масштаб от периода)</div>
      <p class="src-banner" id="srcNote">Загрузка источников данных…</p>
    </div>
    <div class="savings-corner">
      <div class="savings-row">
        <div class="savings-item">
          <span class="savings-hours" id="savedHoursDisplay">—</span>
          <span class="savings-label">сэкономлено чел·часов (модель)</span>
        </div>
        <div class="savings-divider"></div>
        <div class="savings-item">
          <span class="savings-money" id="savedMoneyDisplay">—</span>
          <span class="savings-label">экономия в деньгах (модель)</span>
        </div>
        <div class="savings-divider"></div>
        <div class="savings-item">
          <span class="savings-rate mono" id="rateDisplay">1 875 ₽/ч</span>
          <span class="savings-label">ставка (из конфигурации дашборда)</span>
        </div>
      </div>
    </div>
  </div>

  <div class="grid-2col">
    <div class="card">
      <div class="card-header-section">
        <div class="card-title">📊 Ключевые метрики</div>
        <div class="period-control">
          <button type="button" class="period-btn" data-period="day">День</button>
          <button type="button" class="period-btn" data-period="week">Неделя</button>
          <button type="button" class="period-btn active" data-period="month">Месяц</button>
          <button type="button" class="reset-btn" id="resetMetricsBtn">↺ Сброс</button>
        </div>
      </div>
      <div class="metrics-container">
        <div class="metric-row">
          <div class="metric-item"><div class="metric-number" id="mcpCount">—</div><div class="metric-label">MCP в норме</div><div class="metric-note" id="mcpCountNote">из включённых в конфиге</div></div>
          <div class="metric-item"><div class="metric-number positive" id="totalCalls">—</div><div class="metric-label">Обращений к API UI</div><div class="metric-note" id="periodNote">sdocs_mcp_ui_requests_total</div></div>
          <div class="metric-item"><div class="metric-number positive" id="avgUptime">—</div><div class="metric-label">Доля успешных проверок</div><div class="metric-note">enabled-модули, health</div></div>
        </div>
        <div class="metric-row">
          <div class="metric-item"><div class="metric-number positive" id="savedHoursMetric">—</div><div class="metric-label">Чел·ч (модель × период)</div><div class="metric-note">см. легенду расчёта</div></div>
          <div class="metric-item"><div class="metric-number positive mono" id="incidentResponse">12 сек</div><div class="metric-label">Целевое время ответа MCP</div><div class="metric-note">из методики (не измеряется здесь)</div></div>
          <div class="metric-item"><div class="metric-number" style="color: var(--text-muted);">3–15 мин</div><div class="metric-label">Без MCP (оценка)</div><div class="metric-note">ручной доступ</div></div>
        </div>
      </div>
      <div class="legend-block">
        <div class="legend-header">МОДЕЛЬ ЭКОНОМИИ (как в описании заказчика)</div>
        <div class="legend-body">
          <div class="legend-grid">
            <div class="scenario-card">
              <div style="font-size: 10px; color: var(--text-muted);">Сценарий A — 1 MCP</div>
              <div style="display: flex; justify-content: space-between; margin: 8px 0;"><span>1 специалист</span><span>35 мин</span></div>
              <div style="display: flex; justify-content: space-between;"><span>Затраты (чел·ч)</span><span><strong>0.58</strong></span></div>
            </div>
            <div class="scenario-card">
              <div style="font-size: 10px; color: #F97316;">Сценарий B — ≥2 MCP</div>
              <div style="display: flex; justify-content: space-between; margin: 8px 0;"><span>3+ специалистов</span><span>85 мин</span></div>
              <div style="display: flex; justify-content: space-between;"><span>Затраты (чел·ч)</span><span><strong>4.25</strong></span></div>
            </div>
            <div class="formula-row">
              <div style="font-size: 10px; text-transform: uppercase; color: var(--text-muted);">База для месяца (модель)</div>
              <div class="mono" style="font-size: 11px; margin: 6px 0;" id="formulaLine">—</div>
              <div style="display: flex; justify-content: flex-end;"><span style="background: var(--bg-card-light); padding: 2px 10px; border-radius: 20px; font-size: 10px;">≈ <span id="formulaSaved">—</span> / выбранный период</span></div>
            </div>
            <div class="dynamic-note">
              <span>Серверов в списке: <strong id="dynMcp">—</strong> (данные с <code>/api/dashboard-stats</code>)</span>
              <span>Обновление: <strong>35 с</strong></span>
              <span>Средняя латентность проверок: <strong id="dynLat">—</strong></span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-header-section">
        <div class="card-title">🖥 MCP-серверы (модули)</div>
        <div style="font-size: 10px; color: var(--text-muted);">CPU/RAM в проде — Prometheus/node_exporter; здесь latency и статус</div>
      </div>
      <div class="servers-list" id="mcpServersList"></div>
    </div>
  </div>

  <div class="dashboard-footer">
    <div>2026 · sdocs-mcp · дашборд</div>
    <div class="theme-switch" id="themeToggle" role="button" tabindex="0" aria-label="Тема">
      <span>☀</span>
      <div class="toggle-track"><div class="toggle-thumb"></div></div>
      <span>☾</span>
    </div>
  </div>
</div>
<script>
(function () {
  const $ = (id) => document.getElementById(id);
  let lastPayload = null;
  let currentPeriod = 'month';
  let baseSavedHoursMonth = 14832;
  let rubPerHour = 1875;
  let togglePenaltyHours = 0;
  const TOGGLE_DELTA = 380;

  function authHeader() {
    const t = (localStorage.getItem('sdocs_mcp_ui_token') || '').trim();
    return t ? { 'Authorization': 'Bearer ' + t } : {};
  }

  function getMultiplier(p) {
    if (p === 'day') return 1 / 30;
    if (p === 'week') return 7 / 30;
    return 1;
  }

  function formatMoneyRub(value) {
    if (value >= 1_000_000) return '₽' + (value / 1_000_000).toFixed(1) + 'M';
    if (value >= 1_000) return '₽' + (value / 1_000).toFixed(0) + 'k';
    return '₽' + Math.floor(value);
  }

  function modelSavedHoursMonth(payload) {
    const b = payload.business_defaults || {};
    const inc = b.incidents_month || 1200;
    const manualH = ((b.manual_min_min + b.manual_max_min) / 2) / 60;
    const mcpH = (b.mcp_response_sec || 12) / 3600;
    const coef = 1.15;
    const raw = Math.max(0, (manualH - mcpH) * inc * coef);
    const health = (payload.summary || {}).uptime_score_pct;
    const hFactor = typeof health === 'number' ? (0.85 + 0.15 * (health / 100)) : 1;
    const up = payload.summary.mcp_healthy_count || 0;
    const en = payload.summary.mcp_enabled_count || 1;
    const slot = Math.min(1, up / Math.max(1, en));
    return Math.floor(raw * hFactor * slot);
  }

  function applyPayload(payload) {
    lastPayload = payload;
    const s = payload.summary || {};
    $('srcNote').textContent = payload.data_sources_note || '';
    rubPerHour = (payload.business_defaults && payload.business_defaults.rub_per_hour) || 1875;
    $('rateDisplay').textContent = rubPerHour.toLocaleString('ru-RU') + ' ₽/ч';
    baseSavedHoursMonth = modelSavedHoursMonth(payload);
    $('mcpCount').textContent = String(s.mcp_healthy_count ?? '—');
    $('mcpCountNote').textContent = 'из ' + (s.mcp_enabled_count ?? '—') + ' включённых';
    const req = s.ui_requests_total ?? 0;
    $('totalCalls').textContent = req >= 1000 ? (req / 1000).toFixed(1) + 'k' : String(req);
    const up = s.uptime_score_pct;
    $('avgUptime').textContent = typeof up === 'number' ? up.toFixed(1) + '%' : '—';
    $('dynMcp').textContent = String((payload.modules || []).length);
    const lat = s.avg_check_latency_ms;
    $('dynLat').textContent = typeof lat === 'number' ? lat + ' ms' : '—';
    const inc = (payload.business_defaults || {}).incidents_month || 1200;
    $('formulaLine').textContent = 'инциденты/мес ' + inc + ' · (t_ручн − t_MCP) · коэф., скоррект. по health';
    updatePeriodMetrics();
    renderServers(payload.modules || []);
  }

  function updatePeriodMetrics() {
    const mult = getMultiplier(currentPeriod);
    const hrs = Math.max(0, Math.floor(baseSavedHoursMonth * mult) - togglePenaltyHours);
    const money = hrs * rubPerHour;
    $('savedHoursMetric').textContent = hrs.toLocaleString('ru-RU');
    $('formulaSaved').textContent = hrs.toLocaleString('ru-RU') + ' чел·ч';
    $('savedHoursDisplay').textContent = hrs.toLocaleString('ru-RU');
    $('savedMoneyDisplay').textContent = formatMoneyRub(money);
    $('periodNote').textContent = currentPeriod === 'day' ? 'за сутки (пропорция месяца)' : (currentPeriod === 'week' ? 'за 7 дней' : 'за 30 дней');
  }

  function ledStatus(m) {
    if (!m.enabled) return 'led-offline';
    if (m.ok) return 'led-online';
    return 'led-degraded';
  }

  function uiStatus(m) {
    if (!m.enabled) return 'offline';
    if (m.ok) return 'online';
    return 'degraded';
  }

  function renderServers(mods) {
    const container = $('mcpServersList');
    container.innerHTML = '';
    mods.forEach((srv, idx) => {
      const st = uiStatus(srv);
      const led = ledStatus(srv);
      const lat = typeof srv.latency_ms === 'number' ? srv.latency_ms + ' ms' : '—';
      const div = document.createElement('div');
      div.className = 'server-item';
      div.innerHTML = '<div class="server-header">' +
        '<div><span class="status-led ' + led + '"></span><strong>' + srv.name + '</strong> ' +
        '<span style="font-size:9px;background:var(--border-light);padding:2px 6px;border-radius:20px;">' + srv.type + '</span></div>' +
        '<div class="toggle-mcp" data-idx="' + idx + '"><span style="font-size:9px;">MCP</span>' +
        '<div class="toggle-switch ' + (st !== 'offline' ? 'active' : '') + '"><div class="knob"></div></div></div></div>' +
        '<div class="server-metrics"><span>latency ' + lat + '</span><span>' + (srv.enabled ? 'включён' : 'выкл. в конфиге') + '</span></div>' +
        '<div class="server-footer"><span>' + (srv.detail || '').slice(0, 120) + '</span><span>' +
        (st === 'online' ? 'OK' : st === 'degraded' ? 'проверка не прошла' : 'не активен') + '</span></div>';
      container.appendChild(div);
    });
    document.querySelectorAll('.toggle-mcp').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = parseInt(el.getAttribute('data-idx'), 10);
        const srv = mods[idx];
        if (!srv || !srv.enabled) return;
        const toggleDiv = el.querySelector('.toggle-switch');
        const isActive = toggleDiv.classList.contains('active');
        if (isActive) {
          toggleDiv.classList.remove('active');
          togglePenaltyHours += TOGGLE_DELTA;
        } else {
          toggleDiv.classList.add('active');
          togglePenaltyHours = Math.max(0, togglePenaltyHours - TOGGLE_DELTA);
        }
        updatePeriodMetrics();
      });
    });
  }

  async function refresh() {
    try {
      const r = await fetch(__UI_BASE + '/api/dashboard-stats', { headers: authHeader() });
      const txt = await r.text();
      if (!r.ok) throw new Error(txt);
      applyPayload(JSON.parse(txt));
    } catch (e) {
      $('srcNote').textContent = 'Ошибка: ' + e + ' (нужен токен? введите на /ops и сохраните)';
    }
  }

  document.querySelectorAll('.period-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.period-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      currentPeriod = btn.getAttribute('data-period');
      updatePeriodMetrics();
    });
  });
  $('resetMetricsBtn').addEventListener('click', () => {
    togglePenaltyHours = 0;
    if (lastPayload) applyPayload(lastPayload);
    else refresh();
  });
  $('themeToggle').addEventListener('click', () => document.body.classList.toggle('light'));
  $('themeToggle').addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); document.body.classList.toggle('light'); } });

  refresh();
  setInterval(refresh, 35000);
})();
</script>
</body>
</html>
"""

DASHBOARD_HTML = inject_top_nav(_DASHBOARD_HTML_RAW.replace("{{UI_BASE_PATH}}", normalize_ui_base_path()), "dash")
