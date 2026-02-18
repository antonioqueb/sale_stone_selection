/** @odoo-module */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillStart, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENTE PRINCIPAL: BOTÓN STONE
// El popup se renderiza como DOM puro inyectado en document.body para evitar
// problemas de contexto OWL al montar fuera del árbol principal.
// ═══════════════════════════════════════════════════════════════════════════════
export class StoneExpandButton extends Component {
    static template = "sale_stone_selection.StoneExpandButton";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this._detailsRow = null;
        this._popupRoot = null;
        this._popupKeyHandler = null;

        this.state = useState({
            isExpanded: false,
            selectedCount: 0,
        });

        onWillStart(() => this._updateCount());
        onWillUpdateProps((nextProps) => this._updateCount(nextProps));
        onWillUnmount(() => {
            this.removeDetailsRow();
            this.destroyPopup();
        });
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    _updateCount(props = this.props) {
        const ids = this.extractLotIds(props?.record?.data?.lot_ids);
        this.state.selectedCount = ids.length;
    }

    extractLotIds(rawLots) {
        if (!rawLots) return [];
        if (Array.isArray(rawLots)) return rawLots.filter((x) => typeof x === "number");
        if (rawLots.currentIds) return rawLots.currentIds;
        if (rawLots.resIds) return rawLots.resIds;
        if (rawLots.records) return rawLots.records.map((r) => r.resId || r.data?.id).filter(Boolean);
        return [];
    }

    getProductId() {
        const pd = this.props.record.data.product_id;
        if (!pd) return 0;
        if (Array.isArray(pd)) return pd[0];
        if (typeof pd === "number") return pd;
        if (pd.id) return pd.id;
        return 0;
    }

    getProductName() {
        const pd = this.props.record.data.product_id;
        if (!pd) return "";
        if (Array.isArray(pd)) return pd[1] || "";
        if (pd.display_name) return pd.display_name;
        return "";
    }

    getCurrentLotIds() {
        return this.extractLotIds(this.props.record.data.lot_ids);
    }

    // ─── Toggle principal ─────────────────────────────────────────────────────

    async handleToggle(ev) {
        ev.stopPropagation();

        if (this.state.isExpanded) {
            this.removeDetailsRow();
            this.state.isExpanded = false;
            return;
        }

        // Cerrar cualquier otro expandido
        document.querySelectorAll(".stone-selected-row").forEach((e) => e.remove());

        const tr = ev.currentTarget.closest("tr");
        if (!tr) return;

        this.state.isExpanded = true;
        await this.injectSelectedTable(tr);
    }

    // ─── Tabla de seleccionadas (inline bajo la fila) ─────────────────────────

    async injectSelectedTable(currentRow) {
        const newTr = document.createElement("tr");
        newTr.className = "stone-selected-row";

        const colCount = currentRow.querySelectorAll("td").length || 10;
        const td = document.createElement("td");
        td.colSpan = colCount;
        td.className = "stone-selected-cell";

        const container = document.createElement("div");
        container.className = "stone-selected-container";

        const header = document.createElement("div");
        header.className = "stone-selected-header";
        header.innerHTML = `
            <span class="stone-selected-title">
                <i class="fa fa-check-circle me-2"></i>
                Placas seleccionadas
                <span class="stone-sel-badge" id="stone-sel-badge">${this.getCurrentLotIds().length}</span>
            </span>
            <button class="stone-add-btn stone-add-btn-trigger">
                <i class="fa fa-plus me-1"></i> Agregar placa
            </button>
        `;

        const body = document.createElement("div");
        body.className = "stone-selected-body";

        container.appendChild(header);
        container.appendChild(body);
        td.appendChild(container);
        newTr.appendChild(td);
        currentRow.after(newTr);
        this._detailsRow = newTr;

        await this.renderSelectedTable(body, this.getCurrentLotIds());

        header.querySelector(".stone-add-btn-trigger").addEventListener("click", (e) => {
            e.stopPropagation();
            this.openPopup();
        });
    }

    async renderSelectedTable(container, lotIds) {
        if (!lotIds || lotIds.length === 0) {
            container.innerHTML = `
                <div class="stone-no-selection">
                    <i class="fa fa-info-circle me-2 text-muted"></i>
                    <span class="text-muted">Sin placas seleccionadas. Usa <strong>Agregar placa</strong> para comenzar.</span>
                </div>`;
            return;
        }

        container.innerHTML = `<div class="stone-table-loading"><i class="fa fa-circle-o-notch fa-spin me-2"></i> Cargando datos...</div>`;

        try {
            const [lotsData, quants] = await Promise.all([
                this.orm.searchRead(
                    "stock.lot",
                    [["id", "in", lotIds]],
                    ["name", "x_bloque", "x_atado", "x_alto", "x_ancho", "x_grosor", "x_tipo", "x_color"],
                    { limit: lotIds.length }
                ),
                this.orm.searchRead(
                    "stock.quant",
                    [
                        ["lot_id", "in", lotIds],
                        ["location_id.usage", "=", "internal"],
                        ["quantity", ">", 0],
                    ],
                    ["lot_id", "quantity"]
                ),
            ]);

            const qtyMap = {};
            for (const q of quants) {
                const lid = q.lot_id[0];
                qtyMap[lid] = (qtyMap[lid] || 0) + q.quantity;
            }

            const lotMap = {};
            for (const l of lotsData) lotMap[l.id] = l;

            let totalQty = 0;
            let html = `
                <table class="stone-sel-table">
                    <thead>
                        <tr>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Ancho</th>
                            <th class="col-num">Grosor</th>
                            <th class="col-num">M²</th>
                            <th>Tipo</th>
                            <th>Color</th>
                            <th class="col-act"></th>
                        </tr>
                    </thead>
                    <tbody>`;

            for (const lid of lotIds) {
                const lot = lotMap[lid];
                if (!lot) continue;
                const qty = qtyMap[lid] || 0;
                totalQty += qty;
                html += `
                    <tr>
                        <td class="cell-lot">${lot.name}</td>
                        <td>${lot.x_bloque || "-"}</td>
                        <td>${lot.x_atado || "-"}</td>
                        <td class="col-num">${lot.x_alto ? lot.x_alto.toFixed(0) : "-"}</td>
                        <td class="col-num">${lot.x_ancho ? lot.x_ancho.toFixed(0) : "-"}</td>
                        <td class="col-num">${lot.x_grosor || "-"}</td>
                        <td class="col-num fw-semibold">${qty.toFixed(2)}</td>
                        <td>${lot.x_tipo || "-"}</td>
                        <td>${lot.x_color || "-"}</td>
                        <td class="col-act">
                            <button class="stone-remove-btn" data-lot-id="${lid}" title="Quitar">
                                <i class="fa fa-times"></i>
                            </button>
                        </td>
                    </tr>`;
            }

            html += `
                    </tbody>
                    <tfoot>
                        <tr class="stone-total-row">
                            <td colspan="6" class="text-end fw-bold text-muted">Total:</td>
                            <td class="col-num fw-bold">${totalQty.toFixed(2)}</td>
                            <td colspan="3"></td>
                        </tr>
                    </tfoot>
                </table>`;

            container.innerHTML = html;

            container.querySelectorAll(".stone-remove-btn").forEach((btn) => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.removeLot(parseInt(btn.dataset.lotId));
                });
            });
        } catch (err) {
            console.error("[STONE] Error renderizando seleccionadas:", err);
            container.innerHTML = `<div class="text-danger p-2">Error: ${err.message}</div>`;
        }
    }

    async removeLot(lotId) {
        const newIds = this.getCurrentLotIds().filter((id) => id !== lotId);
        await this.props.record.update({ lot_ids: [[6, 0, newIds]] });
        this._updateCount();
        await this.refreshSelectedTable();
    }

    async refreshSelectedTable() {
        if (!this._detailsRow) return;
        const body = this._detailsRow.querySelector(".stone-selected-body");
        if (!body) return;
        const lots = this.getCurrentLotIds();
        const badge = this._detailsRow.querySelector(".stone-sel-badge");
        if (badge) badge.textContent = lots.length;
        await this.renderSelectedTable(body, lots);
    }

    removeDetailsRow() {
        if (this._detailsRow) {
            this._detailsRow.remove();
            this._detailsRow = null;
        }
    }

    // ─── POPUP (DOM puro en document.body) ────────────────────────────────────

    openPopup() {
        this.destroyPopup();
        const productId = this.getProductId();
        if (!productId) return;

        this._popupRoot = document.createElement("div");
        this._popupRoot.className = "stone-popup-root";
        document.body.appendChild(this._popupRoot);

        this._renderPopupDOM(productId);
    }

    _renderPopupDOM(productId) {
        const root = this._popupRoot;
        const PAGE_SIZE = 35;

        // Estado local del popup
        const state = {
            quants: [],
            totalCount: 0,
            hasMore: false,
            isLoading: false,
            isLoadingMore: false,
            page: 0,
            pendingIds: new Set(this.getCurrentLotIds()),
            filters: { lot_name: "", bloque: "", atado: "", alto_min: "", ancho_min: "" },
        };

        let searchTimeout = null;
        let observer = null;

        root.innerHTML = `
            <div class="stone-popup-overlay" id="stone-overlay">
                <div class="stone-popup-container">

                    <div class="stone-popup-header">
                        <div class="stone-popup-title">
                            <i class="fa fa-th me-2"></i>
                            Seleccionar Placas
                            <span class="stone-popup-subtitle">${this.getProductName() ? "— " + this.getProductName() : ""}</span>
                        </div>
                        <div class="stone-popup-header-actions">
                            <span class="stone-badge-selected">
                                <i class="fa fa-check-circle me-1"></i>
                                <span id="sp-badge-count">${state.pendingIds.size}</span> seleccionadas
                            </span>
                            <button class="stone-btn stone-btn-accent" id="sp-confirm-top">
                                <i class="fa fa-check me-1"></i> Confirmar
                            </button>
                            <button class="stone-btn stone-btn-ghost" id="sp-close">
                                <i class="fa fa-times"></i>
                            </button>
                        </div>
                    </div>

                    <div class="stone-popup-filters">
                        <div class="stone-filter-group">
                            <label>Lote</label>
                            <input type="text" class="stone-filter-input" id="sf-lot" placeholder="Buscar lote..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Bloque</label>
                            <input type="text" class="stone-filter-input" id="sf-bloque" placeholder="Bloque..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Atado</label>
                            <input type="text" class="stone-filter-input" id="sf-atado" placeholder="Atado..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Alto mín.</label>
                            <input type="number" class="stone-filter-input stone-filter-sm" id="sf-alto" placeholder="0"/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Ancho mín.</label>
                            <input type="number" class="stone-filter-input stone-filter-sm" id="sf-ancho" placeholder="0"/>
                        </div>
                        <div class="stone-filter-spacer"></div>
                        <div class="stone-filter-stats">
                            <span id="sp-stat" class="stone-filter-stat-loading">
                                <i class="fa fa-circle-o-notch fa-spin me-1"></i> Buscando...
                            </span>
                        </div>
                    </div>

                    <div class="stone-popup-body" id="sp-body">
                        <div class="stone-empty-state">
                            <i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i>
                            <div class="stone-empty-text mt-2">Cargando inventario...</div>
                        </div>
                    </div>

                    <div class="stone-popup-footer">
                        <span class="stone-footer-info" id="sp-footer-info">—</span>
                        <div class="stone-footer-actions">
                            <button class="stone-btn stone-btn-outline" id="sp-cancel">Cancelar</button>
                            <button class="stone-btn stone-btn-primary-dark" id="sp-confirm-bottom">
                                <i class="fa fa-check me-1"></i> Agregar selección
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const overlay = root.querySelector("#stone-overlay");
        const body = root.querySelector("#sp-body");
        const stat = root.querySelector("#sp-stat");
        const footerInfo = root.querySelector("#sp-footer-info");
        const badgeCount = root.querySelector("#sp-badge-count");

        // ─── Utils ───────────────────────────────────────────────────────────
        const updateBadge = () => { badgeCount.textContent = state.pendingIds.size; };

        const updateStats = () => {
            stat.className = "stone-filter-stat-count";
            stat.innerHTML = `${state.totalCount} placas disponibles`;
            footerInfo.innerHTML = `Mostrando <strong>${state.quants.length}</strong> de <strong>${state.totalCount}</strong>`;
        };

        const renderTable = () => {
            if (state.quants.length === 0 && !state.isLoading) {
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-inbox fa-3x text-muted"></i>
                        <div class="stone-empty-text mt-2">No hay placas con estos filtros</div>
                    </div>`;
                updateStats();
                return;
            }

            // Construir HTML de la tabla
            let rows = "";
            for (const q of state.quants) {
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                const lotName = q.lot_id ? q.lot_id[1] : "-";
                const loc = q.location_id ? q.location_id[1].split("/").pop() : "-";
                const sel = state.pendingIds.has(lotId);
                const reserved = q.reserved_quantity > 0;

                let statusBadge = `<span class="stone-tag stone-tag-free">Libre</span>`;
                if (sel) statusBadge = `<span class="stone-tag stone-tag-ok">Selec.</span>`;
                else if (reserved) statusBadge = `<span class="stone-tag stone-tag-warn">Reservado</span>`;

                rows += `
                    <tr class="${sel ? "row-sel" : ""}" data-lot-id="${lotId}">
                        <td class="col-chk">
                            <div class="stone-chkbox ${sel ? "checked" : ""}">
                                ${sel ? '<i class="fa fa-check"></i>' : ""}
                            </div>
                        </td>
                        <td class="cell-lot">${lotName}</td>
                        <td>${q.x_bloque || "-"}</td>
                        <td>${q.x_atado || "-"}</td>
                        <td class="col-num">${q.x_alto ? q.x_alto.toFixed(0) : "-"}</td>
                        <td class="col-num">${q.x_ancho ? q.x_ancho.toFixed(0) : "-"}</td>
                        <td class="col-num">${q.x_grosor || "-"}</td>
                        <td class="col-num fw-semibold">${q.quantity ? q.quantity.toFixed(2) : "-"}</td>
                        <td>${q.x_tipo || "-"}</td>
                        <td>${q.x_color || "-"}</td>
                        <td class="cell-loc">${loc}</td>
                        <td>${statusBadge}</td>
                    </tr>`;
            }

            const sentinel = `
                <div id="sp-sentinel" class="stone-scroll-sentinel">
                    ${state.isLoadingMore ? '<div class="stone-loading-more"><i class="fa fa-circle-o-notch fa-spin me-2"></i> Cargando más...</div>' : ""}
                    ${state.hasMore && !state.isLoadingMore ? '<div class="stone-scroll-hint"><i class="fa fa-chevron-down me-1"></i> Desplázate para cargar más</div>' : ""}
                </div>`;

            body.innerHTML = `
                <table class="stone-popup-table">
                    <thead>
                        <tr>
                            <th class="col-chk">✓</th>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Ancho</th>
                            <th class="col-num">Gros.</th>
                            <th class="col-num">M²</th>
                            <th>Tipo</th>
                            <th>Color</th>
                            <th>Ubicación</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                ${sentinel}`;

            updateStats();

            // Click en filas (toggle selección sin re-render completo)
            body.querySelectorAll("tr[data-lot-id]").forEach((tr) => {
                tr.style.cursor = "pointer";
                tr.addEventListener("click", () => {
                    const lotId = parseInt(tr.dataset.lotId);
                    if (!lotId) return;
                    if (state.pendingIds.has(lotId)) {
                        state.pendingIds.delete(lotId);
                    } else {
                        state.pendingIds.add(lotId);
                    }
                    const sel = state.pendingIds.has(lotId);
                    tr.className = sel ? "row-sel" : "";
                    const chk = tr.querySelector(".stone-chkbox");
                    if (chk) {
                        chk.className = "stone-chkbox" + (sel ? " checked" : "");
                        chk.innerHTML = sel ? '<i class="fa fa-check"></i>' : "";
                    }
                    const tag = tr.querySelector(".stone-tag");
                    if (tag) {
                        tag.className = sel ? "stone-tag stone-tag-ok" : "stone-tag stone-tag-free";
                        tag.textContent = sel ? "Selec." : "Libre";
                    }
                    updateBadge();
                });
            });

            // Infinite scroll observer
            if (observer) observer.disconnect();
            const sentinelEl = body.querySelector("#sp-sentinel");
            if (sentinelEl && state.hasMore) {
                observer = new IntersectionObserver(
                    (entries) => {
                        if (entries[0].isIntersecting && state.hasMore && !state.isLoadingMore) {
                            loadPage(state.page + 1, false);
                        }
                    },
                    { root: body, rootMargin: "100px", threshold: 0.1 }
                );
                observer.observe(sentinelEl);
            }
        };

        // ─── loadPage ────────────────────────────────────────────────────────
        const loadPage = async (page, reset) => {
            if (reset) {
                state.isLoading = true;
                state.quants = [];
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i>
                        <div class="stone-empty-text mt-2">Buscando...</div>
                    </div>`;
                stat.className = "stone-filter-stat-loading";
                stat.innerHTML = `<i class="fa fa-circle-o-notch fa-spin me-1"></i> Buscando...`;
            } else {
                state.isLoadingMore = true;
            }

            try {
                let result;
                try {
                    result = await this.orm.call(
                        "stock.quant",
                        "search_stone_inventory_for_so_paginated",
                        [],
                        {
                            product_id: productId,
                            filters: state.filters,
                            current_lot_ids: Array.from(state.pendingIds),
                            page,
                            page_size: PAGE_SIZE,
                        }
                    );
                } catch (_e) {
                    // Fallback al método original
                    const all = (await this.orm.call(
                        "stock.quant",
                        "search_stone_inventory_for_so",
                        [],
                        {
                            product_id: productId,
                            filters: state.filters,
                            current_lot_ids: Array.from(state.pendingIds),
                        }
                    )) || [];
                    result = {
                        items: all.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
                        total: all.length,
                    };
                }

                const items = result.items || [];
                if (reset || page === 0) {
                    state.quants = items;
                } else {
                    state.quants = [...state.quants, ...items];
                }
                state.totalCount = result.total || 0;
                state.page = page;
                state.hasMore = state.quants.length < state.totalCount;
            } catch (err) {
                console.error("[STONE POPUP] Error:", err);
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-exclamation-triangle fa-2x text-danger"></i>
                        <div class="stone-empty-text mt-2 text-danger">Error: ${err.message}</div>
                    </div>`;
                return;
            } finally {
                state.isLoading = false;
                state.isLoadingMore = false;
            }

            renderTable();
        };

        // ─── Confirm / Close ─────────────────────────────────────────────────
        const doConfirm = async () => {
            this.destroyPopup();
            const newIds = Array.from(state.pendingIds);
            await this.props.record.update({ lot_ids: [[6, 0, newIds]] });
            this._updateCount();
            await this.refreshSelectedTable();
        };

        const doClose = () => this.destroyPopup();

        // ─── Event listeners ─────────────────────────────────────────────────
        root.querySelector("#sp-close").addEventListener("click", doClose);
        root.querySelector("#sp-cancel").addEventListener("click", doClose);
        root.querySelector("#sp-confirm-top").addEventListener("click", doConfirm);
        root.querySelector("#sp-confirm-bottom").addEventListener("click", doConfirm);
        overlay.addEventListener("click", (e) => { if (e.target === overlay) doClose(); });

        const onKeyDown = (e) => { if (e.key === "Escape") { doClose(); } };
        document.addEventListener("keydown", onKeyDown);
        this._popupKeyHandler = onKeyDown;

        // Filtros
        const bindFilter = (id, key) => {
            const input = root.querySelector(`#${id}`);
            if (!input) return;
            input.addEventListener("input", (e) => {
                state.filters[key] = e.target.value;
                if (searchTimeout) clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => loadPage(0, true), 350);
            });
        };
        bindFilter("sf-lot", "lot_name");
        bindFilter("sf-bloque", "bloque");
        bindFilter("sf-atado", "atado");
        bindFilter("sf-alto", "alto_min");
        bindFilter("sf-ancho", "ancho_min");

        // Carga inicial
        loadPage(0, true);
    }

    destroyPopup() {
        if (observer) { observer.disconnect(); observer = null; }
        if (this._popupKeyHandler) {
            document.removeEventListener("keydown", this._popupKeyHandler);
            this._popupKeyHandler = null;
        }
        if (this._popupRoot) {
            this._popupRoot.remove();
            this._popupRoot = null;
        }
    }
}

registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Botón Selección Piedra",
});

export const stoneOrderLineListView = { ...listView };
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);