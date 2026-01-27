/** @odoo-module */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";
import { StoneGrid } from "../stone_grid/stone_grid";

// --- Botón Expandir ---
export class StoneExpandButton extends Component {
    static template = "sale_stone_selection.ExpandButton";
    static props = { ...standardFieldProps };

    toggle(ev) {
        // Detenemos propagación para que no se abra la línea de edición
        ev.stopPropagation(); 
        const current = this.props.record.data.is_stone_expanded;
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
     * Devuelve el colspan de forma segura incluso si columns es undefined
     */
    getColspanSafe() {
        // Si this.state.columns existe usamos su largo, si no, un valor alto por defecto
        const colCount = this.state.columns ? this.state.columns.length : 15;
        // +1 por selectores (checkboxes), +1 por trash icon, +2 extra por seguridad
        return colCount + 4;
    }

    updateLotSelection(row, ids) {
        // [6, 0, [ids]] es el comando ORM para reemplazar Many2many
        row.record.update({ lot_ids: [[6, 0, ids]] });
    }
}
// Registramos componentes (Importante: NO registrar ListRow aquí, se hereda del padre)
StoneOrderLineRenderer.components = { 
    ...ListRenderer.components, 
    StoneGrid 
};
StoneOrderLineRenderer.template = "sale_stone_selection.ListRenderer";

// --- Vista (View Config) ---
export const stoneOrderLineListView = {
    ...listView, // Heredamos toda la lógica estándar de la lista
    Renderer: StoneOrderLineRenderer,
};

// Registramos en VISTAS
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);