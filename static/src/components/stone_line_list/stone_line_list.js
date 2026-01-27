/** @odoo-module */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { ListRow } from "@web/views/list/list_row";
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";
import { StoneGrid } from "../stone_grid/stone_grid";

// 1. Extendemos la Fila
export class StoneOrderLineRow extends ListRow {
    /**
     * Alterna la visibilidad del panel de piedra
     */
    toggleStoneDetails() {
        const current = this.props.record.data.is_stone_expanded;
        this.props.record.update({ is_stone_expanded: !current });
    }
}
StoneOrderLineRow.template = "sale_stone_selection.ListRow";
StoneOrderLineRow.components = { ...ListRow.components, StoneGrid };

// 2. Extendemos el Renderer
export class StoneOrderLineRenderer extends ListRenderer {
    setup() {
        super.setup();
    }

    /**
     * Calcula cuántas columnas debe ocupar el panel desplegable
     */
    getColspan(row) {
        // columns.length + selectores + botón borrado opcional
        return this.state.columns.length + (this.props.hasSelectors ? 1 : 0) + 1;
    }

    /**
     * Callback para guardar la selección en el Many2many
     */
    updateLotSelection(row, ids) {
        // Comando [6, 0, [ids]] reemplaza la selección
        row.record.update({ lot_ids: [[6, 0, ids]] });
    }
}
StoneOrderLineRenderer.components = { ...ListRenderer.components, ListRow: StoneOrderLineRow, StoneGrid };
StoneOrderLineRenderer.template = "sale_stone_selection.ListRenderer";

// 3. Registramos el Field Widget
export class StoneOrderLineField extends X2ManyField {}
StoneOrderLineField.components = { ...X2ManyField.components, ListRenderer: StoneOrderLineRenderer };

registry.category("fields").add("stone_order_line_list", StoneOrderLineField);