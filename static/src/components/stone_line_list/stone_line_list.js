/** @odoo-module */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view"; // Importamos la configuración base de la lista
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";
import { StoneGrid } from "../stone_grid/stone_grid";

// =========================================================
// 1. COMPONENTE DEL BOTÓN (WIDGET)
// =========================================================
export class StoneExpandButton extends Component {
    static template = "sale_stone_selection.ExpandButton";
    static props = { ...standardFieldProps };

    toggle(ev) {
        ev.stopPropagation(); 
        const current = this.props.record.data.is_stone_expanded;
        this.props.record.update({ is_stone_expanded: !current });
    }
}

// CORRECCIÓN: Registramos un OBJETO, no la clase directamente
registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Stone Expand Button",
});


// =========================================================
// 2. RENDERER DE LA LISTA (CUSTOM RENDERER)
// =========================================================
export class StoneOrderLineRenderer extends ListRenderer {
    setup() {
        super.setup();
    }

    getColspan(row) {
        return this.state.columns.length + (this.props.hasSelectors ? 1 : 0) + 1;
    }

    updateLotSelection(row, ids) {
        row.record.update({ lot_ids: [[6, 0, ids]] });
    }
}

// Registramos los componentes que usará nuestro Renderer
StoneOrderLineRenderer.components = { 
    ...ListRenderer.components, 
    StoneGrid 
};
StoneOrderLineRenderer.template = "sale_stone_selection.ListRenderer";


// =========================================================
// 3. CONFIGURACIÓN DE LA VISTA (JS_CLASS)
// =========================================================
// Esto es lo que busca Odoo cuando usas js_class="stone_order_line_list"
// Heredamos de 'listView' y solo cambiamos el Renderer.

export const stoneOrderLineListView = {
    ...listView,
    Renderer: StoneOrderLineRenderer,
};

// CORRECCIÓN: Registramos en 'views', no en 'fields'
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);