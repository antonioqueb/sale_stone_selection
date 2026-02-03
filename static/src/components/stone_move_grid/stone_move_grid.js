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
            filters: { lot_name: '', bloque: '', atado: '' }
        });
        this.searchTimeout = null;

        onWillStart(async () => { await this.loadInventory(); });

        onWillUpdateProps(async (nextProps) => {
            const oldId = this.props.record.data.product_id ? this.props.record.data.product_id[0] : null;
            const newId = nextProps.record.data.product_id ? nextProps.record.data.product_id[0] : null;
            if (oldId !== newId) await this.loadInventory(nextProps);
        });
    }

    async loadInventory(props = this.props) {
        const recordData = props.record.data;
        const productId = recordData.product_id ? recordData.product_id[0] : false;
        
        this.state.isLoading = true;

        // 1. Recopilar Lotes que YA están en el movimiento (Move Lines)
        // Esto garantiza que veamos los lotes asignados por la venta
        const currentLines = recordData.move_line_ids.records || [];
        const currentLotIds = [];
        const virtualQuants = [];

        currentLines.forEach(line => {
            const lotData = line.data.lot_id;
            if (lotData) {
                const lotId = lotData[0];
                currentLotIds.push(lotId);
                // Crear un "Quant Virtual" visual para mostrar lo asignado
                virtualQuants.push({
                    id: `virtual_${lotId}`,
                    lot_id: lotData,
                    quantity: line.data.quantity || 0,
                    location_id: line.data.location_id || recordData.location_id,
                    x_bloque: ' ASIGNADO', // Espacio para que salga al inicio
                    x_tipo: 'Placa',
                    is_virtual: true
                });
            }
        });

        if (!productId) {
            this.state.quants = virtualQuants;
            this.state.isLoading = false;
            return;
        }

        try {
            // 2. Buscar stock real, incluyendo los IDs actuales
            const quants = await this.orm.call('stock.quant', 'search_stone_inventory_for_so', [], {
                product_id: productId,
                filters: this.state.filters,
                current_lot_ids: currentLotIds
            });

            // 3. Fusión: Usar datos del server, pero rellenar con virtuales si faltan
            const serverLotIds = new Set(quants.map(q => q.lot_id[0]));
            const missingVirtuals = virtualQuants.filter(vq => !serverLotIds.has(vq.lot_id[0]));
            
            this.state.quants = [...missingVirtuals, ...quants];

        } catch (e) {
            console.error("Error cargando inventario:", e);
            this.state.quants = virtualQuants;
        } finally {
            this.state.isLoading = false;
        }
    }

    get groupedQuants() {
        if (this.state.quants.length === 0) return [];

        const groups = {};
        const sorted = this.state.quants.sort((a, b) => {
            const bla = a.x_bloque || 'zzz';
            const blb = b.x_bloque || 'zzz';
            return bla.localeCompare(blb);
        });

        for (const q of sorted) {
            const blockName = (q.x_bloque || 'General').trim();
            if (!groups[blockName]) {
                groups[blockName] = { name: blockName, items: [], totalArea: 0 };
            }
            groups[blockName].items.push(q);
            groups[blockName].totalArea += q.quantity;
        }
        return Object.values(groups);
    }

    getLineForLot(lotId) {
        const lines = this.props.record.data.move_line_ids.records;
        return lines.find(l => l.data.lot_id && l.data.lot_id[0] === lotId);
    }

    isLotSelected(lotId) {
        return !!this.getLineForLot(lotId);
    }

    async toggleLot(quant) {
        if (!quant.lot_id) return;
        const lotId = quant.lot_id[0];
        const existingLine = this.getLineForLot(lotId);
        const x2many = this.props.record.data.move_line_ids;

        if (existingLine) {
            await x2many.removeRecord(existingLine);
        } else {
            // Agregar reserva manual desde el picking
            await x2many.addNewRecord({
                context: {
                    default_lot_id: lotId,
                    default_quantity: quant.quantity,
                    default_location_id: quant.location_id ? quant.location_id[0] : null
                }
            });
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