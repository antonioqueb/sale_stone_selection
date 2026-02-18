/** @odoo-module */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, xml, onWillUnmount, onWillStart, onWillUpdateProps, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// ═══════════════════════════════════════════════════════════════════════════════
// POPUP DE SELECCIÓN DE PLACAS (Fullscreen, Lazy Loading)
// ═══════════════════════════════════════════════════════════════════════════════
export class StoneSelectorPopup extends Component {
    static template = xml`
        <div class="stone-popup-overlay" t-on-click.self="onOverlayClick">
            <div class="stone-popup-container">
                
                <!-- HEADER DEL POPUP -->
                <div class="stone-popup-header">
                    <div class="stone-popup-title">
                        <i class="fa fa-th me-2"/>
                        Seleccionar Placas
                        <span class="stone-popup-subtitle" t-if="props.productName">
                            — <t t-esc="props.productName"/>
                        </span>
                    </div>
                    <div class="stone-popup-header-actions">
                        <span class="stone-badge-selected">
                            <i class="fa fa-check-circle me-1"/>
                            <t t-esc="state.pendingIds.size"/> seleccionadas
                        </span>
                        <button class="stone-btn stone-btn-primary" t-on-click="confirmSelection">
                            <i class="fa fa-check me-1"/> Confirmar selección
                        </button>
                        <button class="stone-btn stone-btn-ghost" t-on-click="onClose">
                            <i class="fa fa-times"/>
                        </button>
                    </div>
                </div>

                <!-- FILTROS -->
                <div class="stone-popup-filters">
                    <div class="stone-filter-group">
                        <label>Lote</label>
                        <input type="text" class="stone-filter-input" placeholder="Buscar lote..."
                               t-on-input="(e) => this.onFilterChange('lot_name', e.target.value)"
                               t-att-value="state.filters.lot_name"/>
                    </div>
                    <div class="stone-filter-group">
                        <label>Bloque</label>
                        <input type="text" class="stone-filter-input" placeholder="Bloque..."
                               t-on-input="(e) => this.onFilterChange('bloque', e.target.value)"
                               t-att-value="state.filters.bloque"/>
                    </div>
                    <div class="stone-filter-group">
                        <label>Atado</label>
                        <input type="text" class="stone-filter-input" placeholder="Atado..."
                               t-on-input="(e) => this.onFilterChange('atado', e.target.value)"
                               t-att-value="state.filters.atado"/>
                    </div>
                    <div class="stone-filter-group">
                        <label>Alto mín.</label>
                        <input type="number" class="stone-filter-input stone-filter-sm" placeholder="0"
                               t-on-input="(e) => this.onFilterChange('alto_min', e.target.value)"
                               t-att-value="state.filters.alto_min"/>
                    </div>
                    <div class="stone-filter-group">
                        <label>Ancho mín.</label>
                        <input type="number" class="stone-filter-input stone-filter-sm" placeholder="0"
                               t-on-input="(e) => this.onFilterChange('ancho_min', e.target.value)"
                               t-att-value="state.filters.ancho_min"/>
                    </div>
                    <div class="stone-filter-spacer"/>
                    <div class="stone-filter-stats">
                        <span t-if="state.isLoading" class="stone-filter-stat-loading">
                            <i class="fa fa-circle-o-notch fa-spin me-1"/> Buscando...
                        </span>
                        <span t-else="" class="stone-filter-stat-count">
                            <t t-esc="state.totalCount"/> placas disponibles
                        </span>
                    </div>
                </div>

                <!-- TABLA SCROLLEABLE -->
                <div class="stone-popup-body" t-ref="scrollContainer">
                    
                    <!-- Estado vacío -->
                    <div t-if="!state.isLoading and state.quants.length === 0" class="stone-empty-state">
                        <i class="fa fa-inbox fa-3x"/>
                        <div class="stone-empty-text">No se encontraron placas con estos filtros</div>
                    </div>

                    <!-- Tabla de datos -->
                    <table t-elif="state.quants.length > 0" class="stone-popup-table">
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
                        <tbody>
                            <t t-foreach="state.quants" t-as="q" t-key="q.id">
                                <t t-set="isSelected" t-value="state.pendingIds.has(q.lot_id ? q.lot_id[0] : 0)"/>
                                <tr t-on-click="() => this.toggleLot(q)"
                                    t-att-class="isSelected ? 'row-sel' : ''">
                                    <td class="col-chk">
                                        <div t-att-class="'stone-chkbox' + (isSelected ? ' checked' : '')">
                                            <i t-if="isSelected" class="fa fa-check"/>
                                        </div>
                                    </td>
                                    <td class="cell-lot"><t t-esc="q.lot_id ? q.lot_id[1] : '-'"/></td>
                                    <td><t t-esc="q.x_bloque or '-'"/></td>
                                    <td><t t-esc="q.x_atado or '-'"/></td>
                                    <td class="col-num"><t t-esc="q.x_alto ? q.x_alto.toFixed(0) : '-'"/></td>
                                    <td class="col-num"><t t-esc="q.x_ancho ? q.x_ancho.toFixed(0) : '-'"/></td>
                                    <td class="col-num"><t t-esc="q.x_grosor or '-'"/></td>
                                    <td class="col-num fw-semibold"><t t-esc="q.quantity ? q.quantity.toFixed(2) : '-'"/></td>
                                    <td><t t-esc="q.x_tipo or '-'"/></td>
                                    <td><t t-esc="q.x_color or '-'"/></td>
                                    <td class="cell-loc">
                                        <t t-esc="q.location_id ? q.location_id[1].split('/').pop() : '-'"/>
                                    </td>
                                    <td>
                                        <span t-if="q.reserved_quantity > 0 and !isSelected" class="stone-tag stone-tag-warn">Reservado</span>
                                        <span t-elif="isSelected" class="stone-tag stone-tag-ok">Selec.</span>
                                        <span t-else="" class="stone-tag stone-tag-free">Libre</span>
                                    </td>
                                </tr>
                            </t>
                        </tbody>
                    </table>

                    <!-- Sentinel para infinite scroll -->
                    <div t-ref="scrollSentinel" class="stone-scroll-sentinel">
                        <div t-if="state.isLoadingMore" class="stone-loading-more">
                            <i class="fa fa-circle-o-notch fa-spin me-2"/> Cargando más placas...
                        </div>
                        <div t-elif="state.hasMore" class="stone-scroll-hint">
                            <i class="fa fa-chevron-down me-1"/> Desplázate para cargar más
                        </div>
                    </div>
                </div>

                <!-- FOOTER -->
                <div class="stone-popup-footer">
                    <span class="stone-footer-info">
                        Mostrando <strong><t t-esc="state.quants.length"/></strong> 
                        de <strong><t t-esc="state.totalCount"/></strong> placas
                    </span>
                    <div class="stone-footer-actions">
                        <button class="stone-btn stone-btn-ghost" t-on-click="onClose">
                            Cancelar
                        </button>
                        <button class="stone-btn stone-btn-primary" t-on-click="confirmSelection">
                            <i class="fa fa-check me-1"/>
                            Agregar <t t-if="state.pendingIds.size > 0">(<t t-esc="state.pendingIds.size"/>)</t>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    static props = {
        productId: Number,
        productName: { type: String, optional: true },
        currentLotIds: { type: Array, optional: true },
        onConfirm: Function,
        onClose: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.scrollContainerRef = useRef("scrollContainer");
        this.scrollSentinelRef = useRef("scrollSentinel");
        this.searchTimeout = null;
        this.observer = null;

        const initialIds = new Set(this.props.currentLotIds || []);

        this.state = useState({
            quants: [],
            isLoading: false,
            isLoadingMore: false,
            hasMore: false,
            totalCount: 0,
            pendingIds: initialIds,
            filters: { lot_name: '', bloque: '', atado: '', alto_min: '', ancho_min: '' },
            page: 0,
        });

        this.PAGE_SIZE = 35;

        onWillStart(async () => {
            await this.loadPage(0, true);
        });

        onWillUnmount(() => {
            if (this.observer) this.observer.disconnect();
        });
    }

    async loadPage(page, reset = false) {
        if (page === 0) {
            this.state.isLoading = true;
        } else {
            this.state.isLoadingMore = true;
        }

        try {
            const result = await this.orm.call(
                'stock.quant',
                'search_stone_inventory_for_so_paginated',
                [],
                {
                    product_id: this.props.productId,
                    filters: this.state.filters,
                    current_lot_ids: Array.from(this.state.pendingIds),
                    page: page,
                    page_size: this.PAGE_SIZE,
                }
            );

            const quants = result.items || [];
            const total = result.total || 0;

            if (reset || page === 0) {
                this.state.quants = quants;
            } else {
                this.state.quants = [...this.state.quants, ...quants];
            }

            this.state.totalCount = total;
            this.state.page = page;
            this.state.hasMore = this.state.quants.length < total;

        } catch (e) {
            console.error("[STONE POPUP] Error cargando inventario:", e);
            // Fallback al método original si el paginado no existe
            try {
                const quants = await this.orm.call(
                    'stock.quant',
                    'search_stone_inventory_for_so',
                    [],
                    {
                        product_id: this.props.productId,
                        filters: this.state.filters,
                        current_lot_ids: Array.from(this.state.pendingIds),
                    }
                );
                const paginated = (quants || []).slice(0, this.PAGE_SIZE * (page + 1));
                this.state.quants = paginated;
                this.state.totalCount = (quants || []).length;
                this.state.hasMore = paginated.length < (quants || []).length;
            } catch (e2) {
                console.error("[STONE POPUP] Fallback también falló:", e2);
            }
        } finally {
            this.state.isLoading = false;
            this.state.isLoadingMore = false;

            // Configurar IntersectionObserver después de renderizar
            setTimeout(() => this.setupIntersectionObserver(), 100);
        }
    }

    setupIntersectionObserver() {
        if (this.observer) this.observer.disconnect();

        const sentinel = this.scrollSentinelRef.el;
        const container = this.scrollContainerRef.el;

        if (!sentinel || !container) return;

        this.observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting && this.state.hasMore && !this.state.isLoadingMore) {
                    this.loadPage(this.state.page + 1, false);
                }
            },
            { root: container, rootMargin: '100px', threshold: 0.1 }
        );

        this.observer.observe(sentinel);
    }

    onFilterChange(key, value) {
        this.state.filters[key] = value;
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => this.loadPage(0, true), 350);
    }

    toggleLot(quant) {
        if (!quant.lot_id) return;
        const lotId = quant.lot_id[0];
        const newSet = new Set(this.state.pendingIds);
        if (newSet.has(lotId)) {
            newSet.delete(lotId);
        } else {
            newSet.add(lotId);
        }
        this.state.pendingIds = newSet;
    }

    confirmSelection() {
        this.props.onConfirm(Array.from(this.state.pendingIds));
    }

    onClose() {
        this.props.onClose();
    }

    onOverlayClick() {
        this.props.onClose();
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENTE PRINCIPAL: BOTÓN + TABLA DE SELECCIONADAS
// ═══════════════════════════════════════════════════════════════════════════════
export class StoneExpandButton extends Component {
    static template = xml`
        <div class="stone-field-wrapper">
            <!-- Botón cuando NO está expandido -->
            <button t-if="!state.isExpanded"
                    class="stone-toggle-btn"
                    t-on-click.stop="openExpanded"
                    title="Ver placas seleccionadas">
                <i class="fa fa-th-large"/>
                <span t-if="state.selectedCount > 0" class="stone-count-badge">
                    <t t-esc="state.selectedCount"/>
                </span>
            </button>

            <!-- Botón cuando está expandido (colapsar) -->
            <button t-if="state.isExpanded"
                    class="stone-toggle-btn active"
                    t-on-click.stop="closeExpanded"
                    title="Colapsar">
                <i class="fa fa-chevron-up"/>
            </button>
        </div>

        <!-- POPUP DE SELECCIÓN -->
        <StoneSelectorPopup t-if="state.showPopup"
            productId="getProductId()"
            productName="getProductName()"
            currentLotIds="getCurrentLotIds()"
            onConfirm.bind="onPopupConfirm"
            onClose.bind="onPopupClose"
        />
    `;

    static components = { StoneSelectorPopup };
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");

        this.state = useState({
            isExpanded: false,
            showPopup: false,
            selectedCount: 0,
            detailsRow: null,
        });

        onWillStart(() => {
            this._updateCount();
        });

        onWillUpdateProps((nextProps) => {
            this._updateCount(nextProps);
        });

        onWillUnmount(() => {
            this.removeDetailsRow();
        });
    }

    _updateCount(props = this.props) {
        const rawLots = props?.record?.data?.lot_ids;
        const ids = this.extractLotIds(rawLots);
        this.state.selectedCount = ids.length;
    }

    getProductId() {
        const pd = this.props.record.data.product_id;
        if (!pd) return 0;
        if (Array.isArray(pd)) return pd[0];
        if (typeof pd === 'number') return pd;
        if (pd.id) return pd.id;
        return 0;
    }

    getProductName() {
        const pd = this.props.record.data.product_id;
        if (!pd) return '';
        if (Array.isArray(pd)) return pd[1] || '';
        if (pd.display_name) return pd.display_name;
        if (pd.name) return pd.name;
        return '';
    }

    getCurrentLotIds() {
        return this.extractLotIds(this.props.record.data.lot_ids);
    }

    extractLotIds(rawLots) {
        if (!rawLots) return [];
        if (Array.isArray(rawLots)) return rawLots.filter(x => typeof x === 'number');
        if (rawLots.currentIds) return rawLots.currentIds;
        if (rawLots.resIds) return rawLots.resIds;
        if (rawLots.records) {
            return rawLots.records.map(r => r.resId || r.data?.id).filter(Boolean);
        }
        return [];
    }

    async openExpanded() {
        const tr = this._getMyTr();
        if (!tr) return;

        if (this.state.isExpanded) {
            this.removeDetailsRow();
            this.state.isExpanded = false;
            return;
        }

        // Cerrar otros expandidos
        document.querySelectorAll('.stone-selected-row').forEach(e => e.remove());

        this.state.isExpanded = true;
        await this.injectSelectedTable(tr);
    }

    closeExpanded() {
        this.removeDetailsRow();
        this.state.isExpanded = false;
    }

    _getMyTr() {
        const el = this.__owl__.bdom?.el || this.el;
        if (el) return el.closest('tr');
        return null;
    }

    async injectSelectedTable(currentRow) {
        const lots = this.getCurrentLotIds();

        const newTr = document.createElement('tr');
        newTr.className = 'stone-selected-row';

        const colCount = currentRow.querySelectorAll('td').length || 10;
        const td = document.createElement('td');
        td.colSpan = colCount;
        td.className = 'stone-selected-cell';

        const container = document.createElement('div');
        container.className = 'stone-selected-container';

        // Header de la sección
        const header = document.createElement('div');
        header.className = 'stone-selected-header';
        header.innerHTML = `
            <span class="stone-selected-title">
                <i class="fa fa-check-circle me-2"></i>
                Placas seleccionadas 
                <span class="stone-selected-count" id="stone-count-${currentRow.rowIndex || 0}">${lots.length}</span>
            </span>
            <button class="stone-add-btn" id="stone-add-btn-${currentRow.rowIndex || 0}">
                <i class="fa fa-plus me-1"></i> Agregar placa
            </button>
        `;
        container.appendChild(header);

        // Tabla de seleccionadas
        const tableWrapper = document.createElement('div');
        tableWrapper.className = 'stone-selected-body';
        tableWrapper.id = `stone-selected-body-${currentRow.rowIndex || 0}`;
        container.appendChild(tableWrapper);

        td.appendChild(container);
        newTr.appendChild(td);
        currentRow.after(newTr);
        this._detailsRow = newTr;

        // Renderizar tabla con datos actuales
        await this.renderSelectedTable(tableWrapper, lots);

        // Bindear botón Agregar
        const addBtn = header.querySelector('.stone-add-btn');
        if (addBtn) {
            addBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.state.showPopup = true;
            });
        }
    }

    async renderSelectedTable(container, lotIds) {
        if (!lotIds || lotIds.length === 0) {
            container.innerHTML = `
                <div class="stone-no-selection">
                    <i class="fa fa-info-circle me-2 text-muted"></i>
                    <span class="text-muted">Sin placas seleccionadas. Usa <strong>Agregar placa</strong> para comenzar.</span>
                </div>
            `;
            return;
        }

        container.innerHTML = `<div class="stone-table-loading"><i class="fa fa-circle-o-notch fa-spin"></i> Cargando datos...</div>`;

        let lotsData = [];
        try {
            lotsData = await this.orm.searchRead(
                'stock.lot',
                [['id', 'in', lotIds]],
                ['name', 'x_bloque', 'x_atado', 'x_alto', 'x_ancho', 'x_grosor', 'x_tipo', 'x_color', 'x_numero_placa'],
                { limit: lotIds.length }
            );

            // Obtener cantidades desde quants
            const quants = await this.orm.searchRead(
                'stock.quant',
                [['lot_id', 'in', lotIds], ['location_id.usage', '=', 'internal'], ['quantity', '>', 0]],
                ['lot_id', 'quantity'],
                {}
            );
            const qtyMap = {};
            for (const q of quants) {
                const lid = q.lot_id[0];
                qtyMap[lid] = (qtyMap[lid] || 0) + q.quantity;
            }

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
                            <th class="col-act">Quitar</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            for (const lot of lotsData) {
                const qty = qtyMap[lot.id] || 0;
                totalQty += qty;
                html += `
                    <tr data-lot-id="${lot.id}">
                        <td class="cell-lot">${lot.name}</td>
                        <td>${lot.x_bloque || '-'}</td>
                        <td>${lot.x_atado || '-'}</td>
                        <td class="col-num">${lot.x_alto ? lot.x_alto.toFixed(0) : '-'}</td>
                        <td class="col-num">${lot.x_ancho ? lot.x_ancho.toFixed(0) : '-'}</td>
                        <td class="col-num">${lot.x_grosor || '-'}</td>
                        <td class="col-num fw-semibold">${qty.toFixed(2)}</td>
                        <td>${lot.x_tipo || '-'}</td>
                        <td>${lot.x_color || '-'}</td>
                        <td class="col-act">
                            <button class="stone-remove-btn" data-lot-id="${lot.id}" title="Quitar placa">
                                <i class="fa fa-times"></i>
                            </button>
                        </td>
                    </tr>
                `;
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
                </table>
            `;

            container.innerHTML = html;

            // Bindear botones de quitar
            container.querySelectorAll('.stone-remove-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const lotId = parseInt(btn.dataset.lotId);
                    this.removeLot(lotId);
                });
            });

        } catch (err) {
            console.error("[STONE] Error renderizando seleccionadas:", err);
            container.innerHTML = `<div class="text-danger p-2">Error cargando datos: ${err.message}</div>`;
        }
    }

    async removeLot(lotId) {
        const currentIds = this.getCurrentLotIds();
        const newIds = currentIds.filter(id => id !== lotId);
        await this.props.record.update({ lot_ids: [[6, 0, newIds]] });
        this._updateCount();
        await this.refreshSelectedTable();
    }

    async refreshSelectedTable() {
        if (!this._detailsRow) return;
        const body = this._detailsRow.querySelector('.stone-selected-body');
        if (!body) return;
        const lots = this.getCurrentLotIds();
        // Actualizar el badge de conteo
        const countEl = this._detailsRow.querySelector('.stone-selected-count');
        if (countEl) countEl.textContent = lots.length;
        await this.renderSelectedTable(body, lots);
    }

    async onPopupConfirm(newLotIds) {
        this.state.showPopup = false;
        await this.props.record.update({ lot_ids: [[6, 0, newLotIds]] });
        this._updateCount();
        await this.refreshSelectedTable();
    }

    onPopupClose() {
        this.state.showPopup = false;
    }

    removeDetailsRow() {
        if (this._detailsRow) {
            this._detailsRow.remove();
            this._detailsRow = null;
        }
    }
}

registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Botón Selección Piedra",
});

export const stoneOrderLineListView = {
    ...listView,
};
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);