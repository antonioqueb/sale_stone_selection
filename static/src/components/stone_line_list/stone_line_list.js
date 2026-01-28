/** @odoo-module */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, xml, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class StoneExpandButton extends Component {
    static template = xml`
        <div class="o_stone_toggle_btn cursor-pointer d-flex align-items-center justify-content-center" 
             t-on-click.stop="handleClick"
             style="width: 100%; height: 100%;">
            <i class="fa fa-chevron-right" style="transition: transform 0.2s ease;"/>
        </div>
    `;
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.detailsRow = null;
        
        onWillUnmount(() => {
            this.removeGrid();
        });
    }

    async handleClick(ev) {
        const btn = ev.currentTarget;
        const icon = btn.querySelector('i');
        const tr = btn.closest('tr');

        if (!tr) return;

        if (this.detailsRow && document.body.contains(this.detailsRow)) {
            icon.style.transform = 'rotate(0deg)';
            this.removeGrid();
        } else {
            icon.style.transform = 'rotate(90deg)';
            await this.injectGrid(tr);
        }
    }

    async injectGrid(currentRow) {
        const newTr = document.createElement('tr');
        newTr.className = 'o_stone_details_row_tr';
        
        const colCount = currentRow.querySelectorAll('td').length || 10;
        const newTd = document.createElement('td');
        newTd.colSpan = colCount;
        newTd.style.padding = '0';
        newTd.style.border = 'none';
        
        const container = document.createElement('div');
        // P-2 para menos padding general
        container.className = 'p-2 bg-light border-bottom'; 
        container.innerHTML = '<div class="text-center text-muted small"><i class="fa fa-circle-o-notch fa-spin"></i> Cargando...</div>';

        newTd.appendChild(container);
        newTr.appendChild(newTd);
        currentRow.after(newTr);
        this.detailsRow = newTr;

        const recordData = this.props.record.data;
        let productId = false;

        if (recordData.product_id) {
            if (Array.isArray(recordData.product_id)) {
                productId = recordData.product_id[0];
            } else if (typeof recordData.product_id === 'number') {
                productId = recordData.product_id;
            } else if (recordData.product_id.id) {
                productId = recordData.product_id.id;
            }
        }

        if (!productId) {
            container.innerHTML = '<div class="alert alert-warning m-1 py-1 px-2 small">Selecciona un producto.</div>';
            return;
        }

        try {
            const quants = await this.orm.searchRead('stock.quant', [
                ['product_id', '=', productId],
                ['location_id.usage', '=', 'internal'],
                ['quantity', '>', 0]
            ], ['lot_id', 'location_id', 'quantity', 'x_bloque', 'x_alto', 'x_ancho']);

            if (!quants || quants.length === 0) {
                container.innerHTML = '<div class="alert alert-info m-1 py-1 px-2 small">No hay stock disponible.</div>';
                return;
            }

            const groups = {};
            quants.forEach(q => {
                const b = q.x_bloque || 'General';
                if (!groups[b]) groups[b] = [];
                groups[b].push(q);
            });

            let selectedIds = [];
            const rawLots = recordData.lot_ids;
            if (rawLots) {
                if (Array.isArray(rawLots)) selectedIds = rawLots;
                else if (rawLots.currentIds) selectedIds = rawLots.currentIds;
            }

            // --- INICIO DE CONSTRUCCIÓN DE TABLA ---
            // Cambio: font-size: 12px y table-sm más compacta
            let html = `
                <div class="bg-white border rounded shadow-sm">
                    <table class="table table-sm table-hover table-bordered mb-0" style="font-size: 12px;">
                        <thead class="bg-200" style="background-color: #f1f3f5;">
                            <tr>
                                <th width="30" class="text-center p-1">#</th>
                                <th class="p-1">Lote</th>
                                <th class="p-1">Ubicación</th> <!-- Solo hija -->
                                <th class="p-1">Bloque</th>
                                <th class="text-end p-1">Medidas</th>
                                <th class="text-end p-1">M²</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            for (const [bloque, items] of Object.entries(groups)) {
                // Header de grupo más discreto
                html += `
                    <tr class="bg-light text-muted">
                        <td colspan="6" class="px-2 py-1 fw-bold" style="font-size: 11px; letter-spacing: 0.5px;">
                            <i class="fa fa-cubes me-1"></i> ${bloque}
                        </td>
                    </tr>
                `;
                
                items.forEach(q => {
                    const lotId = q.lot_id ? q.lot_id[0] : 0;
                    const lotName = q.lot_id ? q.lot_id[1] : '';
                    
                    // --- LÓGICA PARA UBICACIÓN HIJA ---
                    const fullLocName = q.location_id ? q.location_id[1] : '';
                    // Split corta por '/', pop toma el último, trim quita espacios
                    const locName = fullLocName.split('/').pop().trim(); 

                    const isChecked = selectedIds.includes(lotId) ? 'checked' : '';
                    
                    // Filas más compactas (p-1)
                    html += `
                        <tr style="cursor:pointer;" onclick="this.querySelector('input').click()">
                            <td class="text-center align-middle p-1">
                                <input type="checkbox" class="stone-chk form-check-input mt-0" 
                                       style="width: 14px; height: 14px;"
                                       value="${lotId}" ${isChecked} 
                                       onclick="event.stopPropagation()">
                            </td>
                            <td class="align-middle p-1 fw-bold text-dark">${lotName}</td>
                            <td class="align-middle p-1 text-primary">${locName}</td>
                            <td class="align-middle p-1 text-muted">${bloque}</td>
                            <td class="align-middle text-end p-1 font-monospace text-secondary">${q.x_alto || '-'} x ${q.x_ancho || '-'}</td>
                            <td class="align-middle text-end p-1 fw-bold text-dark">${q.quantity}</td>
                        </tr>
                    `;
                });
            }
            html += `</tbody></table></div>`;
            
            container.innerHTML = html;

            const inputs = container.querySelectorAll('.stone-chk');
            inputs.forEach(input => {
                input.addEventListener('change', (e) => {
                    this.onSelectionChange(e);
                });
            });

        } catch (error) {
            console.error(error);
            container.innerHTML = `<div class="alert alert-danger m-1 py-1 small">Error: ${error.message}</div>`;
        }
    }

    onSelectionChange(ev) {
        const id = parseInt(ev.target.value);
        const isChecked = ev.target.checked;
        
        let currentIds = [];
        const rawLots = this.props.record.data.lot_ids;
        if (rawLots) {
            if (Array.isArray(rawLots)) currentIds = [...rawLots];
            else if (rawLots.currentIds) currentIds = [...rawLots.currentIds];
        }

        if (isChecked) {
            if (!currentIds.includes(id)) currentIds.push(id);
        } else {
            currentIds = currentIds.filter(x => x !== id);
        }

        this.props.record.update({ lot_ids: [[6, 0, currentIds]] });
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
    displayName: "Stone Expand Button (Pure JS)",
});

export const stoneOrderLineListView = {
    ...listView,
};
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);