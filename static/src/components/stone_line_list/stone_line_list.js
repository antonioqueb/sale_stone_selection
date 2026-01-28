/** @odoo-module */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, xml, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class StoneExpandButton extends Component {
    // 1. Template: Solo el botón. El resto es JS puro.
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
        this.detailsRow = null; // Variable nativa JS, sin 'useState'
        
        // Limpieza obligatoria al destruir el widget
        onWillUnmount(() => {
            this.removeGrid();
        });
    }

    // --- LÓGICA 100% VANILLA JS / DOM MANIPULATION ---

    async handleClick(ev) {
        const btn = ev.currentTarget;
        const icon = btn.querySelector('i');
        const tr = btn.closest('tr');

        if (!tr) return;

        // 1. Rotación Manual del Icono (Sin Owl state)
        // Verificamos si ya está abierto mirando si existe la fila siguiente
        if (this.detailsRow && document.body.contains(this.detailsRow)) {
            // CERRAR
            icon.style.transform = 'rotate(0deg)';
            this.removeGrid();
        } else {
            // ABRIR
            icon.style.transform = 'rotate(90deg)';
            await this.injectGrid(tr);
        }
    }

    async injectGrid(currentRow) {
        // 2. Crear elementos HTML a mano (document.createElement)
        const newTr = document.createElement('tr');
        newTr.className = 'o_stone_details_row_tr';
        
        const colCount = currentRow.querySelectorAll('td').length || 10;
        const newTd = document.createElement('td');
        newTd.colSpan = colCount;
        newTd.style.padding = '0';
        newTd.style.border = 'none';
        
        const container = document.createElement('div');
        container.className = 'p-3 bg-light border-bottom';
        container.innerHTML = '<div class="text-center text-muted"><i class="fa fa-circle-o-notch fa-spin"></i> Cargando placas...</div>';

        newTd.appendChild(container);
        newTr.appendChild(newTd);
        
        // Inyección en el DOM real
        currentRow.after(newTr);
        this.detailsRow = newTr;

        // 3. Obtener Datos (Fix para "Selecciona un producto")
        const recordData = this.props.record.data;
        let productId = false;

        // Odoo entrega el dato en formatos variados, normalizamos:
        if (recordData.product_id) {
            if (Array.isArray(recordData.product_id)) {
                productId = recordData.product_id[0]; // Caso: [12, "Mármol"]
            } else if (typeof recordData.product_id === 'number') {
                productId = recordData.product_id;    // Caso: 12
            } else if (recordData.product_id.id) {
                productId = recordData.product_id.id; // Caso: {id: 12, ...}
            }
        }

        console.log("[StoneJS] ID Producto detectado:", productId); // Debug en consola

        if (!productId) {
            container.innerHTML = '<div class="alert alert-warning m-0">Debes seleccionar un producto primero.</div>';
            return;
        }

        try {
            // 4. Llamada al Servidor
            const quants = await this.orm.searchRead('stock.quant', [
                ['product_id', '=', productId],
                ['location_id.usage', '=', 'internal'],
                ['quantity', '>', 0]
            ], ['lot_id', 'location_id', 'quantity', 'x_bloque', 'x_alto', 'x_ancho']);

            if (!quants || quants.length === 0) {
                container.innerHTML = '<div class="alert alert-info m-0">No hay stock de placas disponible.</div>';
                return;
            }

            // 5. Construcción de Tabla con Template String (Puro String)
            // Agrupamos datos en JS
            const groups = {};
            quants.forEach(q => {
                const b = q.x_bloque || 'General';
                if (!groups[b]) groups[b] = [];
                groups[b].push(q);
            });

            // Leer seleccionados actuales
            let selectedIds = [];
            const rawLots = recordData.lot_ids;
            if (rawLots) {
                // Manejo robusto de x2many
                if (Array.isArray(rawLots)) selectedIds = rawLots;
                else if (rawLots.currentIds) selectedIds = rawLots.currentIds;
            }

            let html = `
                <div class="table-responsive bg-white border rounded">
                    <table class="table table-sm table-hover mb-0" style="font-size: 0.9rem;">
                        <thead class="table-light">
                            <tr>
                                <th width="40" class="text-center">#</th>
                                <th>Lote</th>
                                <th>Ubicación</th>
                                <th>Bloque</th>
                                <th class="text-end">Medidas</th>
                                <th class="text-end">M²</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            for (const [bloque, items] of Object.entries(groups)) {
                html += `<tr class="bg-light fw-bold"><td colspan="6" class="px-3 text-primary"><i class="fa fa-cubes"></i> ${bloque}</td></tr>`;
                
                items.forEach(q => {
                    const lotId = q.lot_id ? q.lot_id[0] : 0;
                    const lotName = q.lot_id ? q.lot_id[1] : '';
                    const locName = q.location_id ? q.location_id[1] : '';
                    const isChecked = selectedIds.includes(lotId) ? 'checked' : '';
                    
                    html += `
                        <tr style="cursor:pointer" onclick="this.querySelector('input').click()">
                            <td class="text-center align-middle">
                                <input type="checkbox" class="stone-chk form-check-input" 
                                       value="${lotId}" ${isChecked} 
                                       onclick="event.stopPropagation()">
                            </td>
                            <td class="align-middle font-monospace fw-bold">${lotName}</td>
                            <td class="align-middle text-muted small">${locName}</td>
                            <td class="align-middle">${bloque}</td>
                            <td class="align-middle text-end font-monospace">${q.x_alto || '-'} x ${q.x_ancho || '-'}</td>
                            <td class="align-middle text-end fw-bold">${q.quantity}</td>
                        </tr>
                    `;
                });
            }
            html += `</tbody></table></div>`;
            
            // Renderizado final
            container.innerHTML = html;

            // 6. Listeners Nativos (Sin Owl events)
            const inputs = container.querySelectorAll('.stone-chk');
            inputs.forEach(input => {
                input.addEventListener('change', (e) => {
                    this.onSelectionChange(e);
                });
            });

        } catch (error) {
            console.error(error);
            container.innerHTML = `<div class="alert alert-danger m-0">Error: ${error.message}</div>`;
        }
    }

    onSelectionChange(ev) {
        // Lógica JS pura para calcular array
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

        // Único punto de contacto con Odoo: Guardar el cambio
        this.props.record.update({ lot_ids: [[6, 0, currentIds]] });
    }

    removeGrid() {
        if (this.detailsRow) {
            this.detailsRow.remove(); // JS Nativo: element.remove()
            this.detailsRow = null;
        }
    }
}

// Registro obligatorio en Odoo
registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Stone Expand Button (Pure JS)",
});

// Registro de vista lista obligatoria
export const stoneOrderLineListView = {
    ...listView,
};
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);