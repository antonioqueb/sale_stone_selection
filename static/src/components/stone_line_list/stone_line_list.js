/** @odoo-module */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, xml, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class StoneExpandButton extends Component {
    // El botón sigue siendo Owl porque vive dentro de Odoo, pero el contenido será JS puro
    static template = xml`
        <div class="o_stone_toggle_btn cursor-pointer d-flex align-items-center justify-content-center" 
             t-on-click.stop="toggle"
             style="width: 100%; height: 100%;">
            <i class="fa fa-chevron-right" 
               t-att-class="{'o_rotated': state.expanded}"
               style="transition: transform 0.2s ease;"/>
        </div>
    `;
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm"); // Servicio para llamar a BD
        this.state = useState({ expanded: false });
        this.detailsRow = null; // Referencia al TR creado manualmente

        onWillUnmount(() => {
            this.cleanup();
        });
    }

    async toggle(ev) {
        this.state.expanded = !this.state.expanded;

        if (this.state.expanded) {
            // Pasamos el nodo del botón (div)
            await this.injectContent(ev.currentTarget);
        } else {
            this.cleanup();
        }
    }

    async injectContent(targetNode) {
        // 1. Encontrar fila padre
        const currentRow = targetNode.closest('tr');
        if (!currentRow) return;

        // 2. Crear fila contenedora (DOM Vainilla)
        const tr = document.createElement('tr');
        tr.className = 'o_stone_details_row_tr';
        
        const colCount = currentRow.querySelectorAll('td').length || 15;
        const td = document.createElement('td');
        td.colSpan = colCount;
        td.style.padding = '10px';
        td.style.backgroundColor = '#f9f9f9'; // Fondo gris claro
        
        // Contenedor donde pintaremos todo
        const container = document.createElement('div');
        container.innerHTML = '<div class="text-center p-2"><i class="fa fa-spin fa-spinner"></i> Cargando placas...</div>';
        
        td.appendChild(container);
        tr.appendChild(td);
        currentRow.after(tr);
        this.detailsRow = tr;

        // 3. Obtener Datos del Servidor (RPC)
        const productId = this.props.record.data.product_id ? this.props.record.data.product_id[0] : false;
        
        if (!productId) {
            container.innerHTML = '<div class="alert alert-warning">Selecciona un producto primero.</div>';
            return;
        }

        try {
            // Buscamos Stock directamente
            const quants = await this.orm.searchRead('stock.quant', [
                ['product_id', '=', productId],
                ['location_id.usage', '=', 'internal'],
                ['quantity', '>', 0]
            ], ['lot_id', 'location_id', 'quantity', 'x_bloque', 'x_alto', 'x_ancho']);

            if (quants.length === 0) {
                container.innerHTML = '<div class="alert alert-info">No hay stock disponible.</div>';
                return;
            }

            // 4. Construir HTML de la tabla manualmente (String Template)
            // Agrupamos por bloque primero (lógica JS simple)
            const groups = {};
            quants.forEach(q => {
                const bloque = q.x_bloque || 'Sin Bloque';
                if (!groups[bloque]) groups[bloque] = [];
                groups[bloque].push(q);
            });

            // Obtenemos los IDs seleccionados actualmente
            let selectedIds = this.props.record.data.lot_ids.currentIds || [];

            let html = `
                <style>
                    .stone-simple-table { width: 100%; border-collapse: collapse; background: white; }
                    .stone-simple-table th { background: #eee; padding: 5px; font-size: 0.85rem; border-bottom: 2px solid #ccc; }
                    .stone-simple-table td { padding: 5px; border-bottom: 1px solid #eee; vertical-align: middle; }
                    .stone-group-header { background: #eef; font-weight: bold; color: #333; }
                </style>
                <table class="stone-simple-table">
                    <thead>
                        <tr>
                            <th style="width: 30px"></th>
                            <th>Lote</th>
                            <th>Ubicación</th>
                            <th>Bloque</th>
                            <th style="text-align: right">Dimensiones</th>
                            <th style="text-align: right">M²</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            for (const [bloque, items] of Object.entries(groups)) {
                // Header del grupo
                html += `
                    <tr class="stone-group-header">
                        <td colspan="6"><i class="fa fa-cubes"></i> Bloque: ${bloque}</td>
                    </tr>
                `;

                // Filas de items
                items.forEach(q => {
                    const lotId = q.lot_id ? q.lot_id[0] : 0;
                    const lotName = q.lot_id ? q.lot_id[1] : '-';
                    const locName = q.location_id ? q.location_id[1] : '-';
                    const isChecked = selectedIds.includes(lotId) ? 'checked' : '';
                    
                    html += `
                        <tr style="cursor: pointer;" onclick="document.getElementById('chk_${q.id}').click()">
                            <td class="text-center">
                                <input type="checkbox" id="chk_${q.id}" 
                                       data-lot-id="${lotId}" 
                                       class="stone-checkbox" 
                                       ${isChecked} 
                                       onclick="event.stopPropagation()">
                            </td>
                            <td><b>${lotName}</b></td>
                            <td><span class="text-muted">${locName}</span></td>
                            <td>${bloque}</td>
                            <td style="text-align: right">${q.x_alto || 0} x ${q.x_ancho || 0}</td>
                            <td style="text-align: right"><b>${q.quantity}</b></td>
                        </tr>
                    `;
                });
            }
            html += `</tbody></table>`;
            
            // Inyectamos el HTML final
            container.innerHTML = html;

            // 5. Agregar Event Listeners (JS Vainilla)
            // No usamos t-on-click, usamos addEventListener real
            const checkboxes = container.querySelectorAll('.stone-checkbox');
            checkboxes.forEach(chk => {
                chk.addEventListener('change', (e) => {
                    this.onCheckboxChange(e);
                });
            });

        } catch (err) {
            console.error(err);
            container.innerHTML = `<div class="text-danger">Error: ${err.message}</div>`;
        }
    }

    onCheckboxChange(e) {
        const lotId = parseInt(e.target.dataset.lotId);
        const checked = e.target.checked;

        // Obtenemos lista actual
        let currentIds = [...(this.props.record.data.lot_ids.currentIds || [])];

        if (checked) {
            if (!currentIds.includes(lotId)) currentIds.push(lotId);
        } else {
            currentIds = currentIds.filter(id => id !== lotId);
        }

        // Actualizamos Odoo usando el comando [6, 0, ids]
        this.props.record.update({ lot_ids: [[6, 0, currentIds]] });
    }

    cleanup() {
        if (this.detailsRow) {
            this.detailsRow.remove();
            this.detailsRow = null;
        }
    }
}

// Registro
registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Stone Expand Button (Pure JS)",
});

export const stoneOrderLineListView = {
    ...listView,
};

registry.category("views").add("stone_order_line_list", stoneOrderLineListView);