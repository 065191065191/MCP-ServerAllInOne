"""Страница Alert: правила оповещений (UI, localStorage; рассылка через MCP mail)."""

from __future__ import annotations

from sdocs_mcp.ui_interval_options import render_interval_options
from sdocs_mcp.ui_subpage_layout import build_subpage_html

_RULE_INTERVAL_OPTS = render_interval_options(
    default_seconds=3600, selected=3600, include_custom=False
)

_ALERTS_BODY = f"""
  <header class="page-head">
    <h1>Alert — оповещения</h1>
    <p class="lede">Правила реагируют на данные (OpenSearch, Prometheus). Рассылка — через MCP <code>mail_smtp_send</code> на группы ниже.</p>
  </header>
  <div class="alerts-grid">
    <section class="panel">
      <h3 class="section-title" style="margin-top:0;">Как добавлять алерты</h3>
      <ul class="muted" style="margin:0;padding-left:1.1rem;line-height:1.55;">
        <li>Опишите <strong>источник</strong>: индекс OpenSearch, запрос Prometheus и т.д.</li>
        <li>Задайте <strong>условие</strong> (порог, окно времени).</li>
        <li>Выберите <strong>группу</strong> с почтами и рабочим временем (МСК).</li>
        <li>Укажите <strong>интервал</strong> проверки — не чаще, чем позволяет нагрузка на источник.</li>
        <li>Сохраните правило; доставка — через MCP при срабатывании (модуль mail).</li>
      </ul>
      <p class="section-note" style="margin-top:0.85rem;">Сейчас настройки хранятся в браузере (localStorage). API сохранения на сервере — в следующих версиях.</p>
    </section>
    <section class="panel groups-editor">
      <h3 class="section-title" style="margin-top:0;">Группы и рабочее время</h3>
      <p class="section-note">Список получателей в JSON (по одному объекту на строку). Поля: <code>id</code>, <code>name</code>, <code>emails</code>, <code>hours_msk</code> (например <code>08:00-18:00</code>).</p>
      <textarea id="alert-groups" rows="14" spellcheck="false" wrap="off"></textarea>
      <motion class="btn-row" style="margin-top:0.5rem;">
        <button type="button" id="btn-groups-format">Форматировать JSON</button>
      </motion>
    </section>
    <section class="panel alerts-grid-full">
      <h3 class="section-title" style="margin-top:0;">Правило</h3>
      <div class="form-grid">
        <label>Название<input type="text" id="rule-name" placeholder="HTTP 500 в ms-logs" /></label>
        <label>Источник (откуда брать данные)<input type="text" id="rule-source" placeholder="opensearch:index ms-logs | query: status:500" /></label>
        <label>Условие / порог<input type="text" id="rule-condition" placeholder="count &gt;= 1 за 1ч; критично если &gt;= 10" /></label>
        <label>Как часто проверять<select id="rule-interval" class="interval-select-wide">
{_RULE_INTERVAL_OPTS}
        </select></label>
        <label>Группа рассылки<select id="rule-group"></select></label>
        <label>Описание для письма<textarea id="rule-desc" rows="3" placeholder="Текст в уведомлении"></textarea></label>
      </div>
      <div class="example-box">
        <strong>Пример:</strong> OpenSearch <code>ms-logs</code>, HTTP 500 за час: если ≥1 — алерт группе «Сопровождение» (08:00–18:00 МСК);
        если ≥10 — дополнительно «Админы» (18:00–07:00 МСК). Проверка раз в час через MCP OpenSearch + mail.
      </div>
      <div class="btn-row">
        <button type="button" class="primary" id="btn-alert-save">Сохранить в браузере</button>
        <button type="button" id="btn-alert-load-example">Загрузить пример</button>
      </motion>
      <p class="muted" id="alert-save-msg" style="margin-top:0.5rem;"></p>
      <h3 class="section-title">Сохранённые правила</h3>
      <pre id="alert-rules-list">—</pre>
    </section>
  </div>
""".replace("</motion>", "</div>").replace("<motion", "<div")

_ALERTS_SCRIPT = r"""
    const LS_GROUPS = 'sdocs_mcp_alert_groups';
    const LS_RULES = 'sdocs_mcp_alert_rules';
    const $ = (id) => document.getElementById(id);

    const EXAMPLE_GROUPS = [
      { id: 'support', name: 'Сопровождение', emails: 'oncall@example.com', hours_msk: '08:00-18:00' },
      { id: 'admins', name: 'Админы', emails: 'admins@example.com', hours_msk: '18:00-07:00' }
    ];
    const EXAMPLE_RULES = [
      {
        name: 'HTTP 500 в ms-logs (час)',
        source: 'opensearch:index ms-logs query status:500',
        condition: 'count >= 1 per 1h; critical if count >= 10',
        interval_sec: 3600,
        group_id: 'support',
        description: 'Ошибки 500 в ms-logs за последний час',
        escalate_group_id: 'admins',
        escalate_when: 'count >= 10'
      }
    ];

    function parseGroups() {
      try { return JSON.parse($('alert-groups').value || '[]'); } catch (e) { throw new Error('Группы: невалидный JSON'); }
    }
    function groupsToPrettyText(groups) {
      return JSON.stringify(groups, null, 2);
    }
    function formatGroupsTextarea() {
      $('alert-groups').value = groupsToPrettyText(parseGroups());
    }
    function refreshGroupSelect() {
      const sel = $('rule-group');
      const groups = parseGroups();
      sel.innerHTML = '';
      groups.forEach((g) => {
        const o = document.createElement('option');
        o.value = g.id;
        o.textContent = (g.name || g.id) + ' (' + (g.hours_msk || '—') + ')';
        sel.appendChild(o);
      });
    }
    function renderRulesList() {
      const rules = JSON.parse(localStorage.getItem(LS_RULES) || '[]');
      $('alert-rules-list').textContent = rules.length ? JSON.stringify(rules, null, 2) : '—';
    }
    function saveAll() {
      const groups = parseGroups();
      localStorage.setItem(LS_GROUPS, JSON.stringify(groups));
      $('alert-groups').value = groupsToPrettyText(groups);
      const rules = JSON.parse(localStorage.getItem(LS_RULES) || '[]');
      const entry = {
        name: $('rule-name').value.trim(),
        source: $('rule-source').value.trim(),
        condition: $('rule-condition').value.trim(),
        interval_sec: parseInt($('rule-interval').value, 10),
        group_id: $('rule-group').value,
        description: $('rule-desc').value.trim(),
      };
      if (!entry.name) throw new Error('Укажите название правила');
      const idx = rules.findIndex((r) => r.name === entry.name);
      if (idx >= 0) rules[idx] = entry; else rules.push(entry);
      localStorage.setItem(LS_RULES, JSON.stringify(rules));
      refreshGroupSelect();
      renderRulesList();
      $('alert-save-msg').textContent = 'Сохранено в localStorage (' + new Date().toLocaleString() + ').';
    }
    function loadExample() {
      $('alert-groups').value = groupsToPrettyText(EXAMPLE_GROUPS);
      localStorage.setItem(LS_RULES, JSON.stringify(EXAMPLE_RULES));
      $('rule-name').value = EXAMPLE_RULES[0].name;
      $('rule-source').value = EXAMPLE_RULES[0].source;
      $('rule-condition').value = EXAMPLE_RULES[0].condition;
      $('rule-interval').value = String(EXAMPLE_RULES[0].interval_sec);
      $('rule-desc').value = EXAMPLE_RULES[0].description;
      refreshGroupSelect();
      $('rule-group').value = EXAMPLE_RULES[0].group_id;
      renderRulesList();
    }
    (function boot() {
      const g = localStorage.getItem(LS_GROUPS);
      if (g) {
        try { $('alert-groups').value = groupsToPrettyText(JSON.parse(g)); } catch (e) { $('alert-groups').value = g; }
      } else {
        $('alert-groups').value = groupsToPrettyText(EXAMPLE_GROUPS);
      }
      $('alert-groups').addEventListener('blur', () => {
        try { formatGroupsTextarea(); refreshGroupSelect(); } catch (_) { /* оставить как ввёл */ }
      });
      $('btn-groups-format').onclick = () => { try { formatGroupsTextarea(); refreshGroupSelect(); } catch (e) { alert(e); } };
      $('btn-alert-save').onclick = () => { try { formatGroupsTextarea(); saveAll(); } catch (e) { alert(e); } };
      $('btn-alert-load-example').onclick = () => loadExample();
      refreshGroupSelect();
      renderRulesList();
    })();
"""

ALERTS_PAGE_HTML = build_subpage_html(
    title="Alert — sdocs-mcp",
    page="alerts",
    body_html=_ALERTS_BODY,
    extra_script=_ALERTS_SCRIPT,
)
