"""Страница Alert: правила по логам OpenSearch, доставка, журнал."""

from __future__ import annotations

from sdocs_mcp.ui_interval_options import render_interval_options
from sdocs_mcp.ui_subpage_layout import build_subpage_html

_RULE_INTERVAL_OPTS = render_interval_options(
    default_seconds=3600, selected=3600, include_custom=False
)

_ALERTS_BODY = f"""
  <header class="page-head">
    <h1>Alert — логи OpenSearch</h1>
    <p class="lede">Правила по индексу и запросу. Проверяет только <strong>лидер</strong> (один под) — без дублей уведомлений. Синхронизация правил — Kafka <code>sdocs.alerts.*</code> (без новых топиков).</p>
    <p id="config-load-banner" class="config-banner config-banner--unknown" role="status" aria-live="polite">Конфиг: …</p>
    <p id="alerts-leader" class="muted" aria-live="polite"></p>
    <p class="section-note">Bearer (если задан <code>SDOCS_MCP_UI_TOKEN</code>): <input id="token" type="password" placeholder="токен" autocomplete="off" style="max-width:16rem" /></p>
  </header>
  <div class="alerts-grid">
    <section class="panel">
      <h3 class="section-title" style="margin-top:0;">Новое / редактирование правила</h3>
      <input type="hidden" id="rule-edit-id" value="" />
      <div class="form-grid">
        <label><input type="checkbox" id="rule-enabled" checked /> Правило включено</label>
        <label>Название<input type="text" id="rule-name" placeholder="404 ERROR в ms-logs" /></label>
        <label>Описание<textarea id="rule-desc" rows="2" placeholder="Кратко для операторов"></textarea></label>
        <label>MCP-источник<select id="rule-mcp-source"></select></label>
        <label>Индекс OpenSearch<input type="text" id="rule-index" placeholder="ms-logs или *" /></label>
        <label>Запрос (query_string)<input type="text" id="rule-query" placeholder="level:ERROR AND message:*404*" /></label>
        <label>Условие<select id="rule-condition">
          <option value="count_threshold">Количество ≥ порога</option>
          <option value="no_logs">Нет логов за окно</option>
        </select></label>
        <label>Порог (шт.)<input type="number" id="rule-threshold" min="1" value="2" title="Для «нет логов» не используется" /></label>
        <label>Окно (часов)<input type="number" id="rule-window-hours" min="1" value="1" /></label>
        <label>Поле времени<input type="text" id="rule-time-field" value="@timestamp" title="Обычно @timestamp" /></label>
        <label>Интервал проверки<select id="rule-interval" class="interval-select-wide">
{_RULE_INTERVAL_OPTS}
        </select></label>
        <label>Cooldown (сек.)<input type="number" id="rule-cooldown" min="60" value="3600" title="Не чаще одного уведомления за период" /></label>
        <label>Группа<select id="rule-group"></select></label>
        <label>Куда слать<select id="rule-notify-channel">
          <option value="email">E-mail (SMTP modules.mail)</option>
          <option value="webhook">Webhook (POST JSON)</option>
          <option value="telegram">Telegram</option>
          <option value="none">Не слать (только журнал/Kafka)</option>
        </select></label>
        <label>Получатель<input type="text" id="rule-notify-target" placeholder="email@a.com или URL webhook или chat_id" /></label>
      </div>
      <p class="section-note muted">E-mail: оставьте получателя пустым — возьмётся <code>emails</code> из группы. Webhook/Telegram: URL или chat_id; иначе из <code>modules.alerting.notify</code>.</p>
      <div class="btn-row">
        <button type="button" class="primary" id="btn-alert-save">Сохранить на сервер</button>
        <button type="button" id="btn-alert-clear">Очистить форму</button>
        <button type="button" id="btn-alert-load-example">Пример</button>
      </div>
      <p class="muted" id="alert-save-msg"></p>
    </section>
    <section class="panel groups-editor">
      <h3 class="section-title" style="margin-top:0;">Группы получателей</h3>
      <p class="section-note">JSON: <code>id</code>, <code>name</code>, <code>emails</code> (через запятую), <code>hours_msk</code> (информационно).</p>
      <textarea id="alert-groups" rows="12" spellcheck="false" wrap="off"></textarea>
      <button type="button" id="btn-groups-format">Форматировать JSON</button>
    </section>
    <section class="panel alerts-grid-full">
      <div class="btn-row" style="justify-content:space-between;align-items:center;">
        <h3 class="section-title" style="margin:0;">Сохранённые правила</h3>
        <button type="button" id="btn-alert-refresh">Обновить статусы</button>
      </div>
      <div id="alert-rules-list" class="rules-table-wrap"></div>
      <h3 class="section-title">Статус проверок</h3>
      <div id="alert-rules-status"></div>
      <h3 class="section-title">Журнал доставки</h3>
      <p class="section-note muted">Последние попытки отправки на этом поде (успех / ошибка, канал, получатель).</p>
      <div id="alert-notify-log"></div>
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
  .rules-table {{ width:100%; border-collapse:collapse; font-size:0.88rem; }}
  .rules-table th, .rules-table td {{ border-bottom:1px solid var(--border,#333); padding:0.45rem 0.5rem; text-align:left; vertical-align:top; }}
  .rules-table tr.rule-disabled {{ opacity:0.55; }}
  .notify-ok {{ color: #6ee7a0; }}
  .notify-fail {{ color: #fca5a5; }}
  .btn-link {{ background:none; border:none; color: var(--accent,#6af); cursor:pointer; padding:0 0.25rem; font-size:inherit; }}
  </style>
"""

_ALERTS_SCRIPT = r"""
    const $ = (id) => document.getElementById(id);
    let rulesCache = [];
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
        o.textContent = (g.name || g.id) + ' (' + (g.emails || '—') + ')';
        sel.appendChild(o);
      });
    }
    function clearRuleForm() {
      $('rule-edit-id').value = '';
      $('rule-enabled').checked = true;
      $('rule-name').value = '';
      $('rule-desc').value = '';
      $('rule-index').value = '';
      $('rule-query').value = '';
      $('rule-condition').value = 'count_threshold';
      $('rule-threshold').value = '2';
      $('rule-window-hours').value = '1';
      $('rule-time-field').value = '@timestamp';
      $('rule-interval').value = '3600';
      $('rule-cooldown').value = '3600';
      $('rule-notify-channel').value = 'email';
      $('rule-notify-target').value = '';
    }
    function ruleFromForm() {
      const name = $('rule-name').value.trim();
      if (!name) throw new Error('Укажите название');
      const entry = {
        name,
        enabled: $('rule-enabled').checked,
        mcp_source: $('rule-mcp-source').value,
        index: $('rule-index').value.trim() || '*',
        query: $('rule-query').value.trim() || 'level:ERROR',
        condition: $('rule-condition').value,
        threshold: parseInt($('rule-threshold').value, 10) || 1,
        window_hours: parseFloat($('rule-window-hours').value) || 1,
        time_field: ($('rule-time-field').value || '@timestamp').trim(),
        interval_sec: parseInt($('rule-interval').value, 10),
        cooldown_sec: parseInt($('rule-cooldown').value, 10),
        group_id: $('rule-group').value,
        description: $('rule-desc').value.trim(),
        notify_channel: $('rule-notify-channel').value,
        notify_target: $('rule-notify-target').value.trim(),
      };
      const eid = $('rule-edit-id').value.trim();
      if (eid) entry.id = eid;
      return entry;
    }
    function fillFormFromRule(r) {
      $('rule-edit-id').value = r.id || '';
      $('rule-enabled').checked = r.enabled !== false;
      $('rule-name').value = r.name || '';
      $('rule-desc').value = r.description || '';
      $('rule-mcp-source').value = r.mcp_source || 'opensearch';
      let idxVal = r.index || '';
      if (!idxVal && r.params) {
        const im = String(r.params).match(/index\s+(\S+)/i);
        if (im) idxVal = im[1];
      }
      $('rule-index').value = idxVal;
      let qVal = r.query || '';
      if (!qVal && r.params) {
        const m = String(r.params).match(/query\s+(.+)$/i);
        if (m) qVal = m[1].trim();
      }
      $('rule-query').value = qVal;
      $('rule-condition').value = r.condition || 'count_threshold';
      $('rule-threshold').value = String(r.threshold != null ? r.threshold : 2);
      $('rule-window-hours').value = String(r.window_hours != null ? r.window_hours : 1);
      $('rule-time-field').value = r.time_field || '@timestamp';
      $('rule-interval').value = String(r.interval_sec || 3600);
      $('rule-cooldown').value = String(r.cooldown_sec || 3600);
      $('rule-notify-channel').value = r.notify_channel || 'email';
      $('rule-notify-target').value = r.notify_target || '';
      refreshGroupSelect();
      if (r.group_id) $('rule-group').value = r.group_id;
    }
    function renderRulesList() {
      const el = $('alert-rules-list');
      if (!rulesCache.length) {
        el.innerHTML = '<p class="muted">Нет правил — заполните форму и нажмите «Сохранить».</p>';
        return;
      }
      const rows = rulesCache.map((r) => {
        const dis = r.enabled === false ? ' rule-disabled' : '';
        const ch = r.notify_channel || 'email';
        const tgt = (r.notify_target || '(из группы/конфига)').slice(0, 40);
        return '<tr class="' + dis + '"><td><strong>' + (r.name || '—') + '</strong><br><span class="muted">' +
          (r.index || '*') + ' · ' + (r.query || '').slice(0, 50) + '</span></td>' +
          '<td>' + ch + '<br><span class="muted">' + tgt + '</span></td>' +
          '<td><button type="button" class="btn-link" data-edit="' + (r.id || r.name) + '">Изменить</button> ' +
          '<button type="button" class="btn-link" data-del="' + (r.id || r.name) + '">Удалить</button></td></tr>';
      }).join('');
      el.innerHTML = '<table class="rules-table"><thead><tr><th>Правило</th><th>Доставка</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>';
      el.querySelectorAll('[data-edit]').forEach((btn) => {
        btn.onclick = () => {
          const key = btn.getAttribute('data-edit');
          const r = rulesCache.find((x) => (x.id || x.name) === key);
          if (r) fillFormFromRule(r);
        };
      });
      el.querySelectorAll('[data-del]').forEach((btn) => {
        btn.onclick = () => {
          const key = btn.getAttribute('data-del');
          if (!confirm('Удалить правило?')) return;
          rulesCache = rulesCache.filter((x) => (x.id || x.name) !== key);
          saveRulesToServer().catch((e) => alert(e));
        };
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
      if (!sel.value && sel.options.length) sel.value = 'opensearch';
    }
    function ruleRowHtml(r) {
      const cls = { inactive: 'rule-inactive', ok: 'rule-ok', error: 'rule-error', firing: 'rule-firing' }[r.ui_state] || 'rule-inactive';
      const h = r.health || {};
      return '<div class="rule-row"><span class="rule-dot ' + cls + '"></span><div><strong>' + (r.name || '—') + '</strong> · ' +
        (r.mcp_source || '') + (r.enabled === false ? ' · <em>выкл.</em>' : '') + '<br><span class="muted">' + (h.label || '') + ': ' + (h.detail || '') +
        (r.evaluation && r.evaluation.detail ? ' · ' + r.evaluation.detail : '') + '</span></div></div>';
    }
    function notifyLogHtml(entries) {
      if (!entries || !entries.length) return '<p class="muted">Пока нет попыток доставки на этом поде.</p>';
      return '<table class="rules-table"><thead><tr><th>Время</th><th>Правило</th><th>Канал</th><th>Результат</th></tr></thead><tbody>' +
        entries.slice().reverse().map((e) => {
          const cls = e.ok ? 'notify-ok' : 'notify-fail';
          const res = e.ok ? '✓ ' + (e.detail || 'ok') : '✗ ' + (e.detail || 'error');
          return '<tr><td>' + (e.at || '') + '</td><td>' + (e.rule_name || '—') + '</td><td>' + (e.channel || '') +
            '<br><span class="muted">' + (e.target || '') + '</span></td><td class="' + cls + '">' + res + '</td></tr>';
        }).join('') + '</tbody></table>';
    }
    async function refreshStatuses() {
      const st = await jget('/api/alerts/status');
      $('alerts-leader').textContent = st.leader
        ? ('Лидер проверок и доставки: этот под (' + st.instance + ')')
        : ('Лидер: другой под · этот: ' + st.instance);
      $('alert-rules-status').innerHTML = (st.rules || []).length ? (st.rules || []).map(ruleRowHtml).join('') : '<p class="muted">Нет правил</p>';
    }
    async function refreshNotifyLog() {
      try {
        const data = await jget('/api/alerts/notify-log?limit=40');
        $('alert-notify-log').innerHTML = notifyLogHtml(data.entries || []);
      } catch (_) {
        $('alert-notify-log').innerHTML = '<p class="muted">Журнал недоступен</p>';
      }
    }
    async function saveRulesToServer() {
      const groups = parseGroups();
      const res = await jpost('/api/alerts/rules', { groups, rules: rulesCache });
      rulesCache = res.rules || rulesCache;
      $('alert-save-msg').textContent = 'Сохранено, revision=' + res.revision + (res.kafka_published ? ', Kafka OK' : ', Kafka пропущен');
      renderRulesList();
      await refreshStatuses();
    }
    async function saveAll() {
      const entry = ruleFromForm();
      const eid = entry.id;
      const idx = rulesCache.findIndex((x) => (eid && x.id === eid) || (!eid && x.name === entry.name));
      if (idx >= 0) rulesCache[idx] = { ...rulesCache[idx], ...entry };
      else rulesCache.push(entry);
      await saveRulesToServer();
    }
    async function loadFromServer() {
      const snap = await jget('/api/alerts/rules');
      if (snap.groups) $('alert-groups').value = groupsPretty(snap.groups);
      rulesCache = snap.rules || [];
      renderRulesList();
      refreshGroupSelect();
    }
    function loadExample() {
      $('alert-groups').value = groupsPretty([
        { id: 'support', name: 'Сопровождение', emails: 'oncall@example.com', hours_msk: '08:00-18:00' }
      ]);
      rulesCache = [{
        name: '404 ERROR в ms-logs',
        mcp_source: 'opensearch',
        index: 'ms-logs',
        query: 'level:ERROR AND message:*404*',
        condition: 'count_threshold',
        threshold: 2, window_hours: 1, interval_sec: 3600, cooldown_sec: 3600,
        group_id: 'support', description: 'Более 2 ERROR с 404 за час',
        notify_channel: 'email', notify_target: '', enabled: true,
      }];
      fillFormFromRule(rulesCache[0]);
      renderRulesList();
    }
    (async function boot() {
      try { await loadFromServer(); } catch (_) {}
      $('btn-groups-format').onclick = () => { $('alert-groups').value = groupsPretty(parseGroups()); refreshGroupSelect(); };
      $('btn-alert-save').onclick = () => saveAll().catch((e) => { $('alert-save-msg').textContent = String(e); });
      $('btn-alert-clear').onclick = () => clearRuleForm();
      $('btn-alert-refresh').onclick = () => { refreshStatuses(); refreshNotifyLog(); };
      $('btn-alert-load-example').onclick = () => loadExample();
      await loadConfigBanner();
      await loadMcpSources();
      await refreshStatuses();
      await refreshNotifyLog();
      setInterval(() => { refreshStatuses().catch(() => {}); refreshNotifyLog().catch(() => {}); }, 45000);
      setInterval(() => { loadConfigBanner().catch(() => {}); }, 60000);
    })();
"""

ALERTS_PAGE_HTML = build_subpage_html(
    title="Alert — sdocs-mcp",
    page="alerts",
    body_html=_ALERTS_BODY,
    extra_script=_ALERTS_SCRIPT,
)
