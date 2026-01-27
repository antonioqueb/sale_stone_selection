## ./__init__.py
```py
# -*- coding: utf-8 -*-
from . import models
```

## ./__manifest__.py
```py
# -*- coding: utf-8 -*-
{
    'name': 'Stone Selection & Visual Sale Grid',
    'version': '17.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Selección visual agrupada de placas (piedra/mármol) en ventas',
    'description': """
        Módulo profesional para la gestión de ventas de piedra natural.
        
        Características:
        - Inyección de componente OWL en líneas de pedido.
        - Selección visual de lotes (placas) agrupadas por Bloque.
        - Cálculo automático de m² basado en selección.
        - Visualización de dimensiones, ubicación y tipo.
        - UX mejorada: Acordeón expandible sin popups intrusivos.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    'depends': ['sale_management', 'stock'],
    'data': [
        'views/sale_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_stone_selection/static/src/scss/stone_styles.scss',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.xml',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.js',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.xml',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'OPL-1',
}
```

## ./models/__init__.py
```py
# -*- coding: utf-8 -*-
from . import sale_order_line
```

## ./models/sale_order_line.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Relación para almacenar los lotes (placas) seleccionados
    lot_ids = fields.Many2many(
        'stock.lot', 
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=False
    )

    # Campo técnico para controlar el estado visual (expandido/colapsado) en la sesión
    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """
        Recalcula la cantidad de la línea basándose en la suma
        de las cantidades disponibles de los lotes seleccionados.
        """
        if not self.lot_ids:
            return

        # Buscamos los quants para obtener la cantidad real disponible en stock interno
        # Esto previene usar cantidades de lotes que ya no existen o están en clientes
        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])
        
        # Agrupar por lote para evitar duplicados si un lote está fragmentado en ubicaciones
        # (Aunque en placas únicas esto es raro, es buena práctica)
        total_qty = sum(quants.mapped('quantity'))
        
        if total_qty > 0:
            self.product_uom_qty = total_qty
            
            # Opcional: Actualizar el precio si depende de características específicas del lote
            # self.price_unit = ... 
```

## ./static/src/components/stone_grid/stone_grid.js
```js
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
```

## ./static/src/components/stone_grid/stone_grid.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="sale_stone_selection.StoneGrid" owl="1">
        <div class="o_stone_selection_panel">
            
            <!-- Loading State -->
            <div t-if="state.isLoading" class="p-4 text-center text-muted">
                <i class="fa fa-circle-o-notch fa-spin me-2"/> Buscando material disponible...
            </div>

            <!-- Empty State -->
            <div t-elif="state.details.length === 0" class="p-3">
                <div class="alert alert-warning mb-0 d-flex align-items-center">
                    <i class="fa fa-exclamation-triangle me-2"/>
                    <span>No se encontró stock disponible en ubicaciones internas para este producto.</span>
                </div>
            </div>

            <!-- Data Grid -->
            <div t-else="" class="stone-grid-wrapper">
                <table class="table table-sm table-hover o_stone_table mb-0">
                    <thead>
                        <tr>
                            <th class="text-center col-check"><i class="fa fa-check-square-o"/></th>
                            <th class="col-lot">Lote</th>
                            <th class="col-loc">Ubicación</th>
                            <th class="col-dims text-end">Dimensiones</th>
                            <th class="col-qty text-end">M²</th>
                            <th class="col-block">Bloque</th>
                            <th class="col-type">Tipo</th>
                            <th class="col-color">Color</th>
                        </tr>
                    </thead>
                    <tbody>
                        <t t-foreach="groupedDetails" t-as="group" t-key="group.blockName">
                            <!-- Header de Grupo (Bloque) -->
                            <tr class="group-header-row">
                                <td colspan="8">
                                    <div class="d-flex justify-content-between align-items-center px-2">
                                        <span class="fw-bold text-primary">
                                            <i class="fa fa-cubes me-1"/> Bloque: <t t-esc="group.blockName"/>
                                        </span>
                                        <div class="badge bg-light text-dark border">
                                            Total: <t t-esc="formatNum(group.totalArea)"/> m² 
                                            (<t t-esc="group.count"/> pzas)
                                        </div>
                                    </div>
                                </td>
                            </tr>

                            <!-- Items -->
                            <t t-foreach="group.items" t-as="detail" t-key="detail.id">
                                <tr t-on-click="() => this.toggleSelection(detail)" 
                                    t-att-class="isSelected(detail) ? 'row-selected' : ''"
                                    class="stone-item-row">
                                    
                                    <td class="text-center position-relative">
                                        <input type="checkbox" 
                                               t-att-checked="isSelected(detail)"
                                               class="form-check-input stone-checkbox"/>
                                    </td>
                                    
                                    <td class="fw-bold text-dark font-monospace">
                                        <t t-esc="detail.lot_name"/>
                                    </td>
                                    
                                    <td class="text-muted small">
                                        <i class="fa fa-map-marker me-1 text-info"/>
                                        <t t-esc="detail.location_name"/>
                                    </td>
                                    
                                    <td class="text-end font-monospace small">
                                        <t t-if="detail.alto and detail.ancho">
                                            <t t-esc="detail.alto"/> × <t t-esc="detail.ancho"/>
                                        </t>
                                        <t t-else="">-</t>
                                    </td>
                                    
                                    <td class="text-end fw-bold">
                                        <span class="badge bg-white text-dark border">
                                            <t t-esc="formatNum(detail.quantity)"/>
                                        </span>
                                    </td>
                                    
                                    <td class="text-muted small"><t t-esc="detail.bloque"/></td>
                                    <td class="text-muted small"><t t-esc="detail.tipo"/></td>
                                    <td class="text-muted small"><t t-esc="detail.color"/></td>
                                </tr>
                            </t>
                        </t>
                    </tbody>
                </table>
            </div>
            
            <!-- Footer Informativo -->
            <div class="p-2 bg-light border-top d-flex justify-content-between align-items-center small text-muted">
                <span><i class="fa fa-info-circle me-1"/> Selecciona las placas para actualizar la cantidad.</span>
                <span><t t-esc="state.selectedLotIds.size"/> placas seleccionadas</span>
            </div>
        </div>
    </t>
</templates>
```

## ./static/src/components/stone_line_list/stone_line_list.js
```js
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
```

## ./static/src/components/stone_line_list/stone_line_list.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <!-- 1. Override del Renderer Loop -->
    <t t-name="sale_stone_selection.ListRenderer" t-inherit="web.ListRenderer" t-inherit-mode="primary">
        <xpath expr="//table/tbody" position="replace">
            <tbody>
                <t t-foreach="rows" t-as="row" t-key="row.id">
                    <!-- Fila Estándar de Odoo -->
                    <ListRow 
                        t-props="row" 
                        list="list" 
                        onRowClicked="onRowClicked"
                    />
                    
                    <!-- Fila Expandible (Stone Grid) -->
                    <!-- Solo se renderiza si hay producto y el flag 'is_stone_expanded' es true -->
                    <t t-if="row.record.data.product_id and row.record.data.is_stone_expanded">
                         <tr class="o_stone_details_row_tr">
                             <!-- Colspan dinámico para ocupar todo el ancho -->
                             <td t-att-colspan="columns.length + (hasSelectors ? 1 : 0) + 2" class="p-0 border-0">
                                 <div class="o_stone_slide_down">
                                     <StoneGrid 
                                         productId="row.record.data.product_id[0]"
                                         selectedLotIds="row.record.data.lot_ids.currentIds"
                                         onUpdateSelection.bind="(ids) => row.record.update({ lot_ids: [[6, 0, ids]] })"
                                     />
                                 </div>
                             </td>
                         </tr>
                    </t>
                </t>
            </tbody>
        </xpath>
    </t>

    <!-- 2. Override del Row para añadir el botón toggle -->
    <t t-name="sale_stone_selection.ListRow" t-inherit="web.ListRow" t-inherit-mode="primary">
        <xpath expr="//td[1]" position="inside">
            <t t-if="props.record.data.product_id">
                <div class="d-inline-block ms-1" t-on-click.stop="">
                    <button class="btn btn-sm btn-link p-0 text-decoration-none o_stone_toggle_btn"
                            t-on-click="() => props.record.update({ is_stone_expanded: !props.record.data.is_stone_expanded })"
                            title="Seleccionar placas">
                        <i class="fa fa-chevron-down" 
                           t-att-class="{'o_rotated': props.record.data.is_stone_expanded}"/>
                    </button>
                </div>
            </t>
        </xpath>
    </t>

</templates>
```

## ./static/src/scss/stone_styles.scss
```scss
// Variables
$stone-primary: #714B67;
$stone-secondary: #017E84;
$stone-bg: #f8f9fa;
$stone-border: #dee2e6;

// Animación del botón toggle
.o_stone_toggle_btn {
    color: $stone-primary !important;
    transition: color 0.2s;
    
    &:hover {
        color: darken($stone-primary, 15%) !important;
    }

    i.fa {
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        &.o_rotated {
            transform: rotate(180deg);
        }
    }
}

// Fila contenedora
.o_stone_details_row_tr {
    background-color: #ffffff;
    
    // Sombra interna para efecto de profundidad
    box-shadow: inset 0 6px 6px -6px rgba(0,0,0,0.15), inset 0 -6px 6px -6px rgba(0,0,0,0.15);
}

// Animación de entrada
.o_stone_slide_down {
    animation: slideDownStone 0.3s ease-out forwards;
    transform-origin: top;
}

@keyframes slideDownStone {
    from { opacity: 0; transform: scaleY(0.95); max-height: 0; }
    to { opacity: 1; transform: scaleY(1); max-height: 1000px; }
}

// Panel principal
.o_stone_selection_panel {
    background-color: $stone-bg;
    border-left: 4px solid $stone-primary;
    margin: 0;
}

// Tabla interna
.o_stone_table {
    thead th {
        background-color: #e9ecef;
        color: #495057;
        font-weight: 600;
        font-size: 0.85rem;
        border-bottom: 2px solid $stone-border;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    // Header de grupo (Bloque)
    .group-header-row {
        background-color: rgba($stone-primary, 0.05);
        
        td {
            padding: 8px 0;
            border-bottom: 1px solid rgba($stone-primary, 0.1);
        }
    }

    // Fila de Item
    .stone-item-row {
        cursor: pointer;
        transition: background-color 0.15s;

        &:hover {
            background-color: white !important;
        }

        &.row-selected {
            background-color: rgba($stone-secondary, 0.1) !important;
            
            td {
                color: darken($stone-secondary, 20%);
            }
        }
        
        td {
            vertical-align: middle;
            border-bottom: 1px solid $stone-border;
            padding: 8px;
        }
    }
    
    .stone-checkbox {
        cursor: pointer;
        width: 16px;
        height: 16px;
    }
}
```

## ./views/sale_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Herencia de Sale Order Form -->
    <record id="view_order_form_stone_selection" model="ir.ui.view">
        <field name="name">sale.order.form.stone.selection</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            
            <!-- 1. Modificar el Tree View de Order Line -->
            <xpath expr="//field[@name='order_line']/tree" position="attributes">
                <!-- Inyectamos nuestro Widget JS -->
                <attribute name="js_class">stone_order_line_list</attribute>
            </xpath>

            <!-- 2. Agregar campos necesarios (invisibles) al Tree View -->
            <xpath expr="//field[@name='order_line']/tree/field[@name='product_id']" position="after">
                <field name="is_stone_expanded" column_invisible="1"/>
                <field name="lot_ids" widget="many2many_tags" column_invisible="1"/>
            </xpath>

        </field>
    </record>
</odoo>
```

