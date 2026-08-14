/** @odoo-module */
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

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
            this.state.selectedLotIds = new Set(nextProps.selectedLotIds || []);
        });
    }

    async loadStock() {
        this.state.isLoading = true;
        try {
            const domain = [
                ['product_id', '=', this.props.productId],
                ['location_id.usage', '=', 'internal'],
                ['quantity', '>', 0]
            ];

            const fields = [
                'lot_id', 'location_id', 'quantity', 'reserved_quantity',
                'x_grosor', 'x_alto', 'x_ancho', 'x_bloque', 'x_tipo',
                'x_color', 'x_pedimento'
            ];

            const quants = await this.orm.searchRead('stock.quant', domain, fields);

            this.state.details = quants.map(q => ({
                id: q.id,
                lot_id: q.lot_id ? q.lot_id[0] : false,
                lot_name: q.lot_id ? q.lot_id[1] : 'Sin Lote',
                // Recortada: último padre / último hijo, no la ruta completa.
                location_name: q.location_id
                    ? q.location_id[1].split('/').filter(Boolean).slice(-2).join('/')
                    : '',
                quantity: q.quantity,
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

    // Recencia del bloque (misma regla del Inventario Visual): serie
    // S<edad> = lo más reciente (número mayor = más nuevo); folios
    // numéricos después (mayor = más nuevo); sin folio al final.
    _blockRecency(name) {
        const s = String(name || "").trim().toUpperCase();
        const m = s.match(/^S\s*-?(\d+)/);
        if (m) {
            return [2, parseInt(m[1], 10)];
        }
        const n = parseInt(s, 10);
        if (!isNaN(n)) {
            return [1, n];
        }
        return [0, 0];
    }

    get groupedDetails() {
        const groups = {};
        for (const detail of this.state.details) {
            const blockName = detail.bloque;
            if (!groups[blockName]) {
                groups[blockName] = { blockName, items: [], totalArea: 0, count: 0 };
            }
            groups[blockName].items.push(detail);
            groups[blockName].count++;
            groups[blockName].totalArea += detail.quantity;
        }
        const out = Object.values(groups);
        // Placas dentro del bloque: orden natural ascendente (S26-01,
        // S26-02, ... S26-10 — no el orden de llegada del search).
        for (const g of out) {
            g.items.sort((a, b) => String(a.lot_name).localeCompare(
                String(b.lot_name), "es", { numeric: true }));
        }
        // Bloques: del MÁS NUEVO al más viejo, como el Inventario Visual.
        return out.sort((a, b) => {
            const ka = this._blockRecency(a.blockName);
            const kb = this._blockRecency(b.blockName);
            return (kb[0] - ka[0]) || (kb[1] - ka[1])
                || String(a.blockName).localeCompare(String(b.blockName));
        });
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