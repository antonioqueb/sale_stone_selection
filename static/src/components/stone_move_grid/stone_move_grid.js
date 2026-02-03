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
            filters: {
                lot_name: '',
                bloque: '',
                atado: '',
                alto_min: '',
                ancho_min: ''
            }
        });

        this.searchTimeout = null;

        onWillStart(async () => {
            await this.loadInventory();
        });

        onWillUpdateProps(async (nextProps) => {
            // Recargar solo si cambian datos críticos
            const oldId = this.props.record.data.product_id ? this.props.record.data.product_id[0] : null;
            const newId = nextProps.record.data.product_id ? nextProps.record.data.product_id[0] : null;
            
            if (oldId !== newId) {
                await this.loadInventory(nextProps);
            }
        });
    }

    async loadInventory(props = this.props) {
        const recordData = props.record.data;
        const productId = recordData.product_id ? recordData.product_id[0] : false;
        
        if (!productId) {
            this.state.quants = [];
            this.state.isLoading = false;
            return;
        }

        this.state.isLoading = true;

        try {
            // 1. Obtener IDs y DATOS de lo que ya está en move_line_ids
            // Esto es crucial para mostrar las líneas aunque el servidor no devuelva stock disponible
            const currentLines = recordData.move_line_ids.records || [];
            const currentLotIds = [];
            const currentLinesMap = {};

            currentLines.forEach(r => {
                const lotData = r.data.lot_id;
                if (lotData) {
                    const lotId = lotData[0];
                    currentLotIds.push(lotId);
                    // Guardamos datos de respaldo por si el quant no aparece en la búsqueda
                    currentLinesMap[lotId] = {
                        id: `virtual_${lotId}`, // ID falso para la vista
                        lot_id: lotData,
                        quantity: r.data.quantity || 0,
                        location_id: r.data.location_id || recordData.location_id,
                        x_bloque: 'ASIGNADO', // Grupo por defecto si no tenemos datos del quant
                        x_tipo: 'Placa',
                        is_virtual: true // Marca para saber que vino de la línea, no del stock
                    };
                }
            });

            // 2. Buscar en servidor (Pasamos current_lot_ids para intentar forzar su inclusión)
            const quants = await this.orm.call(
                'stock.quant',
                'search_stone_inventory_for_so',
                [],
                {
                    product_id: productId,
                    filters: this.state.filters,
                    current_lot_ids: currentLotIds
                }
            );

            // 3. MERGE (Fusión inteligente)
            // Empezamos con los quants del servidor
            const finalQuants = [...quants];
            const serverLotIds = new Set(quants.map(q => q.lot_id[0]));

            // Agregamos las líneas seleccionadas que NO vinieron del servidor
            // (por ejemplo, si están reservadas totalmente o en una ubicación hija no filtrada)
            for (const lotId of currentLotIds) {
                if (!serverLotIds.has(lotId)) {
                    // Agregamos el "quant virtual" basado en la línea
                    finalQuants.push(currentLinesMap[lotId]);
                }
            }

            this.state.quants = finalQuants;

        } catch (e) {
            console.error("Error cargando inventario:", e);
        } finally {
            this.state.isLoading = false;
        }
    }

    get groupedQuants() {
        const groups = {};
        // Ordenamos para que los 'ASIGNADO' o bloques definidos salgan bien
        const sortedQuants = this.state.quants.sort((a, b) => {
            const blockA = a.x_bloque || 'ZZZ';
            const blockB = b.x_bloque || 'ZZZ';
            return blockA.localeCompare(blockB);
        });

        for (const q of sortedQuants) {
            // Si viene de la línea y no tenemos bloque, le ponemos "ASIGNADOS (Sin info de stock)"
            const blockName = q.x_bloque || 'General';
            
            if (!groups[blockName]) {
                groups[blockName] = { 
                    name: blockName, 
                    items: [], 
                    totalArea: 0, 
                    count: 0 
                };
            }
            groups[blockName].items.push(q);
            groups[blockName].count++;
            groups[blockName].totalArea += q.quantity;
        }
        
        // Ordenar bloques: primero los que tienen más items
        return Object.values(groups).sort((a, b) => b.count - a.count);
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
            // Deseleccionar (Eliminar línea)
            await x2many.removeRecord(existingLine);
        } else {
            // Seleccionar (Crear línea)
            const vals = {
                lot_id: [lotId, quant.lot_id[1]],
                quantity: quant.quantity,
                product_uom_id: this.props.record.data.product_uom,
                location_id: quant.location_id,
                location_dest_id: this.props.record.data.location_dest_id,
            };
            await x2many.addNewRecord({ context: vals });
        }
    }

    // Filtros
    onFilterChange(key, value) {
        this.state.filters[key] = value;
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => this.loadInventory(), 400);
    }
}

StoneMoveGridField.template = "sale_stone_selection.StoneMoveGridField";
StoneMoveGridField.props = {
    ...standardFieldProps,
};

registry.category("fields").add("stone_move_grid", {
    component: StoneMoveGridField,
    displayName: "Stone Selection Grid (Move)",
    supportedTypes: ["one2many"],
});