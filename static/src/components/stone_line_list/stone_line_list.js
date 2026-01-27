/** @odoo-module */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";
import { StoneGrid } from "../stone_grid/stone_grid";

// 1. Componente del Botón (Field Widget)
export class StoneExpandButton extends Component {
    static template = "sale_stone_selection.ExpandButton";
    static props = { ...standardFieldProps };

    toggle(ev) {
        ev.stopPropagation(); // Evitar que Odoo abra la línea para editar
        const current = this.props.record.data.is_stone_expanded;
        this.props.record.update({ is_stone_expanded: !current });
    }
}

// Registramos el widget para usarlo en el XML
export const stoneExpandButton = {
    component: StoneExpandButton,
    displayName: "Stone Expand Button",
};
registry.category("fields").add("stone_expand_button", stoneExpandButton);


// 2. Extendemos el Renderer solo para inyectar el Grid
export class StoneOrderLineRenderer extends ListRenderer {
    setup() {
        super.setup();
    }

    getColspan(row) {
        // columns + selectores + botón borrado
        return this.state.columns.length + (this.props.hasSelectors ? 1 : 0) + 1;
    }

    updateLotSelection(row, ids) {
        row.record.update({ lot_ids: [[6, 0, ids]] });
    }
}
// Solo añadimos StoneGrid, usamos el ListRow estándar de Odoo
StoneOrderLineRenderer.components = { 
    ...ListRenderer.components, 
    StoneGrid 
};
StoneOrderLineRenderer.template = "sale_stone_selection.ListRenderer";


// 3. Registramos el Field Widget de la Lista (X2Many)
export class StoneOrderLineField extends X2ManyField {}
StoneOrderLineField.components = { 
    ...X2ManyField.components, 
    ListRenderer: StoneOrderLineRenderer 
};

registry.category("fields").add("stone_order_line_list", StoneOrderLineField);