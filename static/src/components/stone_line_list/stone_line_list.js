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
             title="Ver/Ocultar detalles de placas"
             style="width: 100%; height: 100%;">
            <i class="fa fa-chevron-right" style="transition: transform 0.2s ease; font-size: 12px;"/>
        </div>
    `;
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.detailsRow = null;
        this.containerNode = null;
        this.gridNode = null;
        
        // Estado local de filtros
        this.filters = {
            bloque: '',
            atado: '',
            alto_min: '',
            ancho_min: '',
            lot_name: '',
            contenedor: ''
        };
        
        // Debounce para la búsqueda
        this.searchTimeout = null;
        
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
            // Colapsar
            icon.style.transform = 'rotate(0deg)';
            this.removeGrid();
        } else {
            // Expandir
            icon.style.transform = 'rotate(90deg)';
            await this.injectContainer(tr);
        }
    }

    /**
     * Crea la fila contenedora e inyecta la estructura base (Filtros + Grid vacío)
     */
    async injectContainer(currentRow) {
        // 1. Crear fila TR
        const newTr = document.createElement('tr');
        newTr.className = 'o_stone_details_row_tr';
        
        const colCount = currentRow.querySelectorAll('td').length || 10;
        const newTd = document.createElement('td');
        newTd.colSpan = colCount;
        newTd.style.padding = '0';
        newTd.style.border = 'none';
        
        // 2. Contenedor principal
        this.containerNode = document.createElement('div');
        this.containerNode.className = 'bg-white border-bottom shadow-sm';
        
        // 3. Renderizar Barra de Filtros
        const filterBar = this.createFilterBar();
        this.containerNode.appendChild(filterBar);

        // 4. Renderizar Contenedor del Grid (Tabla)
        this.gridNode = document.createElement('div');
        this.gridNode.className = 'stone-grid-content p-2';
        this.gridNode.style.maxHeight = '400px';
        this.gridNode.style.overflowY = 'auto';
        this.gridNode.innerHTML = '<div class="text-center text-muted small py-3"><i class="fa fa-circle-o-notch fa-spin"></i> Cargando inventario...</div>';
        
        this.containerNode.appendChild(this.gridNode);
        newTd.appendChild(this.containerNode);
        newTr.appendChild(newTd);
        currentRow.after(newTr);
        this.detailsRow = newTr;

        // 5. Cargar datos iniciales
        await this.loadData();
    }

    /**
     * Genera el HTML de la barra de filtros y asigna eventos
     */
    createFilterBar() {
        const bar = document.createElement('div');
        bar.className = 'd-flex flex-wrap gap-2 p-2 bg-light border-bottom align-items-center';
        bar.style.fontSize = '12px';

        // Definición de filtros a mostrar
        const inputs = [
            { key: 'bloque', label: 'Bloque', width: '100px', placeholder: 'Ej. B-001' },
            { key: 'lot_name', label: 'Lote', width: '100px', placeholder: 'Buscar...' },
            { key: 'alto_min', label: 'Alto Mín.', width: '70px', type: 'number', placeholder: '0.00' },
            { key: 'ancho_min', label: 'Ancho Mín.', width: '70px', type: 'number', placeholder: '0.00' },
            { key: 'atado', label: 'Atado', width: '70px', placeholder: 'A-1' },
            { key: 'contenedor', label: 'Contenedor', width: '90px', placeholder: 'CONT...' },
        ];

        // Icono de filtro
        bar.innerHTML = '<div class="text-secondary me-1"><i class="fa fa-filter"></i></div>';

        inputs.forEach(field => {
            const wrapper = document.createElement('div');
            
            // Input
            const input = document.createElement('input');
            input.type = field.type || 'text';
            input.className = 'form-control form-control-sm';
            input.placeholder = field.placeholder || field.label;
            input.style.width = field.width;
            input.style.fontSize = '11px';
            input.value = this.filters[field.key] || '';
            
            // Evento
            input.addEventListener('input', (e) => {
                this.filters[field.key] = e.target.value;
                this.triggerSearch();
            });

            // Label flotante o simple (usamos title para ahorrar espacio visual)
            input.title = field.label;
            
            wrapper.appendChild(input);
            bar.appendChild(wrapper);
        });

        // Botón limpiar
        const clearBtn = document.createElement('button');
        clearBtn.className = 'btn btn-link btn-sm text-muted p-0 ms-auto';
        clearBtn.innerHTML = '<i class="fa fa-times"></i> Limpiar';
        clearBtn.style.fontSize = '11px';
        clearBtn.style.textDecoration = 'none';
        clearBtn.onclick = () => {
            this.filters = { bloque: '', atado: '', alto_min: '', ancho_min: '', lot_name: '', contenedor: '' };
            // Limpiar inputs visualmente
            bar.querySelectorAll('input').forEach(i => i.value = '');
            this.triggerSearch();
        };
        bar.appendChild(clearBtn);

        return bar;
    }

    triggerSearch() {
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.loadData();
        }, 400); // 400ms delay
    }

    async loadData() {
        if (!this.gridNode) return;
        
        const recordData = this.props.record.data;
        let productId = false;

        // Obtener ID del producto de forma segura
        if (recordData.product_id) {
            if (Array.isArray(recordData.product_id)) productId = recordData.product_id[0];
            else if (typeof recordData.product_id === 'number') productId = recordData.product_id;
            else if (recordData.product_id.id) productId = recordData.product_id.id;
        }

        if (!productId) {
            this.gridNode.innerHTML = '<div class="alert alert-warning m-2 py-1 small">Selecciona un producto primero.</div>';
            return;
        }

        // Indicador de carga sutil sobre la tabla existente si ya hay datos
        this.gridNode.style.opacity = '0.6';

        try {
            // Llamada al backend usando el nuevo método con filtros
            const quants = await this.orm.call(
                'stock.quant', 
                'search_stone_inventory_for_so', 
                [], 
                { 
                    product_id: productId,
                    filters: this.filters
                }
            );

            this.renderTable(quants);
        } catch (error) {
            console.error(error);
            this.gridNode.innerHTML = `<div class="alert alert-danger m-2 py-1 small">Error: ${error.message}</div>`;
        } finally {
            this.gridNode.style.opacity = '1';
        }
    }

    renderTable(quants) {
        if (!quants || quants.length === 0) {
            this.gridNode.innerHTML = `
                <div class="d-flex flex-column align-items-center justify-content-center py-4 text-muted">
                    <i class="fa fa-inbox fa-2x mb-2 opacity-50"></i>
                    <span class="small">No se encontraron placas con estos filtros.</span>
                </div>
            `;
            return;
        }

        // Agrupar por Bloque
        const groups = {};
        quants.forEach(q => {
            const b = q.x_bloque || 'General';
            if (!groups[b]) groups[b] = [];
            groups[b].push(q);
        });

        // Obtener IDs seleccionados actualmente en el record
        let selectedIds = [];
        const rawLots = this.props.record.data.lot_ids;
        if (rawLots) {
            if (Array.isArray(rawLots)) selectedIds = rawLots;
            else if (rawLots.currentIds) selectedIds = rawLots.currentIds;
        }

        // Construir tabla HTML
        let html = `
            <table class="table table-sm table-hover table-bordered mb-0" style="font-size: 11px;">
                <thead class="bg-light sticky-top" style="top: 0; z-index: 5;">
                    <tr>
                        <th width="30" class="text-center p-1">#</th>
                        <th class="p-1">Lote</th>
                        <th class="p-1">Ubicación</th>
                        <th class="p-1">Atado</th>
                        <th class="text-end p-1">Dimensiones</th>
                        <th class="text-end p-1">M²</th>
                    </tr>
                </thead>
                <tbody>
        `;

        // Iterar grupos y filas
        for (const [bloque, items] of Object.entries(groups)) {
            const totalArea = items.reduce((sum, i) => sum + i.quantity, 0).toFixed(2);
            
            // Header de grupo (Bloque)
            html += `
                <tr class="table-light">
                    <td colspan="6" class="px-2 py-1 fw-bold text-dark border-bottom" style="font-size: 11px;">
                        <div class="d-flex justify-content-between">
                            <span><i class="fa fa-cubes me-1 text-primary"></i> Bloque: ${bloque}</span>
                            <span class="badge bg-white text-dark border fw-normal">Total: ${totalArea} m²</span>
                        </div>
                    </td>
                </tr>
            `;
            
            items.forEach(q => {
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                const lotName = q.lot_id ? q.lot_id[1] : '';
                
                // Limpiar nombre de ubicación (quitar almacén padre)
                const fullLocName = q.location_id ? q.location_id[1] : '';
                const locName = fullLocName.split('/').pop().trim();

                const isChecked = selectedIds.includes(lotId) ? 'checked' : '';
                const rowClass = isChecked ? 'bg-primary bg-opacity-10' : '';
                
                html += `
                    <tr class="${rowClass}" style="cursor:pointer;" onclick="this.querySelector('.stone-chk').click()">
                        <td class="text-center align-middle p-1">
                            <input type="checkbox" class="stone-chk form-check-input mt-0" 
                                   style="width: 14px; height: 14px; cursor: pointer;"
                                   value="${lotId}" ${isChecked} 
                                   onclick="event.stopPropagation()">
                        </td>
                        <td class="align-middle p-1 fw-bold text-dark font-monospace">${lotName}</td>
                        <td class="align-middle p-1 text-muted small">${locName}</td>
                        <td class="align-middle p-1 text-muted small">${q.x_atado || '-'}</td>
                        <td class="align-middle text-end p-1 font-monospace text-secondary">
                            ${(q.x_alto || 0).toFixed(2)} x ${(q.x_ancho || 0).toFixed(2)}
                        </td>
                        <td class="align-middle text-end p-1 fw-bold text-dark">${q.quantity.toFixed(2)}</td>
                    </tr>
                `;
            });
        }
        html += `</tbody></table>`;
        
        this.gridNode.innerHTML = html;

        // Re-asignar eventos a los nuevos checkboxes
        const inputs = this.gridNode.querySelectorAll('.stone-chk');
        inputs.forEach(input => {
            input.addEventListener('change', (e) => {
                this.onSelectionChange(e);
            });
        });
    }

    onSelectionChange(ev) {
        const id = parseInt(ev.target.value);
        const isChecked = ev.target.checked;
        const row = ev.target.closest('tr');
        
        // Actualizar visualmente la fila inmediatamente
        if (isChecked) row.classList.add('bg-primary', 'bg-opacity-10');
        else row.classList.remove('bg-primary', 'bg-opacity-10');

        // Lógica de actualización de campo Many2many en Odoo
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

        // Trigger update
        this.props.record.update({ lot_ids: [[6, 0, currentIds]] });
    }

    removeGrid() {
        if (this.detailsRow) {
            this.detailsRow.remove();
            this.detailsRow = null;
            this.containerNode = null;
            this.gridNode = null;
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