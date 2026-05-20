"""Страница Alert: правила, MCP-источники, синхронизация через Kafka."""

from __future__ import annotations

from sdocs_mcp.ui_interval_options import render_interval_options
from sdocs_mcp.ui_subpage_layout import build_subpage_html

_RULE_INTERVAL_OPTS = render_interval_options(
    default_seconds=3600, selected=3600, include_custom=False
)

_ALERTS_BODY = f"""
  <header class="page-head">
    <h1>Alert — оповещения</h1>
    <p class="lede">Проверки по MCP-источникам. Правила синхронизируются между подами через Kafka (<code>sdocs.alerts.*</code>).</p>
    <p id="config-load-banner" class="config-banner config-banner--unknown" role="status" aria-live="polite">Конфиг: …</p>
    <p id="alerts-leader" class="muted" aria-live="polite"></p>
    <p class="section-note">Bearer (если задан <code>SDOCS_MCP_UI_TOKEN</code>): <input id="token" type="password" placeholder="токен" autocomplete="off" style="max-width:16rem" /></p>
  </header>
  <div class="alerts-grid">
    <section class="panel">
      <h3 class="section-title" style="margin-top:0;">Источник (MCP)</h3>
      <p class="section-note">Выберите модуль из доступных в конфиге. Серый — модуль выключен; зелёный — доступен; красный — ошибка обращения.</p>
      <div class="form-grid">
        <label>MCP-источник<select id="rule-mcp-source"></select></label>
        <label>Параметры (индекс / query)<input type="text" id="rule-params" placeholder="index ms-logs; query level:ERROR AND message:*404*" /></label>
        <label>Порог (шт.)<input type="number" id="rule-threshold" min="1" value="2" /></label>
        <label>Окно (часов)<input type="number" id="rule-window-hours" min="1" value="1" /></label>
        <label>Интервал проверки<select id="rule-interval" class="interval-select-wide">
{_RULE_INTERVAL_OPTS}
        </select></label>
        <label>Cooldown (сек., анти-спам)<input type="number" id="rule-cooldown" min="60" value="3600" title="Не чаще одного письма за период" /></label>
        <label>Группа<select id="rule-group"></select></label>
      </div>
    </section>
    <section class="panel groups-editor">
      <h3 class="section-title" style="margin-top:0;">Группы</h3>
      <textarea id="alert-groups" rows="10" spellcheck="false" wrap="off"></textarea>
      <button type="button" id="btn-groups-format">Форматировать JSON</button>
    </section>
    <section class="panel alerts-grid-full">
      <h3 class="section-title" style="margin-top:0;">Правило</h3>
      <div class="form-grid">
        <label>Название<input type="text" id="rule-name" placeholder="404 ERROR в ms-logs" /></label>
        <label>Описание<textarea id="rule-desc" rows="2"></textarea></label>
      </div>
      <div class="btn-row">
        <button type="button" class="primary" id="btn-alert-save">Сохранить на сервер (+ Kafka)</button>
        <button type="button" id="btn-alert-refresh">Обновить статусы</button>
        <button type="button" id="btn-alert-load-example">Пример</button>
      </div>
      <p class="muted" id="alert-save-msg"></p>
      <h3 class="section-title">Статус правил</h3>
      <div id="alert-rules-status"></div>
    </section>
  </div>
  <style>
    .config-banner {{ padding: 0.5rem 0.75rem; border-radius: 6px; font-weight: 600; }}
    .config-banner--ok {{ background: #0d3320; color: #6ee7a0; border: 1px solid #1a5c38; }}
    .config-banner--missing {{ background: #3d3010; color: #fcd34d; border: 1px solid #854d0e; }}
    .config-banner--invalid {{ background: #3f1515; color: #fca5a5; border: 1px solid #991b1b; }}
    .rule-row {{ display:flex; gap:0.75rem; align-items:flex-start; padding:0.6rem 0; border-bottom:1px solid var(--border, #333); }}
    .rule-dot {{ width:10px; height:10px; border-radius:50%; margin-top:0.35rem; flex-shrink:0; }}
    .rule-inactive {{ background:#888; }}
    .rule-ok {{ background:#22c55e; }}
    .rule-error {{ background:#ef4444; }}
    .rule-firing {{ background:#f59e0b; }}
  </style>
"""

_ALERTS_SCRIPT = r"""
    const $ = (id) => document.getElementById(id);
    function authHeader() {
      const t = ($('token') || {}).value ? $('token').value.trim() : '';
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
    function parseGroups() {
      return JSON.parse($('alert-groups').value || '[]');
    }
    function groupsPretty(g) { return JSON.stringify(g, null, 2); }
    function refreshGroupSelect() {
      const sel = $('rule-group');
      sel.innerHTML = '';
      parseGroups().forEach((g) => {
        const o = document.createElement('option');
        o.value = g.id;
        o.textContent = (g.name || g.id) + ' (' + (g.hours_msk || '—') + ')';
        sel.appendChild(o);
      });
    }
    async function loadConfigBanner() {
      const el = $('config-load-banner');
      try {
        const c = await jget('/api/config-load');
        el.className = 'config-banner config-banner--' + (c.state === 'ok' ? 'ok' : (c.state === 'invalid' ? 'invalid' : 'missing'));
        const t = c.loaded_at ? (' · ' + c.loaded_at) : '';
        el.textContent = (c.state === 'ok' ? '✓ Конфиг загружен' : (c.state === 'invalid' ? '✗ Ошибка конфига' : '○ Конфиг не загружен')) + t + ' — ' + (c.message || '');
      } catch (e) {
        el.className = 'config-banner config-banner--invalid';
        el.textContent = '✗ Не удалось получить статус конфига';
      }
    }
    async function loadMcpSources() {
      const data = await jget('/api/alerts/mcp-sources');
      const sel = $('rule-mcp-source');
      sel.innerHTML = '';
      (data.sources || []).forEach((s) => {
        const o = document.createElement('option');
        o.value = s.id;
        o.textContent = s.label + (s.enabled_in_config ? '' : ' (выкл. в конфиге)');
        o.disabled = !s.enabled_in_config;
        sel.appendChild(o);
      });
    }
    function ruleRowHtml(r) {
      const cls = { inactive: 'rule-inactive', ok: 'rule-ok', error: 'rule-error', firing: 'rule-firing' }[r.ui_state] || 'rule-inactive';
      const h = r.health || {};
      return '<div class="rule-row"><span class="rule-dot ' + cls + '"></span><div><strong>' + (r.name || '—') + '</strong> · ' +
        (r.mcp_source || '') + '<br><span class="muted">' + (h.label || '') + ': ' + (h.detail || '') +
        (r.evaluation && r.evaluation.detail ? ' · ' + r.evaluation.detail : '') + '</span></div></div>';
    }
    async function refreshStatuses() {
      const st = await jget('/api/alerts/status');
      $('alerts-leader').textContent = st.leader ? ('Лидер проверок: этот под (' + st.instance + ')') : ('Лидер: другой под · ' + st.instance);
      $('alert-rules-status').innerHTML = (st.rules || []).length ? (st.rules || []).map(ruleRowHtml).join('') : '<p class="muted">Нет правил</p>';
    }
    async function saveAll() {
      const groups = parseGroups();
      const rules = JSON.parse(localStorage.getItem('sdocs_mcp_alert_rules') || '[]');
      const entry = {
        name: $('rule-name').value.trim(),
        mcp_source: $('rule-mcp-source').value,
        params: $('rule-params').value.trim(),
        threshold: parseInt($('rule-threshold').value, 10),
        window_hours: parseFloat($('rule-window-hours').value),
        interval_sec: parseInt($('rule-interval').value, 10),
        cooldown_sec: parseInt($('rule-cooldown').value, 10),
        group_id: $('rule-group').value,
        description: $('rule-desc').value.trim(),
      };
      if (!entry.name) throw new Error('Укажите название');
      let list = rules;
      const idx = list.findIndex((x) => x.name === entry.name);
      if (idx >= 0) list[idx] = { ...list[idx], ...entry }; else list.push(entry);
      localStorage.setItem('sdocs_mcp_alert_rules', JSON.stringify(list));
      const res = await jpost('/api/alerts/rules', { groups, rules: list });
      $('alert-save-msg').textContent = 'Сохранено, revision=' + res.revision + (res.kafka_published ? ', Kafka OK' : ', Kafka пропущен (allowlist/produce)');
      await refreshStatuses();
    }
    async function loadFromServer() {
      const snap = await jget('/api/alerts/rules');
      if (snap.groups) $('alert-groups').value = groupsPretty(snap.groups);
      if (snap.rules) localStorage.setItem('sdocs_mcp_alert_rules', JSON.stringify(snap.rules));
      refreshGroupSelect();
    }
    function loadExample() {
      $('alert-groups').value = groupsPretty([
        { id: 'support', name: 'Сопровождение', emails: 'oncall@example.com', hours_msk: '08:00-18:00' }
      ]);
      const rules = [{
        name: '404 ERROR в ms-logs',
        mcp_source: 'opensearch',
        params: 'index ms-logs; query level:ERROR AND message:*404*',
        threshold: 2, window_hours: 1, interval_sec: 3600, cooldown_sec: 3600,
        group_id: 'support', description: 'Более 2 ERROR с 404 за час'
      }];
      localStorage.setItem('sdocs_mcp_alert_rules', JSON.stringify(rules));
      const r = rules[0];
      $('rule-name').value = r.name;
      $('rule-mcp-source').value = r.mcp_source;
      $('rule-params').value = r.params;
      $('rule-threshold').value = r.threshold;
      $('rule-window-hours').value = r.window_hours;
      $('rule-interval').value = String(r.interval_sec);
      $('rule-cooldown').value = String(r.cooldown_sec);
      $('rule-desc').value = r.description;
      refreshGroupSelect();
      $('rule-group').value = r.group_id;
    }
    (async function boot() {
      try { await loadFromServer(); } catch (_) {}
      $('btn-groups-format').onclick = () => { $('alert-groups').value = groupsPretty(parseGroups()); refreshGroupSelect(); };
      $('btn-alert-save').onclick = () => saveAll().catch((e) => alert(e));
      $('btn-alert-refresh').onclick = () => refreshStatuses().catch((e) => alert(e));
      $('btn-alert-load-example').onclick = () => loadExample();
      await loadConfigBanner();
      await loadMcpSources();
      await refreshStatuses();
      setInterval(() => { refreshStatuses().catch(() => {}); }, 45000);
      setInterval(() => { loadConfigBanner().catch(() => {}); }, 60000);
    })();
"""

ALERTS_PAGE_HTML = build_subpage_html(
    title="Alert — sdocs-mcp",
    page="alerts",
    body_html=_ALERTS_BODY,
    extra_script=_ALERTS_SCRIPT,
)
