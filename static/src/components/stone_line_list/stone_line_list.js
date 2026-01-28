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
        
        // Estado local de filtros (Actualizado)
        this.filters = {
            lot_name: '',
            bloque: '',
            atado: '',
            alto_min: '',  // Nuevo
            ancho_min: ''  // Nuevo
        };
        
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
            icon.style.transform = 'rotate(0deg)';
            this.removeGrid();
        } else {
            icon.style.transform = 'rotate(90deg)';
            await this.injectContainer(tr);
        }
    }

    async injectContainer(currentRow) {
        const newTr = document.createElement('tr');
        newTr.className = 'o_stone_details_row_tr';
        
        const colCount = currentRow.querySelectorAll('td').length || 10;
        const newTd = document.createElement('td');
        newTd.colSpan = colCount;
        newTd.style.padding = '0';
        newTd.style.border = 'none';
        
        this.containerNode = document.createElement('div');
        this.containerNode.className = 'bg-white border-bottom shadow-sm';
        
        // Barra de Filtros (Actualizada)
        const filterBar = this.createFilterBar();
        this.containerNode.appendChild(filterBar);

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

        await this.loadData();
    }

    createFilterBar() {
        const bar = document.createElement('div');
        bar.className = 'd-flex flex-wrap gap-3 p-2 bg-light border-bottom align-items-end';
        bar.style.fontSize = '12px';

        // Definición de filtros (Agregados Alto/Ancho Min)
        const inputs = [
            { key: 'lot_name', label: 'Lote / Serial', width: '120px', placeholder: 'Buscar...', type: 'text' },
            { key: 'bloque', label: 'Bloque', width: '80px', placeholder: 'B-01', type: 'text' },
            { key: 'atado', label: 'Atado', width: '80px', placeholder: 'A-1', type: 'text' },
            { key: 'alto_min', label: 'Alto Min (m)', width: '70px', placeholder: '0.00', type: 'number' }, // Nuevo
            { key: 'ancho_min', label: 'Ancho Min (m)', width: '70px', placeholder: '0.00', type: 'number' }, // Nuevo
        ];

        const iconContainer = document.createElement('div');
        iconContainer.className = 'text-secondary me-1 mb-2';
        iconContainer.innerHTML = '<i class="fa fa-filter fa-lg"></i>';
        bar.appendChild(iconContainer);

        inputs.forEach(field => {
            const wrapper = document.createElement('div');
            wrapper.className = 'd-flex flex-column'; 

            const label = document.createElement('span');
            label.className = 'text-muted fw-bold mb-1';
            label.style.fontSize = '10px';
            label.style.textTransform = 'uppercase';
            label.innerText = field.label;

            const input = document.createElement('input');
            input.type = field.type; // text o number
            input.className = 'form-control form-control-sm';
            input.placeholder = field.placeholder;
            input.style.width = field.width;
            input.style.fontSize = '12px';
            input.value = this.filters[field.key] || '';
            
            if(field.type === 'number') {
                input.step = "0.01";
                input.min = "0";
            }
            
            input.addEventListener('input', (e) => {
                this.filters[field.key] = e.target.value;
                this.triggerSearch();
            });

            wrapper.appendChild(label);
            wrapper.appendChild(input);
            bar.appendChild(wrapper);
        });

        // Botón limpiar
        const clearBtnWrapper = document.createElement('div');
        clearBtnWrapper.className = 'd-flex flex-column justify-content-end ms-auto';
        
        const clearBtn = document.createElement('button');
        clearBtn.className = 'btn btn-link btn-sm text-muted p-0 mb-1';
        clearBtn.innerHTML = '<i class="fa fa-times"></i> Limpiar';
        clearBtn.style.fontSize = '11px';
        clearBtn.style.textDecoration = 'none';
        clearBtn.onclick = () => {
            this.filters = { lot_name: '', bloque: '', atado: '', alto_min: '', ancho_min: '' };
            bar.querySelectorAll('input').forEach(i => i.value = '');
            this.triggerSearch();
        };
        
        clearBtnWrapper.appendChild(clearBtn);
        bar.appendChild(clearBtnWrapper);

        return bar;
    }

    triggerSearch() {
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.loadData();
        }, 500);
    }

    async loadData() {
        if (!this.gridNode) return;
        
        const recordData = this.props.record.data;
        let productId = false;

        if (recordData.product_id) {
            if (Array.isArray(recordData.product_id)) productId = recordData.product_id[0];
            else if (typeof recordData.product_id === 'number') productId = recordData.product_id;
            else if (recordData.product_id.id) productId = recordData.product_id.id;
        }

        if (!productId) {
            this.gridNode.innerHTML = '<div class="alert alert-warning m-2 py-1 small">Selecciona un producto primero.</div>';
            return;
        }

        // Obtener IDs seleccionados para pasarlos al backend y asegurar que se muestren
        // aunque estén reservados (por nosotros).
        let currentLotIds = [];
        const rawLots = this.props.record.data.lot_ids;
        if (rawLots) {
            if (Array.isArray(rawLots)) currentLotIds = [...rawLots];
            else if (rawLots.currentIds) currentLotIds = [...rawLots.currentIds];
        }

        this.gridNode.style.opacity = '0.6';

        try {
            const quants = await this.orm.call(
                'stock.quant', 
                'search_stone_inventory_for_so', 
                [], 
                { 
                    product_id: productId,
                    filters: this.filters,
                    current_lot_ids: currentLotIds // Importante: Pasar selección actual
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
                    <i class="fa fa-search fa-2x mb-2 opacity-50"></i>
                    <span class="small">No se encontraron placas disponibles o libres de Hold.</span>
                </div>
            `;
            return;
        }

        const groups = {};
        quants.forEach(q => {
            const b = q.x_bloque || 'General';
            if (!groups[b]) groups[b] = [];
            groups[b].push(q);
        });

        let selectedIds = [];
        const rawLots = this.props.record.data.lot_ids;
        if (rawLots) {
            if (Array.isArray(rawLots)) selectedIds = rawLots;
            else if (rawLots.currentIds) selectedIds = rawLots.currentIds;
        }

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
                        <th class="text-center p-1" title="Estado"><i class="fa fa-info-circle"></i></th>
                    </tr>
                </thead>
                <tbody>
        `;

        for (const [bloque, items] of Object.entries(groups)) {
            const totalArea = items.reduce((sum, i) => sum + i.quantity, 0).toFixed(2);
            
            html += `
                <tr class="table-light">
                    <td colspan="7" class="px-2 py-1 fw-bold text-dark border-bottom" style="font-size: 11px;">
                        <div class="d-flex justify-content-between align-items-center">
                            <span><i class="fa fa-cubes me-1 text-primary"></i> Bloque: ${bloque}</span>
                            <span class="badge bg-white text-dark border fw-normal">Total: ${totalArea} m²</span>
                        </div>
                    </td>
                </tr>
            `;
            
            items.forEach(q => {
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                const lotName = q.lot_id ? q.lot_id[1] : '';
                const fullLocName = q.location_id ? q.location_id[1] : '';
                const locName = fullLocName.split('/').pop().trim();

                const isChecked = selectedIds.includes(lotId);
                // Si está reservado por OTRO, no debería salir (filtrado en python), 
                // pero si sale y tiene reserved_qty > 0, es que probablemente es NUESTRA reserva.
                const isReserved = q.reserved_quantity > 0;
                
                // Estilo visual
                let rowClass = isChecked ? 'bg-primary bg-opacity-10' : '';
                let statusIcon = '';
                
                if (isReserved) {
                    // Si está reservado y seleccionado, asumimos que es por nosotros
                    if (isChecked) statusIcon = '<span class="badge bg-success" style="font-size:8px;">ASIG</span>';
                    else statusIcon = '<span class="badge bg-warning text-dark" style="font-size:8px;">RSV</span>';
                }

                html += `
                    <tr class="${rowClass}" style="cursor:pointer;" onclick="this.querySelector('.stone-chk').click()">
                        <td class="text-center align-middle p-1">
                            <input type="checkbox" class="stone-chk form-check-input mt-0" 
                                   style="width: 14px; height: 14px; cursor: pointer;"
                                   value="${lotId}" ${isChecked ? 'checked' : ''} 
                                   onclick="event.stopPropagation()">
                        </td>
                        <td class="align-middle p-1 fw-bold text-dark font-monospace">${lotName}</td>
                        <td class="align-middle p-1 text-muted small">${locName}</td>
                        <td class="align-middle p-1 text-muted small">${q.x_atado || '-'}</td>
                        <td class="align-middle text-end p-1 font-monospace text-secondary">
                            ${(q.x_alto || 0).toFixed(2)} x ${(q.x_ancho || 0).toFixed(2)}
                        </td>
                        <td class="align-middle text-end p-1 fw-bold text-dark">${q.quantity.toFixed(2)}</td>
                        <td class="align-middle text-center p-1">${statusIcon}</td>
                    </tr>
                `;
            });
        }
        html += `</tbody></table>`;
        
        this.gridNode.innerHTML = html;

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
        
        if (isChecked) row.classList.add('bg-primary', 'bg-opacity-10');
        else row.classList.remove('bg-primary', 'bg-opacity-10');

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