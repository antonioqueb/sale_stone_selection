/** @odoo-module */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";

export class StoneMoveGridField extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            isLoading: true,
            quants: [],
            selectedLotIds: new Set(),
            filters: { lot_name: '', bloque: '', atado: '' }
        });
        this.searchTimeout = null;

        onWillStart(async () => { 
            this._syncSelectedFromRecord();
            await this.loadInventory(); 
        });
        
        onWillUpdateProps(async (nextProps) => {
            const oldId = this.props.record.data.product_id ? this.props.record.data.product_id[0] : null;
            const newId = nextProps.record.data.product_id ? nextProps.record.data.product_id[0] : null;
            if (oldId !== newId) {
                await this.loadInventory(nextProps);
            }
            this._syncSelectedFromRecord(nextProps);
        });
    }

    /**
     * Sincroniza los IDs seleccionados desde el record (move_line_ids)
     */
    _syncSelectedFromRecord(props = this.props) {
        const lines = props.record.data.move_line_ids;
        const selectedIds = new Set();
        
        if (lines && lines.records) {
            for (const line of lines.records) {
                const lotData = line.data.lot_id;
                if (lotData) {
                    selectedIds.add(lotData[0]);
                }
            }
        }
        this.state.selectedLotIds = selectedIds;
    }

    async loadInventory(props = this.props) {
        const recordData = props.record.data;
        const productId = recordData.product_id ? recordData.product_id[0] : false;
        
        this.state.isLoading = true;

        if (!productId) {
            this.state.quants = [];
            this.state.isLoading = false;
            return;
        }

        // Obtener IDs de lotes ya asignados
        const currentLotIds = Array.from(this.state.selectedLotIds);

        try {
            // Llamar al servidor para obtener TODOS los datos de los lotes
            const quants = await this.orm.call('stock.quant', 'search_stone_inventory_for_so', [], {
                product_id: productId,
                filters: this.state.filters,
                current_lot_ids: currentLotIds
            });
            
            this.state.quants = quants;
        } catch (e) {
            console.error("Error cargando inventario:", e);
            this.state.quants = [];
        } finally {
            this.state.isLoading = false;
        }
    }

    get groupedQuants() {
        if (this.state.quants.length === 0) return [];
        
        const groups = {};
        
        // Ordenar: seleccionados primero, luego por bloque
        const sorted = [...this.state.quants].sort((a, b) => {
            const aSelected = this.isLotSelected(a.lot_id ? a.lot_id[0] : 0) ? 0 : 1;
            const bSelected = this.isLotSelected(b.lot_id ? b.lot_id[0] : 0) ? 0 : 1;
            if (aSelected !== bSelected) return aSelected - bSelected;
            
            const bla = a.x_bloque || 'zzz';
            const blb = b.x_bloque || 'zzz';
            return bla.localeCompare(blb);
        });

        for (const q of sorted) {
            const isSelected = this.isLotSelected(q.lot_id ? q.lot_id[0] : 0);
            const blockName = isSelected ? '★ SELECCIONADOS' : (q.x_bloque || 'Sin Bloque').trim();
            
            if (!groups[blockName]) {
                groups[blockName] = { 
                    name: blockName, 
                    items: [], 
                    totalArea: 0,
                    isSelectedGroup: isSelected
                };
            }
            groups[blockName].items.push(q);
            groups[blockName].totalArea += q.quantity;
        }
        
        // Ordenar grupos: seleccionados primero
        return Object.values(groups).sort((a, b) => {
            if (a.isSelectedGroup && !b.isSelectedGroup) return -1;
            if (!a.isSelectedGroup && b.isSelectedGroup) return 1;
            return a.name.localeCompare(b.name);
        });
    }

    get selectedCount() {
        return this.state.selectedLotIds.size;
    }

    get selectedTotalArea() {
        let total = 0;
        for (const q of this.state.quants) {
            if (q.lot_id && this.state.selectedLotIds.has(q.lot_id[0])) {
                total += q.quantity;
            }
        }
        return total.toFixed(2);
    }

    isLotSelected(lotId) {
        return this.state.selectedLotIds.has(lotId);
    }

    async toggleLot(quant) {
        if (!quant.lot_id) return;
        
        const lotId = quant.lot_id[0];
        const field = this.props.record.fields.move_line_ids;
        const list = this.props.record.data.move_line_ids;
        
        if (this.state.selectedLotIds.has(lotId)) {
            // DESELECCIONAR: Buscar y eliminar la línea
            const lineToRemove = list.records.find(
                line => line.data.lot_id && line.data.lot_id[0] === lotId
            );
            
            if (lineToRemove) {
                // Odoo 19: usar delete en el command list
                const currentIds = list.records
                    .filter(r => r.data.lot_id && r.data.lot_id[0] !== lotId)
                    .map(r => r.resId)
                    .filter(id => id);
                
                // Actualizar con comando de reemplazo
                await this.props.record.update({
                    move_line_ids: [[5, 0, 0], ...currentIds.map(id => [4, id, 0])]
                });
            }
            
            this.state.selectedLotIds.delete(lotId);
        } else {
            // SELECCIONAR: Crear nueva línea
            const recordData = this.props.record.data;
            
            // Comando para crear nueva línea (0, 0, values)
            const newLineVals = {
                lot_id: lotId,
                quantity: quant.quantity,
                location_id: quant.location_id ? quant.location_id[0] : (recordData.location_id ? recordData.location_id[0] : false),
                location_dest_id: recordData.location_dest_id ? recordData.location_dest_id[0] : false,
            };
            
            await this.props.record.update({
                move_line_ids: [[0, 0, newLineVals]]
            });
            
            this.state.selectedLotIds.add(lotId);
        }
        
        // Recargar para refrescar grupos
        await this.loadInventory();
    }

    onFilterChange(key, value) {
        this.state.filters[key] = value;
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => this.loadInventory(), 400);
    }
}

StoneMoveGridField.template = "sale_stone_selection.StoneMoveGridField";
StoneMoveGridField.props = { ...standardFieldProps };

registry.category("fields").add("stone_move_grid", {
    component: StoneMoveGridField,
    displayName: "Stone Grid",
    supportedTypes: ["one2many"],
});