/** @odoo-module */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillStart, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENTE PRINCIPAL: BOTÓN STONE
// ═══════════════════════════════════════════════════════════════════════════════
export class StoneExpandButton extends Component {
    static template = "sale_stone_selection.StoneExpandButton";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this._detailsRow = null;
        this._popupRoot = null;
        this._popupKeyHandler = null;
        this._popupObserver = null;
        this._lightboxRoot = null;
        this._localBreakdown = {};

        this.state = useState({
            isExpanded: false,
            selectedCount: 0,
        });

        onWillStart(() => {
            this._loadBreakdownFromRecord();
            this._updateCount();
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

    // ─── Helpers ──────────────────────────────────────────────────────────────

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

    _loadBreakdownFromRecord() {
        const raw = this.props.record.data.x_lot_breakdown_json;
        if (!raw) {
            this._localBreakdown = {};
            return;
        }
        if (typeof raw === "string") {
            try { this._localBreakdown = JSON.parse(raw); } catch { this._localBreakdown = {}; }
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
        this._localBreakdown = { ...breakdown };
        const recordId = this._getRecordId();
        if (recordId && typeof recordId === "number" && recordId > 0) {
            try {
                await this.orm.write("sale.order.line", [recordId], {
                    x_lot_breakdown_json: breakdown,
                });
            } catch (e) {
                console.warn("[STONE] Error guardando breakdown al server:", e);
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // LIGHTBOX — Preview de fotos a pantalla completa
    // ═══════════════════════════════════════════════════════════════════════════

    /**
     * Abre un lightbox con todas las fotos de un lote.
     * @param {number} lotId - ID del lote
     * @param {string} lotName - Nombre del lote (para título)
     * @param {string|false} mainPhoto - Base64 de la foto principal (para mostrar rápido)
     */
    async openLightbox(lotId, lotName, mainPhoto) {
        this._destroyLightbox();

        this._lightboxRoot = document.createElement("div");
        this._lightboxRoot.className = "stone-lightbox-root";
        document.body.appendChild(this._lightboxRoot);

        // Mostrar inmediatamente la foto principal si la tenemos
        const initialSrc = mainPhoto ? `data:image/jpeg;base64,${mainPhoto}` : null;

        this._lightboxRoot.innerHTML = `
            <div class="stone-lightbox-overlay" id="slb-overlay">
                <div class="stone-lightbox-container">
                    <div class="stone-lightbox-header">
                        <span class="stone-lightbox-title">
                            <i class="fa fa-camera me-2"></i>
                            Fotos del lote <strong>${lotName || lotId}</strong>
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
        overlay.addEventListener("click", (e) => { if (e.target === overlay) closeLb(); });

        const keyHandler = (e) => {
            if (e.key === "Escape") closeLb();
            if (e.key === "ArrowLeft" && prevBtn) prevBtn.click();
            if (e.key === "ArrowRight" && nextBtn) nextBtn.click();
        };
        document.addEventListener("keydown", keyHandler);
        this._lightboxKeyHandler = keyHandler;

        // Cargar todas las fotos del lote
        try {
            const photos = await this.orm.searchRead(
                "stock.lot.image",
                [["lot_id", "=", lotId]],
                ["id", "name", "image", "notas", "fecha_captura"],
                { order: "sequence, id", limit: 50 }
            );

            if (!photos || photos.length === 0) {
                if (initialSrc) {
                    // Solo tenemos la principal, ya se muestra
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

            // Render con navegación
            let currentIdx = 0;

            const showPhoto = (idx) => {
                currentIdx = idx;
                const photo = photos[idx];
                const src = `data:image/jpeg;base64,${photo.image}`;
                bodyEl.innerHTML = `
                    <img src="${src}" class="stone-lightbox-img" id="slb-main-img"/>
                    <div class="stone-lightbox-info" id="slb-info">
                        <strong>${photo.name || ''}</strong>
                        ${photo.notas ? `<span class="ms-3 text-muted">${photo.notas}</span>` : ''}
                        ${photo.fecha_captura ? `<span class="ms-3 text-muted small"><i class="fa fa-clock-o me-1"></i>${photo.fecha_captura}</span>` : ''}
                    </div>`;
                counterEl.textContent = `(${idx + 1} / ${photos.length})`;

                // Actualizar thumbs activo
                thumbsEl.querySelectorAll(".stone-lightbox-thumb").forEach((th, i) => {
                    th.classList.toggle("active", i === idx);
                });
            };

            // Generar thumbnails
            if (photos.length > 1) {
                navEl.style.display = "flex";
                let thumbsHtml = "";
                for (let i = 0; i < photos.length; i++) {
                    const src = `data:image/jpeg;base64,${photos[i].image}`;
                    thumbsHtml += `<img src="${src}" class="stone-lightbox-thumb ${i === 0 ? 'active' : ''}" data-idx="${i}"/>`;
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
                    <div class="mt-2 text-danger">Error cargando fotos: ${e.message}</div>
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

    // ─── Render de celda de foto (reutilizable) ──────────────────────────────

    /**
     * Genera HTML para una celda de foto thumbnail
     * @param {string|false} photoBase64 - Foto principal en base64
     * @param {number} photoCount - Cantidad de fotos
     * @param {number} lotId - ID del lote
     * @param {string} lotName - Nombre del lote
     * @returns {string} HTML
     */
    _renderPhotoCell(photoBase64, photoCount, lotId, lotName) {
        if (photoBase64) {
            const badge = photoCount > 1 ? `<span class="stone-photo-count">${photoCount}</span>` : "";
            return `<div class="stone-photo-cell" data-lot-id="${lotId}" data-lot-name="${lotName}" data-has-photo="1">
                        <img src="data:image/jpeg;base64,${photoBase64}" class="stone-photo-thumb" alt="Foto"/>
                        ${badge}
                    </div>`;
        }
        if (photoCount > 0) {
            return `<div class="stone-photo-cell" data-lot-id="${lotId}" data-lot-name="${lotName}" data-has-photo="1">
                        <div class="stone-photo-placeholder-has"><i class="fa fa-camera"></i><span>${photoCount}</span></div>
                    </div>`;
        }
        return `<div class="stone-photo-cell stone-photo-empty"><i class="fa fa-picture-o text-muted"></i></div>`;
    }

    /**
     * Vincula click handlers a las celdas de fotos dentro de un contenedor
     */
    _bindPhotoClicks(container) {
        container.querySelectorAll(".stone-photo-cell[data-has-photo]").forEach((cell) => {
            cell.style.cursor = "pointer";
            cell.addEventListener("click", (e) => {
                e.stopPropagation();
                const lotId = parseInt(cell.dataset.lotId);
                const lotName = cell.dataset.lotName || "";
                // Intentar extraer la base64 del thumb si existe
                const img = cell.querySelector(".stone-photo-thumb");
                let mainPhoto = false;
                if (img && img.src.startsWith("data:")) {
                    mainPhoto = img.src.replace(/^data:image\/\w+;base64,/, "");
                }
                this.openLightbox(lotId, lotName, mainPhoto);
            });
        });
    }

    // ─── Toggle principal ─────────────────────────────────────────────────────

    async handleToggle(ev) {
        ev.stopPropagation();

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
            <button class="stone-add-btn stone-add-btn-trigger stone-add-btn-prominent">
                <i class="fa fa-plus me-1"></i> Agregar lotes
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
                    <i class="fa fa-info-circle me-1 text-muted"></i>
                    <span class="text-muted">Sin lotes. Usa <strong>Agregar</strong> para comenzar.</span>
                </div>`;
            return;
        }

        container.innerHTML = `<div class="stone-table-loading"><i class="fa fa-circle-o-notch fa-spin me-1"></i> Cargando...</div>`;

        try {
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

            let totalQty = 0;
            let html = `
                <table class="stone-sel-table">
                    <thead>
                        <tr>
                            <th class="col-photo">Foto</th>
                            <th>Lote</th>
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
                totalQty += displayQty;

                const qtyLabel = tipo === "pieza" ? "pzas" : "m²";
                const inputStep = tipo === "pieza" ? "1" : "0.01";

                const photoCell = this._renderPhotoCell(
                    lot.x_fotografia_principal, lot.x_cantidad_fotos || 0, lid, lot.name
                );

                html += `
                    <tr>
                        <td class="col-photo">${photoCell}</td>
                        <td class="cell-lot">${lot.name}</td>
                        <td>${lot.x_bloque || "-"}</td>
                        <td>${lot.x_atado || "-"}</td>
                        <td class="col-num">${this._fmtDim(lot.x_alto)}</td>
                        <td class="col-num">${this._fmtDim(lot.x_ancho)}</td>
                        <td class="col-num">${this._fmtDim(lot.x_grosor)}</td>
                        <td>
                            <span class="stone-tag stone-tag-tipo-${tipo}">${tipo.charAt(0).toUpperCase() + tipo.slice(1)}</span>
                        </td>
                        <td class="col-num text-muted">${this._fmt(availQty)} ${qtyLabel}</td>
                        <td class="col-num col-qty-input">
                            ${isPartial
                                ? `<input type="number" class="stone-qty-input" 
                                          data-lot-id="${lid}" data-max="${availQty}" 
                                          step="${inputStep}" min="0" max="${availQty}"
                                          value="${displayQty}" />`
                                : `<span class="fw-semibold">${this._fmt(displayQty)} m²</span>`
                            }
                        </td>
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
                            <td colspan="9" class="text-end fw-bold text-muted">Total:</td>
                            <td class="col-num fw-bold" id="stone-sel-total">${this._fmt(totalQty)}</td>
                            <td colspan="2"></td>
                        </tr>
                    </tfoot>
                </table>`;

            container.innerHTML = html;

            // Bind remove buttons
            container.querySelectorAll(".stone-remove-btn").forEach((btn) => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.removeLot(parseInt(btn.dataset.lotId));
                });
            });

            // Bind qty inputs
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

            // Bind photo clicks
            this._bindPhotoClicks(container);

        } catch (err) {
            console.error("[STONE] Error renderizando seleccionadas:", err);
            container.innerHTML = `<div class="text-danger p-2">Error: ${err.message}</div>`;
        }
    }

    async _onQtyInputChange(input) {
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
        this._detailsRow.querySelectorAll(".stone-qty-input").forEach((inp) => {
            total += parseFloat(inp.value) || 0;
        });
        this._detailsRow.querySelectorAll("td.col-qty-input .fw-semibold").forEach((span) => {
            const m = span.textContent.match(/([\d.]+)/);
            if (m) total += parseFloat(m[1]) || 0;
        });
        totalEl.textContent = this._fmt(total);
    }

    async removeLot(lotId) {
        const newIds = this.getCurrentLotIds().filter((id) => id !== lotId);

        const breakdown = this.getBreakdown();
        delete breakdown[String(lotId)];
        await this._saveBreakdownToServer(breakdown);

        const totalQty = await this._computeTotalQty(newIds, breakdown);

        await this.props.record.update({
            lot_ids: [[6, 0, newIds]],
            product_uom_qty: totalQty,
        });
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

    // ─── Cálculo de cantidad total ────────────────────────────────────────────

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

    // ═══════════════════════════════════════════════════════════════════════════
    // POPUP (DOM puro en document.body)
    // ═══════════════════════════════════════════════════════════════════════════

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
        const self = this;

        const state = {
            quants: [],
            totalCount: 0,
            hasMore: false,
            isLoading: false,
            isLoadingMore: false,
            page: 0,
            pendingIds: new Set(this.getCurrentLotIds()),
            pendingBreakdown: { ...this.getBreakdown() },
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
                            <span class="stone-popup-subtitle">${this.getProductName() ? "— " + this.getProductName() : ""}</span>
                        </div>
                        <div class="stone-popup-header-actions">
                            <span class="stone-badge-selected">
                                <i class="fa fa-check-circle me-1"></i>
                                <span id="sp-badge-count">${state.pendingIds.size}</span> selec.
                            </span>
                            <span class="stone-badge-qty-total">
                                <i class="fa fa-balance-scale me-1"></i>
                                <span id="sp-badge-qty">0.00</span>
                                <span id="sp-badge-unit">m²</span>
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

        const computeSelectedTotals = () => {
            let totalM2 = 0;
            let totalPiezas = 0;
            let hasPiezas = false;
            let hasM2 = false;

            for (const lotId of state.pendingIds) {
                const q = state.quants.find((qq) => qq.lot_id && qq.lot_id[0] === lotId);
                const tipo = q ? (q.x_tipo || "placa").toLowerCase() : "placa";
                const lotIdStr = String(lotId);

                let qty = 0;
                if ((tipo === "formato" || tipo === "pieza") && state.pendingBreakdown[lotIdStr] !== undefined) {
                    qty = parseFloat(state.pendingBreakdown[lotIdStr]) || 0;
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
            const { totalM2, totalPiezas, hasM2, hasPiezas } = computeSelectedTotals();

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

        const doSelectAll = () => {
            for (const q of state.quants) {
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
            state.pendingIds.clear();
            state.pendingBreakdown = {};
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

                let statusBadge;
                if (sel) {
                    statusBadge = `<span class="stone-tag stone-tag-ok">Selec.</span>`;
                } else if (reserved) {
                    statusBadge = `<span class="stone-tag stone-tag-warn">Reserv.</span>`;
                } else {
                    statusBadge = `<span class="stone-tag stone-tag-free">Libre</span>`;
                }

                const tipoLabel = tipo.charAt(0).toUpperCase() + tipo.slice(1);

                let qtyCell;
                if (isPartial && sel) {
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

                // Foto
                const photoCell = self._renderPhotoCell(
                    q.x_fotografia_principal || false,
                    q.x_cantidad_fotos || 0,
                    lotId,
                    lotName
                );

                rows += `
                    <tr class="${sel ? "row-sel" : ""}" data-lot-id="${lotId}" data-reserved="${reserved ? "1" : "0"}" data-tipo="${tipo}">
                        <td class="col-chk">
                            <div class="stone-chkbox ${sel ? "checked" : ""}">
                                ${sel ? '<i class="fa fa-check"></i>' : ""}
                            </div>
                        </td>
                        <td class="col-photo">${photoCell}</td>
                        <td class="cell-lot">${lotName}</td>
                        <td>${q.x_bloque || "-"}</td>
                        <td>${q.x_atado || "-"}</td>
                        <td class="col-num">${self._fmtDim(q.x_alto)}</td>
                        <td class="col-num">${self._fmtDim(q.x_ancho)}</td>
                        <td class="col-num">${self._fmtDim(q.x_grosor)}</td>
                        <td class="col-num fw-semibold">${self._fmt(q.quantity)}</td>
                        <td><span class="stone-tag stone-tag-tipo-${tipo}">${tipoLabel}</span></td>
                        <td class="col-num col-popup-qty">${qtyCell}</td>
                        <td>${q.x_color || "-"}</td>
                        <td class="cell-loc">${loc}</td>
                        <td>${statusBadge}</td>
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

            // Click en filas (evitar click en foto y en input)
            body.querySelectorAll("tr[data-lot-id]").forEach((tr) => {
                tr.style.cursor = "pointer";
                tr.addEventListener("click", (ev) => {
                    if (ev.target.closest(".stone-popup-qty-input")) return;
                    if (ev.target.closest(".stone-photo-cell[data-has-photo]")) return;

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

            // Inputs de cantidad parcial
            body.querySelectorAll(".stone-popup-qty-input").forEach((input) => {
                input.addEventListener("click", (e) => e.stopPropagation());
                input.addEventListener("input", (e) => {
                    const lotId = parseInt(input.dataset.lotId);
                    const max = parseFloat(input.dataset.max) || 0;
                    let val = parseFloat(input.value) || 0;
                    if (val < 0) val = 0;
                    if (val > max) { val = max; input.value = val; }
                    state.pendingBreakdown[String(lotId)] = val;
                    updateQtyDisplay();
                });
            });

            // Bind photo clicks
            self._bindPhotoClicks(body);

            // Infinite scroll
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
            const newIds = Array.from(state.pendingIds);

            const cleanBreakdown = {};
            for (const [k, v] of Object.entries(state.pendingBreakdown)) {
                if (state.pendingIds.has(parseInt(k))) {
                    cleanBreakdown[k] = v;
                }
            }

            const totalQty = await self._computeTotalQty(newIds, cleanBreakdown, state.quants);

            self.destroyPopup();

            await self._saveBreakdownToServer(cleanBreakdown);

            await self.props.record.update({
                lot_ids: [[6, 0, newIds]],
                product_uom_qty: totalQty,
            });

            self._updateCount();
            await self.refreshSelectedTable();
        };

        const doClose = () => self.destroyPopup();

        // ─── Event listeners ─────────────────────────────────────────────────
        root.querySelector("#sp-close").addEventListener("click", doClose);
        root.querySelector("#sp-cancel").addEventListener("click", doClose);
        root.querySelector("#sp-confirm-top").addEventListener("click", doConfirm);
        root.querySelector("#sp-confirm-bottom").addEventListener("click", doConfirm);
        root.querySelector("#sp-select-all").addEventListener("click", doSelectAll);
        root.querySelector("#sp-clear-all").addEventListener("click", doClearAll);
        overlay.addEventListener("click", (e) => { if (e.target === overlay) doClose(); });

        const onKeyDown = (e) => { if (e.key === "Escape") { doClose(); } };
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