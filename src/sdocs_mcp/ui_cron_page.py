"""Страница Cron: Prometheus → Kafka."""

from __future__ import annotations

from sdocs_mcp.ui_interval_options import render_interval_options
from sdocs_mcp.ui_subpage_layout import build_subpage_html

_INTERVAL_OPTS = render_interval_options(default_seconds=60, selected=60)

_CRON_BODY = (
    """
  <header class="page-head">
    <h1>Cron — Prometheus → Kafka</h1>
    <p class="lede">Фоновый instant query в Kafka. Токен UI — как на <a href="{{UI_PAGES_BASE}}/ops" style="color:var(--accent);">консоли</a> (localStorage).</p>
  </header>
  <div class="panel compact-panel" style="margin-bottom:0.75rem;">
    <div class="field-group">
      <label class="field-label" for="token">Токен UI / API</label>
      <input id="token" type="password" placeholder="SDOCS_MCP_UI_TOKEN" autocomplete="off" />
    </div>
  </div>
  <p id="cron-alert" class="alert" role="alert" hidden></p>
  <div id="cron-status-box" class="panel" style="margin-bottom:0.75rem;padding:0.85rem;">Загрузка…</div>
  <form class="cron-form" id="cron-form" onsubmit="return false;">
    <p class="cron-hint">
      <strong>PromQL</strong> — запрос к <em>вашему</em> Prometheus (не к /metrics SDocsMCP).
      Примеры: <code>up</code> (все цели живы),
      <code>sum(rate(http_requests_total{status=~"5.."}[5m]))</code> (ошибки 5xx),
      <code>avg_over_time(up[1h])</code>.
    </p>
    <div class="cron-settings-row">
      <label class="cron-check"><input type="checkbox" id="cron-enabled" checked /> Включено</label>
      <label>Интервал
        <select id="cron-interval" class="interval-select-wide">
"""
    + _INTERVAL_OPTS
    + """
        </select>
        <input type="number" id="cron-interval-custom" min="1" max="1440" placeholder="мин" hidden style="width:5.5rem;margin-top:0.25rem;" />
      </label>
      <label class="cron-promql">PromQL
        <input type="text" id="cron-query" value="up" spellcheck="false" autocomplete="off" placeholder="up" />
      </label>
    </div>
    <div class="btn-row">
      <button type="button" class="primary" id="btn-cron-save">Сохранить</button>
      <button type="button" id="btn-cron-refresh">Обновить статус</button>
    </div>
  </form>
"""

)

_CRON_SCRIPT = r"""
    const INTERVAL_PRESETS = [30, 60, 120, 180, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 86400];
    const $ = (id) => document.getElementById(id);
    function authHeader() {
      const t = ($('token').value || '').trim();
      return t ? { 'Authorization': 'Bearer ' + t } : {};
    }
    async function jget(path) {
      const r = await fetch(__UI_BASE + path, { headers: authHeader() });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    }
    async function jpost(path, body) {
      const r = await fetch(__UI_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify(body || {}),
      });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    }
    function fmtTs(ts) {
      if (!ts) return '—';
      try { return new Date(ts * 1000).toLocaleString(); } catch (e) { return String(ts); }
    }
    function fmtInterval(sec) {
      const s = parseInt(sec, 10) || 0;
      if (s < 60) return s + ' сек';
      if (s < 3600) return Math.round(s / 60) + ' мин';
      if (s < 86400) return (s / 3600) + ' ч';
      return '24 ч';
    }
    function cronIntervalSeconds() {
      const sel = $('cron-interval').value;
      if (sel === 'custom') {
        const m = parseInt($('cron-interval-custom').value, 10);
        return (m > 0 ? m : 1) * 60;
      }
      return parseInt(sel, 10) || 60;
    }
    function setCronIntervalUi(sec) {
      const s = parseInt(sec, 10) || 60;
      if (INTERVAL_PRESETS.includes(s)) {
        $('cron-interval').value = String(s);
        $('cron-interval-custom').hidden = true;
      } else {
        $('cron-interval').value = 'custom';
        $('cron-interval-custom').hidden = false;
        $('cron-interval-custom').value = String(Math.max(1, Math.round(s / 60)));
      }
    }
    function renderCronStatus(s) {
      const box = $('cron-status-box');
      const alert = $('cron-alert');
      alert.hidden = true;
      alert.textContent = '';
      alert.className = 'alert';
      if (!s.configured) {
        alert.hidden = false;
        alert.textContent = s.ready_reason || 'MCP Prometheus не настроен.';
      } else if (s.ui_workers > 1) {
        alert.hidden = false;
        alert.className = 'alert warn';
        alert.textContent = 'SDOCS_MCP_UI_WORKERS=' + s.ui_workers + ' — возможны дубли в Kafka. Лучше workers=1.';
      }
      let stateLabel = 'выключено';
      if (s.running) stateLabel = 'тик выполняется…';
      else if (s.active) stateLabel = 'работает';
      else if (s.enabled && !s.configured) stateLabel = 'включён, но не настроен';
      const lines = [
        'Состояние: ' + stateLabel,
        'Prometheus: ' + (s.prometheus_base_url || '—'),
        'Топик Kafka: ' + (s.kafka_topic || '—'),
        'Интервал: ' + fmtInterval(s.interval_seconds),
        'PromQL: ' + s.query,
        'Последний запуск: ' + fmtTs(s.last_run_at),
        'Последний успех: ' + fmtTs(s.last_success_at),
        'Запусков: ' + s.runs_total + ' (успехов ' + s.successes_total + ')',
        s.last_skip_reason ? ('Последний пропуск: ' + s.last_skip_reason) : '',
        s.last_error ? ('Ошибка: ' + s.last_error) : '',
      ].filter(Boolean);
      box.innerHTML = '<p class="muted" style="margin:0;">' + lines.map(l => l.replace(/</g, '&lt;')).join('<br>') + '</p>';
      $('cron-enabled').checked = !!s.enabled;
      setCronIntervalUi(s.interval_seconds);
      $('cron-query').value = s.query || 'up';
    }
    async function loadCronStatus() { renderCronStatus(await jget('/api/prometheus-metrics-cron')); }
    async function saveCron() {
      renderCronStatus(await jpost('/api/prometheus-metrics-cron', {
        enabled: $('cron-enabled').checked,
        interval_seconds: cronIntervalSeconds(),
        query: ($('cron-query').value || '').trim() || 'up',
      }));
    }
    (async function boot() {
      $('token').value = localStorage.getItem('sdocs_mcp_ui_token') || '';
      $('token').onchange = () => localStorage.setItem('sdocs_mcp_ui_token', $('token').value || '');
      $('cron-interval').onchange = () => { $('cron-interval-custom').hidden = $('cron-interval').value !== 'custom'; };
      $('btn-cron-save').onclick = () => saveCron().catch(e => alert(e));
      $('btn-cron-refresh').onclick = () => loadCronStatus().catch(e => alert(e));
      await loadCronStatus().catch(e => { $('cron-status-box').textContent = String(e); });
      setInterval(() => loadCronStatus().catch(() => {}), 15000);
    })();
"""

CRON_PAGE_HTML = build_subpage_html(
    title="Cron — sdocs-mcp",
    page="cron",
    body_html=_CRON_BODY,
    extra_script=_CRON_SCRIPT,
)
