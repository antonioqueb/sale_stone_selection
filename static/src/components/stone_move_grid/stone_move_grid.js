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
            assignedLots: [],
            filters: { lot_name: '', bloque: '', atado: '' },
            error: null
        });
        this.searchTimeout = null;

        onWillStart(async () => { 
            await this.loadInventory(); 
        });
        
        onWillUpdateProps(async (nextProps) => {
            const oldId = this._extractId(this.props.record.data.product_id);
            const newId = this._extractId(nextProps.record.data.product_id);
            if (oldId !== newId) {
                await this.loadInventory(nextProps);
            }
        });
    }

    _extractId(field) {
        if (!field) return null;
        if (typeof field === 'number') return field;
        if (Array.isArray(field)) return field[0];
        if (typeof field === 'object' && field.id) return field.id;
        if (typeof field === 'object' && field[0]) return field[0];
        return null;
    }

    _extractIdName(field) {
        if (!field) return null;
        if (Array.isArray(field)) return field;
        if (typeof field === 'object' && field.id) {
            return [field.id, field.display_name || field.name || ''];
        }
        return null;
    }

    _getAssignedLotIds(props = this.props) {
        const lines = props.record.data.move_line_ids;
        const ids = [];
        
        if (lines && lines.records) {
            for (const line of lines.records) {
                const lotId = this._extractId(line.data.lot_id);
                if (lotId) {
                    ids.push(lotId);
                }
            }
        }
        return ids;
    }

    _getAssignedLotsData(props = this.props) {
        const lines = props.record.data.move_line_ids;
        const lotsData = [];
        
        if (lines && lines.records) {
            for (const line of lines.records) {
                const lotIdName = this._extractIdName(line.data.lot_id);
                const locIdName = this._extractIdName(line.data.location_id);
                
                if (lotIdName && lotIdName[0]) {
                    lotsData.push({
                        id: `assigned_${lotIdName[0]}`,
                        lot_id: lotIdName,
                        quantity: line.data.quantity || 0,
                        reserved_quantity: line.data.quantity || 0,
                        location_id: locIdName || false,
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
                        _isAssigned: true
                    });
                }
            }
        }
        return lotsData;
    }

    async loadInventory(props = null) {
        // Si no se pasa props, usar this.props
        const currentProps = props || this.props;
        
        if (!currentProps || !currentProps.record || !currentProps.record.data) {
            console.warn("No hay props/record disponible");
            this.state.isLoading = false;
            return;
        }
        
        const recordData = currentProps.record.data;
        const productId = this._extractId(recordData.product_id);
        
        this.state.isLoading = true;
        this.state.error = null;

        if (!productId) {
            this.state.quants = [];
            this.state.assignedLots = [];
            this.state.isLoading = false;
            return;
        }

        const assignedLotIds = this._getAssignedLotIds(currentProps);
        const assignedLotsData = this._getAssignedLotsData(currentProps);

        try {
            const quants = await this.orm.call('stock.quant', 'search_stone_inventory_for_so', [], {
                product_id: productId,
                filters: this.state.filters,
                current_lot_ids: assignedLotIds
            });
            
            const quantsMap = new Map();
            for (const q of (quants || [])) {
                if (q.lot_id) {
                    quantsMap.set(q.lot_id[0], q);
                }
            }

            const enrichedQuants = (quants || []).map(q => ({
                ...q,
                _isAssigned: q.lot_id ? assignedLotIds.includes(q.lot_id[0]) : false
            }));

            for (const assigned of assignedLotsData) {
                const lotId = assigned.lot_id[0];
                if (!quantsMap.has(lotId)) {
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
                        enrichedQuants.unshift(assigned);
                    }
                }
            }
            
            this.state.quants = enrichedQuants;
            this.state.assignedLots = assignedLotIds;
            
        } catch (e) {
            console.error("Error en loadInventory:", e);
            this.state.error = e.message || "Error cargando datos";
            this.state.quants = assignedLotsData;
            this.state.assignedLots = assignedLotIds;
        } finally {
            this.state.isLoading = false;
        }
    }

    get allItems() {
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
                // DESELECCIONAR
                if (lines && lines.records) {
                    const lineRecord = lines.records.find(
                        line => this._extractId(line.data.lot_id) === lotId
                    );
                    
                    if (lineRecord && lineRecord.resId) {
                        await this.props.record.update({
                            move_line_ids: [[2, lineRecord.resId, 0]]
                        });
                    }
                }
            } else {
                // SELECCIONAR
                const locationId = this._extractId(recordData.location_id);
                const locationDestId = this._extractId(recordData.location_dest_id);
                
                const newLineVals = {
                    lot_id: lotId,
                    quantity: quant.quantity || 0,
                    location_id: quant.location_id ? quant.location_id[0] : locationId,
                    location_dest_id: locationDestId,
                };
                
                await this.props.record.update({
                    move_line_ids: [[0, 0, newLineVals]]
                });
            }
            
            // Recargar
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
    
    onRefresh() {
        this.loadInventory();
    }
}

StoneMoveGridField.template = "sale_stone_selection.StoneMoveGridField";
StoneMoveGridField.props = { ...standardFieldProps };

registry.category("fields").add("stone_move_grid", {
    component: StoneMoveGridField,
    displayName: "Stone Grid",
    supportedTypes: ["one2many"],
});