/** @odoo-module */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
// ELIMINAR ESTA LÍNEA QUE CAUSA EL ERROR:
// import { ListRow } from "@web/views/list/list_row"; 
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";
import { StoneGrid } from "../stone_grid/stone_grid";

// SOLUCIÓN: Obtenemos la clase base directamente del Renderer padre.
// Esto funciona en Odoo 17/18/19 independientemente de dónde esté el archivo físico.
const BaseListRow = ListRenderer.components.ListRow;

export class StoneOrderLineRow extends BaseListRow {
    /**
     * Alterna la visibilidad del panel de piedra
     */
    toggleStoneDetails() {
        const current = this.props.record.data.is_stone_expanded;
        this.props.record.update({ is_stone_expanded: !current });
    }
}
StoneOrderLineRow.template = "sale_stone_selection.ListRow";
StoneOrderLineRow.components = { ...BaseListRow.components, StoneGrid };

export class StoneOrderLineRenderer extends ListRenderer {
    setup() {
        super.setup();
    }

    getColspan(row) {
        // Calculamos columnas dinámicamente + selectores
        return this.state.columns.length + (this.props.hasSelectors ? 1 : 0) + 1;
    }

    updateLotSelection(row, ids) {
        row.record.update({ lot_ids: [[6, 0, ids]] });
    }
}
StoneOrderLineRenderer.components = { ...ListRenderer.components, ListRow: StoneOrderLineRow, StoneGrid };
StoneOrderLineRenderer.template = "sale_stone_selection.ListRenderer";

export class StoneOrderLineField extends X2ManyField {}
StoneOrderLineField.components = { ...X2ManyField.components, ListRenderer: StoneOrderLineRenderer };

registry.category("fields").add("stone_order_line_list", StoneOrderLineField);