/** @odoo-module */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";
import { StoneGrid } from "../stone_grid/stone_grid";

// --- Botón ---
export class StoneExpandButton extends Component {
    static template = "sale_stone_selection.ExpandButton";
    static props = { ...standardFieldProps };

    toggle(ev) {
        ev.stopPropagation(); 
        const current = this.props.record.data.is_stone_expanded;
        // Actualizamos el registro. Esto dispara el onchange y luego el re-render
        this.props.record.update({ is_stone_expanded: !current });
    }
}
registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Stone Expand Button",
});

// --- Renderer ---
export class StoneOrderLineRenderer extends ListRenderer {
    setup() {
        super.setup();
    }

    /**
     * Calcula columnas de forma segura.
     * Si this.state.columns falla, devuelve 20 para asegurar que ocupe todo el ancho.
     */
    getColspanSafe() {
        const colCount = this.state.columns ? this.state.columns.length : 15;
        // +1 por selectores, +1 por botón de borrado, +2 extra por seguridad
        return colCount + 4;
    }

    updateLotSelection(row, ids) {
        row.record.update({ lot_ids: [[6, 0, ids]] });
    }
}
StoneOrderLineRenderer.components = { ...ListRenderer.components, StoneGrid };
StoneOrderLineRenderer.template = "sale_stone_selection.ListRenderer";

// --- Vista ---
export const stoneOrderLineListView = {
    ...listView,
    Renderer: StoneOrderLineRenderer,
};
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);