/** @odoo-module */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import {
    Component,
    useState,
    onWillStart,
    onMounted,
    onWillUpdateProps,
    onWillUnmount,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const AUTO_OPEN_STONE_SELECTOR_KEY = "stock_transit_allocation.auto_open_stone_selector";

const STATUS_CLASS_MAP = {
    delivered: "stone-tag-delivered",
    returned: "stone-tag-returned",
    redelivered: "stone-tag-redelivered",
    redelivery_pending: "stone-tag-redelivery-pending",
    pick_ticket: "stone-tag-pickticket",
    swap_replaced: "stone-tag-swap-old",
    swap_replacement: "stone-tag-swap-new",
    pending: "stone-tag-pending",
};

export class StoneExpandButton extends Component {
    static template = "sale_stone_selection.StoneExpandButton";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this._detailsRow = null;
        this._popupRoot = null;
        this._popupKeyHandler = null;
        this._popupObserver = null;
        this._lightboxRoot = null;
        this._lightboxKeyHandler = null;
        this._localBreakdown = {};
        this._removingLot = false;

        this.state = useState({
            isExpanded: false,
            selectedCount: 0,
        });

        onWillStart(() => {
            this._loadBreakdownFromRecord();
            this._updateCount();
        });

        onMounted(() => {
            window.setTimeout(() => {
                this._autoOpenStoneSelectorFromAllocationHub();
            }, 350);
        });

        onWillUpdateProps((nextProps) => {
            this._updateCount(nextProps);
        });

        onWillUnmount(() => {
            this.removeDetailsRow();
            this.destroyPopup();
            this._destroyLightbox();
        });
    }

    _getStateValue(props = this.props) {
        const value = props?.record?.data?.state;

        if (!value) {
            return "";
        }

        if (typeof value === "string") {
            return value;
        }

        if (typeof value === "object") {
            return value.value || value.raw_value || value.name || value.display_name || "";
        }

        return String(value || "");
    }

    _isSaleOrderConfirmed(props = this.props) {
        const state = this._getStateValue(props);
        return state === "sale" || state === "done";
    }

    isSelectionLocked(props = this.props) {
        return !this._isSaleOrderConfirmed(props);
    }

    _warnQuoteSelectionBlocked() {
        this.notification.add(
            "La selección de stock solo está permitida cuando la cotización ya fue confirmada como orden de venta. En cotización captura únicamente la cantidad.",
            {
                type: "warning",
                sticky: false,
            }
        );
    }

    _fmt(num) {
        if (num === null || num === undefined || isNaN(num)) return "0.00";
        return parseFloat(num).toFixed(2);
    }

    _fmtDim(num) {
        if (!num) return "-";
        const v = parseFloat(num);
        if (isNaN(v)) return "-";
        return v % 1 === 0 ? v.toFixed(0) : v.toFixed(2);
    }

    _fmtPct(num) {
        if (num === null || num === undefined || isNaN(num)) return "0";
        const v = parseFloat(num);
        return v % 1 === 0 ? v.toFixed(0) : v.toFixed(1);
    }

    _escapeHtml(text) {
        if (text === null || text === undefined) return "";
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    _parseFloatField(value) {
        if (value === null || value === undefined || value === false) return 0;
        if (typeof value === "number") return value;
        if (typeof value === "string") return parseFloat(value.replace(",", ".")) || 0;
        if (typeof value === "object") {
            if ("value" in value) return this._parseFloatField(value.value);
            if ("raw_value" in value) return this._parseFloatField(value.raw_value);
        }
        return 0;
    }

    _getRequestedQty() {
        return this._parseFloatField(this.props?.record?.data?.product_uom_qty);
    }

    _getRequestedUnit() {
        const data = this.props?.record?.data || {};
        const uom = data.product_uom || data.product_uom_id || data.product_uom_name;

        if (Array.isArray(uom)) return uom[1] || "m²";
        if (typeof uom === "string" && uom.trim()) return uom.trim();
        if (uom && typeof uom === "object") {
            return uom.display_name || uom.name || "m²";
        }

        return "m²";
    }

    _isPieceUnit(unit) {
        const txt = String(unit || "").toLowerCase();
        return txt.includes("pza") || txt.includes("pieza") || txt.includes("unidad") || txt.includes("unit");
    }

    _getAllocationBaseFromTotals(totals, targetUnit) {
        if (this._isPieceUnit(targetUnit)) {
            return totals.totalPiezas || totals.totalM2 || 0;
        }
        return totals.totalM2 || totals.totalPiezas || 0;
    }

    _updateCount(props = this.props) {
        if (this.isSelectionLocked(props)) {
            this.state.selectedCount = 0;
            return;
        }

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
        if (this.isSelectionLocked()) {
            return [];
        }
        return this.extractLotIds(this.props.record.data.lot_ids);
    }

    _loadBreakdownFromRecord() {
        if (this.isSelectionLocked()) {
            this._localBreakdown = {};
            return;
        }

        const raw = this.props.record.data.x_lot_breakdown_json;
        if (!raw) {
            this._localBreakdown = {};
            return;
        }
        if (typeof raw === "string") {
            try {
                this._localBreakdown = JSON.parse(raw);
            } catch {
                this._localBreakdown = {};
            }
        } else if (typeof raw === "object") {
            this._localBreakdown = { ...raw };
        } else {
            this._localBreakdown = {};
        }
    }

    getBreakdown() {
        return { ...this._localBreakdown };
    }

    _getRecordId() {
        const rec = this.props.record;
        if (rec.resId) return rec.resId;
        if (rec.data && rec.data.id) return rec.data.id;
        return null;
    }

    async _saveBreakdownToServer(breakdown) {
        if (this.isSelectionLocked()) {
            this._warnQuoteSelectionBlocked();
            return;
        }

        this._localBreakdown = { ...breakdown };
        const recordId = this._getRecordId();
        if (recordId && typeof recordId === "number" && recordId > 0) {
            try {
                await this.orm.write("sale.order.line", [recordId], {
                    x_lot_breakdown_json: breakdown,
                });
                // Sin 'Mandar a pedir', el backend iguala Solicitado a la suma de placas.
                await this._refreshRequestedQtyFromServer();
            } catch (e) {
                console.warn("[STONE] Error guardando breakdown al server:", e);
            }
        }
    }

    /**
     * Refresca product_uom_qty (Solicitado) desde el servidor hacia el record en
     * memoria.
     *
     * Sin 'Mandar a pedir', la cantidad vendible la fija el backend igualándola a
     * la suma de placas asignadas. Hay que reflejar ese valor en el record para
     * que la línea lo muestre al instante y para que un guardado posterior del
     * formulario no reescriba el valor viejo encima del derivado.
     */
    async _refreshRequestedQtyFromServer() {
        const recordId = this._getRecordId();
        if (!recordId || typeof recordId !== "number" || recordId <= 0) {
            return;
        }
        try {
            const rows = await this.orm.read(
                "sale.order.line",
                [recordId],
                ["product_uom_qty"],
            );
            if (!rows || !rows.length) {
                return;
            }
            const serverQty = rows[0].product_uom_qty || 0;
            const currentQty = this._getRequestedQty();
            if (Math.abs(serverQty - currentQty) > 0.000001) {
                await this.props.record.update({ product_uom_qty: serverQty });
            }
        } catch (e) {
            console.warn("[STONE] No se pudo refrescar la cantidad solicitada:", e);
        }
    }

    /**
     * Persiste lot_ids + breakdown de inmediato al backend SIN recargar la página.
     * 1. Actualiza el record en memoria para mantener coherente la orden y el popup.
     * 2. Escribe directo por ORM, lo que dispara el write de Python
     *    (=> _sync_lots_to_picking_moves) sin necesidad de pulsar Guardar.
     */
    async _commitSelectionToServer(newIds, breakdown) {
        if (this.isSelectionLocked()) {
            this._warnQuoteSelectionBlocked();
            return;
        }

        this._localBreakdown = { ...breakdown };

        await this.props.record.update({
            lot_ids: [[6, 0, newIds]],
            x_lot_breakdown_json: breakdown,
        });

        const recordId = this._getRecordId();
        if (recordId && typeof recordId === "number" && recordId > 0) {
            await this.orm.write("sale.order.line", [recordId], {
                lot_ids: [[6, 0, newIds]],
                x_lot_breakdown_json: breakdown,
            });
            // Sin 'Mandar a pedir', el backend iguala Solicitado a la suma de placas.
            await this._refreshRequestedQtyFromServer();
        }
    }

    async _loadFullStatus() {
        if (this.isSelectionLocked()) {
            return [];
        }

        const recordId = this._getRecordId();
        if (!recordId || typeof recordId !== "number" || recordId <= 0) {
            return null;
        }
        try {
            const result = await this.orm.call(
                "sale.order.line",
                "get_stone_lots_full_status",
                [[recordId]],
            );
            return Array.isArray(result) ? result : null;
        } catch (e) {
            console.warn("[STONE] No se pudo cargar full status:", e);
            return null;
        }
    }

    _renderStatusBadges(badges, opts = {}) {
        if (!badges || badges.length === 0) return "";
        const compact = opts.compact || false;

        return badges.map((b) => {
            const cls = STATUS_CLASS_MAP[b.type] || "stone-tag-pending";
            const icon = b.icon || "fa-tag";
            const labelEsc = this._escapeHtml(b.label);
            const labelText = compact ? labelEsc.split(" · ")[0] : labelEsc;
            return `<span class="stone-tag stone-status-tag ${cls}" title="${labelEsc}">
                        <i class="fa ${icon}"></i><span>${labelText}</span>
                    </span>`;
        }).join("");
    }

    _autoOpenStoneSelectorFromAllocationHub() {
        if (this.isSelectionLocked()) {
            return;
        }

        if (typeof window === "undefined" || !window.sessionStorage) {
            return;
        }

        let payload = null;

        try {
            const raw = window.sessionStorage.getItem(AUTO_OPEN_STONE_SELECTOR_KEY);
            if (!raw) {
                return;
            }

            payload = JSON.parse(raw);
        } catch (error) {
            console.warn("[STONE] Auto-open inválido:", error);
            window.sessionStorage.removeItem(AUTO_OPEN_STONE_SELECTOR_KEY);
            return;
        }

        if (!payload || payload.source !== "to_be_allocated") {
            return;
        }

        const maxAgeMs = 5 * 60 * 1000;
        if (!payload.ts || Date.now() - payload.ts > maxAgeMs) {
            window.sessionStorage.removeItem(AUTO_OPEN_STONE_SELECTOR_KEY);
            return;
        }

        const currentLineId = this._getRecordId();
        const targetLineId = parseInt(payload.sale_line_id, 10);

        if (!currentLineId || !targetLineId || parseInt(currentLineId, 10) !== targetLineId) {
            return;
        }

        window.sessionStorage.removeItem(AUTO_OPEN_STONE_SELECTOR_KEY);

        window.setTimeout(() => {
            this.openPopup();
        }, 150);
    }

    async openLightbox(lotId, lotName, mainPhoto) {
        this._destroyLightbox();

        this._lightboxRoot = document.createElement("div");
        this._lightboxRoot.className = "stone-lightbox-root";
        document.body.appendChild(this._lightboxRoot);

        const initialSrc = mainPhoto ? `data:image/jpeg;base64,${mainPhoto}` : null;

        this._lightboxRoot.innerHTML = `
            <div class="stone-lightbox-overlay" id="slb-overlay">
                <div class="stone-lightbox-container">
                    <div class="stone-lightbox-header">
                        <span class="stone-lightbox-title">
                            <i class="fa fa-camera me-2"></i>
                            Fotos del lote <strong>${this._escapeHtml(lotName || lotId)}</strong>
                            <span class="stone-lightbox-counter" id="slb-counter"></span>
                        </span>
                        <button class="stone-lightbox-close" id="slb-close">
                            <i class="fa fa-times"></i>
                        </button>
                    </div>
                    <div class="stone-lightbox-body" id="slb-body">
                        ${initialSrc
                            ? `<img src="${initialSrc}" class="stone-lightbox-img" id="slb-main-img"/>`
                            : `<div class="stone-lightbox-loading"><i class="fa fa-circle-o-notch fa-spin fa-2x"></i><div class="mt-2">Cargando fotos...</div></div>`
                        }
                    </div>
                    <div class="stone-lightbox-nav" id="slb-nav" style="display:none;">
                        <button class="stone-lightbox-nav-btn" id="slb-prev"><i class="fa fa-chevron-left"></i></button>
                        <div class="stone-lightbox-thumbs" id="slb-thumbs"></div>
                        <button class="stone-lightbox-nav-btn" id="slb-next"><i class="fa fa-chevron-right"></i></button>
                    </div>
                </div>
            </div>`;

        const overlay = this._lightboxRoot.querySelector("#slb-overlay");
        const bodyEl = this._lightboxRoot.querySelector("#slb-body");
        const navEl = this._lightboxRoot.querySelector("#slb-nav");
        const thumbsEl = this._lightboxRoot.querySelector("#slb-thumbs");
        const counterEl = this._lightboxRoot.querySelector("#slb-counter");
        const prevBtn = this._lightboxRoot.querySelector("#slb-prev");
        const nextBtn = this._lightboxRoot.querySelector("#slb-next");

        const closeLb = () => this._destroyLightbox();

        this._lightboxRoot.querySelector("#slb-close").addEventListener("click", closeLb);
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) closeLb();
        });

        const keyHandler = (e) => {
            if (e.key === "Escape") closeLb();
            if (e.key === "ArrowLeft" && prevBtn) prevBtn.click();
            if (e.key === "ArrowRight" && nextBtn) nextBtn.click();
        };
        document.addEventListener("keydown", keyHandler);
        this._lightboxKeyHandler = keyHandler;

        try {
            const photos = await this.orm.searchRead(
                "stock.lot.image",
                [["lot_id", "=", lotId]],
                ["id", "name", "image", "notas", "fecha_captura"],
                { order: "sequence, id", limit: 50 }
            );

            if (!photos || photos.length === 0) {
                if (initialSrc) {
                    counterEl.textContent = "(1 foto)";
                } else {
                    bodyEl.innerHTML = `
                        <div class="stone-lightbox-loading">
                            <i class="fa fa-picture-o fa-2x text-muted"></i>
                            <div class="mt-2 text-muted">Este lote no tiene fotografías</div>
                        </div>`;
                }
                return;
            }

            let currentIdx = 0;

            const showPhoto = (idx) => {
                currentIdx = idx;
                const photo = photos[idx];
                const src = `data:image/jpeg;base64,${photo.image}`;
                bodyEl.innerHTML = `
                    <img src="${src}" class="stone-lightbox-img" id="slb-main-img"/>
                    <div class="stone-lightbox-info" id="slb-info">
                        <strong>${this._escapeHtml(photo.name || "")}</strong>
                        ${photo.notas ? `<span class="ms-3 text-muted">${this._escapeHtml(photo.notas)}</span>` : ""}
                        ${photo.fecha_captura ? `<span class="ms-3 text-muted small"><i class="fa fa-clock-o me-1"></i>${this._escapeHtml(photo.fecha_captura)}</span>` : ""}
                    </div>`;
                counterEl.textContent = `(${idx + 1} / ${photos.length})`;

                thumbsEl.querySelectorAll(".stone-lightbox-thumb").forEach((th, i) => {
                    th.classList.toggle("active", i === idx);
                });
            };

            if (photos.length > 1) {
                navEl.style.display = "flex";
                let thumbsHtml = "";
                for (let i = 0; i < photos.length; i++) {
                    const src = `data:image/jpeg;base64,${photos[i].image}`;
                    thumbsHtml += `<img src="${src}" class="stone-lightbox-thumb ${i === 0 ? "active" : ""}" data-idx="${i}"/>`;
                }
                thumbsEl.innerHTML = thumbsHtml;

                thumbsEl.querySelectorAll(".stone-lightbox-thumb").forEach((th) => {
                    th.addEventListener("click", () => showPhoto(parseInt(th.dataset.idx)));
                });

                prevBtn.addEventListener("click", () => {
                    if (currentIdx > 0) showPhoto(currentIdx - 1);
                });
                nextBtn.addEventListener("click", () => {
                    if (currentIdx < photos.length - 1) showPhoto(currentIdx + 1);
                });
            }

            showPhoto(0);

        } catch (e) {
            console.error("[STONE] Error cargando fotos:", e);
            bodyEl.innerHTML = `
                <div class="stone-lightbox-loading">
                    <i class="fa fa-exclamation-triangle fa-2x text-danger"></i>
                    <div class="mt-2 text-danger">Error cargando fotos: ${this._escapeHtml(e.message)}</div>
                </div>`;
        }
    }

    _destroyLightbox() {
        if (this._lightboxKeyHandler) {
            document.removeEventListener("keydown", this._lightboxKeyHandler);
            this._lightboxKeyHandler = null;
        }
        if (this._lightboxRoot) {
            this._lightboxRoot.remove();
            this._lightboxRoot = null;
        }
    }

    _renderPhotoCell(photoBase64, photoCount, lotId, lotName) {
        const safeName = this._escapeHtml(lotName);
        if (photoBase64) {
            const badge = photoCount > 1 ? `<span class="stone-photo-count">${photoCount}</span>` : "";
            return `<div class="stone-photo-cell" data-lot-id="${lotId}" data-lot-name="${safeName}" data-has-photo="1">
                        <img src="data:image/jpeg;base64,${photoBase64}" class="stone-photo-thumb" alt="Foto"/>
                        ${badge}
                    </div>`;
        }
        if (photoCount > 0) {
            return `<div class="stone-photo-cell" data-lot-id="${lotId}" data-lot-name="${safeName}" data-has-photo="1">
                        <div class="stone-photo-placeholder-has"><i class="fa fa-camera"></i><span>${photoCount}</span></div>
                    </div>`;
        }
        return `<div class="stone-photo-cell stone-photo-empty"><i class="fa fa-picture-o text-muted"></i></div>`;
    }

    _bindPhotoClicks(container) {
        container.querySelectorAll(".stone-photo-cell[data-has-photo]").forEach((cell) => {
            cell.style.cursor = "pointer";
            cell.addEventListener("click", (e) => {
                e.stopPropagation();
                const lotId = parseInt(cell.dataset.lotId);
                const lotName = cell.dataset.lotName || "";
                const img = cell.querySelector(".stone-photo-thumb");
                let mainPhoto = false;
                if (img && img.src.startsWith("data:")) {
                    mainPhoto = img.src.replace(/^data:image\/\w+;base64,/, "");
                }
                this.openLightbox(lotId, lotName, mainPhoto);
            });
        });
    }

    async handleToggle(ev) {
        ev.stopPropagation();

        if (this.isSelectionLocked()) {
            this.removeDetailsRow();
            this.state.isExpanded = false;
            this._warnQuoteSelectionBlocked();
            return;
        }

        if (this.state.isExpanded) {
            this.removeDetailsRow();
            this.state.isExpanded = false;
            return;
        }

        document.querySelectorAll(".stone-selected-row").forEach((e) => e.remove());

        const tr = ev.currentTarget.closest("tr");
        if (!tr) return;

        this._loadBreakdownFromRecord();

        this.state.isExpanded = true;
        await this.injectSelectedTable(tr);
    }

    _addBtnLabel(count) {
        // Sin selección: "Añadir Materiales". Con al menos una placa: "Editar".
        // En ambos casos sin el signo "+".
        return (count > 0) ? "Editar" : "Añadir Materiales";
    }

    _updateAddButtonLabel(count = null) {
        if (!this._detailsRow) return;
        const btn = this._detailsRow.querySelector(".stone-add-btn-trigger");
        if (!btn) return;
        const n = (count === null) ? this.getCurrentLotIds().length : count;
        btn.textContent = this._addBtnLabel(n);
    }

    /**
     * Busca el contenedor con scroll horizontal de la lista de Odoo para conocer
     * el ancho realmente visible (el del viewport de la lista, no el de la tabla
     * estirada con muchas columnas).
     */
    _getListScroller(fromEl) {
        let node = fromEl ? fromEl.parentElement : null;
        while (node && node !== document.body) {
            const st = window.getComputedStyle(node);
            if (/(auto|scroll)/.test(st.overflowX)) {
                return node;
            }
            node = node.parentElement;
        }
        if (fromEl && fromEl.closest) {
            return fromEl.closest(".o_list_renderer") || fromEl.closest(".o_content");
        }
        return null;
    }

    /**
     * Limita el ancho del panel de seleccionadas al ancho visible de la lista,
     * de modo que quepa en pantalla sin scroll horizontal propio.
     */
    _fitDetailsToViewport(fromEl) {
        if (!this._detailsRow) return;
        const container = this._detailsRow.querySelector(".stone-selected-container");
        if (!container) return;

        const scroller = this._getListScroller(fromEl || this._detailsRow);
        const visibleWidth = scroller ? scroller.clientWidth : (window.innerWidth || 0);
        if (visibleWidth > 0) {
            // Resta los márgenes laterales del contenedor (16 izq + 10 der).
            const w = Math.max(320, visibleWidth - 26);
            container.style.width = `${w}px`;
            container.style.maxWidth = `${w}px`;
        }
    }

    _bindDetailsResize(fromEl) {
        this._unbindDetailsResize();
        this._selResizeHandler = () => this._fitDetailsToViewport(fromEl);
        window.addEventListener("resize", this._selResizeHandler);
    }

    _unbindDetailsResize() {
        if (this._selResizeHandler) {
            window.removeEventListener("resize", this._selResizeHandler);
            this._selResizeHandler = null;
        }
    }

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
            <button class="stone-add-btn stone-add-btn-trigger stone-add-btn-prominent">
                ${this._addBtnLabel(this.getCurrentLotIds().length)}
            </button>
            <span class="stone-selected-title">
                <i class="fa fa-check-circle me-2"></i>
                Lotes seleccionados
                <span class="stone-sel-badge" id="stone-sel-badge">${this.getCurrentLotIds().length}</span>
            </span>
        `;

        const body = document.createElement("div");
        body.className = "stone-selected-body";

        container.appendChild(header);
        container.appendChild(body);
        td.appendChild(container);
        newTr.appendChild(td);
        currentRow.after(newTr);
        this._detailsRow = newTr;

        // Ancla el panel al ancho VISIBLE de la lista para no requerir scroll
        // horizontal aunque la línea tenga muchísimas columnas.
        this._fitDetailsToViewport(currentRow);
        this._bindDetailsResize(currentRow);

        await this.renderSelectedTable(body, this.getCurrentLotIds());

        header.querySelector(".stone-add-btn-trigger").addEventListener("click", (e) => {
            e.stopPropagation();
            this.openPopup();
        });
    }

    async renderSelectedTable(container, lotIds) {
        container.innerHTML = `<div class="stone-table-loading"><i class="fa fa-circle-o-notch fa-spin me-1"></i> Cargando...</div>`;

        try {
            const fullStatus = await this._loadFullStatus();

            if (fullStatus !== null) {
                this._renderSelectedTableFromFullStatus(container, fullStatus);
                return;
            }

            await this._renderSelectedTableLegacy(container, lotIds);
        } catch (err) {
            console.error("[STONE] Error renderizando seleccionadas:", err);
            container.innerHTML = `<div class="text-danger p-2">Error: ${this._escapeHtml(err.message)}</div>`;
        }
    }

    _renderSelectedTableFromFullStatus(container, items) {
        if (!items || items.length === 0) {
            container.innerHTML = `
                <div class="stone-no-selection">
                    <i class="fa fa-info-circle me-1 text-muted"></i>
                    <span class="text-muted">Sin lotes. Usa <strong>Agregar</strong> para comenzar.</span>
                </div>`;
            return;
        }

        let totalQty = 0;
        let html = `
            <table class="stone-sel-table stone-sel-table-with-status">
                <thead>
                    <tr>
                        <th class="col-photo">Foto</th>
                        <th>Lote</th>
                        <th class="col-status">Estatus</th>
                        <th>Bloque</th>
                        <th>Atado</th>
                        <th class="col-num">Alto</th>
                        <th class="col-num">Ancho</th>
                        <th class="col-num">Esp.</th>
                        <th>Tipo</th>
                        <th class="col-num">Disp.</th>
                        <th class="col-num col-qty-input">Cant.</th>
                        <th>Color</th>
                        <th class="col-act"></th>
                    </tr>
                </thead>
                <tbody>`;

        for (const item of items) {
            const tipo = item.tipo || "placa";
            const isPartial = (tipo === "formato" || tipo === "pieza");
            const isGhost = !!item.is_ghost;
            const isLocked = !!item.is_locked;

            if (!isGhost) {
                totalQty += item.displayed_qty || 0;
            }

            const rowClasses = [];
            if (isGhost) rowClasses.push("stone-row-ghost");
            if (isLocked && !isGhost) rowClasses.push("stone-row-locked");

            const qtyLabel = tipo === "pieza" ? "pzas" : "m²";
            const inputStep = tipo === "pieza" ? "1" : "0.01";

            const photoCell = this._renderPhotoCell(
                item.x_fotografia_principal,
                item.x_cantidad_fotos || 0,
                item.lot_id,
                item.lot_name
            );

            const badgesHtml = this._renderStatusBadges(item.status_badges, { compact: false });

            let qtyCell;
            if (isGhost) {
                qtyCell = `<span class="text-muted"><s>0.00</s> ${qtyLabel}</span>`;
            } else if (isPartial && !isLocked) {
                qtyCell = `<input type="number" class="stone-qty-input"
                                  data-lot-id="${item.lot_id}" data-max="${item.available_qty}"
                                  step="${inputStep}" min="0" max="${item.available_qty}"
                                  value="${item.displayed_qty || 0}" />`;
            } else {
                qtyCell = `<span class="fw-semibold">${this._fmt(item.displayed_qty)} ${qtyLabel}</span>`;
            }

            const lockMsg = isLocked
                ? this._escapeHtml(item.status_badges?.[0]?.label || "Bloqueado")
                : "Quitar";

            const removeBtn = isLocked
                ? `<button class="stone-remove-btn stone-remove-btn-disabled" disabled title="${lockMsg}">
                       <i class="fa fa-lock"></i>
                   </button>`
                : `<button class="stone-remove-btn" data-lot-id="${item.lot_id}" title="Quitar">
                       <i class="fa fa-times"></i>
                   </button>`;

            const lotNameHtml = isGhost
                ? `<s>${this._escapeHtml(item.lot_name)}</s>`
                : this._escapeHtml(item.lot_name);

            const tipoLabel = tipo.charAt(0).toUpperCase() + tipo.slice(1);

            html += `
                <tr class="${rowClasses.join(" ")}">
                    <td class="col-photo">${photoCell}</td>
                    <td class="cell-lot">${lotNameHtml}</td>
                    <td class="col-status">${badgesHtml}</td>
                    <td>${this._escapeHtml(item.x_bloque) || "-"}</td>
                    <td>${this._escapeHtml(item.x_atado) || "-"}</td>
                    <td class="col-num">${this._fmtDim(item.x_alto)}</td>
                    <td class="col-num">${this._fmtDim(item.x_ancho)}</td>
                    <td class="col-num">${this._fmtDim(item.x_grosor)}</td>
                    <td>
                        <span class="stone-tag stone-tag-tipo-${tipo}">${tipoLabel}</span>
                    </td>
                    <td class="col-num text-muted">${this._fmt(item.available_qty)} ${qtyLabel}</td>
                    <td class="col-num col-qty-input">${qtyCell}</td>
                    <td>${this._escapeHtml(item.x_color) || "-"}</td>
                    <td class="col-act">${removeBtn}</td>
                </tr>`;
        }

        html += `
                </tbody>
                <tfoot>
                    <tr class="stone-total-row">
                        <td colspan="10" class="text-end fw-bold text-muted">Total:</td>
                        <td class="col-num fw-bold" id="stone-sel-total">${this._fmt(totalQty)}</td>
                        <td colspan="2"></td>
                    </tr>
                </tfoot>
            </table>`;

        container.innerHTML = html;

        container.querySelectorAll(".stone-remove-btn:not([disabled])").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                this.removeLot(parseInt(btn.dataset.lotId), btn);
            });
        });

        container.querySelectorAll(".stone-qty-input").forEach((input) => {
            let debounceTimer = null;
            input.addEventListener("input", (e) => {
                if (debounceTimer) clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    this._onQtyInputChange(e.target);
                }, 500);
            });
            input.addEventListener("blur", (e) => {
                if (debounceTimer) clearTimeout(debounceTimer);
                this._onQtyInputChange(e.target);
            });
        });

        this._bindPhotoClicks(container);
    }

    async _renderSelectedTableLegacy(container, lotIds) {
        if (!lotIds || lotIds.length === 0) {
            container.innerHTML = `
                <div class="stone-no-selection">
                    <i class="fa fa-info-circle me-1 text-muted"></i>
                    <span class="text-muted">Sin lotes. Usa <strong>Agregar</strong> para comenzar.</span>
                </div>`;
            return;
        }

        const [lotsData, quants] = await Promise.all([
            this.orm.searchRead(
                "stock.lot",
                [["id", "in", lotIds]],
                ["name", "x_bloque", "x_atado", "x_alto", "x_ancho", "x_grosor", "x_tipo", "x_color",
                 "x_fotografia_principal", "x_cantidad_fotos"],
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

        const breakdown = this.getBreakdown();

        const items = [];
        for (const lid of lotIds) {
            const lot = lotMap[lid];
            if (!lot) continue;
            const availQty = qtyMap[lid] || 0;
            const tipo = (lot.x_tipo || "placa").toLowerCase();
            const isPartial = (tipo === "formato" || tipo === "pieza");
            const lotIdStr = String(lid);

            let displayQty;
            if (isPartial && breakdown[lotIdStr] !== undefined) {
                displayQty = parseFloat(breakdown[lotIdStr]);
            } else {
                displayQty = availQty;
            }

            items.push({
                lot_id: lid,
                lot_name: lot.name || "",
                product_id: this.getProductId(),
                available_qty: availQty,
                displayed_qty: displayQty,
                tipo,
                x_bloque: lot.x_bloque || "",
                x_atado: lot.x_atado || "",
                x_alto: lot.x_alto || 0,
                x_ancho: lot.x_ancho || 0,
                x_grosor: lot.x_grosor || 0,
                x_color: lot.x_color || "",
                x_fotografia_principal: lot.x_fotografia_principal || false,
                x_cantidad_fotos: lot.x_cantidad_fotos || 0,
                status_badges: [{ type: "pending", label: "Pendiente", icon: "fa-clock-o" }],
                is_locked: false,
                is_ghost: false,
            });
        }

        this._renderSelectedTableFromFullStatus(container, items);
    }

    async _onQtyInputChange(input) {
        if (this.isSelectionLocked()) {
            this._warnQuoteSelectionBlocked();
            return;
        }

        const lotId = parseInt(input.dataset.lotId);
        const maxQty = parseFloat(input.dataset.max) || 0;
        let val = parseFloat(input.value) || 0;

        if (val < 0) val = 0;
        if (val > maxQty) val = maxQty;
        input.value = val;

        const breakdown = this.getBreakdown();
        if (val > 0) {
            breakdown[String(lotId)] = val;
        } else {
            delete breakdown[String(lotId)];
        }

        await this._saveBreakdownToServer(breakdown);
        this._recalcInlineTotal();
    }

    _recalcInlineTotal() {
        if (!this._detailsRow) return;
        const totalEl = this._detailsRow.querySelector("#stone-sel-total");
        if (!totalEl) return;

        let total = 0;
        this._detailsRow.querySelectorAll("tbody tr:not(.stone-row-ghost) .stone-qty-input").forEach((inp) => {
            total += parseFloat(inp.value) || 0;
        });
        this._detailsRow.querySelectorAll("tbody tr:not(.stone-row-ghost) td.col-qty-input .fw-semibold").forEach((span) => {
            const m = span.textContent.match(/([\d.]+)/);
            if (m) total += parseFloat(m[1]) || 0;
        });
        totalEl.textContent = this._fmt(total);
    }

    /**
     * Quita un lote de la selección.
     * - Animación de salida + eliminación optimista en el DOM (sensación instantánea).
     * - Persiste de inmediato al backend SIN recargar la página.
     * - Si algo falla, restaura la tabla al estado real.
     */
    async removeLot(lotId, btnEl = null) {
        if (this.isSelectionLocked()) {
            this._warnQuoteSelectionBlocked();
            return;
        }

        if (this._removingLot) return;
        this._removingLot = true;

        const toggleableBtns = () =>
            this._detailsRow
                ? this._detailsRow.querySelectorAll(".stone-remove-btn:not(.stone-remove-btn-disabled)")
                : [];

        const rowEl = btnEl ? btnEl.closest("tr") : null;
        if (rowEl) rowEl.classList.add("stone-row-removing");
        toggleableBtns().forEach((b) => (b.disabled = true));

        const newIds = this.getCurrentLotIds().filter((id) => id !== lotId);
        const breakdown = this.getBreakdown();
        delete breakdown[String(lotId)];

        try {
            // Eliminación optimista en pantalla
            if (rowEl) {
                await new Promise((r) => setTimeout(r, 170));
                rowEl.remove();
            }

            // Refresca contadores de la UI al instante
            this._recalcInlineTotal();
            if (this._detailsRow) {
                const badge = this._detailsRow.querySelector(".stone-sel-badge");
                if (badge) badge.textContent = newIds.length;
                this._updateAddButtonLabel(newIds.length);
            }

            // Persiste al backend (dispara la sync del picking)
            await this._commitSelectionToServer(newIds, breakdown);
            this._updateCount();

            // Si ya no quedan lotes, mostrar estado vacío
            if (newIds.length === 0) {
                await this.refreshSelectedTable();
            }
        } catch (e) {
            console.error("[STONE] Error eliminando lote:", e);
            this.notification.add("No se pudo eliminar el lote. Reintenta.", { type: "danger" });
            await this.refreshSelectedTable();
        } finally {
            this._removingLot = false;
            toggleableBtns().forEach((b) => (b.disabled = false));
        }
    }

    async refreshSelectedTable() {
        if (!this._detailsRow) return;
        const body = this._detailsRow.querySelector(".stone-selected-body");
        if (!body) return;
        const lots = this.getCurrentLotIds();
        const badge = this._detailsRow.querySelector(".stone-sel-badge");
        if (badge) badge.textContent = lots.length;
        this._updateAddButtonLabel();
        await this.renderSelectedTable(body, lots);
    }

    removeDetailsRow() {
        this._unbindDetailsResize();
        if (this._detailsRow) {
            this._detailsRow.remove();
            this._detailsRow = null;
        }
    }

    async _computeTotalQty(lotIds, breakdown, quantsCache = null) {
        if (!lotIds || lotIds.length === 0) return 0;

        let qtyMap = {};

        if (quantsCache) {
            for (const q of quantsCache) {
                const lid = q.lot_id ? q.lot_id[0] : 0;
                if (lid && lotIds.includes(lid)) {
                    qtyMap[lid] = { qty: q.quantity || 0, tipo: (q.x_tipo || "placa").toLowerCase() };
                }
            }
        }

        const missingIds = lotIds.filter((id) => !qtyMap[id]);
        if (missingIds.length > 0) {
            try {
                const [lotsData, quants] = await Promise.all([
                    this.orm.searchRead(
                        "stock.lot",
                        [["id", "in", missingIds]],
                        ["id", "x_tipo"],
                        { limit: missingIds.length }
                    ),
                    this.orm.searchRead(
                        "stock.quant",
                        [
                            ["lot_id", "in", missingIds],
                            ["location_id.usage", "=", "internal"],
                            ["quantity", ">", 0],
                        ],
                        ["lot_id", "quantity"],
                        { limit: missingIds.length * 2 }
                    ),
                ]);

                const tipoMap = {};
                for (const l of lotsData) {
                    tipoMap[l.id] = (l.x_tipo || "placa").toLowerCase();
                }

                for (const q of quants) {
                    const lid = q.lot_id[0];
                    const prevQty = qtyMap[lid]?.qty || 0;
                    qtyMap[lid] = {
                        qty: prevQty + q.quantity,
                        tipo: tipoMap[lid] || "placa",
                    };
                }

                for (const lid of missingIds) {
                    if (!qtyMap[lid]) {
                        qtyMap[lid] = { qty: 0, tipo: tipoMap[lid] || "placa" };
                    }
                }
            } catch (e) {
                console.error("[STONE] Error calculando qty total:", e);
            }
        }

        let total = 0;
        for (const lid of lotIds) {
            const info = qtyMap[lid];
            if (!info) continue;

            const tipo = info.tipo;
            const lotIdStr = String(lid);
            const isPartial = tipo === "formato" || tipo === "pieza";

            if (isPartial && breakdown[lotIdStr] !== undefined) {
                total += parseFloat(breakdown[lotIdStr]) || 0;
            } else {
                total += info.qty;
            }
        }

        return total;
    }

    openPopup() {
        if (this.isSelectionLocked()) {
            this._warnQuoteSelectionBlocked();
            return;
        }

        this.destroyPopup();
        const productId = this.getProductId();
        if (!productId) return;

        this._popupRoot = document.createElement("div");
        this._popupRoot.className = "stone-popup-root";
        document.body.appendChild(this._popupRoot);

        this._renderPopupDOM(productId);
    }

    async _loadPopupStatusMap() {
        const fullStatus = await this._loadFullStatus();
        if (!fullStatus) return new Map();
        const m = new Map();
        for (const item of fullStatus) {
            m.set(item.lot_id, item);
        }
        return m;
    }

    async _renderPopupDOM(productId) {
        const root = this._popupRoot;
        const PAGE_SIZE = 35;
        const self = this;

        const statusMap = await this._loadPopupStatusMap();

        const state = {
            quants: [],
            totalCount: 0,
            hasMore: false,
            isLoading: false,
            isLoadingMore: false,
            page: 0,
            pendingIds: new Set(this.getCurrentLotIds()),
            pendingBreakdown: { ...this.getBreakdown() },
            requestedQty: this._getRequestedQty(),
            requestedUnit: this._getRequestedUnit(),
            qtyCache: {},
            statusMap,
            filters: { lot_name: "", bloque: "", atado: "", alto_min: "", ancho_min: "", tipo: "" },
        };

        let searchTimeout = null;

        root.innerHTML = `
            <div class="stone-popup-overlay" id="stone-overlay">
                <div class="stone-popup-container">

                    <div class="stone-popup-header">
                        <div class="stone-popup-title">
                            <i class="fa fa-th me-2"></i>
                            Seleccionar Lotes
                            <span class="stone-popup-subtitle">${this.getProductName() ? "— " + this._escapeHtml(this.getProductName()) : ""}</span>
                        </div>
                        <div class="stone-popup-header-actions">
                            <span class="stone-badge-requested">
                                <i class="fa fa-bullseye me-1"></i>
                                Solicitado <span id="sp-badge-target">${this._fmt(state.requestedQty)}</span>
                                <span id="sp-badge-target-unit">${this._escapeHtml(state.requestedUnit)}</span>
                            </span>
                            <span class="stone-badge-selected">
                                <i class="fa fa-check-circle me-1"></i>
                                <span id="sp-badge-count">${state.pendingIds.size}</span> selec.
                            </span>
                            <span class="stone-badge-qty-total">
                                <i class="fa fa-balance-scale me-1"></i>
                                <span id="sp-badge-qty">0.00</span>
                                <span id="sp-badge-unit">m²</span>
                            </span>
                            <button class="stone-btn stone-btn-ghost" id="sp-close">
                                <i class="fa fa-times"></i>
                            </button>
                        </div>
                    </div>

                    <div class="stone-popup-allocation-summary" id="sp-allocation-summary">
                        <div class="stone-allocation-card stone-allocation-target">
                            <span class="stone-allocation-label">Solicitado</span>
                            <strong id="sp-allocation-target">${this._fmt(state.requestedQty)} ${this._escapeHtml(state.requestedUnit)}</strong>
                        </div>
                        <div class="stone-allocation-card stone-allocation-selected">
                            <span class="stone-allocation-label">Asignado</span>
                            <strong id="sp-allocation-selected">0.00 ${this._escapeHtml(state.requestedUnit)}</strong>
                        </div>
                        <div class="stone-allocation-card stone-allocation-remaining">
                            <span class="stone-allocation-label">Pendiente</span>
                            <strong id="sp-allocation-remaining">${this._fmt(state.requestedQty)} ${this._escapeHtml(state.requestedUnit)}</strong>
                        </div>
                        <div class="stone-allocation-progress-box">
                            <div class="stone-allocation-progress-head">
                                <span id="sp-allocation-progress-text">0.00 de ${this._fmt(state.requestedQty)} ${this._escapeHtml(state.requestedUnit)}</span>
                                <strong id="sp-allocation-progress-label">0%</strong>
                            </div>
                            <div class="stone-allocation-progress-track">
                                <div class="stone-allocation-progress-fill" id="sp-allocation-progress-fill"></div>
                            </div>
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
                            <input type="number" class="stone-filter-input stone-filter-sm" id="sf-alto" placeholder="0" step="0.01"/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Ancho mín.</label>
                            <input type="number" class="stone-filter-input stone-filter-sm" id="sf-ancho" placeholder="0" step="0.01"/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Tipo</label>
                            <select class="stone-filter-input" id="sf-tipo">
                                <option value="">Todos</option>
                                <option value="placa">Placa</option>
                                <option value="formato">Formato</option>
                                <option value="pieza">Pieza</option>
                            </select>
                        </div>
                        <div class="stone-filter-actions">
                            <button class="stone-btn stone-btn-select-all" id="sp-select-all" title="Seleccionar todas">
                                <i class="fa fa-check-square-o me-1"></i> Todo
                            </button>
                            <button class="stone-btn stone-btn-clear-all" id="sp-clear-all" title="Borrar selección">
                                <i class="fa fa-square-o me-1"></i> Limpiar
                            </button>
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
                        <div class="stone-footer-qty-summary" id="sp-footer-qty">
                            <span id="sp-footer-qty-text">0.00 m²</span>
                        </div>
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
        const badgeQty = root.querySelector("#sp-badge-qty");
        const badgeUnit = root.querySelector("#sp-badge-unit");
        const footerQtyText = root.querySelector("#sp-footer-qty-text");
        const allocationSummary = root.querySelector("#sp-allocation-summary");
        const allocationTarget = root.querySelector("#sp-allocation-target");
        const allocationSelected = root.querySelector("#sp-allocation-selected");
        const allocationRemaining = root.querySelector("#sp-allocation-remaining");
        const allocationProgressText = root.querySelector("#sp-allocation-progress-text");
        const allocationProgressLabel = root.querySelector("#sp-allocation-progress-label");
        const allocationProgressFill = root.querySelector("#sp-allocation-progress-fill");

        const cacheQuantForTotals = (q) => {
            const lotId = q && q.lot_id ? q.lot_id[0] : 0;
            if (!lotId) return;
            state.qtyCache[String(lotId)] = {
                qty: q.quantity || 0,
                tipo: (q.x_tipo || "placa").toLowerCase(),
            };
        };

        const cacheQuantListForTotals = (items) => {
            for (const q of (items || [])) {
                cacheQuantForTotals(q);
            }
        };

        const ensureQtyCacheForPending = async () => {
            const missingIds = Array.from(state.pendingIds).filter((lotId) => !state.qtyCache[String(lotId)]);
            if (!missingIds.length) return;

            try {
                const [lotsData, quants] = await Promise.all([
                    self.orm.searchRead(
                        "stock.lot",
                        [["id", "in", missingIds]],
                        ["id", "x_tipo"],
                        { limit: missingIds.length }
                    ),
                    self.orm.searchRead(
                        "stock.quant",
                        [
                            ["lot_id", "in", missingIds],
                            ["location_id.usage", "=", "internal"],
                            ["quantity", ">", 0],
                        ],
                        ["lot_id", "quantity"],
                        { limit: missingIds.length * 5 }
                    ),
                ]);

                const tipoMap = {};
                for (const lot of (lotsData || [])) {
                    tipoMap[lot.id] = (lot.x_tipo || "placa").toLowerCase();
                }

                for (const lotId of missingIds) {
                    state.qtyCache[String(lotId)] = {
                        qty: 0,
                        tipo: tipoMap[lotId] || "placa",
                    };
                }

                for (const q of (quants || [])) {
                    const lotId = q.lot_id ? q.lot_id[0] : 0;
                    if (!lotId) continue;
                    const key = String(lotId);
                    if (!state.qtyCache[key]) {
                        state.qtyCache[key] = { qty: 0, tipo: tipoMap[lotId] || "placa" };
                    }
                    state.qtyCache[key].qty += q.quantity || 0;
                }
            } catch (error) {
                console.warn("[STONE] No se pudo precargar cantidad de lotes seleccionados:", error);
            }
        };

        const computeSelectedTotals = () => {
            let totalM2 = 0;
            let totalPiezas = 0;
            let hasPiezas = false;
            let hasM2 = false;

            for (const lotId of state.pendingIds) {
                const lotIdStr = String(lotId);
                const cached = state.qtyCache[lotIdStr];
                const q = state.quants.find((qq) => qq.lot_id && qq.lot_id[0] === lotId);
                const tipo = (cached?.tipo || q?.x_tipo || "placa").toLowerCase();

                let qty = 0;
                if ((tipo === "formato" || tipo === "pieza") && state.pendingBreakdown[lotIdStr] !== undefined) {
                    qty = parseFloat(state.pendingBreakdown[lotIdStr]) || 0;
                } else if (cached) {
                    qty = cached.qty || 0;
                } else if (q) {
                    qty = q.quantity || 0;
                }

                if (tipo === "pieza") {
                    totalPiezas += qty;
                    hasPiezas = true;
                } else {
                    totalM2 += qty;
                    hasM2 = true;
                }
            }

            return { totalM2, totalPiezas, hasM2, hasPiezas };
        };

        const updateQtyDisplay = () => {
            const totals = computeSelectedTotals();
            const { totalM2, totalPiezas, hasM2, hasPiezas } = totals;

            if (hasM2 && hasPiezas) {
                badgeQty.textContent = self._fmt(totalM2);
                badgeUnit.textContent = `m² + ${self._fmt(totalPiezas)} pzas`;
            } else if (hasPiezas && !hasM2) {
                badgeQty.textContent = self._fmt(totalPiezas);
                badgeUnit.textContent = "pzas";
            } else {
                badgeQty.textContent = self._fmt(totalM2);
                badgeUnit.textContent = "m²";
            }

            const parts = [];
            if (hasM2) parts.push(`${self._fmt(totalM2)} m²`);
            if (hasPiezas) parts.push(`${self._fmt(totalPiezas)} pzas`);
            footerQtyText.textContent = parts.length > 0 ? parts.join(" + ") : "0.00 m²";

            const selectedForTarget = self._getAllocationBaseFromTotals(totals, state.requestedUnit);
            const requestedQty = state.requestedQty || 0;
            const requestedUnit = state.requestedUnit || "m²";
            const rawPercent = requestedQty > 0 ? (selectedForTarget / requestedQty) * 100 : 0;
            const barPercent = Math.max(0, Math.min(rawPercent, 100));
            const diff = requestedQty - selectedForTarget;

            if (allocationTarget) {
                allocationTarget.textContent = `${self._fmt(requestedQty)} ${requestedUnit}`;
            }
            if (allocationSelected) {
                allocationSelected.textContent = `${self._fmt(selectedForTarget)} ${requestedUnit}`;
            }
            if (allocationRemaining) {
                allocationRemaining.textContent = `${diff >= 0 ? self._fmt(diff) : "+" + self._fmt(Math.abs(diff))} ${requestedUnit}`;
            }
            if (allocationProgressText) {
                allocationProgressText.textContent = `${self._fmt(selectedForTarget)} de ${self._fmt(requestedQty)} ${requestedUnit}`;
            }
            if (allocationProgressLabel) {
                allocationProgressLabel.textContent = `${self._fmtPct(rawPercent)}%`;
            }
            if (allocationProgressFill) {
                allocationProgressFill.style.width = `${barPercent}%`;
            }
            if (allocationSummary) {
                allocationSummary.classList.toggle("is-empty-target", requestedQty <= 0);
                allocationSummary.classList.toggle("is-under", requestedQty > 0 && rawPercent < 99.995);
                allocationSummary.classList.toggle("is-ok", requestedQty > 0 && rawPercent >= 99.995 && rawPercent <= 100.005);
                allocationSummary.classList.toggle("is-over", requestedQty > 0 && rawPercent > 100.005);
            }
        };

        const updateBadge = () => {
            badgeCount.textContent = state.pendingIds.size;
            updateQtyDisplay();
        };

        const updateStats = () => {
            stat.className = "stone-filter-stat-count";
            stat.innerHTML = `${state.totalCount} lotes`;
            footerInfo.innerHTML = `<strong>${state.quants.length}</strong> de <strong>${state.totalCount}</strong>`;
        };

        const isLotLocked = (lotId) => {
            const info = state.statusMap.get(lotId);
            return info && info.is_locked;
        };

        const doSelectAll = () => {
            for (const q of state.quants) {
                cacheQuantForTotals(q);
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                if (!lotId) continue;
                state.pendingIds.add(lotId);
                const tipo = (q.x_tipo || "placa").toLowerCase();
                if ((tipo === "formato" || tipo === "pieza") && !state.pendingBreakdown[String(lotId)]) {
                    state.pendingBreakdown[String(lotId)] = q.quantity || 0;
                }
            }
            updateBadge();
            renderTable();
        };

        const doClearAll = () => {
            const newIds = new Set();
            const newBreakdown = {};
            for (const lotId of state.pendingIds) {
                if (isLotLocked(lotId)) {
                    newIds.add(lotId);
                    if (state.pendingBreakdown[String(lotId)] !== undefined) {
                        newBreakdown[String(lotId)] = state.pendingBreakdown[String(lotId)];
                    }
                }
            }
            state.pendingIds = newIds;
            state.pendingBreakdown = newBreakdown;
            updateBadge();
            renderTable();
        };

        const renderTable = () => {
            if (state.quants.length === 0 && !state.isLoading) {
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-inbox fa-3x text-muted"></i>
                        <div class="stone-empty-text mt-2">No hay lotes con estos filtros</div>
                    </div>`;
                updateStats();
                return;
            }

            let rows = "";
            for (const q of state.quants) {
                cacheQuantForTotals(q);
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                const lotName = q.lot_id ? q.lot_id[1] : "-";
                const loc = q.location_id ? q.location_id[1].split("/").pop() : "-";
                const sel = state.pendingIds.has(lotId);
                const reserved = q.reserved_quantity > 0;
                const tipo = (q.x_tipo || "placa").toLowerCase();
                const isPartial = (tipo === "formato" || tipo === "pieza");
                const lotIdStr = String(lotId);
                const qtyLabel = tipo === "pieza" ? "pzas" : "m²";
                const inputStep = tipo === "pieza" ? "1" : "0.01";

                const statusInfo = state.statusMap.get(lotId);
                const lockedByStatus = statusInfo && statusInfo.is_locked;

                let statusBadge;
                if (statusInfo && statusInfo.status_badges && statusInfo.status_badges.length > 0) {
                    statusBadge = self._renderStatusBadges(statusInfo.status_badges, { compact: true });
                } else if (sel) {
                    statusBadge = `<span class="stone-tag stone-tag-ok">Selec.</span>`;
                } else if (reserved) {
                    statusBadge = `<span class="stone-tag stone-tag-warn">Reserv.</span>`;
                } else {
                    statusBadge = `<span class="stone-tag stone-tag-free">Libre</span>`;
                }

                const tipoLabel = tipo.charAt(0).toUpperCase() + tipo.slice(1);

                let qtyCell;
                if (lockedByStatus && sel) {
                    const lockedQty = statusInfo.displayed_qty || 0;
                    qtyCell = `<span class="text-muted"><i class="fa fa-lock me-1"></i>${self._fmt(lockedQty)} ${qtyLabel}</span>`;
                } else if (isPartial && sel) {
                    const currentVal = state.pendingBreakdown[lotIdStr] !== undefined
                        ? state.pendingBreakdown[lotIdStr]
                        : q.quantity;
                    qtyCell = `<input type="number" class="stone-popup-qty-input"
                                     data-lot-id="${lotId}" data-max="${q.quantity}"
                                     step="${inputStep}" min="0" max="${q.quantity}"
                                     value="${currentVal}" />`;
                } else if (isPartial && !sel) {
                    qtyCell = `<span class="text-muted">—</span>`;
                } else {
                    qtyCell = `<span>${self._fmt(q.quantity)} ${qtyLabel}</span>`;
                }

                const photoCell = self._renderPhotoCell(
                    q.x_fotografia_principal || false,
                    q.x_cantidad_fotos || 0,
                    lotId,
                    lotName
                );

                const rowClasses = [];
                if (sel) rowClasses.push("row-sel");
                if (lockedByStatus) rowClasses.push("stone-popup-row-locked");

                rows += `
                    <tr class="${rowClasses.join(" ")}" data-lot-id="${lotId}" data-reserved="${reserved ? "1" : "0"}" data-tipo="${tipo}" data-locked="${lockedByStatus ? "1" : "0"}">
                        <td class="col-chk">
                            <div class="stone-chkbox ${sel ? "checked" : ""}">
                                ${sel ? '<i class="fa fa-check"></i>' : ""}
                            </div>
                        </td>
                        <td class="col-photo">${photoCell}</td>
                        <td class="cell-lot">${self._escapeHtml(lotName)}</td>
                        <td>${self._escapeHtml(q.x_bloque) || "-"}</td>
                        <td>${self._escapeHtml(q.x_atado) || "-"}</td>
                        <td class="col-num">${self._fmtDim(q.x_alto)}</td>
                        <td class="col-num">${self._fmtDim(q.x_ancho)}</td>
                        <td class="col-num">${self._fmtDim(q.x_grosor)}</td>
                        <td class="col-num fw-semibold">${self._fmt(q.quantity)}</td>
                        <td><span class="stone-tag stone-tag-tipo-${tipo}">${tipoLabel}</span></td>
                        <td class="col-num col-popup-qty">${qtyCell}</td>
                        <td>${self._escapeHtml(q.x_color) || "-"}</td>
                        <td class="cell-loc">${self._escapeHtml(loc)}</td>
                        <td class="stone-popup-status-cell">${statusBadge}</td>
                    </tr>`;
            }

            const sentinel = `
                <div id="sp-sentinel" class="stone-scroll-sentinel">
                    ${state.isLoadingMore ? '<div class="stone-loading-more"><i class="fa fa-circle-o-notch fa-spin me-1"></i> Cargando más...</div>' : ""}
                    ${state.hasMore && !state.isLoadingMore ? '<div class="stone-scroll-hint"><i class="fa fa-chevron-down me-1"></i> Más resultados</div>' : ""}
                </div>`;

            body.innerHTML = `
                <table class="stone-popup-table">
                    <thead>
                        <tr>
                            <th class="col-chk">✓</th>
                            <th class="col-photo">Foto</th>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Ancho</th>
                            <th class="col-num">Esp.</th>
                            <th class="col-num">Disp.</th>
                            <th>Tipo</th>
                            <th class="col-num">A tomar</th>
                            <th>Color</th>
                            <th>Ubic.</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                ${sentinel}`;

            updateStats();
            updateQtyDisplay();

            body.querySelectorAll("tr[data-lot-id]").forEach((tr) => {
                const lockedRow = tr.dataset.locked === "1";
                tr.style.cursor = lockedRow ? "not-allowed" : "pointer";
                tr.addEventListener("click", (ev) => {
                    if (ev.target.closest(".stone-popup-qty-input")) return;
                    if (ev.target.closest(".stone-photo-cell[data-has-photo]")) return;

                    if (lockedRow) {
                        return;
                    }

                    const lotId = parseInt(tr.dataset.lotId);
                    if (!lotId) return;
                    const tipo = tr.dataset.tipo || "placa";
                    const isPartial = (tipo === "formato" || tipo === "pieza");

                    if (state.pendingIds.has(lotId)) {
                        state.pendingIds.delete(lotId);
                        delete state.pendingBreakdown[String(lotId)];
                    } else {
                        state.pendingIds.add(lotId);
                        if (isPartial) {
                            const q = state.quants.find(qq => qq.lot_id && qq.lot_id[0] === lotId);
                            if (q) {
                                state.pendingBreakdown[String(lotId)] = q.quantity || 0;
                            }
                        }
                    }
                    updateBadge();
                    renderTable();
                });
            });

            body.querySelectorAll(".stone-popup-qty-input").forEach((input) => {
                input.addEventListener("click", (e) => e.stopPropagation());
                input.addEventListener("input", (e) => {
                    const lotId = parseInt(input.dataset.lotId);
                    const max = parseFloat(input.dataset.max) || 0;
                    let val = parseFloat(input.value) || 0;
                    if (val < 0) val = 0;
                    if (val > max) {
                        val = max;
                        input.value = val;
                    }
                    state.pendingBreakdown[String(lotId)] = val;
                    updateQtyDisplay();
                });
            });

            self._bindPhotoClicks(body);

            if (self._popupObserver) {
                self._popupObserver.disconnect();
                self._popupObserver = null;
            }
            const sentinelEl = body.querySelector("#sp-sentinel");
            if (sentinelEl && state.hasMore) {
                self._popupObserver = new IntersectionObserver(
                    (entries) => {
                        if (entries[0].isIntersecting && state.hasMore && !state.isLoadingMore) {
                            loadPage(state.page + 1, false);
                        }
                    },
                    { root: body, rootMargin: "100px", threshold: 0.1 }
                );
                self._popupObserver.observe(sentinelEl);
            }
        };

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
                    result = await self.orm.call(
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
                    const all = (await self.orm.call(
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
                cacheQuantListForTotals(items);

                if (reset || page === 0) {
                    state.quants = items;
                } else {
                    state.quants = [...state.quants, ...items];
                }
                state.totalCount = result.total || 0;
                state.page = page;
                state.hasMore = state.quants.length < state.totalCount;

                await ensureQtyCacheForPending();
            } catch (err) {
                console.error("[STONE POPUP] Error:", err);
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-exclamation-triangle fa-2x text-danger"></i>
                        <div class="stone-empty-text mt-2 text-danger">Error: ${self._escapeHtml(err.message)}</div>
                    </div>`;
                return;
            } finally {
                state.isLoading = false;
                state.isLoadingMore = false;
            }

            renderTable();
        };

        const doConfirm = async () => {
            if (self.isSelectionLocked()) {
                self._warnQuoteSelectionBlocked();
                return;
            }

            const newIds = Array.from(state.pendingIds);

            const cleanBreakdown = {};
            for (const [k, v] of Object.entries(state.pendingBreakdown)) {
                if (state.pendingIds.has(parseInt(k))) {
                    cleanBreakdown[k] = v;
                }
            }

            self.destroyPopup();

            // Persiste de inmediato al backend (memoria + ORM write) sin recargar la página.
            await self._commitSelectionToServer(newIds, cleanBreakdown);

            self._updateCount();
            await self.refreshSelectedTable();
        };

        const doClose = () => self.destroyPopup();

        root.querySelector("#sp-close").addEventListener("click", doClose);
        root.querySelector("#sp-cancel").addEventListener("click", doClose);
        root.querySelector("#sp-confirm-bottom").addEventListener("click", doConfirm);
        root.querySelector("#sp-select-all").addEventListener("click", doSelectAll);
        root.querySelector("#sp-clear-all").addEventListener("click", doClearAll);
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) doClose();
        });

        const onKeyDown = (e) => {
            if (e.key === "Escape") {
                doClose();
            }
        };
        document.addEventListener("keydown", onKeyDown);
        this._popupKeyHandler = onKeyDown;

        const bindFilter = (id, key) => {
            const input = root.querySelector(`#${id}`);
            if (!input) return;
            input.addEventListener("input", (e) => {
                state.filters[key] = e.target.value;
                if (searchTimeout) clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => loadPage(0, true), 350);
            });
            input.addEventListener("change", (e) => {
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
        bindFilter("sf-tipo", "tipo");

        loadPage(0, true);
    }

    destroyPopup() {
        if (this._popupObserver) {
            this._popupObserver.disconnect();
            this._popupObserver = null;
        }
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