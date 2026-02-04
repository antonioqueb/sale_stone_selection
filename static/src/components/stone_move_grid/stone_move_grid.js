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
            assignedLots: [], // Lotes ya asignados en move_line_ids
            filters: { lot_name: '', bloque: '', atado: '' }
        });
        this.searchTimeout = null;

        onWillStart(async () => { 
            await this.loadInventory(); 
        });
        
        onWillUpdateProps(async (nextProps) => {
            const oldId = this.props.record.data.product_id ? this.props.record.data.product_id[0] : null;
            const newId = nextProps.record.data.product_id ? nextProps.record.data.product_id[0] : null;
            if (oldId !== newId) {
                await this.loadInventory(nextProps);
            }
        });
    }

    /**
     * Extrae los lotes asignados desde move_line_ids
     */
    _getAssignedLotIds(props = this.props) {
        const lines = props.record.data.move_line_ids;
        const ids = [];
        
        if (lines && lines.records) {
            for (const line of lines.records) {
                const lotData = line.data.lot_id;
                if (lotData && lotData[0]) {
                    ids.push(lotData[0]);
                }
            }
        }
        return ids;
    }

    /**
     * Extrae información de los lotes asignados para mostrar aunque no estén en quants
     */
    _getAssignedLotsData(props = this.props) {
        const lines = props.record.data.move_line_ids;
        const lotsData = [];
        
        if (lines && lines.records) {
            for (const line of lines.records) {
                const lotData = line.data.lot_id;
                const locData = line.data.location_id;
                if (lotData && lotData[0]) {
                    lotsData.push({
                        id: `assigned_${lotData[0]}`,
                        lot_id: lotData,
                        quantity: line.data.quantity || 0,
                        reserved_quantity: line.data.quantity || 0,
                        location_id: locData || false,
                        x_bloque: '',
                        x_atado: '',
                        x_alto: 0,
                        x_ancho: 0,
                        x_grosor: 0,
                        x_tipo: '',
                        x_color: '',
                        x_origen: '',
                        x_pedimento: '',
                        x_detalles_placa: '',
                        _isAssigned: true,
                        _needsEnrichment: true
                    });
                }
            }
        }
        return lotsData;
    }

    async loadInventory(props = this.props) {
        const recordData = props.record.data;
        const productId = recordData.product_id ? recordData.product_id[0] : false;
        
        this.state.isLoading = true;

        if (!productId) {
            this.state.quants = [];
            this.state.assignedLots = [];
            this.state.isLoading = false;
            return;
        }

        // Obtener lotes ya asignados
        const assignedLotIds = this._getAssignedLotIds(props);
        const assignedLotsData = this._getAssignedLotsData(props);

        try {
            // Llamar al servidor incluyendo los IDs asignados para que los traiga
            const quants = await this.orm.call('stock.quant', 'search_stone_inventory_for_so', [], {
                product_id: productId,
                filters: this.state.filters,
                current_lot_ids: assignedLotIds
            });
            
            // Enriquecer los lotes asignados con datos del servidor si están disponibles
            const quantsMap = new Map();
            for (const q of quants) {
                if (q.lot_id) {
                    quantsMap.set(q.lot_id[0], q);
                }
            }

            // Marcar quants que están asignados
            const enrichedQuants = quants.map(q => ({
                ...q,
                _isAssigned: q.lot_id ? assignedLotIds.includes(q.lot_id[0]) : false
            }));

            // Agregar lotes asignados que no aparecieron en quants (por estar completamente reservados)
            for (const assigned of assignedLotsData) {
                const lotId = assigned.lot_id[0];
                if (!quantsMap.has(lotId)) {
                    // Buscar datos del lote directamente
                    try {
                        const lotData = await this.orm.read('stock.lot', [lotId], [
                            'name', 'x_bloque', 'x_atado', 'x_alto', 'x_ancho', 
                            'x_grosor', 'x_tipo', 'x_color', 'x_origen', 
                            'x_pedimento', 'x_detalles_placa'
                        ]);
                        if (lotData && lotData[0]) {
                            const lot = lotData[0];
                            enrichedQuants.unshift({
                                ...assigned,
                                lot_id: [lotId, lot.name],
                                x_bloque: lot.x_bloque || '',
                                x_atado: lot.x_atado || '',
                                x_alto: lot.x_alto || 0,
                                x_ancho: lot.x_ancho || 0,
                                x_grosor: lot.x_grosor || 0,
                                x_tipo: lot.x_tipo || '',
                                x_color: lot.x_color || '',
                                x_origen: lot.x_origen || '',
                                x_pedimento: lot.x_pedimento || '',
                                x_detalles_placa: lot.x_detalles_placa || '',
                                _isAssigned: true
                            });
                        }
                    } catch (e) {
                        console.warn("No se pudo obtener datos del lote", lotId, e);
                        enrichedQuants.unshift(assigned);
                    }
                }
            }
            
            this.state.quants = enrichedQuants;
            this.state.assignedLots = assignedLotIds;
        } catch (e) {
            console.error("Error cargando inventario:", e);
            this.state.quants = assignedLotsData; // Al menos mostrar los asignados
            this.state.assignedLots = assignedLotIds;
        } finally {
            this.state.isLoading = false;
        }
    }

    get allItems() {
        // Ordenar: asignados primero
        return [...this.state.quants].sort((a, b) => {
            if (a._isAssigned && !b._isAssigned) return -1;
            if (!a._isAssigned && b._isAssigned) return 1;
            const bla = a.x_bloque || 'zzz';
            const blb = b.x_bloque || 'zzz';
            return bla.localeCompare(blb);
        });
    }

    get selectedCount() {
        return this.state.assignedLots.length;
    }

    get selectedTotalArea() {
        let total = 0;
        for (const q of this.state.quants) {
            if (q._isAssigned) {
                total += q.quantity || 0;
            }
        }
        return total.toFixed(2);
    }

    isLotSelected(lotId) {
        return this.state.assignedLots.includes(lotId);
    }

    async toggleLot(quant) {
        if (!quant.lot_id) return;
        
        const lotId = quant.lot_id[0];
        const isCurrentlySelected = this.isLotSelected(lotId);
        const recordData = this.props.record.data;
        const lines = recordData.move_line_ids;
        
        try {
            if (isCurrentlySelected) {
                // DESELECCIONAR: Buscar línea a eliminar
                let lineIndex = -1;
                if (lines && lines.records) {
                    lineIndex = lines.records.findIndex(
                        line => line.data.lot_id && line.data.lot_id[0] === lotId
                    );
                }
                
                if (lineIndex >= 0) {
                    const lineRecord = lines.records[lineIndex];
                    // Usar comando de eliminación
                    if (lineRecord.resId) {
                        await this.props.record.update({
                            move_line_ids: [[2, lineRecord.resId, 0]]
                        });
                    } else {
                        // Línea nueva no guardada - usar comando 3
                        await this.props.record.update({
                            move_line_ids: [[3, lineIndex, 0]]
                        });
                    }
                }
            } else {
                // SELECCIONAR: Crear nueva línea
                const newLineVals = {
                    lot_id: lotId,
                    quantity: quant.quantity || 0,
                    location_id: quant.location_id ? quant.location_id[0] : (recordData.location_id ? recordData.location_id[0] : false),
                    location_dest_id: recordData.location_dest_id ? recordData.location_dest_id[0] : false,
                };
                
                await this.props.record.update({
                    move_line_ids: [[0, 0, newLineVals]]
                });
            }
            
            // Recargar datos
            await this.loadInventory();
        } catch (e) {
            console.error("Error en toggleLot:", e);
        }
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