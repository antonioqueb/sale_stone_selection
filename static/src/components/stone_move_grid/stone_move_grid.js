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
            console.log("═══════════════════════════════════════════════════════");
            console.log("🔷 [STONE GRID] onWillStart");
            await this.loadInventory(); 
        });
        
        onWillUpdateProps(async (nextProps) => {
            console.log("🔷 [STONE GRID] onWillUpdateProps");
            const oldId = this._extractId(this.props.record.data.product_id);
            const newId = this._extractId(nextProps.record.data.product_id);
            console.log("  oldProductId:", oldId, "newProductId:", newId);
            if (oldId !== newId) {
                await this.loadInventory(nextProps);
            }
        });
    }

    /**
     * Extrae ID de un campo Many2one (puede ser array, objeto o número)
     */
    _extractId(field) {
        if (!field) return null;
        // Caso 1: Es un número directo
        if (typeof field === 'number') return field;
        // Caso 2: Es un array [id, name]
        if (Array.isArray(field)) return field[0];
        // Caso 3: Es un objeto con .id (Odoo 19 Proxy)
        if (typeof field === 'object' && field.id) return field.id;
        // Caso 4: Es un objeto con [0]
        if (typeof field === 'object' && field[0]) return field[0];
        return null;
    }

    /**
     * Extrae [id, name] de un campo Many2one
     */
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
        
        console.group("🔍 [STONE GRID] _getAssignedLotIds");
        
        if (lines && lines.records) {
            console.log("lines.records.length:", lines.records.length);
            for (const line of lines.records) {
                const lotId = this._extractId(line.data.lot_id);
                console.log("  line lot_id:", line.data.lot_id, "-> extracted:", lotId);
                if (lotId) {
                    ids.push(lotId);
                }
            }
        } else {
            console.log("No hay lines.records");
        }
        
        console.log("IDs extraídos:", ids);
        console.groupEnd();
        
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
                        _isAssigned: true,
                        _needsEnrichment: true
                    });
                }
            }
        }
        
        console.log("🔍 [STONE GRID] _getAssignedLotsData:", lotsData.length, "lotes");
        return lotsData;
    }

    async loadInventory(props = this.props) {
        console.group("🚀 [STONE GRID] loadInventory");
        
        const recordData = props.record.data;
        const productId = this._extractId(recordData.product_id);
        const locationId = this._extractId(recordData.location_id);
        
        console.log("productId:", productId);
        console.log("locationId:", locationId);
        
        this.state.isLoading = true;
        this.state.error = null;

        if (!productId) {
            console.warn("⚠️ No hay productId, abortando");
            this.state.quants = [];
            this.state.assignedLots = [];
            this.state.isLoading = false;
            console.groupEnd();
            return;
        }

        const assignedLotIds = this._getAssignedLotIds(props);
        const assignedLotsData = this._getAssignedLotsData(props);

        try {
            console.log("📡 Llamando a search_stone_inventory_for_so...");
            console.log("  product_id:", productId);
            console.log("  filters:", this.state.filters);
            console.log("  current_lot_ids:", assignedLotIds);
            
            const quants = await this.orm.call('stock.quant', 'search_stone_inventory_for_so', [], {
                product_id: productId,
                filters: this.state.filters,
                current_lot_ids: assignedLotIds
            });
            
            console.log("✅ Respuesta del servidor:", quants);
            console.log("  Cantidad de quants:", quants ? quants.length : 0);
            
            // Crear mapa de quants por lot_id
            const quantsMap = new Map();
            for (const q of (quants || [])) {
                if (q.lot_id) {
                    quantsMap.set(q.lot_id[0], q);
                }
            }
            console.log("  quantsMap size:", quantsMap.size);

            // Marcar quants asignados
            const enrichedQuants = (quants || []).map(q => ({
                ...q,
                _isAssigned: q.lot_id ? assignedLotIds.includes(q.lot_id[0]) : false
            }));

            // Agregar lotes asignados que no están en quants (ya reservados completamente)
            for (const assigned of assignedLotsData) {
                const lotId = assigned.lot_id[0];
                if (!quantsMap.has(lotId)) {
                    console.log("📥 Lote asignado no en quants, buscando datos:", lotId);
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
                        console.warn("⚠️ Error obteniendo datos del lote:", lotId, e);
                        enrichedQuants.unshift(assigned);
                    }
                }
            }
            
            console.log("📦 enrichedQuants final:", enrichedQuants.length);
            this.state.quants = enrichedQuants;
            this.state.assignedLots = assignedLotIds;
            
        } catch (e) {
            console.error("❌ Error en loadInventory:", e);
            this.state.error = e.message || "Error desconocido";
            this.state.quants = assignedLotsData;
            this.state.assignedLots = assignedLotIds;
        } finally {
            this.state.isLoading = false;
            console.groupEnd();
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
        console.group("🔄 [STONE GRID] toggleLot");
        
        if (!quant.lot_id) {
            console.warn("No hay lot_id");
            console.groupEnd();
            return;
        }
        
        const lotId = quant.lot_id[0];
        const isCurrentlySelected = this.isLotSelected(lotId);
        console.log("lotId:", lotId, "isCurrentlySelected:", isCurrentlySelected);
        
        const recordData = this.props.record.data;
        const lines = recordData.move_line_ids;
        
        try {
            if (isCurrentlySelected) {
                console.log("➖ Deseleccionando...");
                if (lines && lines.records) {
                    const lineRecord = lines.records.find(
                        line => this._extractId(line.data.lot_id) === lotId
                    );
                    
                    if (lineRecord && lineRecord.resId) {
                        console.log("Eliminando línea resId:", lineRecord.resId);
                        await this.props.record.update({
                            move_line_ids: [[2, lineRecord.resId, 0]]
                        });
                    }
                }
            } else {
                console.log("➕ Seleccionando...");
                const locationId = this._extractId(recordData.location_id);
                const locationDestId = this._extractId(recordData.location_dest_id);
                
                const newLineVals = {
                    lot_id: lotId,
                    quantity: quant.quantity || 0,
                    location_id: quant.location_id ? quant.location_id[0] : locationId,
                    location_dest_id: locationDestId,
                };
                console.log("newLineVals:", newLineVals);
                
                await this.props.record.update({
                    move_line_ids: [[0, 0, newLineVals]]
                });
            }
            
            console.log("✅ Update completado, recargando...");
            await this.loadInventory();
        } catch (e) {
            console.error("❌ Error en toggleLot:", e);
        }
        
        console.groupEnd();
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