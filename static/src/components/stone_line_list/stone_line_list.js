/** @odoo-module */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { ListRow } from "@web/views/list/list_row";
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";
import { StoneGrid } from "../stone_grid/stone_grid";
import { Component, useState } from "@odoo/owl";

// 1. Extendemos la Fila (Row) para funcionalidad
export class StoneOrderLineRow extends ListRow {
    // No necesitamos lógica compleja aquí ya que el toggle 
    // lo manejamos directamente modificando el registro en el XML
}
StoneOrderLineRow.template = "sale_stone_selection.ListRow";
StoneOrderLineRow.components = { ...ListRow.components, StoneGrid };

// 2. Extendemos el Renderer para inyectar la fila extra
export class StoneOrderLineRenderer extends ListRenderer {
    setup() {
        super.setup();
    }
}
StoneOrderLineRenderer.components = { ...ListRenderer.components, ListRow: StoneOrderLineRow, StoneGrid };
StoneOrderLineRenderer.template = "sale_stone_selection.ListRenderer";

// 3. Registramos el Field Widget
export class StoneOrderLineField extends X2ManyField {}
StoneOrderLineField.components = { ...X2ManyField.components, ListRenderer: StoneOrderLineRenderer };

registry.category("fields").add("stone_order_line_list", StoneOrderLineField);
