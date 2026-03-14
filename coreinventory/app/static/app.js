const state = {
  token: localStorage.getItem('coreinventory_token') || null,
  user: null,
  categories: [],
  warehouses: [],
  locations: [],
  products: [],
  dashboardFilters: { doc_type: '', status: '', warehouse_id: '', category_id: '' },
  operationType: 'receipt',
  operationLines: [],
  productFilters: { search: '', category_id: '' },
  editingProductId: null,
};

const $ = (id) => document.getElementById(id);

function toMessage(value, fallback = 'Something went wrong') {
  if (value == null) return fallback;
  if (typeof value === 'string') return value;
  if (value instanceof Error) return value.message || fallback;
  if (typeof value === 'object') {
    if (typeof value.message === 'string') return value.message;
    if (typeof value.detail === 'string') return value.detail;
    if (Array.isArray(value.detail) && value.detail.length) {
      const first = value.detail[0];
      if (typeof first === 'string') return first;
      if (first && typeof first.msg === 'string') return first.msg;
    }
    try {
      return JSON.stringify(value);
    } catch {
      return fallback;
    }
  }
  return String(value);
}

function toast(msg) {
  const t = $('toast');
  t.textContent = toMessage(msg, 'Notification');
  t.classList.remove('hidden');
  setTimeout(() => t.classList.add('hidden'), 2600);
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;

  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = 'Request failed';
    if (typeof data?.detail === 'string') {
      msg = data.detail;
    } else if (Array.isArray(data?.detail) && data.detail.length > 0) {
      const first = data.detail[0];
      if (typeof first === 'string') {
        msg = first;
      } else if (first?.msg) {
        msg = first.msg;
      } else {
        msg = JSON.stringify(first);
      }
    } else if (data?.detail && typeof data.detail === 'object') {
      msg = data.detail.msg || JSON.stringify(data.detail);
    } else if (typeof data?.message === 'string') {
      msg = data.message;
    }
    throw new Error(msg);
  }
  return data;
}

function setAuthVisible(isAuth) {
  $('auth-screen').classList.toggle('hidden', !isAuth);
  $('app').classList.toggle('hidden', isAuth);
}

function setActiveAuthTab(tab) {
  ['login', 'signup', 'reset'].forEach((x) => {
    $(`tab-${x}`).classList.toggle('active', x === tab);
    $(`${x}-form`).classList.toggle('hidden', x !== tab);
  });
}

function setActiveView(view) {
  ['dashboard', 'products', 'operations', 'settings', 'profile'].forEach((v) => {
    $(`view-${v}`).classList.toggle('hidden', v !== view);
  });
  document.querySelectorAll('.nav-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.view === view);
  });
  $('page-title').textContent = view.charAt(0).toUpperCase() + view.slice(1);
}

function isManager() {
  return state.user?.role === 'manager';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function bootstrapData() {
  const [cats, whs, locs, prods] = await Promise.all([
    api('/api/categories'),
    api('/api/warehouses'),
    api('/api/locations'),
    api('/api/products'),
  ]);
  state.categories = cats;
  state.warehouses = whs;
  state.locations = locs;
  state.products = prods;
}

function options(items, valueKey = 'id', labelKey = 'name', includeAll = false) {
  let html = includeAll ? '<option value="">All</option>' : '<option value="">Select</option>';
  for (const item of items) {
    html += `<option value="${item[valueKey]}">${item[labelKey]}</option>`;
  }
  return html;
}

async function renderDashboard() {
  const f = state.dashboardFilters;
  const params = new URLSearchParams();
  if (f.doc_type) params.set('doc_type', f.doc_type);
  if (f.status) params.set('status', f.status);
  if (f.warehouse_id) params.set('warehouse_id', f.warehouse_id);
  if (f.category_id) params.set('category_id', f.category_id);

  const [kpis, docs, movements, lowStockAlerts] = await Promise.all([
    api(`/api/dashboard/kpis?${params}`),
    api(`/api/operations/documents?${params}`),
    api('/api/dashboard/recent-movements'),
    api(`/api/alerts/low-stock?${params}`),
  ]);

  $('view-dashboard').innerHTML = `
    <div class="card">
      <h3>Dynamic Filters</h3>
      <div class="filters">
        <select id="f-doc-type">
          <option value="">All Document Types</option>
          <option value="receipt">Receipts</option>
          <option value="delivery">Delivery</option>
          <option value="transfer">Internal</option>
          <option value="adjustment">Adjustments</option>
        </select>
        <select id="f-status">
          <option value="">All Status</option>
          <option value="draft">Draft</option>
          <option value="waiting">Waiting</option>
          <option value="ready">Ready</option>
          <option value="done">Done</option>
          <option value="canceled">Canceled</option>
        </select>
        <select id="f-warehouse">${options(state.warehouses, 'id', 'name', true)}</select>
        <select id="f-category">${options(state.categories, 'id', 'name', true)}</select>
      </div>
      <button id="apply-filters">Apply Filters</button>
    </div>

    <div class="grid-kpi">
      <div class="card"><div class="kpi-title">Total Products In Stock</div><div class="kpi-value">${kpis.total_products_in_stock}</div></div>
      <div class="card"><div class="kpi-title">Low Stock Items</div><div class="kpi-value">${kpis.low_stock_items}</div></div>
      <div class="card"><div class="kpi-title">Out of Stock Items</div><div class="kpi-value">${kpis.out_of_stock_items}</div></div>
      <div class="card"><div class="kpi-title">Pending Receipts</div><div class="kpi-value">${kpis.pending_receipts}</div></div>
      <div class="card"><div class="kpi-title">Pending Deliveries</div><div class="kpi-value">${kpis.pending_deliveries}</div></div>
      <div class="card"><div class="kpi-title">Internal Transfers Scheduled</div><div class="kpi-value">${kpis.internal_transfers_scheduled}</div></div>
    </div>

    <div class="card">
      <div class="section-title"><h3>Low Stock Alerts</h3><span class="pill">${lowStockAlerts.count}</span></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Product</th><th>SKU</th><th>Category</th><th>Qty</th><th>Reorder</th><th>Severity</th></tr></thead>
          <tbody>
            ${lowStockAlerts.items.map(x => `<tr><td>${x.product_name}</td><td>${x.sku}</td><td>${x.category_name || '-'}</td><td>${x.total_qty}</td><td>${x.reorder_level}</td><td>${x.severity}</td></tr>`).join('') || '<tr><td colspan="6">No low stock alerts</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="section-title"><h3>Filtered Operations</h3><span class="pill">${docs.length} docs</span></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Source</th><th>Destination</th><th>Partner</th><th>Lines</th></tr></thead>
          <tbody>
            ${docs.map(d => `<tr><td>${d.id}</td><td>${d.type}</td><td>${d.status}</td><td>${d.source_location_name || '-'}</td><td>${d.dest_location_name || '-'}</td><td>${d.partner_name || '-'}</td><td>${d.line_count}</td></tr>`).join('') || '<tr><td colspan="7">No records</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="section-title"><h3>Recent Stock Movements</h3></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>When</th><th>Product</th><th>Location</th><th>Delta</th><th>Doc</th></tr></thead>
          <tbody>
            ${movements.map(m => `<tr><td>${new Date(m.created_at).toLocaleString()}</td><td>${m.product || '-'}</td><td>${m.location || '-'}</td><td>${m.qty_delta}</td><td>${m.doc_type}#${m.doc_id}</td></tr>`).join('') || '<tr><td colspan="5">No movements yet</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>
  `;

  $('f-doc-type').value = f.doc_type;
  $('f-status').value = f.status;
  $('f-warehouse').value = f.warehouse_id;
  $('f-category').value = f.category_id;

  $('apply-filters').onclick = () => {
    state.dashboardFilters = {
      doc_type: $('f-doc-type').value,
      status: $('f-status').value,
      warehouse_id: $('f-warehouse').value,
      category_id: $('f-category').value,
    };
    renderDashboard().catch(showError);
  };
}

async function renderProducts() {
  const pf = state.productFilters;
  const query = new URLSearchParams();
  if (pf.search) query.set('search', pf.search);
  if (pf.category_id) query.set('category_id', pf.category_id);

  state.products = await api(`/api/products?${query}`);
  const editingProduct = state.products.find((p) => p.id === state.editingProductId) || null;
  const canManageProducts = isManager();
  $('view-products').innerHTML = `
    <div class="card">
      <h3>${editingProduct ? 'Edit Product' : 'Create Product'}</h3>
      ${canManageProducts ? '' : '<p class="muted">Only inventory managers can create or edit products. Staff can still view stock availability.</p>'}
      <div class="row">
        <input id="p-name" placeholder="Name" value="${escapeHtml(editingProduct?.name || '')}" ${canManageProducts ? '' : 'disabled'} />
        <input id="p-sku" placeholder="SKU / Code" value="${escapeHtml(editingProduct?.sku || '')}" ${canManageProducts ? '' : 'disabled'} />
        <select id="p-category">${options(state.categories)}</select>
        <input id="p-uom" placeholder="Unit of Measure (e.g. kg, pcs)" value="${escapeHtml(editingProduct?.uom || '')}" ${canManageProducts ? '' : 'disabled'} />
        <input id="p-reorder" type="number" placeholder="Reorder Level" value="${editingProduct?.reorder_level ?? ''}" ${canManageProducts ? '' : 'disabled'} />
        <input id="p-initial-stock" type="number" placeholder="Initial Stock (optional)" ${editingProduct ? 'disabled' : ''} ${canManageProducts ? '' : 'disabled'} />
        <select id="p-initial-location" ${editingProduct ? 'disabled' : ''} ${canManageProducts ? '' : 'disabled'}>${options(state.locations)}</select>
      </div>
      ${canManageProducts ? `<div class="row"><button id="save-product">${editingProduct ? 'Update Product' : 'Create Product'}</button>${editingProduct ? '<button id="cancel-edit-product" class="secondary" type="button">Cancel Edit</button>' : ''}</div>` : ''}
    </div>

    <div class="card">
      <h3>SKU Search & Smart Filters</h3>
      <div class="row">
        <input id="product-search" placeholder="Search by name or SKU" value="${pf.search}" />
        <select id="product-category-filter">${options(state.categories, 'id', 'name', true)}</select>
      </div>
      <button id="apply-product-filters">Apply Product Filters</button>
    </div>

    <div class="card">
      <div class="section-title"><h3>Products</h3><span class="pill">${state.products.length}</span></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Name</th><th>SKU</th><th>Category</th><th>UOM</th><th>Reorder</th><th>Total Qty</th><th>Stock by Location</th><th>Action</th></tr></thead>
          <tbody>
            ${state.products.map(p => `<tr><td>${p.name}</td><td>${p.sku}</td><td>${p.category_name || '-'}</td><td>${p.uom}</td><td>${p.reorder_level}</td><td>${p.total_qty}</td><td><button class="secondary product-availability" data-id="${p.id}">View</button></td><td>${canManageProducts ? `<button class="secondary product-edit" data-id="${p.id}">Edit</button>` : '<span class="muted">View only</span>'}</td></tr>`).join('') || '<tr><td colspan="8">No products</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <div id="product-availability-panel" class="card hidden"></div>
  `;

  $('product-category-filter').value = pf.category_id;
  $('p-category').value = editingProduct?.category_id || '';

  $('apply-product-filters').onclick = async () => {
    state.productFilters = {
      search: $('product-search').value.trim(),
      category_id: $('product-category-filter').value,
    };
    await renderProducts();
  };

  if (canManageProducts) {
    $('save-product').onclick = async () => {
      try {
        const body = {
          name: $('p-name').value,
          sku: $('p-sku').value,
          category_id: Number($('p-category').value) || null,
          uom: $('p-uom').value,
          reorder_level: Number($('p-reorder').value || 0),
          initial_stock: $('p-initial-stock').value ? Number($('p-initial-stock').value) : null,
          initial_location_id: Number($('p-initial-location').value) || null,
        };

        if (editingProduct) {
          await api(`/api/products/${editingProduct.id}`, {
            method: 'PUT',
            body: JSON.stringify({
              name: body.name,
              sku: body.sku,
              category_id: body.category_id,
              uom: body.uom,
              reorder_level: body.reorder_level,
            }),
          });
          toast('Product updated');
        } else {
          await api('/api/products', { method: 'POST', body: JSON.stringify(body) });
          toast('Product created');
        }

        state.editingProductId = null;
        await bootstrapData();
        await renderProducts();
        await renderDashboard();
      } catch (e) {
        showError(e);
      }
    };

    if ($('cancel-edit-product')) {
      $('cancel-edit-product').onclick = async () => {
        state.editingProductId = null;
        await renderProducts();
      };
    }
  }

  document.querySelectorAll('.product-availability').forEach((btn) => {
    btn.onclick = async () => {
      try {
        const productId = Number(btn.dataset.id);
        const product = state.products.find((p) => p.id === productId);
        const availability = await api(`/api/products/${productId}/availability`);
        const panel = $('product-availability-panel');
        panel.classList.remove('hidden');
        panel.innerHTML = `
          <div class="section-title"><h3>Stock Availability: ${product ? product.name : productId}</h3></div>
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>Warehouse</th><th>Location</th><th>Qty</th></tr></thead>
              <tbody>
                ${availability.map(a => `<tr><td>${a.warehouse_name || '-'}</td><td>${a.location_name || '-'}</td><td>${a.qty}</td></tr>`).join('') || '<tr><td colspan="3">No stock records</td></tr>'}
              </tbody>
            </table>
          </div>
        `;
      } catch (e) {
        showError(e);
      }
    };
  });

  document.querySelectorAll('.product-edit').forEach((btn) => {
    btn.onclick = async () => {
      state.editingProductId = Number(btn.dataset.id);
      await renderProducts();
    };
  });
}

function operationTypeFields(type) {
  const sourceRequired = type === 'delivery' || type === 'transfer' || type === 'adjustment';
  const destRequired = type === 'receipt' || type === 'transfer';
  return { sourceRequired, destRequired };
}

async function renderOperations() {
  const docs = await api('/api/operations/documents');
  const ledger = await api('/api/ledger');

  $('view-operations').innerHTML = `
    <div class="card">
      <div class="ops-tabs">
        <button class="ops-tab ${state.operationType === 'receipt' ? 'active' : ''}" data-op="receipt">Receipts</button>
        <button class="ops-tab ${state.operationType === 'delivery' ? 'active' : ''}" data-op="delivery">Delivery Orders</button>
        <button class="ops-tab ${state.operationType === 'transfer' ? 'active' : ''}" data-op="transfer">Internal Transfers</button>
        <button class="ops-tab ${state.operationType === 'adjustment' ? 'active' : ''}" data-op="adjustment">Inventory Adjustment</button>
      </div>
      <h3>Create ${state.operationType === 'receipt' ? 'Receipt (Incoming)' : state.operationType === 'delivery' ? 'Delivery Order (Outgoing)' : state.operationType === 'transfer' ? 'Internal Transfer' : 'Stock Adjustment'}</h3>
      ${state.operationType === 'delivery' ? '<p class="muted">Delivery workflow: create order → Pick → Pack → Validate.</p>' : ''}
      <div class="row">
        ${state.operationType === 'receipt' ? `
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Receiving Location *<select id="op-dest">${options(state.locations)}</select></label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Supplier Name<input id="op-partner" placeholder="e.g. ABC Metals" /></label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Reference<input id="op-reference" placeholder="e.g. GRN-1001" /></label>
          <input id="op-source" type="hidden" value="" />
        ` : state.operationType === 'delivery' ? `
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Dispatch Location *<select id="op-source">${options(state.locations)}</select></label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Customer Name<input id="op-partner" placeholder="e.g. Customer One" /></label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Reference<input id="op-reference" placeholder="e.g. SO-3001" /></label>
          <input id="op-dest" type="hidden" value="" />
        ` : state.operationType === 'transfer' ? `
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">From Location *<select id="op-source">${options(state.locations)}</select></label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">To Location *<select id="op-dest">${options(state.locations)}</select></label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Reference<input id="op-reference" placeholder="e.g. TRF-2001" /></label>
          <input id="op-partner" type="hidden" value="" />
        ` : `
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Location to Adjust *<select id="op-source">${options(state.locations)}</select></label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--muted)">Reference<input id="op-reference" placeholder="e.g. ADJ-4001" /></label>
          <input id="op-dest" type="hidden" value="" />
          <input id="op-partner" type="hidden" value="" />
        `}
      </div>

      <div class="card">
        <h4>Add Line</h4>
        <div class="row">
          <select id="op-product">${options(state.products)}</select>
          <input id="op-qty-planned" type="number" placeholder="Planned Qty" />
          <input id="op-qty-done" type="number" placeholder="Done Qty / Counted Qty" />
          <button id="add-line">Add line</button>
        </div>
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th>Product</th><th>Planned</th><th>Done</th><th>Action</th></tr></thead>
            <tbody id="op-lines-body">
            </tbody>
          </table>
        </div>
      </div>

      <button id="create-document">Create Document</button>
    </div>

    <div class="card">
      <div class="section-title"><h3>Operations Documents</h3></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Source</th><th>Destination</th><th>Partner</th><th>Actions</th></tr></thead>
          <tbody>
            ${docs.map(d => `
              <tr>
                <td>${d.id}</td>
                <td>${d.type}</td>
                <td>${d.status}</td>
                <td>${d.source_location_name || '-'}</td>
                <td>${d.dest_location_name || '-'}</td>
                <td>${d.partner_name || '-'}</td>
                <td>
                  ${d.type === 'delivery' && d.status === 'draft' ? `<button class="secondary doc-pick" data-id="${d.id}">Pick</button>` : ''}
                  ${d.type === 'delivery' && d.status === 'waiting' ? `<button class="secondary doc-pack" data-id="${d.id}">Pack</button>` : ''}
                  ${d.type !== 'delivery' || d.status === 'ready' ? `<button class="secondary doc-validate" data-id="${d.id}">Validate</button>` : ''}
                  <button class="danger doc-cancel" data-id="${d.id}">Cancel</button>
                </td>
              </tr>
            `).join('') || '<tr><td colspan="7">No documents</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="section-title"><h3>Move History (Stock Ledger)</h3></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>When</th><th>Product</th><th>Location</th><th>Delta</th><th>Doc</th><th>Reason</th></tr></thead>
          <tbody>
            ${ledger.map(l => `<tr><td>${new Date(l.created_at).toLocaleString()}</td><td>${l.product_name || '-'}</td><td>${l.location_name || '-'}</td><td>${l.qty_delta}</td><td>${l.doc_type}#${l.doc_id}</td><td>${l.reason || '-'}</td></tr>`).join('') || '<tr><td colspan="6">No ledger records</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>
  `;

  document.querySelectorAll('.ops-tab').forEach((btn) => {
    btn.onclick = async () => {
      state.operationType = btn.dataset.op;
      state.operationLines = [];
      await renderOperations();
    };
  });

  renderOperationLines();

  $('add-line').onclick = () => {
    const productId = Number($('op-product').value);
    const qtyPlanned = Number($('op-qty-planned').value || 0);
    const qtyDone = Number($('op-qty-done').value || 0);
    if (!productId || qtyDone <= 0) return toast('Enter valid line values');
    state.operationLines.push({ product_id: productId, qty_planned: qtyPlanned || qtyDone, qty_done: qtyDone });
    renderOperationLines();
  };

  $('create-document').onclick = async () => {
    try {
      if (!state.operationLines.length) return toast('Add at least one line');
      const req = operationTypeFields(state.operationType);
      const source = Number($('op-source').value) || null;
      const dest = Number($('op-dest').value) || null;
      if (req.sourceRequired && !source) return toast('Source location is required');
      if (req.destRequired && !dest) return toast('Destination location is required');

      const body = {
        type: state.operationType,
        status: 'draft',
        source_location_id: source,
        dest_location_id: dest,
        partner_name: $('op-partner').value || null,
        reference: $('op-reference').value || null,
        lines: state.operationLines,
      };

      await api('/api/operations/documents', { method: 'POST', body: JSON.stringify(body) });
      state.operationLines = [];
      toast('Document created');
      await renderOperations();
      await renderDashboard();
    } catch (e) {
      showError(e);
    }
  };

  document.querySelectorAll('.doc-pick').forEach((b) => {
    b.onclick = async () => {
      try {
        await api(`/api/operations/documents/${b.dataset.id}/pick`, { method: 'POST' });
        toast('Items picked');
        await renderOperations();
        await renderDashboard();
      } catch (e) {
        showError(e);
      }
    };
  });

  document.querySelectorAll('.doc-pack').forEach((b) => {
    b.onclick = async () => {
      try {
        await api(`/api/operations/documents/${b.dataset.id}/pack`, { method: 'POST' });
        toast('Items packed and ready');
        await renderOperations();
        await renderDashboard();
      } catch (e) {
        showError(e);
      }
    };
  });

  document.querySelectorAll('.doc-validate').forEach((b) => {
    b.onclick = async () => {
      try {
        await api(`/api/operations/documents/${b.dataset.id}/validate`, { method: 'POST' });
        toast('Document validated');
        await bootstrapData();
        await renderOperations();
        await renderDashboard();
        await renderProducts();
      } catch (e) {
        showError(e);
      }
    };
  });

  document.querySelectorAll('.doc-cancel').forEach((b) => {
    b.onclick = async () => {
      try {
        await api(`/api/operations/documents/${b.dataset.id}/cancel`, { method: 'POST' });
        toast('Document canceled');
        await renderOperations();
        await renderDashboard();
      } catch (e) {
        showError(e);
      }
    };
  });
}

function renderOperationLines() {
  const tbody = $('op-lines-body');
  if (!tbody) return;
  tbody.innerHTML = state.operationLines.map((line, idx) => {
    const p = state.products.find((x) => x.id === line.product_id);
    return `<tr>
      <td>${p ? p.name : line.product_id}</td>
      <td>${line.qty_planned}</td>
      <td>${line.qty_done}</td>
      <td><button class="danger line-remove" data-idx="${idx}">Remove</button></td>
    </tr>`;
  }).join('') || '<tr><td colspan="4">No lines</td></tr>';

  document.querySelectorAll('.line-remove').forEach((btn) => {
    btn.onclick = () => {
      state.operationLines.splice(Number(btn.dataset.idx), 1);
      renderOperationLines();
    };
  });
}

async function renderSettings() {
  const canManageSettings = isManager();
  $('view-settings').innerHTML = `
    <div class="card">
      <h3>Create Warehouse</h3>
      ${canManageSettings ? '' : '<p class="muted">Only inventory managers can change warehouse, location, and category settings.</p>'}
      <div class="row">
        <input id="wh-name" placeholder="Warehouse name" ${canManageSettings ? '' : 'disabled'} />
        <button id="create-wh" ${canManageSettings ? '' : 'disabled'}>Create</button>
      </div>
    </div>

    <div class="card">
      <h3>Create Location</h3>
      <div class="row">
        <select id="loc-wh" ${canManageSettings ? '' : 'disabled'}>${options(state.warehouses)}</select>
        <input id="loc-name" placeholder="Location name" ${canManageSettings ? '' : 'disabled'} />
        <input id="loc-code" placeholder="Location code" ${canManageSettings ? '' : 'disabled'} />
        <button id="create-loc" ${canManageSettings ? '' : 'disabled'}>Create</button>
      </div>
    </div>

    <div class="card">
      <h3>Create Product Category</h3>
      <div class="row">
        <input id="cat-name" placeholder="Category name" ${canManageSettings ? '' : 'disabled'} />
        <button id="create-cat" ${canManageSettings ? '' : 'disabled'}>Create</button>
      </div>
    </div>

    <div class="card">
      <h3>Warehouses</h3>
      <div class="table-wrap"><table class="table"><thead><tr><th>ID</th><th>Name</th></tr></thead><tbody>
        ${state.warehouses.map(w => `<tr><td>${w.id}</td><td>${w.name}</td></tr>`).join('') || '<tr><td colspan="2">No data</td></tr>'}
      </tbody></table></div>
    </div>

    <div class="card">
      <h3>Locations</h3>
      <div class="table-wrap"><table class="table"><thead><tr><th>ID</th><th>Name</th><th>Code</th><th>Warehouse</th></tr></thead><tbody>
        ${state.locations.map(l => `<tr><td>${l.id}</td><td>${l.name}</td><td>${l.code}</td><td>${l.warehouse_name || '-'}</td></tr>`).join('') || '<tr><td colspan="4">No data</td></tr>'}
      </tbody></table></div>
    </div>
  `;

  if (!canManageSettings) {
    return;
  }

  $('create-wh').onclick = async () => {
    try {
      await api('/api/warehouses', { method: 'POST', body: JSON.stringify({ name: $('wh-name').value }) });
      toast('Warehouse created');
      await bootstrapData();
      await renderSettings();
      await renderDashboard();
    } catch (e) {
      showError(e);
    }
  };

  $('create-loc').onclick = async () => {
    try {
      await api('/api/locations', {
        method: 'POST',
        body: JSON.stringify({
          warehouse_id: Number($('loc-wh').value),
          name: $('loc-name').value,
          code: $('loc-code').value,
        }),
      });
      toast('Location created');
      await bootstrapData();
      await renderSettings();
      await renderDashboard();
    } catch (e) {
      showError(e);
    }
  };

  $('create-cat').onclick = async () => {
    try {
      await api('/api/categories', { method: 'POST', body: JSON.stringify({ name: $('cat-name').value }) });
      toast('Category created');
      await bootstrapData();
      await renderSettings();
      await renderDashboard();
      await renderProducts();
    } catch (e) {
      showError(e);
    }
  };
}

function renderProfile() {
  $('view-profile').innerHTML = `
    <div class="card">
      <h3>My Profile</h3>
      <p><strong>Name:</strong> ${state.user?.name || '-'}</p>
      <p><strong>Email:</strong> ${state.user?.email || '-'}</p>
      <p><strong>Role:</strong> ${state.user?.role || '-'}</p>
    </div>
  `;
}

function showError(err) {
  toast(toMessage(err, 'Something went wrong'));
}

async function afterLogin() {
  state.user = await api('/api/auth/me');
  await bootstrapData();
  setAuthVisible(false);
  setActiveView('dashboard');
  await renderDashboard();
  await renderProducts();
  await renderOperations();
  await renderSettings();
  renderProfile();
}

function bindAuthHandlers() {
  $('tab-login').onclick = () => setActiveAuthTab('login');
  $('tab-signup').onclick = () => setActiveAuthTab('signup');
  $('tab-reset').onclick = () => setActiveAuthTab('reset');

  $('login-form').onsubmit = async (e) => {
    e.preventDefault();
    try {
      const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: $('login-email').value, password: $('login-password').value }),
      });
      state.token = data.access_token;
      localStorage.setItem('coreinventory_token', state.token);
      toast('Login successful');
      await afterLogin();
    } catch (err) {
      showError(err);
    }
  };

  $('signup-form').onsubmit = async (e) => {
    e.preventDefault();
    try {
      const data = await api('/api/auth/signup', {
        method: 'POST',
        body: JSON.stringify({
          name: $('signup-name').value,
          email: $('signup-email').value,
          password: $('signup-password').value,
          role: $('signup-role').value,
        }),
      });
      state.token = data.access_token;
      localStorage.setItem('coreinventory_token', state.token);
      toast('Account created');
      await afterLogin();
    } catch (err) {
      showError(err);
    }
  };

  $('request-otp').onclick = async () => {
    try {
      const data = await api('/api/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email: $('reset-email').value }),
      });
      if (data.demo_otp) {
        const hint = $('otp-hint');
        hint.innerHTML = `Your OTP: <strong style="font-size:22px;letter-spacing:4px;color:#46d39a">${data.demo_otp}</strong><br><small>Copy this and paste it in the OTP field below. Expires in 10 minutes.</small><br><small style="color:#ffd166">Email not sent: ${data.delivery_message || 'Unknown SMTP issue'}</small>`;
        hint.style.display = 'block';
        hint.style.background = '#0d2a1f';
        hint.style.border = '2px solid #46d39a';
        hint.style.borderRadius = '10px';
        hint.style.padding = '12px';
        hint.style.marginTop = '10px';
        $('reset-otp').value = data.demo_otp;
        toast(`OTP is: ${data.demo_otp} — auto-filled for you!`);
      } else {
        $('otp-hint').textContent = data.message || 'OTP sent.';
        $('otp-hint').style.display = 'block';
        toast('OTP sent');
      }
    } catch (err) {
      showError(err);
    }
  };

  $('reset-form').onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({
          email: $('reset-email').value,
          otp: $('reset-otp').value,
          new_password: $('reset-new-password').value,
        }),
      });
      toast('Password reset successful');
      setActiveAuthTab('login');
    } catch (err) {
      showError(err);
    }
  };
}

function bindNavigationHandlers() {
  document.querySelectorAll('.nav-btn').forEach((btn) => {
    btn.onclick = async () => {
      const view = btn.dataset.view;
      setActiveView(view);
      if (view === 'dashboard') await renderDashboard();
      if (view === 'products') await renderProducts();
      if (view === 'operations') await renderOperations();
      if (view === 'settings') await renderSettings();
      if (view === 'profile') renderProfile();
    };
  });

  $('logout').onclick = () => {
    state.token = null;
    state.user = null;
    localStorage.removeItem('coreinventory_token');
    setAuthVisible(true);
    setActiveAuthTab('login');
    toast('Logged out');
  };
}

(async function init() {
  bindAuthHandlers();
  bindNavigationHandlers();

  if (!state.token) {
    setAuthVisible(true);
    setActiveAuthTab('login');
    return;
  }

  try {
    await afterLogin();
  } catch {
    localStorage.removeItem('coreinventory_token');
    state.token = null;
    setAuthVisible(true);
    setActiveAuthTab('login');
  }
})();
