/** @odoo-module */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, xml, onWillUnmount, useState } from "@odoo/owl";
import { mount } from "@odoo/owl"; // Importante para montar componentes manualmente
import { StoneGrid } from "../stone_grid/stone_grid";
import { useService } from "@web/core/utils/hooks";

// --- Botón de Inyección Manual (Pure JS Style) ---
export class StoneExpandButton extends Component {
    static template = xml`
        <div class="o_stone_toggle_btn cursor-pointer text-center" 
             t-on-click.stop="toggle"
             style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;">
            <i class="fa fa-chevron-right" 
               t-att-class="{'o_rotated': state.expanded}"
               style="transition: transform 0.2s ease;"/>
        </div>
    `;
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({ expanded: false });
        this.mountedApp = null; // Guardamos la referencia a la app montada
        this.detailsRow = null; // Guardamos referencia al TR creado

        onWillUnmount(() => {
            this.cleanup();
        });
    }

    async toggle(ev) {
        // 1. Alternar estado visual del icono
        this.state.expanded = !this.state.expanded;

        // 2. Lógica de DOM Manual
        if (this.state.expanded) {
            await this.injectGrid(ev.target);
        } else {
            this.cleanup();
        }
    }

    async injectGrid(target) {
        // A. Encontrar la fila actual (TR) usando JS puro
        // this.el es el div del botón. Subimos hasta encontrar el TR.
        const currentRow = this.el.closest('tr');
        if (!currentRow) return;

        // B. Crear la nueva fila contenedora
        const tr = document.createElement('tr');
        tr.className = 'o_stone_details_row_tr';
        
        // Calculamos colspan contando las celdas de la fila actual para que cuadre perfecto
        const colCount = currentRow.querySelectorAll('td').length;
        
        const td = document.createElement('td');
        td.colSpan = colCount;
        td.style.padding = '0';
        td.style.border = '0';
        
        const divContainer = document.createElement('div');
        divContainer.className = 'o_stone_slide_down';
        
        td.appendChild(divContainer);
        tr.appendChild(td);

        // C. Inyectar en el DOM (Justo después de la fila actual)
        currentRow.after(tr);
        this.detailsRow = tr;

        // D. Montar el componente Owl (StoneGrid) dentro de nuestro div creado manualmente
        // Esto arranca el ciclo de vida de StoneGrid (loadStock, etc) independientemente de la lista
        const env = this.env;
        const productId = this.props.record.data.product_id ? this.props.record.data.product_id[0] : false;
        const currentLotIds = this.props.record.data.lot_ids.currentIds;

        if (productId) {
            // Creamos una "mini aplicación" Owl solo para este div
            this.mountedApp = await mount(StoneGrid, divContainer, {
                env: env, // Heredamos el entorno (ORM, servicios)
                props: {
                    productId: productId,
                    selectedLotIds: currentLotIds,
                    onUpdateSelection: (ids) => {
                        // Aquí sí llamamos al update del registro para guardar
                        this.props.record.update({ lot_ids: [[6, 0, ids]] });
                    }
                }
            });
        }
    }

    cleanup() {
        // Desmontar componente Owl para liberar memoria
        if (this.mountedApp) {
            this.mountedApp.destroy();
            this.mountedApp = null;
        }
        // Eliminar HTML del DOM
        if (this.detailsRow) {
            this.detailsRow.remove();
            this.detailsRow = null;
        }
    }
}

registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Stone Expand Button (Manual Injection)",
});

// --- Configuración de Vista (Mínima) ---
// Ya no necesitamos sobreescribir el Renderer ni ListRow porque lo hacemos manualmente.
// Solo necesitamos registrar la vista para que no de error la js_class.

export const stoneOrderLineListView = {
    ...listView,
};

registry.category("views").add("stone_order_line_list", stoneOrderLineListView);