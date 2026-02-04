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
            this._logRecordData();
            await this.loadInventory(); 
        });
        
        onWillUpdateProps(async (nextProps) => {
            console.log("🔷 [STONE GRID] onWillUpdateProps");
            const oldId = this.props.record.data.product_id ? this.props.record.data.product_id[0] : null;
            const newId = nextProps.record.data.product_id ? nextProps.record.data.product_id[0] : null;
            console.log("  oldProductId:", oldId, "newProductId:", newId);
            if (oldId !== newId) {
                await this.loadInventory(nextProps);
            }
        });
    }

    _logRecordData(props = this.props) {
        console.group("📊 [STONE GRID] Record Data");
        
        const record = props.record;
        const data = record.data;
        
        console.log("record.resId:", record.resId);
        console.log("record.resModel:", record.resModel);
        
        // Product
        console.log("product_id:", data.product_id);
        const productId = data.product_id ? data.product_id[0] : null;
        console.log("  -> productId extraído:", productId);
        
        // Location
        console.log("location_id:", data.location_id);
        console.log("location_dest_id:", data.location_dest_id);
        
        // Move lines
        console.log("move_line_ids:", data.move_line_ids);
        if (data.move_line_ids) {
            console.log("  -> records:", data.move_line_ids.records);
            console.log("  -> count:", data.move_line_ids.count);
            if (data.move_line_ids.records) {
                data.move_line_ids.records.forEach((rec, idx) => {
                    console.log(`  -> line[${idx}]:`, {
                        resId: rec.resId,
                        lot_id: rec.data.lot_id,
                        quantity: rec.data.quantity,
                        location_id: rec.data.location_id
                    });
                });
            }
        }
        
        console.groupEnd();
    }

    _getAssignedLotIds(props = this.props) {
        const lines = props.record.data.move_line_ids;
        const ids = [];
        
        console.group("🔍 [STONE GRID] _getAssignedLotIds");
        
        if (lines && lines.records) {
            console.log("lines.records.length:", lines.records.length);
            for (const line of lines.records) {
                const lotData = line.data.lot_id;
                console.log("  line lot_id:", lotData);
                if (lotData && lotData[0]) {
                    ids.push(lotData[0]);
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
        
        console.log("🔍 [STONE GRID] _getAssignedLotsData:", lotsData);
        return lotsData;
    }

    async loadInventory(props = this.props) {
        console.group("🚀 [STONE GRID] loadInventory");
        
        const recordData = props.record.data;
        const productId = recordData.product_id ? recordData.product_id[0] : false;
        
        console.log("productId:", productId);
        console.log("location_id:", recordData.location_id);
        
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
            
            if (quants && quants.length > 0) {
                console.log("  Primer quant:", quants[0]);
            }
            
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

            // Agregar lotes asignados que no están en quants
            for (const assigned of assignedLotsData) {
                const lotId = assigned.lot_id[0];
                if (!quantsMap.has(lotId)) {
                    console.log("📥 Lote asignado no está en quants, buscando datos:", lotId);
                    try {
                        const lotData = await this.orm.read('stock.lot', [lotId], [
                            'name', 'x_bloque', 'x_atado', 'x_alto', 'x_ancho', 
                            'x_grosor', 'x_tipo', 'x_color', 'x_origen', 
                            'x_pedimento', 'x_detalles_placa'
                        ]);
                        console.log("  Datos del lote:", lotData);
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
        console.log("quant:", quant);
        
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
                let lineIndex = -1;
                if (lines && lines.records) {
                    lineIndex = lines.records.findIndex(
                        line => line.data.lot_id && line.data.lot_id[0] === lotId
                    );
                }
                console.log("lineIndex encontrado:", lineIndex);
                
                if (lineIndex >= 0) {
                    const lineRecord = lines.records[lineIndex];
                    console.log("lineRecord:", lineRecord);
                    if (lineRecord.resId) {
                        console.log("Eliminando con comando [2, resId]");
                        await this.props.record.update({
                            move_line_ids: [[2, lineRecord.resId, 0]]
                        });
                    } else {
                        console.log("Línea nueva, usando comando [3, index]");
                        await this.props.record.update({
                            move_line_ids: [[3, lineIndex, 0]]
                        });
                    }
                }
            } else {
                console.log("➕ Seleccionando...");
                const newLineVals = {
                    lot_id: lotId,
                    quantity: quant.quantity || 0,
                    location_id: quant.location_id ? quant.location_id[0] : (recordData.location_id ? recordData.location_id[0] : false),
                    location_dest_id: recordData.location_dest_id ? recordData.location_dest_id[0] : false,
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
        console.log("🔍 [STONE GRID] onFilterChange:", key, "=", value);
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