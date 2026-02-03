/** @odoo-module */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, xml, onWillUnmount, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class StoneExpandButton extends Component {
    static template = xml`
        <div class="o_stone_toggle_btn cursor-pointer d-flex align-items-center justify-content-center" 
             t-on-click.stop="handleClick"
             title="Seleccionar Placas"
             style="width: 100%; height: 100%; min-height: 24px;">
            <i class="fa fa-th text-primary" t-if="!isExpanded" style="font-size: 14px;"/>
            <i class="fa fa-chevron-up text-danger" t-else="" style="font-size: 14px;"/>
        </div>
    `;
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.detailsRow = null;
        this.containerNode = null;
        this.gridNode = null;
        this.isExpanded = false;
        
        this.filters = { lot_name: '', bloque: '', atado: '', alto_min: '', ancho_min: '' };
        this.searchTimeout = null;

        // =====================================================================
        // DIAGNÓSTICO: Logs en el ciclo de vida del componente
        // =====================================================================
        onWillStart(() => {
            console.group("🔷 [STONE onWillStart] Componente inicializando");
            this._logRecordState("onWillStart");
            console.groupEnd();
        });

        onWillUpdateProps((nextProps) => {
            console.group("🔷 [STONE onWillUpdateProps] Props actualizándose");
            console.log("Props actuales:", this.props);
            console.log("Props nuevos:", nextProps);
            this._logRecordState("onWillUpdateProps (current)", this.props);
            this._logRecordState("onWillUpdateProps (next)", nextProps);
            console.groupEnd();
        });
        
        onWillUnmount(() => {
            console.log("🔷 [STONE onWillUnmount] Componente desmontándose");
            this.removeGrid();
        });
    }

    /**
     * DIAGNÓSTICO: Loguear estado completo del record
     */
    _logRecordState(context, props = this.props) {
        console.group(`📊 [STONE ${context}] Estado del Record`);
        
        if (!props || !props.record) {
            console.warn("❌ props.record NO EXISTE");
            console.groupEnd();
            return;
        }

        const record = props.record;
        const data = record.data;

        console.log("Record completo:", record);
        console.log("Record.data:", data);
        console.log("Record.resId:", record.resId);
        console.log("Record.isNew:", record.isNew);
        
        // Inspeccionar lot_ids específicamente
        console.group("🏷️ lot_ids inspection");
        console.log("data.lot_ids:", data.lot_ids);
        console.log("data.lot_ids tipo:", typeof data.lot_ids);
        
        if (data.lot_ids) {
            console.log("data.lot_ids constructor:", data.lot_ids.constructor?.name);
            console.log("data.lot_ids keys:", Object.keys(data.lot_ids));
            
            // Intentar diferentes formas de acceder a los IDs
            if (Array.isArray(data.lot_ids)) {
                console.log("✅ Es Array directo:", data.lot_ids);
            }
            
            if (data.lot_ids.records) {
                console.log("✅ Tiene .records:", data.lot_ids.records);
                console.log("Records mapped:", data.lot_ids.records.map(r => ({
                    resId: r.resId,
                    data: r.data,
                    id: r.data?.id
                })));
            }
            
            if (data.lot_ids.currentIds) {
                console.log("✅ Tiene .currentIds:", data.lot_ids.currentIds);
            }
            
            if (data.lot_ids.resIds) {
                console.log("✅ Tiene .resIds:", data.lot_ids.resIds);
            }

            // Propiedad count si existe
            if ('count' in data.lot_ids) {
                console.log("✅ Tiene .count:", data.lot_ids.count);
            }

            // Iterar si es iterable
            try {
                if (typeof data.lot_ids[Symbol.iterator] === 'function') {
                    console.log("✅ Es iterable, expandiendo:", [...data.lot_ids]);
                }
            } catch (e) {
                console.log("❌ No es iterable");
            }
        } else {
            console.log("❌ lot_ids es null/undefined/falsy");
        }
        console.groupEnd();

        // Otros campos relevantes
        console.log("product_id:", data.product_id);
        console.log("product_uom_qty:", data.product_uom_qty);
        
        console.groupEnd();
    }

    async handleClick(ev) {
        console.group("🔷 [STONE handleClick]");
        this._logRecordState("handleClick");
        
        const tr = ev.currentTarget.closest('tr');
        if (!tr) {
            console.warn("❌ No se encontró <tr>");
            console.groupEnd();
            return;
        }

        if (this.isExpanded) {
            this.removeGrid();
            this.isExpanded = false;
        } else {
            document.querySelectorAll('.o_stone_details_row_tr').forEach(e => e.remove());
            await this.injectContainer(tr);
            this.isExpanded = true;
        }
        this.render();
        console.groupEnd();
    }

    async injectContainer(currentRow) {
        console.log("🔷 [STONE injectContainer] Creando contenedor");
        
        const newTr = document.createElement('tr');
        newTr.className = 'o_stone_details_row_tr';
        
        const colCount = currentRow.querySelectorAll('td').length || 10;
        const newTd = document.createElement('td');
        newTd.colSpan = colCount;
        newTd.style.padding = '0';
        newTd.style.borderTop = '2px solid #714B67';
        
        this.containerNode = document.createElement('div');
        this.containerNode.className = 'bg-white';
        
        const filterBar = this.createFilterBar();
        this.containerNode.appendChild(filterBar);

        this.gridNode = document.createElement('div');
        this.gridNode.className = 'stone-grid-content p-0';
        this.gridNode.style.maxHeight = '400px';
        this.gridNode.style.overflowY = 'auto';
        this.gridNode.innerHTML = '<div class="text-center p-4"><i class="fa fa-circle-o-notch fa-spin"></i> Cargando inventario...</div>';
        
        this.containerNode.appendChild(this.gridNode);
        newTd.appendChild(this.containerNode);
        newTr.appendChild(newTd);
        
        currentRow.after(newTr);
        this.detailsRow = newTr;

        await this.loadData();
    }

    createFilterBar() {
        const bar = document.createElement('div');
        bar.className = 'd-flex flex-wrap gap-2 p-2 bg-light border-bottom align-items-end';

        const inputs = [
            { key: 'lot_name', label: 'Lote', width: '100px', type: 'text' },
            { key: 'bloque', label: 'Bloque', width: '80px', type: 'text' },
            { key: 'atado', label: 'Atado', width: '60px', type: 'text' },
            { key: 'alto_min', label: 'Alto >', width: '60px', type: 'number' },
            { key: 'ancho_min', label: 'Ancho >', width: '60px', type: 'number' },
        ];

        inputs.forEach(field => {
            const wrapper = document.createElement('div');
            wrapper.className = 'd-flex flex-column'; 
            
            const label = document.createElement('span');
            label.style.fontSize = '9px';
            label.className = 'fw-bold text-muted';
            label.innerText = field.label;
            
            const input = document.createElement('input');
            input.type = field.type;
            input.className = 'form-control form-control-sm';
            input.style.width = field.width;
            input.style.fontSize = '12px';
            input.value = this.filters[field.key] || '';
            
            input.addEventListener('input', (e) => {
                this.filters[field.key] = e.target.value;
                if(this.searchTimeout) clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => this.loadData(), 400);
            });

            wrapper.appendChild(label);
            wrapper.appendChild(input);
            bar.appendChild(wrapper);
        });

        const closeBtn = document.createElement('button');
        closeBtn.className = 'btn btn-sm btn-light border ms-auto';
        closeBtn.innerHTML = '<i class="fa fa-times"></i> Cerrar';
        closeBtn.onclick = () => {
            this.removeGrid();
            this.isExpanded = false;
            this.render();
        };
        bar.appendChild(closeBtn);

        return bar;
    }

    /**
     * DIAGNÓSTICO: Extractor con logs exhaustivos
     */
    extractLotIds(rawLots) {
        console.group("🔷 [STONE extractLotIds] Extrayendo IDs");
        console.log("Input rawLots:", rawLots);
        console.log("Input tipo:", typeof rawLots);
        
        if (!rawLots) {
            console.log("❌ rawLots es falsy, retornando []");
            console.groupEnd();
            return [];
        }

        console.log("rawLots constructor:", rawLots.constructor?.name);
        console.log("rawLots keys:", Object.keys(rawLots));
        
        // 1. Caso Array simple [1, 2, 3]
        if (Array.isArray(rawLots)) {
            console.log("✅ Es Array directo:", rawLots);
            console.groupEnd();
            return rawLots;
        }
        
        // 2. Caso Odoo X2Many RecordList (Odoo 16+)
        if (rawLots.records && Array.isArray(rawLots.records)) {
            console.log("✅ Tiene .records, extrayendo resIds");
            const ids = rawLots.records.map(r => {
                console.log("  Record:", r, "resId:", r.resId, "data.id:", r.data?.id);
                return r.resId || r.data?.id;
            }).filter(id => id);
            console.log("IDs extraídos:", ids);
            console.groupEnd();
            return ids;
        }

        // 3. Caso .currentIds
        if (rawLots.currentIds && Array.isArray(rawLots.currentIds)) {
            console.log("✅ Tiene .currentIds:", rawLots.currentIds);
            console.groupEnd();
            return rawLots.currentIds;
        }

        // 4. Caso .resIds
        if (rawLots.resIds && Array.isArray(rawLots.resIds)) {
            console.log("✅ Tiene .resIds:", rawLots.resIds);
            console.groupEnd();
            return rawLots.resIds;
        }

        // 5. Caso iterable
        try {
            if (typeof rawLots[Symbol.iterator] === 'function') {
                const ids = [...rawLots];
                console.log("✅ Es iterable, expandido:", ids);
                console.groupEnd();
                return ids;
            }
        } catch (e) {
            console.log("❌ No es iterable:", e);
        }

        console.log("❌ No se pudo extraer IDs, retornando []");
        console.groupEnd();
        return [];
    }

    async loadData() {
        if (!this.gridNode) return;
        
        console.group("🔷 [STONE loadData] Cargando datos");
        
        const recordData = this.props.record.data;
        this._logRecordState("loadData");
        
        let productId = false;
        if (recordData.product_id) {
            if (Array.isArray(recordData.product_id)) {
                productId = recordData.product_id[0];
            } else if (typeof recordData.product_id === 'number') {
                productId = recordData.product_id;
            } else if (recordData.product_id.id) {
                productId = recordData.product_id.id;
            } else if (typeof recordData.product_id === 'object' && recordData.product_id[0]) {
                productId = recordData.product_id[0];
            }
        }
        console.log("productId resuelto:", productId);

        if (!productId) {
            this.gridNode.innerHTML = '<div class="alert alert-warning m-2">Selecciona un producto primero.</div>';
            console.groupEnd();
            return;
        }

        const currentLotIds = this.extractLotIds(recordData.lot_ids);
        console.log("IDs finales para enviar al server:", currentLotIds);

        try {
            console.log("🔷 Llamando a search_stone_inventory_for_so...");
            const quants = await this.orm.call(
                'stock.quant', 
                'search_stone_inventory_for_so', 
                [], 
                { 
                    product_id: productId,
                    filters: this.filters,
                    current_lot_ids: currentLotIds
                }
            );
            console.log("🔷 Respuesta del server:", quants);

            this.renderTable(quants, currentLotIds);
        } catch (error) {
            console.error("❌ Error en loadData:", error);
            this.gridNode.innerHTML = `<div class="alert alert-danger m-2">Error: ${error.message}</div>`;
        }
        
        console.groupEnd();
    }

    renderTable(quants, selectedIds) {
        console.group("🔷 [STONE renderTable]");
        console.log("quants:", quants?.length);
        console.log("selectedIds:", selectedIds);
        
        if (!quants || quants.length === 0) {
            this.gridNode.innerHTML = '<div class="p-3 text-center text-muted">No se encontraron placas disponibles con estos filtros.</div>';
            console.groupEnd();
            return;
        }

        const groups = {};
        quants.forEach(q => {
            const b = q.x_bloque || 'Sin Bloque';
            if (!groups[b]) groups[b] = [];
            groups[b].push(q);
        });

        let html = `
            <table class="table table-sm table-hover table-bordered mb-0" style="font-size: 11px;">
                <thead class="bg-light sticky-top" style="top: 0;">
                    <tr>
                        <th width="30" class="text-center">#</th>
                        <th>Lote</th>
                        <th>Ubicación</th>
                        <th class="text-end">Dimensión</th>
                        <th class="text-end">M²</th>
                        <th class="text-center">Estado</th>
                    </tr>
                </thead>
                <tbody>
        `;

        for (const [bloque, items] of Object.entries(groups)) {
            const totalArea = items.reduce((sum, i) => sum + i.quantity, 0).toFixed(2);
            
            html += `
                <tr class="table-secondary">
                    <td colspan="6" class="px-2 fw-bold">
                        <i class="fa fa-cubes me-1"></i> Bloque: ${bloque} 
                        <span class="float-end badge bg-secondary">Total: ${totalArea} m²</span>
                    </td>
                </tr>
            `;
            
            items.forEach(q => {
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                const lotName = q.lot_id ? q.lot_id[1] : '';
                const locName = q.location_id ? q.location_id[1].split('/').pop() : '';
                
                const isChecked = selectedIds.includes(lotId);
                const isReserved = q.reserved_quantity > 0;

                let rowClass = isChecked ? 'table-primary' : '';
                let statusBadge = '';
                
                if (isChecked && isReserved) {
                    statusBadge = '<span class="badge bg-success" style="font-size:9px">Asignado</span>';
                } else if (isReserved) {
                    statusBadge = '<span class="badge bg-warning text-dark" style="font-size:9px">Reservado</span>';
                } else {
                    statusBadge = '<span class="badge bg-light text-muted border" style="font-size:9px">Libre</span>';
                }

                html += `
                    <tr class="${rowClass}" style="cursor:pointer;" onclick="this.querySelector('.stone-chk').click()">
                        <td class="text-center align-middle">
                            <input type="checkbox" class="stone-chk form-check-input mt-0" 
                                   value="${lotId}" ${isChecked ? 'checked' : ''} 
                                   onclick="event.stopPropagation()">
                        </td>
                        <td class="align-middle fw-bold font-monospace">${lotName}</td>
                        <td class="align-middle text-muted">${locName}</td>
                        <td class="align-middle text-end font-monospace">
                            ${(q.x_alto || 0).toFixed(2)} x ${(q.x_ancho || 0).toFixed(2)}
                        </td>
                        <td class="align-middle text-end fw-bold">${q.quantity.toFixed(2)}</td>
                        <td class="align-middle text-center">${statusBadge}</td>
                    </tr>
                `;
            });
        }
        html += `</tbody></table>`;
        
        this.gridNode.innerHTML = html;

        this.gridNode.querySelectorAll('.stone-chk').forEach(input => {
            input.addEventListener('change', (e) => this.onSelectionChange(e));
        });
        
        console.groupEnd();
    }

    onSelectionChange(ev) {
        console.group("🔷 [STONE onSelectionChange]");
        
        const id = parseInt(ev.target.value);
        const isChecked = ev.target.checked;
        const row = ev.target.closest('tr');
        
        console.log("Lot ID:", id);
        console.log("isChecked:", isChecked);
        
        if (isChecked) row.classList.add('table-primary');
        else row.classList.remove('table-primary');

        // Estado actual
        let currentIds = this.extractLotIds(this.props.record.data.lot_ids);
        console.log("currentIds ANTES:", currentIds);

        if (isChecked) {
            if (!currentIds.includes(id)) currentIds.push(id);
        } else {
            currentIds = currentIds.filter(x => x !== id);
        }
        console.log("currentIds DESPUÉS:", currentIds);

        // Actualizar el record
        const updateCommand = [[6, 0, currentIds]];
        console.log("Enviando update con:", updateCommand);
        
        this.props.record.update({ lot_ids: updateCommand });
        
        console.groupEnd();
    }

    removeGrid() {
        if (this.detailsRow) {
            this.detailsRow.remove();
            this.detailsRow = null;
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