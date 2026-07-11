const state = {
  panel: "overview",
  pricingTab: "classes",
  catalogCategory: "style",
  escLogFilter: "",
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "same-origin",
    ...options,
  });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 2400);
}

function showPanel(name) {
  state.panel = name;
  $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.panel === name));
  $("#back-menu-btn").classList.toggle("hidden", name === "overview");
  if (name === "overview") loadSummary();
  if (name === "orders") {
    const search = $("#orders-search");
    if (search && search.value.trim() === "admin") search.value = "";
    loadOrders();
  }
  if (name === "faq") loadFaq();
  if (name === "escalation") loadEscalation();
  if (name === "pricing") loadPricing();
  if (name === "catalog") loadCatalog();
  if (name === "settings") loadSettings();
  if (name === "managers") loadManagers();
  if (name === "escalation-log") loadEscalationLog();
}

function openModal(title, fields, onSubmit) {
  $("#modal-title").textContent = title;
  const form = $("#modal-form");
  form.innerHTML = fields
    .map((f) => {
      if (f.type === "textarea") {
        return `<label><span>${f.label}</span><textarea name="${f.name}" ${f.required ? "required" : ""}>${f.value || ""}</textarea></label>`;
      }
      if (f.type === "checkbox") {
        return `<label class="switch"><input type="checkbox" name="${f.name}" ${f.value ? "checked" : ""} /><span>${f.label}</span></label>`;
      }
      return `<label><span>${f.label}</span><input name="${f.name}" type="${f.type || "text"}" value="${f.value ?? ""}" ${f.required ? "required" : ""} /></label>`;
    })
    .join("");
  form.innerHTML += `<button class="btn btn-primary" type="submit">Сохранить</button>`;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const data = new FormData(form);
    const payload = {};
    fields.forEach((f) => {
      if (f.type === "checkbox") payload[f.name] = !!form.querySelector(`[name="${f.name}"]`).checked;
      else payload[f.name] = data.get(f.name);
    });
    await onSubmit(payload);
    closeModal();
  };
  $("#modal").classList.remove("hidden");
}

function closeModal() {
  $("#modal").classList.add("hidden");
}

async function loadSummary() {
  const data = await api("/api/summary");
  $("#stats-grid").innerHTML = `
    <div class="stat-card"><div class="stat-value">${data.new_leads}</div><div class="stat-label">Новые за 24ч</div></div>
    <div class="stat-card"><div class="stat-value">${data.escalated}</div><div class="stat-label">Эскалации</div></div>
    <div class="stat-card"><div class="stat-value">${data.new_orders ?? 0}</div><div class="stat-label">Заявки 24ч</div></div>
    <div class="stat-card"><div class="stat-value">${data.orders_count ?? 0}</div><div class="stat-label">Всего заявок</div></div>
    <div class="stat-card"><div class="stat-value">${data.activity}</div><div class="stat-label">Сообщения</div></div>
    <div class="stat-card"><div class="stat-value">${data.escalation_cases_24h ?? 0}</div><div class="stat-label">Эскалации 24ч</div></div>
    <div class="stat-card"><div class="stat-value">${data.escalation_with_order ?? 0}</div><div class="stat-label">С заказом</div></div>
    <div class="stat-card"><div class="stat-value">${(data.escalation_cases_count ?? 0) - (data.escalation_with_order ?? 0)}</div><div class="stat-label">Без заказа</div></div>
  `;
}

function fmtMoney(v) {
  if (v == null) return "—";
  return `${Math.round(v).toLocaleString("ru-RU")} ₽`;
}

function fmtDt(v) {
  if (!v) return "—";
  const d = new Date(v);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function loadOrders() {
  const q = $("#orders-search").value.trim();
  const items = await api(`/api/orders?q=${encodeURIComponent(q)}`);
  $("#order-detail").classList.add("hidden");
  $("#orders-list").innerHTML = items.length
    ? items
        .map(
          (item) => `
      <div class="item order-item">
        <div class="item-head">
          <div>
            <div class="item-title">#${item.id} · ${item.phone || "—"} · ${fmtMoney(item.estimate_total)}</div>
            <div class="item-meta">${fmtDt(item.created_at)} · ${item.style_title || item.style_code || "—"} · ${item.shape || "—"}</div>
          </div>
          <button class="btn btn-ghost btn-sm" data-order-open="${item.id}">Открыть</button>
        </div>
      </div>`
        )
        .join("")
    : q
      ? `<div class="item"><div class="item-meta">По запросу «${q}» ничего не найдено. <button type="button" class="btn btn-ghost btn-sm" id="orders-search-reset">Сбросить</button></div></div>`
      : `<div class="item"><div class="item-meta">Заявок пока нет</div></div>`;
  const resetBtn = $("#orders-search-reset");
  if (resetBtn) {
    resetBtn.onclick = () => {
      $("#orders-search").value = "";
      loadOrders();
    };
  }
  $$("[data-order-open]").forEach((btn) => {
    btn.onclick = () => openOrder(Number(btn.dataset.orderOpen));
  });
}

async function openOrder(orderId) {
  const data = await api(`/api/orders/${orderId}`);
  const o = data.order;
  const dialogs = data.dialogs || [];
  $("#order-detail").classList.remove("hidden");
  $("#order-detail").innerHTML = `
    <h3>Заявка #${o.id}</h3>
    <div class="order-grid">
      <div><span class="muted">Статус</span><div>${o.status}</div></div>
      <div><span class="muted">Дата</span><div>${fmtDt(o.created_at)}</div></div>
      <div><span class="muted">Телефон</span><div>${o.phone || "—"}</div></div>
      <div><span class="muted">Клиент</span><div>${o.full_name || "—"} ${o.username ? `(${o.username})` : ""}</div></div>
      <div><span class="muted">User ID</span><div>${o.user_id || "—"}</div></div>
      <div><span class="muted">Ориентир</span><div>${fmtMoney(o.estimate_total)}</div></div>
      <div><span class="muted">Стиль</span><div>${o.style_title || o.style_code || "—"}</div></div>
      <div><span class="muted">Длина</span><div>${o.length_m != null ? `${o.length_m} м` : "—"}</div></div>
      <div><span class="muted">Планировка</span><div>${o.shape || "—"}</div></div>
      <div><span class="muted">Фасады</span><div>${o.facade_title || o.facade_code || "—"}</div></div>
      <div><span class="muted">Столешница</span><div>${o.countertop_title || o.countertop_code || "—"}</div></div>
      <div><span class="muted">Фурнитура</span><div>${o.hardware_title || o.hardware_code || "—"}</div></div>
    </div>
    <h4>Диалог</h4>
    <div class="dialog-list">
      ${dialogs
        .map(
          (d) => `<div class="dialog-line"><span class="muted">${fmtDt(d.created_at)} · ${d.source}</span><div>${d.text}</div></div>`
        )
        .join("") || '<div class="muted">Сообщений нет</div>'}
    </div>
  `;
  $("#order-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadFaq() {
  const q = $("#faq-search").value.trim();
  const items = await api(`/api/faq?q=${encodeURIComponent(q)}`);
  $("#faq-list").innerHTML = items
    .map(
      (item) => `
      <div class="item">
        <div class="item-head">
          <div>
            <div class="item-title">${item.key} ${item.is_active ? "" : '<span class="badge off">off</span>'}</div>
            <div class="item-meta">${item.answer}</div>
          </div>
          <button class="btn btn-ghost btn-sm" data-faq-edit="${item.key}">Изменить</button>
        </div>
      </div>`
    )
    .join("");
  $$("[data-faq-edit]").forEach((btn) => {
    btn.onclick = () => editFaq(btn.dataset.faqEdit, items.find((i) => i.key === btn.dataset.faqEdit));
  });
}

async function editFaq(key, item) {
  openModal(
    `FAQ: ${key}`,
    [
      { name: "answer", label: "Ответ", type: "textarea", value: item?.answer || "", required: true },
      { name: "is_active", label: "Активен", type: "checkbox", value: item?.is_active ?? true },
    ],
    async (payload) => {
      await api(`/api/faq/${encodeURIComponent(key)}`, {
        method: "PUT",
        body: JSON.stringify({ answer: payload.answer, is_active: payload.is_active }),
      });
      toast("FAQ сохранён");
      loadFaq();
    }
  );
}

async function loadEscalation() {
  const q = $("#esc-search").value.trim();
  const items = await api(`/api/escalation?q=${encodeURIComponent(q)}`);
  $("#esc-list").innerHTML = items
    .map(
      (item) => `
      <div class="item">
        <div class="item-head">
          <div class="item-title">${item.keyword}</div>
          <label class="switch">
            <input type="checkbox" data-esc-toggle="${item.keyword}" ${item.is_active ? "checked" : ""} />
            <span>${item.is_active ? "вкл" : "выкл"}</span>
          </label>
        </div>
      </div>`
    )
    .join("");
  $$("[data-esc-toggle]").forEach((el) => {
    el.onchange = async () => {
      await api(`/api/escalation/${encodeURIComponent(el.dataset.escToggle)}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: el.checked }),
      });
      toast("Триггер обновлён");
      loadEscalation();
    };
  });
}

async function loadPricing() {
  const q = $("#pricing-search").value.trim();
  const [classes, tops, fees] = await Promise.all([
    api(`/api/product-classes?q=${encodeURIComponent(q)}`),
    api(`/api/countertops?q=${encodeURIComponent(q)}`),
    api("/api/service-fees"),
  ]);

  $("#pricing-classes").innerHTML = classes
    .map(
      (item) => `
      <div class="item">
        <div class="item-head">
          <div>
            <div class="item-title">${item.code}</div>
            <div class="item-meta">от ${Number(item.price_from).toLocaleString("ru-RU")} ₽/п.м.</div>
          </div>
          <button class="btn btn-ghost btn-sm" data-class-edit="${item.code}">Изменить</button>
        </div>
      </div>`
    )
    .join("");

  $("#pricing-tops").innerHTML = tops
    .map(
      (item) => `
      <div class="item">
        <div class="item-head">
          <div>
            <div class="item-title">${item.code}</div>
            <div class="item-meta">от ${Number(item.price_from).toLocaleString("ru-RU")} ₽/п.м.</div>
          </div>
          <button class="btn btn-ghost btn-sm" data-top-edit="${item.code}">Изменить</button>
        </div>
      </div>`
    )
    .join("");

  $("#pricing-fees").innerHTML = fees
    .map(
      (item) => `
      <div class="item">
        <div class="item-head">
          <div>
            <div class="item-title">${item.label}</div>
            <div class="item-meta">${item.code}: ${item.value}</div>
          </div>
          <button class="btn btn-ghost btn-sm" data-fee-edit="${item.code}">Изменить</button>
        </div>
      </div>`
    )
    .join("");

  $$("[data-class-edit]").forEach((btn) => {
    const item = classes.find((i) => i.code === btn.dataset.classEdit);
    btn.onclick = () =>
      openModal(`Класс: ${item.code}`, [
        { name: "price_from", label: "Цена от, ₽/п.м.", type: "number", value: item.price_from, required: true },
        { name: "is_active", label: "Активен", type: "checkbox", value: item.is_active },
      ], async (payload) => {
        await api(`/api/product-classes/${encodeURIComponent(item.code)}`, {
          method: "PUT",
          body: JSON.stringify({ price_from: Number(payload.price_from), is_active: payload.is_active }),
        });
        toast("Класс сохранён");
        loadPricing();
      });
  });

  $$("[data-top-edit]").forEach((btn) => {
    const item = tops.find((i) => i.code === btn.dataset.topEdit);
    btn.onclick = () =>
      openModal(`Столешница: ${item.code}`, [
        { name: "price_from", label: "Цена от, ₽/п.м.", type: "number", value: item.price_from, required: true },
        { name: "is_active", label: "Активен", type: "checkbox", value: item.is_active },
      ], async (payload) => {
        await api(`/api/countertops/${encodeURIComponent(item.code)}`, {
          method: "PUT",
          body: JSON.stringify({ price_from: Number(payload.price_from), is_active: payload.is_active }),
        });
        toast("Столешница сохранена");
        loadPricing();
      });
  });

  $$("[data-fee-edit]").forEach((btn) => {
    const item = fees.find((i) => i.code === btn.dataset.feeEdit);
    btn.onclick = () =>
      openModal(item.label, [
        { name: "value", label: "Значение", type: "number", value: item.value, required: true },
        { name: "is_active", label: "Активен", type: "checkbox", value: item.is_active },
      ], async (payload) => {
        await api(`/api/service-fees/${encodeURIComponent(item.code)}`, {
          method: "PUT",
          body: JSON.stringify({ value: Number(payload.value), is_active: payload.is_active }),
        });
        toast("Сбор сохранён");
        loadPricing();
      });
  });
}

async function loadCatalog() {
  const q = $("#catalog-search").value.trim();
  const cat = state.catalogCategory;
  const items = await api(`/api/catalog/${cat}?q=${encodeURIComponent(q)}`);
  $("#catalog-grid").innerHTML = items
    .map((item) => {
      const preview = item.image_thumb_path || item.image_path;
      const cacheBust = item.updated_at ? `?v=${encodeURIComponent(item.updated_at)}` : "";
      const img = preview
        ? `<img src="${preview}${cacheBust}" alt="${item.title}" />`
        : `<img src="/static/placeholder.svg" alt="нет фото" />`;
      const price = item.price_from != null ? `${Number(item.price_from).toLocaleString("ru-RU")} ₽` : "—";
      return `
      <article class="catalog-card">
        ${img}
        <div class="body">
          <div class="title">${item.title}</div>
          <div class="item-meta">${item.code} · ${price}</div>
          <div class="item-meta">${item.description || ""}</div>
          <div class="actions">
            <button class="btn btn-ghost btn-sm" data-catalog-edit="${item.id}">Изменить</button>
            <label class="btn btn-ghost btn-sm">
              Фото
              <input type="file" hidden accept="image/*" data-catalog-upload="${item.id}" />
            </label>
          </div>
        </div>
      </article>`;
    })
    .join("");

  $$("[data-catalog-edit]").forEach((btn) => {
    const item = items.find((i) => String(i.id) === btn.dataset.catalogEdit);
    btn.onclick = () => editCatalogItem(item);
  });

  $$("[data-catalog-upload]").forEach((input) => {
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      try {
        const res = await fetch(`/api/catalog/item/${input.dataset.catalogUpload}/image`, {
          method: "POST",
          body: fd,
          credentials: "same-origin",
        });
        if (res.status === 401) {
          window.location.href = "/login";
          return;
        }
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(detail || "upload failed");
        }
        toast("Фото загружено");
        loadCatalog();
      } catch (err) {
        toast(err instanceof Error ? err.message : "Ошибка загрузки");
      } finally {
        input.value = "";
      }
    };
  });
}

function editCatalogItem(item) {
  openModal(
    item ? `Каталог: ${item.title}` : "Новая позиция",
    [
      { name: "code", label: "Код", value: item?.code || "", required: true },
      { name: "title", label: "Название", value: item?.title || "", required: true },
      { name: "description", label: "Описание", type: "textarea", value: item?.description || "" },
      { name: "price_from", label: "Цена от, ₽", type: "number", value: item?.price_from ?? "" },
      { name: "sort_order", label: "Порядок", type: "number", value: item?.sort_order ?? 0 },
      { name: "is_active", label: "Активна", type: "checkbox", value: item?.is_active ?? true },
    ],
    async (payload) => {
      const body = {
        category: state.catalogCategory,
        code: payload.code,
        title: payload.title,
        description: payload.description,
        price_from: payload.price_from === "" ? null : Number(payload.price_from),
        sort_order: Number(payload.sort_order || 0),
        is_active: payload.is_active,
      };
      if (item) {
        await api(`/api/catalog/item/${item.id}`, { method: "PUT", body: JSON.stringify(body) });
      } else {
        await api(`/api/catalog/${state.catalogCategory}`, { method: "POST", body: JSON.stringify(body) });
      }
      toast("Каталог сохранён");
      loadCatalog();
    }
  );
}

async function loadSettings() {
  const settings = await api("/api/settings");
  $("#timezone-select").value = settings.timezone || "Asia/Irkutsk";
  $("#brand-name-input").value = settings.brand_name || "";
  $("#brand-city-input").value = settings.brand_city || "";
  try {
    const managers = await api("/api/managers");
    $("#abandon-timeout-input").value = Math.max(10, managers.abandon_timeout_minutes ?? 10);
  } catch {
    $("#abandon-timeout-input").value = 10;
  }
  const audit = await api("/api/audit?limit=30");
  $("#audit-list").innerHTML = audit
    .map(
      (row) => `
      <div class="item">
        <div class="item-title">${row.entity} · ${row.entity_key}</div>
        <div class="item-meta">${row.created_at || ""}</div>
      </div>`
    )
    .join("");
}

const ROUTE_LABELS = {
  sales: "Продажи / заказы",
  technical: "Техника / монтаж",
  duty: "Жалобы / дежурный",
};

function renderManagerCard(manager, index) {
  const routes = manager.routes || [];
  const routeChecks = Object.entries(ROUTE_LABELS)
    .map(
      ([key, label]) => `
      <label class="inline-check">
        <input type="checkbox" data-route="${key}" data-index="${index}" ${routes.includes(key) ? "checked" : ""} />
        ${label}
      </label>`
    )
    .join("");
  return `
    <div class="card stack manager-card" data-manager-index="${index}">
      <div class="item-title">${manager.name || "Менеджер"}</div>
      <label><span>ID</span><input data-field="id" data-index="${index}" value="${manager.id || ""}" /></label>
      <label><span>ФИО</span><input data-field="name" data-index="${index}" value="${manager.name || ""}" /></label>
      <label><span>Краткое имя (в ответе бота)</span><input data-field="short_name" data-index="${index}" value="${manager.short_name || ""}" /></label>
      <label><span>Роль</span><input data-field="role" data-index="${index}" value="${manager.role || ""}" /></label>
      <label><span>Телефон</span><input data-field="phone" data-index="${index}" value="${manager.phone || ""}" /></label>
      <label><span>Telegram</span><input data-field="telegram" data-index="${index}" value="${manager.telegram || ""}" placeholder="@username" /></label>
      <label><span>Email</span><input data-field="email" data-index="${index}" value="${manager.email || ""}" /></label>
      <label><span>График (подпись)</span><input data-field="schedule_label" data-index="${index}" value="${manager.schedule_label || ""}" /></label>
      <div class="chip-row">${routeChecks}</div>
    </div>`;
}

let managersState = null;

async function loadManagers() {
  managersState = await api("/api/managers");
  const office = managersState.office_hours || {};
  const monFri = office.mon_fri || { start: 9, end: 18 };
  const sat = office.sat || { start: 9, end: 19 };
  $("#office-mon-fri-start").value = monFri.start ?? 9;
  $("#office-mon-fri-end").value = monFri.end ?? 18;
  $("#office-sat-start").value = sat.start ?? 9;
  $("#office-sat-end").value = sat.end ?? 19;
  $("#sla-minutes-input").value = managersState.sla_minutes ?? 15;
  const dutySelect = $("#duty-manager-select");
  dutySelect.innerHTML = (managersState.managers || [])
    .map((m) => `<option value="${m.id}">${m.short_name || m.name}</option>`)
    .join("");
  dutySelect.value = managersState.duty_manager_id || (managersState.managers?.[0]?.id || "");
  $("#managers-list").innerHTML = (managersState.managers || [])
    .map((manager, index) => renderManagerCard(manager, index))
    .join("");
  const style = managersState.style || {};
  $("#style-sales").value = style.sales_handoff || "";
  $("#style-technical").value = style.technical_handoff || "";
  $("#style-complaint").value = style.complaint_handoff || "";
  $("#style-uncertain").value = style.uncertain_handoff || "";
}

function collectManagersPayload() {
  const cards = $$(".manager-card");
  const managers = cards.map((card) => {
    const index = card.dataset.managerIndex;
    const read = (field) => card.querySelector(`[data-field="${field}"][data-index="${index}"]`)?.value?.trim() || "";
    const routes = Array.from(card.querySelectorAll(`input[data-route][data-index="${index}"]:checked`)).map(
      (el) => el.dataset.route
    );
    return {
      id: read("id"),
      name: read("name"),
      short_name: read("short_name"),
      role: read("role"),
      phone: read("phone"),
      telegram: read("telegram"),
      email: read("email"),
      schedule_label: read("schedule_label"),
      routes: routes.length ? routes : ["sales"],
    };
  });
  return {
    office_hours: {
      mon_fri: {
        start: Number($("#office-mon-fri-start").value || 9),
        end: Number($("#office-mon-fri-end").value || 18),
      },
      sat: {
        start: Number($("#office-sat-start").value || 9),
        end: Number($("#office-sat-end").value || 19),
      },
      sun: null,
    },
    duty_manager_id: $("#duty-manager-select").value,
    sla_minutes: Number($("#sla-minutes-input").value || 15),
    abandon_timeout_minutes: Math.max(10, Number($("#abandon-timeout-input")?.value || 10)),
    managers,
    style: {
      greeting: managersState?.style?.greeting || "",
      sales_handoff: $("#style-sales").value.trim(),
      technical_handoff: $("#style-technical").value.trim(),
      complaint_handoff: $("#style-complaint").value.trim(),
      uncertain_handoff: $("#style-uncertain").value.trim(),
    },
  };
}

async function loadEscalationLog() {
  const q = $("#esc-log-search").value.trim();
  const filter = state.escLogFilter;
  let kind = "";
  let hasOrder = "";
  if (filter === "order") hasOrder = "yes";
  else if (filter === "no_order") hasOrder = "no";
  else if (filter === "abandoned_funnel") kind = "abandoned_funnel";
  const items = await api(
    `/api/escalation-cases?q=${encodeURIComponent(q)}&kind=${encodeURIComponent(kind)}&has_order=${encodeURIComponent(hasOrder)}`
  );
  $("#esc-log-detail").classList.add("hidden");
  $("#esc-log-list").innerHTML = items.length
    ? items
        .map(
          (item) => `
      <div class="item">
        <div class="item-head">
          <div>
            <div class="item-title">#${item.id} · ${item.kind_label || item.kind}${item.order_id ? ` · заказ #${item.order_id}` : ""}</div>
            <div class="item-meta">${fmtDt(item.created_at)} · ${item.full_name || "—"} · ${item.phone || "—"} · id ${item.user_id}</div>
            <div class="item-meta">${(item.summary || "").slice(0, 120)}${(item.summary || "").length > 120 ? "…" : ""}</div>
          </div>
          <button class="btn btn-ghost btn-sm" data-esc-open="${item.id}">Открыть</button>
        </div>
      </div>`
        )
        .join("")
    : `<div class="item"><div class="item-meta">Записей нет</div></div>`;
  $$("[data-esc-open]").forEach((btn) => {
    btn.onclick = () => openEscalationCase(Number(btn.dataset.escOpen));
  });
}

async function openEscalationCase(caseId) {
  const item = await api(`/api/escalation-cases/${caseId}`);
  const snap = item.funnel_snapshot || {};
  const snapLines = Object.entries(snap)
    .filter(([, v]) => v != null && v !== "" && v !== false)
    .map(([k, v]) => `<div>${k}: ${v}</div>`)
    .join("");
  $("#esc-log-detail").classList.remove("hidden");
  $("#esc-log-detail").innerHTML = `
    <h3>Эскалация #${item.id}</h3>
    <div class="order-grid">
      <div><span class="muted">Тип</span><div>${item.kind_label || item.kind}</div></div>
      <div><span class="muted">Дата</span><div>${fmtDt(item.created_at)}</div></div>
      <div><span class="muted">Менеджер</span><div>${item.manager_name || "—"}</div></div>
      <div><span class="muted">Заказ</span><div>${item.order_id ? `#${item.order_id}` : "—"}</div></div>
      <div><span class="muted">Клиент</span><div>${item.full_name || "—"} ${item.username || ""} · id ${item.user_id}</div></div>
      <div><span class="muted">Телефон</span><div>${item.phone || "—"}</div></div>
    </div>
    <pre class="summary-pre">${item.summary || ""}</pre>
    ${snapLines ? `<h4>Снимок воронки</h4><div class="stack small">${snapLines}</div>` : ""}
    ${item.order_id ? `<button class="btn btn-ghost btn-sm" type="button" id="esc-open-order">Открыть заявку #${item.order_id}</button>` : ""}
  `;
  const orderBtn = $("#esc-open-order");
  if (orderBtn) {
    orderBtn.onclick = () => {
      showPanel("orders");
      openOrder(item.order_id);
    };
  }
}

function bindUi() {
  $$(".nav-btn").forEach((btn) => {
    btn.onclick = () => showPanel(btn.dataset.panel);
  });
  $$("[data-go]").forEach((btn) => {
    btn.onclick = () => showPanel(btn.dataset.go);
  });
  $("#back-menu-btn").onclick = () => showPanel("overview");
  $$("[data-close-modal]").forEach((el) => {
    el.onclick = closeModal;
  });

  $("#faq-search").oninput = () => loadFaq();
  $("#orders-search").oninput = () => loadOrders();
  $("#esc-search").oninput = () => loadEscalation();
  $("#esc-log-search").oninput = () => loadEscalationLog();
  $("#esc-log-tabs").onclick = (e) => {
    const tab = e.target.closest(".tab");
    if (!tab) return;
    state.escLogFilter = tab.dataset.filter || "";
    $$("#esc-log-tabs .tab").forEach((t) => t.classList.toggle("active", t === tab));
    loadEscalationLog();
  };
  $("#pricing-search").oninput = () => loadPricing();
  $("#catalog-search").oninput = () => loadCatalog();

  $("#faq-add-btn").onclick = () =>
    openModal("Новый FAQ", [
      { name: "key", label: "Ключ (например: цена)", required: true },
      { name: "answer", label: "Ответ", type: "textarea", required: true },
      { name: "is_active", label: "Активен", type: "checkbox", value: true },
    ], async (payload) => {
      await api(`/api/faq/${encodeURIComponent(payload.key)}`, {
        method: "PUT",
        body: JSON.stringify({ answer: payload.answer, is_active: payload.is_active }),
      });
      toast("FAQ добавлен");
      loadFaq();
    });

  $("#esc-add-btn").onclick = () =>
    openModal("Новый триггер", [{ name: "keyword", label: "Слово/фраза", required: true }], async (payload) => {
      await api(`/api/escalation/${encodeURIComponent(payload.keyword)}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: true }),
      });
      toast("Триггер добавлен");
      loadEscalation();
    });

  $("#catalog-add-btn").onclick = () => editCatalogItem(null);

  $("#pricing-tabs").onclick = (e) => {
    const tab = e.target.closest(".tab");
    if (!tab) return;
    state.pricingTab = tab.dataset.tab;
    $$("#pricing-tabs .tab").forEach((t) => t.classList.toggle("active", t === tab));
    $$("#pricing-classes, #pricing-tops, #pricing-fees").forEach((panel) => panel.classList.remove("active"));
    const map = { classes: "#pricing-classes", tops: "#pricing-tops", fees: "#pricing-fees" };
    $(map[state.pricingTab]).classList.add("active");
  };

  $("#catalog-tabs").onclick = (e) => {
    const tab = e.target.closest(".tab");
    if (!tab) return;
    state.catalogCategory = tab.dataset.cat;
    $$("#catalog-tabs .tab").forEach((t) => t.classList.toggle("active", t === tab));
    loadCatalog();
  };

  $("#settings-save-btn").onclick = async () => {
    const entries = [
      ["timezone", $("#timezone-select").value],
      ["brand_name", $("#brand-name-input").value.trim()],
      ["brand_city", $("#brand-city-input").value.trim()],
    ];
    for (const [key, value] of entries) {
      await api(`/api/settings/${key}`, { method: "PUT", body: JSON.stringify({ value }) });
    }
    try {
      const managers = await api("/api/managers");
      managers.abandon_timeout_minutes = Math.max(10, Number($("#abandon-timeout-input").value || 10));
      await api("/api/managers", { method: "PUT", body: JSON.stringify(managers) });
      managersState = managers;
    } catch {
      toast("Настройки сохранены, но таймаут воронки не обновился");
      loadSettings();
      return;
    }
    toast("Настройки сохранены");
    loadSettings();
  };

  $("#managers-save-btn").onclick = async () => {
    try {
      const payload = collectManagersPayload();
      await api("/api/managers", { method: "PUT", body: JSON.stringify(payload) });
      toast("Менеджеры сохранены");
      loadManagers();
    } catch (err) {
      toast("Ошибка сохранения менеджеров");
    }
  };

  $("#password-save-btn").onclick = async () => {
    try {
      await api("/api/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: $("#pwd-current").value,
          new_password: $("#pwd-new").value,
          confirm_password: $("#pwd-confirm").value,
        }),
      });
      $("#pwd-current").value = "";
      $("#pwd-new").value = "";
      $("#pwd-confirm").value = "";
      toast("Пароль обновлён");
    } catch (err) {
      toast("Ошибка: проверьте текущий пароль");
    }
  };
}

bindUi();
showPanel("overview");
