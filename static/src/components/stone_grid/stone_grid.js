/** @odoo-module */
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/core/utils/numbers";

export class StoneGrid extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            isLoading: true,
            details: [],
            selectedLotIds: new Set(this.props.selectedLotIds || []),
        });

        onWillStart(async () => {
            await this.loadStock();
        });

        onWillUpdateProps((nextProps) => {
            // Sincronizar selección si cambia desde el padre (ej. guardado del server)
            this.state.selectedLotIds = new Set(nextProps.selectedLotIds || []);
        });
    }

    async loadStock() {
        this.state.isLoading = true;
        try {
            // Buscar Quants Disponibles (Stock Interno)
            const domain = [
                ['product_id', '=', this.props.productId],
                ['location_id.usage', '=', 'internal'],
                ['quantity', '>', 0]
            ];

            // Solicitamos campos estándar y personalizados (x_)
            // Nota: Si los campos x_ no existen en la BD, Odoo los ignorará o devolverá false,
            // pero idealmente deben existir en el módulo stock_lot_dimensions o similar.
            const fields = [
                'lot_id', 'location_id', 'quantity', 'reserved_quantity',
                'x_grosor', 'x_alto', 'x_ancho', 'x_bloque', 'x_tipo',
                'x_color', 'x_pedimento'
            ];

            // Verificar existencia de campos antes de pedir para evitar crash si no están instalados
            // Para este script asumimos que existen o manejamos fallos silenciosamente en la vista.
            const quants = await this.orm.searchRead('stock.quant', domain, fields);

            this.state.details = quants.map(q => ({
                id: q.id,
                lot_id: q.lot_id ? q.lot_id[0] : false,
                lot_name: q.lot_id ? q.lot_id[1] : 'Sin Lote',
                location_name: q.location_id ? q.location_id[1] : '',
                quantity: q.quantity,
                // Manejo seguro de campos x_
                bloque: q.x_bloque || 'Sin Bloque',
                tipo: q.x_tipo || 'Placa',
                alto: q.x_alto || 0,
                ancho: q.x_ancho || 0,
                grosor: q.x_grosor || 0,
                color: q.x_color || '',
                pedimento: q.x_pedimento || ''
            }));

        } catch (e) {
            console.error("Error cargando stock de piedra:", e);
        } finally {
            this.state.isLoading = false;
        }
    }

    /**
     * Agrupa los quants por 'Bloque' para visualización
     */
    get groupedDetails() {
        const groups = {};
        for (const detail of this.state.details) {
            const blockName = detail.bloque;
            if (!groups[blockName]) {
                groups[blockName] = { 
                    blockName, 
                    items: [], 
                    totalArea: 0, 
                    count: 0 
                };
            }
            groups[blockName].items.push(detail);
            groups[blockName].count++;
            groups[blockName].totalArea += detail.quantity;
        }
        // Ordenar: Bloques con más piezas primero
        return Object.values(groups).sort((a, b) => b.count - a.count);
    }

    toggleSelection(detail) {
        if (!detail.lot_id) return;

        const newSet = new Set(this.state.selectedLotIds);
        if (newSet.has(detail.lot_id)) {
            newSet.delete(detail.lot_id);
        } else {
            newSet.add(detail.lot_id);
        }
        
        this.state.selectedLotIds = newSet;
        // Notificar al padre (OrderLine)
        this.props.onUpdateSelection(Array.from(newSet));
    }

    isSelected(detail) {
        return this.state.selectedLotIds.has(detail.lot_id);
    }

    formatNum(num) {
        return num ? num.toFixed(2) : '0.00';
    }
}

StoneGrid.template = "sale_stone_selection.StoneGrid";
StoneGrid.props = {
    productId: Number,
    selectedLotIds: { type: Array, optional: true },
    onUpdateSelection: Function,
};
