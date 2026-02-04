## ./__init__.py
```py
# -*- coding: utf-8 -*-
from . import models
```

## ./__manifest__.py
```py
# ./__manifest__.py
{
    'name': 'Stone Selection & Visual Sale Grid',
    'version': '19.0.1.2.0',
    'category': 'Sales/Sales',
    'summary': 'Selección visual de placas con reserva estricta',
    'description': """
        Módulo profesional para la gestión de ventas de piedra natural.
        - Selección visual (Grid) en líneas de venta.
        - Reserva estricta de lotes seleccionados (Bypass FIFO).
        - Integración con stock_lot_dimensions para limpieza de asignaciones automáticas.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    # IMPORTANTE: Se agrega stock_lot_dimensions para garantizar el orden de ejecución correcto
    'depends': ['sale_management', 'stock', 'stock_lot_dimensions', 'inventory_shopping_cart'],
    'data': [
        'views/sale_views.xml',
        'views/stock_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_stone_selection/static/src/scss/stone_styles.scss',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.xml',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.js',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.js',
            'sale_stone_selection/static/src/components/stone_move_grid/stone_move_grid.xml',
            'sale_stone_selection/static/src/components/stone_move_grid/stone_move_grid.js', 
        ],
    },
    'installable': True,
    'application': True,
    'license': 'OPL-1',
}```

## ./models/__init__.py
```py
# -*- coding: utf-8 -*-
from . import sale_order
from . import sale_order_line
from . import stock_quant
from . import stock_move```

## ./models/sale_order.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Confirmación con asignación estricta de lotes seleccionados.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE] ACTION_CONFIRM INICIO - Orden: %s", self.name)
        
        # 1. GUARDAR los lotes ANTES de confirmar
        lines_lots_map = {}
        all_protected_lot_ids = []
        
        for order in self:
            for line in order.order_line.filtered(lambda l: l.lot_ids):
                lot_ids = line.lot_ids.ids.copy()
                lines_lots_map[line.id] = {
                    'lot_ids': lot_ids,
                    'product_id': line.product_id.id,
                }
                all_protected_lot_ids.extend(lot_ids)
                _logger.info("[STONE] Protegiendo para línea %s: %s lotes", line.id, len(lot_ids))
        
        if not lines_lots_map:
            return super().action_confirm()
        
        # 2. Definir Contexto de Protección
        # skip_picking_clean: CRÍTICO. Le dice a 'stock_lot_dimensions' Y 'inventory_shopping_cart' 
        # que NO ejecuten sus limpiezas automáticas.
        ctx = dict(self.env.context,
                   skip_picking_clean=True,
                   protected_lot_ids=all_protected_lot_ids,
                   is_stone_confirming=True)
        
        _logger.info("[STONE] Llamando a super() con skip_picking_clean=True...")
        
        # Al depender de 'inventory_shopping_cart', este super() llamará al Carrito con el contexto activado.
        # El Carrito verá el flag 'skip_picking_clean' en su código interno (si lo tiene implementado correctamente)
        # o al menos 'PickingLotCleaner' (usado por el Carrito) lo verá y se detendrá.
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        
        _logger.info("[STONE] Retorno de super(). Iniciando asignación forzada.")
        
        # 3. Asignación Forzada
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
            
            if not pickings:
                _logger.warning("[STONE] No se generaron pickings para la orden %s", order.name)
                continue

            # A. Limpieza Quirúrgica (Solo lo que NO es nuestro)
            for picking in pickings:
                for move in picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                    # Borrar líneas automáticas (FIFO) que Odoo haya puesto y que NO sean nuestros lotes
                    lines_to_remove = move.move_line_ids.filtered(
                        lambda ml: ml.lot_id and ml.lot_id.id not in all_protected_lot_ids
                    )
                    if lines_to_remove:
                        _logger.info("[STONE] Eliminando %s asignaciones automáticas incorrectas (FIFO)", len(lines_to_remove))
                        lines_to_remove.unlink()

            # B. Inyectar nuestros lotes
            for line in order.order_line:
                line_data = lines_lots_map.get(line.id)
                if not line_data:
                    continue
                    
                lots = self.env['stock.lot'].browse(line_data['lot_ids'])
                if lots:
                    # Pasamos el contexto también aquí para evitar bloqueos por Hold
                    self.with_context(ctx)._assign_stone_lots_to_picking(pickings, line, lots)
        
        # 4. Restaurar visualización en Sale Order (por si se perdió)
        for line_id, line_data in lines_lots_map.items():
            line = self.env['sale.order.line'].browse(line_id)
            if line.exists() and set(line.lot_ids.ids) != set(line_data['lot_ids']):
                line.with_context(ctx).write({'lot_ids': [(6, 0, line_data['lot_ids'])]})
        
        _logger.info("[STONE] ACTION_CONFIRM FIN")
        _logger.info("=" * 80)
        return res

    def _assign_stone_lots_to_picking(self, pickings, sale_line, lots):
        """Asigna los lotes seleccionados al picking."""
        product = sale_line.product_id
        if not lots:
            return

        # Contexto reforzado para la creación de move_lines
        # skip_hold_validation: CRÍTICO para permitir mover lotes apartados/reservados
        ctx = dict(self.env.context, 
                   skip_stone_sync=True, 
                   skip_picking_clean=True,
                   skip_hold_validation=True)

        for picking in pickings:
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id 
                and m.state not in ['done', 'cancel']
            )
            
            for move in moves:
                existing_lot_ids = move.move_line_ids.mapped('lot_id').ids
                
                for lot in lots:
                    if lot.id in existing_lot_ids:
                        continue
                    
                    # Buscar Stock Físico Total
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', product.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        _logger.warning("[STONE] Lote %s no encontrado físicamente en %s", lot.name, move.location_id.name)
                        continue
                    
                    # USAR CANTIDAD TOTAL (Ignorar reservas previas porque las acabamos de limpiar)
                    qty_to_assign = quant.quantity
                    
                    move_line_vals = {
                        'move_id': move.id,
                        'picking_id': picking.id,
                        'product_id': product.id,
                        'product_uom_id': move.product_uom.id,
                        'lot_id': lot.id,
                        'location_id': quant.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'quantity': qty_to_assign, # Forzar cantidad total
                    }
                    
                    try:
                        self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        _logger.info("[STONE] > Asignado Lote %s (Qty: %s) a Picking %s", lot.name, qty_to_assign, picking.name)
                    except Exception as e:
                        _logger.error("[STONE] Error asignando lote %s: %s", lot.name, str(e))

    def copy_data(self, default=None):
        return super().copy_data(default)

    def copy(self, default=None):
        return super().copy(default)```

## ./models/sale_order_line.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    lot_ids = fields.Many2many(
        'stock.lot',
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=True
    )

    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    # =========================================================================
    # DIAGNÓSTICO: Interceptar TODOS los métodos de copia/duplicación
    # =========================================================================

    def copy_data(self, default=None):
        """
        Método que prepara los datos para copiar una línea.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE COPY_DATA] INICIO - Línea ID: %s", self.id)
        _logger.info("[STONE COPY_DATA] self.lot_ids ANTES: %s (IDs: %s)", self.lot_ids, self.lot_ids.ids if self.lot_ids else [])
        _logger.info("[STONE COPY_DATA] default recibido: %s", default)
        _logger.info("[STONE COPY_DATA] Contexto: %s", self.env.context)
        
        if default is None:
            default = {}
        
        # Verificar si lot_ids ya está en default
        if 'lot_ids' in default:
            _logger.info("[STONE COPY_DATA] lot_ids YA está en default: %s", default['lot_ids'])
        else:
            if self.lot_ids:
                _logger.info("[STONE COPY_DATA] Agregando lot_ids a default: %s", self.lot_ids.ids)
                default['lot_ids'] = [(6, 0, self.lot_ids.ids)]
            else:
                _logger.info("[STONE COPY_DATA] NO hay lot_ids para copiar")
        
        result = super(SaleOrderLine, self).copy_data(default)
        
        _logger.info("[STONE COPY_DATA] Resultado de super().copy_data: %s", result)
        
        # Verificar si lot_ids está en el resultado
        if result:
            for idx, data in enumerate(result):
                if 'lot_ids' in data:
                    _logger.info("[STONE COPY_DATA] lot_ids EN RESULTADO[%s]: %s", idx, data['lot_ids'])
                else:
                    _logger.info("[STONE COPY_DATA] lot_ids NO ESTÁ en resultado[%s]", idx)
        
        _logger.info("[STONE COPY_DATA] FIN")
        _logger.info("=" * 80)
        return result

    def copy(self, default=None):
        """
        Método copy directo de la línea.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE LINE COPY] INICIO - Línea ID: %s", self.id)
        _logger.info("[STONE LINE COPY] lot_ids actuales: %s", self.lot_ids.ids if self.lot_ids else [])
        _logger.info("[STONE LINE COPY] default recibido: %s", default)
        _logger.info("[STONE LINE COPY] Contexto: %s", self.env.context)
        
        result = super(SaleOrderLine, self).copy(default)
        
        _logger.info("[STONE LINE COPY] Nueva línea creada ID: %s", result.id if result else None)
        _logger.info("[STONE LINE COPY] lot_ids en nueva línea: %s", result.lot_ids.ids if result and result.lot_ids else [])
        _logger.info("[STONE LINE COPY] FIN")
        _logger.info("=" * 80)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """
        Interceptar creación para ver qué valores llegan.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE LINE CREATE] INICIO - Creando %s línea(s)", len(vals_list))
        
        for idx, vals in enumerate(vals_list):
            _logger.info("[STONE LINE CREATE] vals[%s] completo: %s", idx, vals)
            if 'lot_ids' in vals:
                _logger.info("[STONE LINE CREATE] vals[%s] lot_ids: %s", idx, vals['lot_ids'])
            else:
                _logger.info("[STONE LINE CREATE] vals[%s] SIN lot_ids", idx)
        
        _logger.info("[STONE LINE CREATE] Contexto: %s", self.env.context)
        
        result = super(SaleOrderLine, self).create(vals_list)
        
        _logger.info("[STONE LINE CREATE] Líneas creadas IDs: %s", result.ids)
        for line in result:
            _logger.info("[STONE LINE CREATE] Línea ID %s - lot_ids DESPUÉS de create: %s", 
                        line.id, line.lot_ids.ids if line.lot_ids else [])
        
        _logger.info("[STONE LINE CREATE] FIN")
        _logger.info("=" * 80)
        return result

    def write(self, vals):
        """
        Interceptar escritura para ver cambios en lot_ids.
        """
        if 'lot_ids' in vals:
            _logger.info("=" * 80)
            _logger.info("[STONE LINE WRITE] Líneas IDs: %s", self.ids)
            _logger.info("[STONE LINE WRITE] lot_ids ANTES: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] lot_ids EN vals: %s", vals['lot_ids'])
            _logger.info("[STONE LINE WRITE] Contexto: %s", self.env.context)
        
        result = super(SaleOrderLine, self).write(vals)
        
        if 'lot_ids' in vals:
            _logger.info("[STONE LINE WRITE] lot_ids DESPUÉS: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] FIN")
            _logger.info("=" * 80)
        
        return result

    def read(self, fields=None, load='_classic_read'):
        """
        Interceptar lectura para ver qué se está leyendo.
        """
        result = super(SaleOrderLine, self).read(fields, load)
        
        # Solo loguear si se está leyendo lot_ids específicamente
        if fields and 'lot_ids' in fields:
            _logger.info("[STONE LINE READ] IDs: %s, fields: %s", self.ids, fields)
            for record_data in result:
                if 'lot_ids' in record_data:
                    _logger.info("[STONE LINE READ] ID %s -> lot_ids: %s", 
                                record_data.get('id'), record_data.get('lot_ids'))
        
        return result

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """Actualiza la cantidad (m2) de la línea al seleccionar placas"""
        _logger.info("=" * 80)
        _logger.info("[STONE ONCHANGE lot_ids] Línea ID: %s (origin: %s)", 
                    self.id, self._origin.id if hasattr(self, '_origin') else 'N/A')
        _logger.info("[STONE ONCHANGE lot_ids] lot_ids: %s", self.lot_ids.ids if self.lot_ids else [])
        _logger.info("[STONE ONCHANGE lot_ids] Contexto: %s", self.env.context)
        
        if not self.lot_ids:
            _logger.info("[STONE ONCHANGE lot_ids] Sin lotes, saliendo")
            return

        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])

        total_qty = sum(quants.mapped('quantity'))
        _logger.info("[STONE ONCHANGE lot_ids] Total qty calculado: %s", total_qty)
        
        if total_qty > 0:
            self.product_uom_qty = total_qty
            _logger.info("[STONE ONCHANGE lot_ids] product_uom_qty actualizado a: %s", total_qty)
        
        _logger.info("[STONE ONCHANGE lot_ids] FIN")
        _logger.info("=" * 80)```

## ./models/stock_move.py
```py
# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _recompute_state(self):
        """
        Detecta cambios en las reservas del Picking.
        """
        res = super(StockMove, self)._recompute_state()
        
        # NO sincronizar durante confirmación
        if self.env.context.get('is_stone_confirming'):
            return res
        if self.env.context.get('skip_stone_sync'):
            return res
            
        return res```

## ./models/stock_quant.py
```py
# -*- coding: utf-8 -*-
from odoo import models, api
import logging
_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None):
        """
        Búsqueda de inventario para selección de piedra.
        Devuelve datos completos del lote incluyendo todos los campos personalizados.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE QUANT SEARCH] INICIO")
        _logger.info("[STONE QUANT SEARCH] product_id: %s", product_id)
        _logger.info("[STONE QUANT SEARCH] filters: %s", filters)
        _logger.info("[STONE QUANT SEARCH] current_lot_ids (raw): %s", current_lot_ids)
        
        if not filters:
            filters = {}
        
        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]
            _logger.info("[STONE QUANT SEARCH] safe_current_ids: %s", safe_current_ids)

        # 1. Dominio base
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        # 2. Disponibilidad: (Es mío) OR (Está libre)
        free_domain = [('reserved_quantity', '=', 0)]
        if 'x_tiene_hold' in self.env['stock.quant']._fields:
            free_domain.append(('x_tiene_hold', '=', False))
        
        if safe_current_ids:
            availability_domain = ['|', ('lot_id', 'in', safe_current_ids)] + ['&'] + free_domain
        else:
            availability_domain = free_domain
            
        domain = base_domain + availability_domain

        # 3. Filtros UI
        if filters.get('bloque'):
            domain.append(('lot_id.x_bloque', 'ilike', filters['bloque']))
        if filters.get('atado'):
            domain.append(('lot_id.x_atado', 'ilike', filters['atado']))
        if filters.get('lot_name'):
            domain.append(('lot_id.name', 'ilike', filters['lot_name']))
        if filters.get('alto_min'):
            try:
                domain.append(('lot_id.x_alto', '>=', float(filters['alto_min'])))
            except:
                pass
        if filters.get('ancho_min'):
            try:
                domain.append(('lot_id.x_ancho', '>=', float(filters['ancho_min'])))
            except:
                pass

        # 4. Buscar quants
        quants = self.search(domain, limit=300, order='lot_id')
        
        # 5. Obtener IDs de lotes únicos para traer datos completos
        lot_ids = quants.mapped('lot_id').ids
        
        # 6. Leer TODOS los campos del lote de una sola vez (eficiente)
        lots_data = {}
        if lot_ids:
            lots = self.env['stock.lot'].browse(lot_ids)
            for lot in lots:
                lots_data[lot.id] = {
                    'name': lot.name,
                    # Dimensiones
                    'x_grosor': lot.x_grosor or 0,
                    'x_alto': lot.x_alto or 0,
                    'x_ancho': lot.x_ancho or 0,
                    'x_peso': lot.x_peso or 0,
                    # Clasificación
                    'x_tipo': lot.x_tipo or '',
                    'x_numero_placa': lot.x_numero_placa or '',
                    'x_bloque': lot.x_bloque or '',
                    'x_atado': lot.x_atado or '',
                    'x_grupo': lot.x_grupo or '',
                    'x_color': lot.x_color or '',
                    # Logística
                    'x_pedimento': lot.x_pedimento or '',
                    'x_contenedor': lot.x_contenedor or '',
                    'x_referencia_proveedor': lot.x_referencia_proveedor or '',
                    'x_proveedor': [lot.x_proveedor.id, lot.x_proveedor.name] if lot.x_proveedor else False,
                    'x_origen': lot.x_origen or '',
                    # Fotografías
                    'x_fotografia_principal': lot.x_fotografia_principal or False,
                    'x_tiene_fotografias': lot.x_tiene_fotografias or False,
                    'x_cantidad_fotos': lot.x_cantidad_fotos or 0,
                    # Detalles
                    'x_detalles_placa': lot.x_detalles_placa or '',
                }
        
        # 7. Construir resultado enriquecido
        result = []
        for q in quants:
            lot_id = q.lot_id.id if q.lot_id else False
            lot_info = lots_data.get(lot_id, {})
            
            result.append({
                'id': q.id,
                'lot_id': [lot_id, lot_info.get('name', '')] if lot_id else False,
                'location_id': [q.location_id.id, q.location_id.display_name] if q.location_id else False,
                'quantity': q.quantity,
                'reserved_quantity': q.reserved_quantity,
                # Todos los campos del lote
                'x_grosor': lot_info.get('x_grosor', 0),
                'x_alto': lot_info.get('x_alto', 0),
                'x_ancho': lot_info.get('x_ancho', 0),
                'x_peso': lot_info.get('x_peso', 0),
                'x_tipo': lot_info.get('x_tipo', ''),
                'x_numero_placa': lot_info.get('x_numero_placa', ''),
                'x_bloque': lot_info.get('x_bloque', ''),
                'x_atado': lot_info.get('x_atado', ''),
                'x_grupo': lot_info.get('x_grupo', ''),
                'x_color': lot_info.get('x_color', ''),
                'x_pedimento': lot_info.get('x_pedimento', ''),
                'x_contenedor': lot_info.get('x_contenedor', ''),
                'x_referencia_proveedor': lot_info.get('x_referencia_proveedor', ''),
                'x_proveedor': lot_info.get('x_proveedor', False),
                'x_origen': lot_info.get('x_origen', ''),
                'x_fotografia_principal': lot_info.get('x_fotografia_principal', False),
                'x_tiene_fotografias': lot_info.get('x_tiene_fotografias', False),
                'x_cantidad_fotos': lot_info.get('x_cantidad_fotos', 0),
                'x_detalles_placa': lot_info.get('x_detalles_placa', ''),
            })
        
        _logger.info("[STONE QUANT SEARCH] Encontrados: %s quants con datos completos", len(result))
        _logger.info("[STONE QUANT SEARCH] FIN")
        _logger.info("=" * 80)
        
        return result```

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
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, xml, onWillUnmount, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class StoneExpandButton extends Component {
    static template = xml`
        <div class="o_stone_toggle_btn cursor-pointer d-flex align-items-center justify-content-center" 
             t-on-click.stop="handleClick"
             title="Seleccionar Placas"
             style="width: 100%; height: 100%; min-height: 24px;">
            <i class="fa fa-th text-primary" t-if="!isExpanded" style="font-size: 14px;"/>
            <i class="fa fa-chevron-up text-danger" t-else="" style="font-size: 14px;"/>
        </div>
    `;
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.detailsRow = null;
        this.containerNode = null;
        this.gridNode = null;
        this.isExpanded = false;
        
        this.filters = { lot_name: '', bloque: '', atado: '', alto_min: '', ancho_min: '' };
        this.searchTimeout = null;

        // =====================================================================
        // DIAGNÓSTICO: Logs en el ciclo de vida del componente
        // =====================================================================
        onWillStart(() => {
            console.group("🔷 [STONE onWillStart] Componente inicializando");
            this._logRecordState("onWillStart");
            console.groupEnd();
        });

        onWillUpdateProps((nextProps) => {
            console.group("🔷 [STONE onWillUpdateProps] Props actualizándose");
            console.log("Props actuales:", this.props);
            console.log("Props nuevos:", nextProps);
            this._logRecordState("onWillUpdateProps (current)", this.props);
            this._logRecordState("onWillUpdateProps (next)", nextProps);
            console.groupEnd();
        });
        
        onWillUnmount(() => {
            console.log("🔷 [STONE onWillUnmount] Componente desmontándose");
            this.removeGrid();
        });
    }

    /**
     * DIAGNÓSTICO: Loguear estado completo del record
     */
    _logRecordState(context, props = this.props) {
        console.group(`📊 [STONE ${context}] Estado del Record`);
        
        if (!props || !props.record) {
            console.warn("❌ props.record NO EXISTE");
            console.groupEnd();
            return;
        }

        const record = props.record;
        const data = record.data;

        console.log("Record completo:", record);
        console.log("Record.data:", data);
        console.log("Record.resId:", record.resId);
        console.log("Record.isNew:", record.isNew);
        
        // Inspeccionar lot_ids específicamente
        console.group("🏷️ lot_ids inspection");
        console.log("data.lot_ids:", data.lot_ids);
        console.log("data.lot_ids tipo:", typeof data.lot_ids);
        
        if (data.lot_ids) {
            console.log("data.lot_ids constructor:", data.lot_ids.constructor?.name);
            console.log("data.lot_ids keys:", Object.keys(data.lot_ids));
            
            // Intentar diferentes formas de acceder a los IDs
            if (Array.isArray(data.lot_ids)) {
                console.log("✅ Es Array directo:", data.lot_ids);
            }
            
            if (data.lot_ids.records) {
                console.log("✅ Tiene .records:", data.lot_ids.records);
                console.log("Records mapped:", data.lot_ids.records.map(r => ({
                    resId: r.resId,
                    data: r.data,
                    id: r.data?.id
                })));
            }
            
            if (data.lot_ids.currentIds) {
                console.log("✅ Tiene .currentIds:", data.lot_ids.currentIds);
            }
            
            if (data.lot_ids.resIds) {
                console.log("✅ Tiene .resIds:", data.lot_ids.resIds);
            }

            // Propiedad count si existe
            if ('count' in data.lot_ids) {
                console.log("✅ Tiene .count:", data.lot_ids.count);
            }

            // Iterar si es iterable
            try {
                if (typeof data.lot_ids[Symbol.iterator] === 'function') {
                    console.log("✅ Es iterable, expandiendo:", [...data.lot_ids]);
                }
            } catch (e) {
                console.log("❌ No es iterable");
            }
        } else {
            console.log("❌ lot_ids es null/undefined/falsy");
        }
        console.groupEnd();

        // Otros campos relevantes
        console.log("product_id:", data.product_id);
        console.log("product_uom_qty:", data.product_uom_qty);
        
        console.groupEnd();
    }

    async handleClick(ev) {
        console.group("🔷 [STONE handleClick]");
        this._logRecordState("handleClick");
        
        const tr = ev.currentTarget.closest('tr');
        if (!tr) {
            console.warn("❌ No se encontró <tr>");
            console.groupEnd();
            return;
        }

        if (this.isExpanded) {
            this.removeGrid();
            this.isExpanded = false;
        } else {
            document.querySelectorAll('.o_stone_details_row_tr').forEach(e => e.remove());
            await this.injectContainer(tr);
            this.isExpanded = true;
        }
        this.render();
        console.groupEnd();
    }

    async injectContainer(currentRow) {
        console.log("🔷 [STONE injectContainer] Creando contenedor");
        
        const newTr = document.createElement('tr');
        newTr.className = 'o_stone_details_row_tr';
        
        const colCount = currentRow.querySelectorAll('td').length || 10;
        const newTd = document.createElement('td');
        newTd.colSpan = colCount;
        newTd.style.padding = '0';
        newTd.style.borderTop = '2px solid #714B67';
        
        this.containerNode = document.createElement('div');
        this.containerNode.className = 'bg-white';
        
        const filterBar = this.createFilterBar();
        this.containerNode.appendChild(filterBar);

        this.gridNode = document.createElement('div');
        this.gridNode.className = 'stone-grid-content p-0';
        this.gridNode.style.maxHeight = '400px';
        this.gridNode.style.overflowY = 'auto';
        this.gridNode.innerHTML = '<div class="text-center p-4"><i class="fa fa-circle-o-notch fa-spin"></i> Cargando inventario...</div>';
        
        this.containerNode.appendChild(this.gridNode);
        newTd.appendChild(this.containerNode);
        newTr.appendChild(newTd);
        
        currentRow.after(newTr);
        this.detailsRow = newTr;

        await this.loadData();
    }

    createFilterBar() {
        const bar = document.createElement('div');
        bar.className = 'd-flex flex-wrap gap-2 p-2 bg-light border-bottom align-items-end';

        const inputs = [
            { key: 'lot_name', label: 'Lote', width: '100px', type: 'text' },
            { key: 'bloque', label: 'Bloque', width: '80px', type: 'text' },
            { key: 'atado', label: 'Atado', width: '60px', type: 'text' },
            { key: 'alto_min', label: 'Alto >', width: '60px', type: 'number' },
            { key: 'ancho_min', label: 'Ancho >', width: '60px', type: 'number' },
        ];

        inputs.forEach(field => {
            const wrapper = document.createElement('div');
            wrapper.className = 'd-flex flex-column'; 
            
            const label = document.createElement('span');
            label.style.fontSize = '9px';
            label.className = 'fw-bold text-muted';
            label.innerText = field.label;
            
            const input = document.createElement('input');
            input.type = field.type;
            input.className = 'form-control form-control-sm';
            input.style.width = field.width;
            input.style.fontSize = '12px';
            input.value = this.filters[field.key] || '';
            
            input.addEventListener('input', (e) => {
                this.filters[field.key] = e.target.value;
                if(this.searchTimeout) clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => this.loadData(), 400);
            });

            wrapper.appendChild(label);
            wrapper.appendChild(input);
            bar.appendChild(wrapper);
        });

        const closeBtn = document.createElement('button');
        closeBtn.className = 'btn btn-sm btn-light border ms-auto';
        closeBtn.innerHTML = '<i class="fa fa-times"></i> Cerrar';
        closeBtn.onclick = () => {
            this.removeGrid();
            this.isExpanded = false;
            this.render();
        };
        bar.appendChild(closeBtn);

        return bar;
    }

    /**
     * DIAGNÓSTICO: Extractor con logs exhaustivos
     */
    extractLotIds(rawLots) {
        console.group("🔷 [STONE extractLotIds] Extrayendo IDs");
        console.log("Input rawLots:", rawLots);
        console.log("Input tipo:", typeof rawLots);
        
        if (!rawLots) {
            console.log("❌ rawLots es falsy, retornando []");
            console.groupEnd();
            return [];
        }

        console.log("rawLots constructor:", rawLots.constructor?.name);
        console.log("rawLots keys:", Object.keys(rawLots));
        
        // 1. Caso Array simple [1, 2, 3]
        if (Array.isArray(rawLots)) {
            console.log("✅ Es Array directo:", rawLots);
            console.groupEnd();
            return rawLots;
        }
        
        // 2. Caso Odoo X2Many RecordList (Odoo 16+)
        if (rawLots.records && Array.isArray(rawLots.records)) {
            console.log("✅ Tiene .records, extrayendo resIds");
            const ids = rawLots.records.map(r => {
                console.log("  Record:", r, "resId:", r.resId, "data.id:", r.data?.id);
                return r.resId || r.data?.id;
            }).filter(id => id);
            console.log("IDs extraídos:", ids);
            console.groupEnd();
            return ids;
        }

        // 3. Caso .currentIds
        if (rawLots.currentIds && Array.isArray(rawLots.currentIds)) {
            console.log("✅ Tiene .currentIds:", rawLots.currentIds);
            console.groupEnd();
            return rawLots.currentIds;
        }

        // 4. Caso .resIds
        if (rawLots.resIds && Array.isArray(rawLots.resIds)) {
            console.log("✅ Tiene .resIds:", rawLots.resIds);
            console.groupEnd();
            return rawLots.resIds;
        }

        // 5. Caso iterable
        try {
            if (typeof rawLots[Symbol.iterator] === 'function') {
                const ids = [...rawLots];
                console.log("✅ Es iterable, expandido:", ids);
                console.groupEnd();
                return ids;
            }
        } catch (e) {
            console.log("❌ No es iterable:", e);
        }

        console.log("❌ No se pudo extraer IDs, retornando []");
        console.groupEnd();
        return [];
    }

    async loadData() {
        if (!this.gridNode) return;
        
        console.group("🔷 [STONE loadData] Cargando datos");
        
        const recordData = this.props.record.data;
        this._logRecordState("loadData");
        
        let productId = false;
        if (recordData.product_id) {
            if (Array.isArray(recordData.product_id)) {
                productId = recordData.product_id[0];
            } else if (typeof recordData.product_id === 'number') {
                productId = recordData.product_id;
            } else if (recordData.product_id.id) {
                productId = recordData.product_id.id;
            } else if (typeof recordData.product_id === 'object' && recordData.product_id[0]) {
                productId = recordData.product_id[0];
            }
        }
        console.log("productId resuelto:", productId);

        if (!productId) {
            this.gridNode.innerHTML = '<div class="alert alert-warning m-2">Selecciona un producto primero.</div>';
            console.groupEnd();
            return;
        }

        const currentLotIds = this.extractLotIds(recordData.lot_ids);
        console.log("IDs finales para enviar al server:", currentLotIds);

        try {
            console.log("🔷 Llamando a search_stone_inventory_for_so...");
            const quants = await this.orm.call(
                'stock.quant', 
                'search_stone_inventory_for_so', 
                [], 
                { 
                    product_id: productId,
                    filters: this.filters,
                    current_lot_ids: currentLotIds
                }
            );
            console.log("🔷 Respuesta del server:", quants);

            this.renderTable(quants, currentLotIds);
        } catch (error) {
            console.error("❌ Error en loadData:", error);
            this.gridNode.innerHTML = `<div class="alert alert-danger m-2">Error: ${error.message}</div>`;
        }
        
        console.groupEnd();
    }

    renderTable(quants, selectedIds) {
        console.group("🔷 [STONE renderTable]");
        console.log("quants:", quants?.length);
        console.log("selectedIds:", selectedIds);
        
        if (!quants || quants.length === 0) {
            this.gridNode.innerHTML = '<div class="p-3 text-center text-muted">No se encontraron placas disponibles con estos filtros.</div>';
            console.groupEnd();
            return;
        }

        const groups = {};
        quants.forEach(q => {
            const b = q.x_bloque || 'Sin Bloque';
            if (!groups[b]) groups[b] = [];
            groups[b].push(q);
        });

        let html = `
            <table class="table table-sm table-hover table-bordered mb-0" style="font-size: 11px;">
                <thead class="bg-light sticky-top" style="top: 0;">
                    <tr>
                        <th width="30" class="text-center">#</th>
                        <th>Lote</th>
                        <th>Ubicación</th>
                        <th class="text-end">Dimensión</th>
                        <th class="text-end">M²</th>
                        <th class="text-center">Estado</th>
                    </tr>
                </thead>
                <tbody>
        `;

        for (const [bloque, items] of Object.entries(groups)) {
            const totalArea = items.reduce((sum, i) => sum + i.quantity, 0).toFixed(2);
            
            html += `
                <tr class="table-secondary">
                    <td colspan="6" class="px-2 fw-bold">
                        <i class="fa fa-cubes me-1"></i> Bloque: ${bloque} 
                        <span class="float-end badge bg-secondary">Total: ${totalArea} m²</span>
                    </td>
                </tr>
            `;
            
            items.forEach(q => {
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                const lotName = q.lot_id ? q.lot_id[1] : '';
                const locName = q.location_id ? q.location_id[1].split('/').pop() : '';
                
                const isChecked = selectedIds.includes(lotId);
                const isReserved = q.reserved_quantity > 0;

                let rowClass = isChecked ? 'table-primary' : '';
                let statusBadge = '';
                
                if (isChecked && isReserved) {
                    statusBadge = '<span class="badge bg-success" style="font-size:9px">Asignado</span>';
                } else if (isReserved) {
                    statusBadge = '<span class="badge bg-warning text-dark" style="font-size:9px">Reservado</span>';
                } else {
                    statusBadge = '<span class="badge bg-light text-muted border" style="font-size:9px">Libre</span>';
                }

                html += `
                    <tr class="${rowClass}" style="cursor:pointer;" onclick="this.querySelector('.stone-chk').click()">
                        <td class="text-center align-middle">
                            <input type="checkbox" class="stone-chk form-check-input mt-0" 
                                   value="${lotId}" ${isChecked ? 'checked' : ''} 
                                   onclick="event.stopPropagation()">
                        </td>
                        <td class="align-middle fw-bold font-monospace">${lotName}</td>
                        <td class="align-middle text-muted">${locName}</td>
                        <td class="align-middle text-end font-monospace">
                            ${(q.x_alto || 0).toFixed(2)} x ${(q.x_ancho || 0).toFixed(2)}
                        </td>
                        <td class="align-middle text-end fw-bold">${q.quantity.toFixed(2)}</td>
                        <td class="align-middle text-center">${statusBadge}</td>
                    </tr>
                `;
            });
        }
        html += `</tbody></table>`;
        
        this.gridNode.innerHTML = html;

        this.gridNode.querySelectorAll('.stone-chk').forEach(input => {
            input.addEventListener('change', (e) => this.onSelectionChange(e));
        });
        
        console.groupEnd();
    }

    onSelectionChange(ev) {
        console.group("🔷 [STONE onSelectionChange]");
        
        const id = parseInt(ev.target.value);
        const isChecked = ev.target.checked;
        const row = ev.target.closest('tr');
        
        console.log("Lot ID:", id);
        console.log("isChecked:", isChecked);
        
        if (isChecked) row.classList.add('table-primary');
        else row.classList.remove('table-primary');

        // Estado actual
        let currentIds = this.extractLotIds(this.props.record.data.lot_ids);
        console.log("currentIds ANTES:", currentIds);

        if (isChecked) {
            if (!currentIds.includes(id)) currentIds.push(id);
        } else {
            currentIds = currentIds.filter(x => x !== id);
        }
        console.log("currentIds DESPUÉS:", currentIds);

        // Actualizar el record
        const updateCommand = [[6, 0, currentIds]];
        console.log("Enviando update con:", updateCommand);
        
        this.props.record.update({ lot_ids: updateCommand });
        
        console.groupEnd();
    }

    removeGrid() {
        if (this.detailsRow) {
            this.detailsRow.remove();
            this.detailsRow = null;
        }
    }
}

registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Botón Selección Piedra",
});

export const stoneOrderLineListView = {
    ...listView,
};
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);```

## ./static/src/components/stone_line_list/stone_line_list.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <!-- 
        Ya no heredamos ListRenderer.
        Toda la lógica visual está en el JS del botón.
        Dejamos este archivo vacío o con templates auxiliares si hicieran falta.
    -->
</templates>```

## ./static/src/components/stone_move_grid/stone_move_grid.js
```js
/** @odoo-module */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";

export class StoneMoveGridField extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            isLoading: true,
            quants: [],
            filters: { lot_name: '', bloque: '', atado: '' }
        });
        this.searchTimeout = null;

        onWillStart(async () => { await this.loadInventory(); });

        onWillUpdateProps(async (nextProps) => {
            const oldId = this.props.record.data.product_id ? this.props.record.data.product_id[0] : null;
            const newId = nextProps.record.data.product_id ? nextProps.record.data.product_id[0] : null;
            if (oldId !== newId) await this.loadInventory(nextProps);
        });
    }

    async loadInventory(props = this.props) {
        const recordData = props.record.data;
        const productId = recordData.product_id ? recordData.product_id[0] : false;
        
        this.state.isLoading = true;

        // 1. Recopilar Lotes que YA están en el movimiento (Move Lines)
        // Esto garantiza que veamos los lotes asignados por la venta
        const currentLines = recordData.move_line_ids.records || [];
        const currentLotIds = [];
        const virtualQuants = [];

        currentLines.forEach(line => {
            const lotData = line.data.lot_id;
            if (lotData) {
                const lotId = lotData[0];
                currentLotIds.push(lotId);
                // Crear un "Quant Virtual" visual para mostrar lo asignado
                virtualQuants.push({
                    id: `virtual_${lotId}`,
                    lot_id: lotData,
                    quantity: line.data.quantity || 0,
                    location_id: line.data.location_id || recordData.location_id,
                    x_bloque: ' ASIGNADO', // Espacio para que salga al inicio
                    x_tipo: 'Placa',
                    is_virtual: true
                });
            }
        });

        if (!productId) {
            this.state.quants = virtualQuants;
            this.state.isLoading = false;
            return;
        }

        try {
            // 2. Buscar stock real, incluyendo los IDs actuales
            const quants = await this.orm.call('stock.quant', 'search_stone_inventory_for_so', [], {
                product_id: productId,
                filters: this.state.filters,
                current_lot_ids: currentLotIds
            });

            // 3. Fusión: Usar datos del server, pero rellenar con virtuales si faltan
            const serverLotIds = new Set(quants.map(q => q.lot_id[0]));
            const missingVirtuals = virtualQuants.filter(vq => !serverLotIds.has(vq.lot_id[0]));
            
            this.state.quants = [...missingVirtuals, ...quants];

        } catch (e) {
            console.error("Error cargando inventario:", e);
            this.state.quants = virtualQuants;
        } finally {
            this.state.isLoading = false;
        }
    }

    get groupedQuants() {
        if (this.state.quants.length === 0) return [];

        const groups = {};
        const sorted = this.state.quants.sort((a, b) => {
            const bla = a.x_bloque || 'zzz';
            const blb = b.x_bloque || 'zzz';
            return bla.localeCompare(blb);
        });

        for (const q of sorted) {
            const blockName = (q.x_bloque || 'General').trim();
            if (!groups[blockName]) {
                groups[blockName] = { name: blockName, items: [], totalArea: 0 };
            }
            groups[blockName].items.push(q);
            groups[blockName].totalArea += q.quantity;
        }
        return Object.values(groups);
    }

    getLineForLot(lotId) {
        const lines = this.props.record.data.move_line_ids.records;
        return lines.find(l => l.data.lot_id && l.data.lot_id[0] === lotId);
    }

    isLotSelected(lotId) {
        return !!this.getLineForLot(lotId);
    }

    async toggleLot(quant) {
        if (!quant.lot_id) return;
        const lotId = quant.lot_id[0];
        const existingLine = this.getLineForLot(lotId);
        const x2many = this.props.record.data.move_line_ids;

        if (existingLine) {
            await x2many.removeRecord(existingLine);
        } else {
            // Agregar reserva manual desde el picking
            await x2many.addNewRecord({
                context: {
                    default_lot_id: lotId,
                    default_quantity: quant.quantity,
                    default_location_id: quant.location_id ? quant.location_id[0] : null
                }
            });
        }
    }

    onFilterChange(key, value) {
        this.state.filters[key] = value;
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => this.loadInventory(), 400);
    }
}

StoneMoveGridField.template = "sale_stone_selection.StoneMoveGridField";
StoneMoveGridField.props = { ...standardFieldProps };
registry.category("fields").add("stone_move_grid", {
    component: StoneMoveGridField,
    displayName: "Stone Grid",
    supportedTypes: ["one2many"],
});```

## ./static/src/components/stone_move_grid/stone_move_grid.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="sale_stone_selection.StoneMoveGridField" owl="1">
        <div class="o_stone_move_panel border-0 bg-white d-flex flex-column" style="height: 100%;">
            
            <!-- ═══════════════════════════════════════════════════════════════════ -->
            <!-- 1. BARRA DE FILTROS COMPACTA -->
            <!-- ═══════════════════════════════════════════════════════════════════ -->
            <div class="d-flex flex-wrap gap-2 p-3 bg-gradient border-bottom align-items-end" 
                 style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                
                <div class="d-flex flex-column">
                    <span class="text-white fw-bold" style="font-size:10px; text-transform:uppercase; letter-spacing:1px;">Lote</span>
                    <input type="text" class="form-control form-control-sm shadow-sm" style="width:140px;" 
                           placeholder="Buscar lote..."
                           t-model="state.filters.lot_name" 
                           t-on-input="(e) => this.onFilterChange('lot_name', e.target.value)"/>
                </div>
                <div class="d-flex flex-column">
                    <span class="text-white fw-bold" style="font-size:10px; text-transform:uppercase; letter-spacing:1px;">Bloque</span>
                    <input type="text" class="form-control form-control-sm shadow-sm" style="width:100px;" 
                           placeholder="B-01"
                           t-model="state.filters.bloque" 
                           t-on-input="(e) => this.onFilterChange('bloque', e.target.value)"/>
                </div>
                <div class="d-flex flex-column">
                    <span class="text-white fw-bold" style="font-size:10px; text-transform:uppercase; letter-spacing:1px;">Atado</span>
                    <input type="text" class="form-control form-control-sm shadow-sm" style="width:80px;" 
                           placeholder="A-1"
                           t-model="state.filters.atado" 
                           t-on-input="(e) => this.onFilterChange('atado', e.target.value)"/>
                </div>
                
                <!-- Resumen visual -->
                <div class="ms-auto d-flex align-items-center gap-3">
                    <div class="text-white text-center">
                        <div style="font-size: 24px; font-weight: 700; line-height: 1;">
                            <t t-esc="state.quants.length"/>
                        </div>
                        <div style="font-size: 10px; opacity: 0.8; text-transform: uppercase;">Placas</div>
                    </div>
                    <div class="text-white text-center">
                        <div style="font-size: 24px; font-weight: 700; line-height: 1;">
                            <t t-esc="props.record.data.move_line_ids.records.length"/>
                        </div>
                        <div style="font-size: 10px; opacity: 0.8; text-transform: uppercase;">Seleccionadas</div>
                    </div>
                    <button class="btn btn-light btn-sm shadow-sm" t-on-click="loadInventory" title="Actualizar">
                        <i class="fa fa-refresh" t-att-class="state.isLoading ? 'fa-spin' : ''"/>
                    </button>
                </div>
            </div>

            <!-- ═══════════════════════════════════════════════════════════════════ -->
            <!-- 2. ÁREA PRINCIPAL - GRID DE PLACAS -->
            <!-- ═══════════════════════════════════════════════════════════════════ -->
            <div class="stone-grid-content flex-grow-1" style="overflow-y: auto; min-height: 0;">
                
                <!-- Loading -->
                <div t-if="state.isLoading" class="d-flex flex-column align-items-center justify-content-center py-5">
                    <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status">
                        <span class="visually-hidden">Cargando...</span>
                    </div>
                    <div class="mt-3 text-muted fw-bold">Cargando inventario de placas...</div>
                </div>

                <!-- Empty State -->
                <div t-elif="state.quants.length === 0" class="d-flex flex-column align-items-center justify-content-center py-5">
                    <i class="fa fa-inbox text-muted" style="font-size: 64px; opacity: 0.3;"/>
                    <div class="mt-3 text-muted fw-bold">No hay placas disponibles</div>
                    <div class="text-muted small">Intenta modificar los filtros de búsqueda</div>
                </div>

                <!-- Grid con datos -->
                <div t-else="" class="p-3">
                    <t t-foreach="groupedQuants" t-as="group" t-key="group.name">
                        
                        <!-- ═══════ CABECERA DE BLOQUE ═══════ -->
                        <div class="d-flex align-items-center justify-content-between mb-2 mt-3 pb-2 border-bottom">
                            <div class="d-flex align-items-center gap-2">
                                <span class="badge bg-dark px-3 py-2" style="font-size: 14px;">
                                    <i class="fa fa-cubes me-1"/> <t t-esc="group.name"/>
                                </span>
                                <span class="text-muted small">
                                    <t t-esc="group.items.length"/> placas
                                </span>
                            </div>
                            <div class="badge bg-success px-3 py-2" style="font-size: 13px;">
                                <i class="fa fa-th me-1"/> Total: <t t-esc="group.totalArea.toFixed(2)"/> m²
                            </div>
                        </div>

                        <!-- ═══════ CARDS DE PLACAS ═══════ -->
                        <div class="row g-3 mb-3">
                            <t t-foreach="group.items" t-as="q" t-key="q.id">
                                <t t-set="isSelected" t-value="isLotSelected(q.lot_id ? q.lot_id[0] : 0)"/>
                                <t t-set="hasPhoto" t-value="q.x_tiene_fotografias"/>
                                
                                <div class="col-12 col-md-6 col-lg-4 col-xl-3">
                                    <div t-on-click="() => this.toggleLot(q)" 
                                         class="card h-100 shadow-sm stone-card"
                                         t-att-class="isSelected ? 'border-primary border-3 bg-primary bg-opacity-10' : 'border-light'"
                                         style="cursor: pointer; transition: all 0.2s ease;">
                                        
                                        <!-- Header del Card con Foto o Placeholder -->
                                        <div class="position-relative" style="height: 120px; overflow: hidden; background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);">
                                            <t t-if="hasPhoto and q.x_fotografia_principal">
                                                <img t-att-src="'data:image/png;base64,' + q.x_fotografia_principal" 
                                                     class="w-100 h-100" style="object-fit: cover;"/>
                                            </t>
                                            <t t-else="">
                                                <div class="d-flex align-items-center justify-content-center h-100">
                                                    <i class="fa fa-image text-muted" style="font-size: 40px; opacity: 0.3;"/>
                                                </div>
                                            </t>
                                            
                                            <!-- Badge de selección -->
                                            <div class="position-absolute top-0 start-0 m-2">
                                                <span t-if="isSelected" class="badge bg-primary shadow">
                                                    <i class="fa fa-check"/> Seleccionada
                                                </span>
                                            </div>
                                            
                                            <!-- Badge de cantidad de fotos -->
                                            <div t-if="q.x_cantidad_fotos > 0" class="position-absolute top-0 end-0 m-2">
                                                <span class="badge bg-dark shadow-sm">
                                                    <i class="fa fa-camera"/> <t t-esc="q.x_cantidad_fotos"/>
                                                </span>
                                            </div>
                                            
                                            <!-- M² grande superpuesto -->
                                            <div class="position-absolute bottom-0 end-0 m-2">
                                                <span class="badge bg-success shadow px-2 py-1" style="font-size: 16px; font-weight: 700;">
                                                    <t t-esc="q.quantity.toFixed(2)"/> m²
                                                </span>
                                            </div>
                                        </div>
                                        
                                        <!-- Body del Card -->
                                        <div class="card-body p-2">
                                            <!-- Nombre del Lote -->
                                            <h6 class="card-title mb-2 fw-bold font-monospace text-truncate" 
                                                style="font-size: 14px; color: #333;"
                                                t-att-title="q.lot_id ? q.lot_id[1] : 'S/L'">
                                                <i class="fa fa-barcode me-1 text-muted"/>
                                                <t t-esc="q.lot_id ? q.lot_id[1] : 'Sin Lote'"/>
                                            </h6>
                                            
                                            <!-- Grid de Info Principal -->
                                            <div class="row g-1 small">
                                                <!-- Dimensiones -->
                                                <div class="col-6">
                                                    <div class="bg-light rounded p-1 text-center">
                                                        <div class="text-muted" style="font-size: 9px; text-transform: uppercase;">Dimensión</div>
                                                        <div class="fw-bold" style="font-size: 12px;">
                                                            <t t-if="q.x_alto and q.x_ancho">
                                                                <t t-esc="q.x_alto.toFixed(0)"/> × <t t-esc="q.x_ancho.toFixed(0)"/>
                                                            </t>
                                                            <t t-else="">-</t>
                                                        </div>
                                                    </div>
                                                </div>
                                                <!-- Grosor -->
                                                <div class="col-6">
                                                    <div class="bg-light rounded p-1 text-center">
                                                        <div class="text-muted" style="font-size: 9px; text-transform: uppercase;">Grosor</div>
                                                        <div class="fw-bold" style="font-size: 12px;">
                                                            <t t-if="q.x_grosor"><t t-esc="q.x_grosor"/> cm</t>
                                                            <t t-else="">-</t>
                                                        </div>
                                                    </div>
                                                </div>
                                                <!-- Tipo -->
                                                <div class="col-6">
                                                    <div class="bg-light rounded p-1 text-center">
                                                        <div class="text-muted" style="font-size: 9px; text-transform: uppercase;">Tipo</div>
                                                        <div class="fw-bold text-truncate" style="font-size: 11px;">
                                                            <t t-esc="q.x_tipo || '-'"/>
                                                        </div>
                                                    </div>
                                                </div>
                                                <!-- Color -->
                                                <div class="col-6">
                                                    <div class="bg-light rounded p-1 text-center">
                                                        <div class="text-muted" style="font-size: 9px; text-transform: uppercase;">Color</div>
                                                        <div class="fw-bold text-truncate" style="font-size: 11px;">
                                                            <t t-esc="q.x_color || '-'"/>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                            
                                            <!-- Línea separadora -->
                                            <hr class="my-2"/>
                                            
                                            <!-- Info Secundaria Compacta -->
                                            <div class="d-flex flex-wrap gap-1" style="font-size: 10px;">
                                                <span t-if="q.x_atado" class="badge bg-secondary bg-opacity-25 text-dark">
                                                    <i class="fa fa-link"/> <t t-esc="q.x_atado"/>
                                                </span>
                                                <span t-if="q.x_numero_placa" class="badge bg-info bg-opacity-25 text-dark">
                                                    # <t t-esc="q.x_numero_placa"/>
                                                </span>
                                                <span t-if="q.x_grupo" class="badge bg-warning bg-opacity-25 text-dark">
                                                    <i class="fa fa-object-group"/> <t t-esc="q.x_grupo"/>
                                                </span>
                                                <span t-if="q.x_origen" class="badge bg-dark bg-opacity-25 text-dark">
                                                    <i class="fa fa-globe"/> <t t-esc="q.x_origen"/>
                                                </span>
                                            </div>
                                            
                                            <!-- Ubicación -->
                                            <div class="mt-2 text-muted d-flex align-items-center" style="font-size: 10px;">
                                                <i class="fa fa-map-marker me-1 text-danger"/>
                                                <span class="text-truncate">
                                                    <t t-esc="(q.location_id and q.location_id[1]) ? q.location_id[1] : 'Sin ubicación'"/>
                                                </span>
                                            </div>
                                            
                                            <!-- Detalles especiales si existen -->
                                            <div t-if="q.x_detalles_placa" class="mt-2 p-1 bg-warning bg-opacity-10 rounded" style="font-size: 10px;">
                                                <i class="fa fa-exclamation-triangle text-warning me-1"/>
                                                <span class="text-truncate"><t t-esc="q.x_detalles_placa"/></span>
                                            </div>
                                        </div>
                                        
                                        <!-- Footer: Info Logística -->
                                        <div class="card-footer bg-transparent p-2 border-top" style="font-size: 9px;">
                                            <div class="d-flex flex-wrap gap-2 text-muted">
                                                <span t-if="q.x_pedimento" title="Pedimento">
                                                    <i class="fa fa-file-text-o"/> <t t-esc="q.x_pedimento"/>
                                                </span>
                                                <span t-if="q.x_contenedor" title="Contenedor">
                                                    <i class="fa fa-truck"/> <t t-esc="q.x_contenedor"/>
                                                </span>
                                                <span t-if="q.x_proveedor" title="Proveedor">
                                                    <i class="fa fa-building"/> <t t-esc="q.x_proveedor[1]"/>
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </t>
                        </div>
                    </t>
                </div>
            </div>

            <!-- ═══════════════════════════════════════════════════════════════════ -->
            <!-- 3. FOOTER FIJO -->
            <!-- ═══════════════════════════════════════════════════════════════════ -->
            <div class="bg-dark text-white p-3 d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2">
                    <i class="fa fa-info-circle"/>
                    <span>Haz clic en una placa para seleccionarla/deseleccionarla</span>
                </div>
                <div class="d-flex align-items-center gap-3">
                    <span class="badge bg-light text-dark px-3 py-2" style="font-size: 14px;">
                        <i class="fa fa-check-square me-1"/>
                        <t t-esc="props.record.data.move_line_ids.records.length"/> placas asignadas
                    </span>
                </div>
            </div>
        </div>
    </t>
</templates>```

## ./static/src/scss/stone_styles.scss
```scss
// Variables
$stone-primary: #714B67;
$stone-secondary: #667eea;
$stone-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

// ═══════════════════════════════════════════════════════════════════════════
// BOTÓN TOGGLE
// ═══════════════════════════════════════════════════════════════════════════
.o_stone_toggle_btn {
    color: $stone-primary !important;
    transition: color 0.2s;
    &:hover { 
        color: darken($stone-primary, 15%) !important; 
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// CHECKBOX PERSONALIZADO
// ═══════════════════════════════════════════════════════════════════════════
.stone-chk {
    cursor: pointer;
    border-color: #adb5bd;
    &:checked {
        background-color: $stone-primary;
        border-color: $stone-primary;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// FILA EXPANDIDA (Sale Order Line)
// ═══════════════════════════════════════════════════════════════════════════
.o_stone_details_row_tr td {
    background-color: #f8f9fa;
    padding: 0 !important;
}

// ═══════════════════════════════════════════════════════════════════════════
// MODAL GIGANTE (95% pantalla)
// ═══════════════════════════════════════════════════════════════════════════
.o_dialog:has(.o_stone_move_panel),
.o_dialog:has(.stone-grid-wrapper),
.modal-dialog:has(.stone-grid-wrapper),
.modal-dialog:has(.o_stone_move_panel) {
    max-width: 95vw !important;
    width: 95vw !important;
    margin: 10px auto !important;
    height: 95vh !important;
    display: flex;
    flex-direction: column;
}

.o_dialog:has(.o_stone_move_panel) .modal-content,
.modal-dialog:has(.o_stone_move_panel) .modal-content {
    height: 100%;
    display: flex;
    flex-direction: column;
}

.o_dialog:has(.o_stone_move_panel) .modal-body,
.modal-dialog:has(.o_stone_move_panel) .modal-body {
    flex: 1 1 auto;
    overflow: hidden !important;
    padding: 0 !important;
    display: flex;
    flex-direction: column;
}

// ═══════════════════════════════════════════════════════════════════════════
// CONTENEDORES PRINCIPALES
// ═══════════════════════════════════════════════════════════════════════════
.o_stone_move_panel,
.o_stone_selection_panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 100%;
    background-color: white;
}

// ═══════════════════════════════════════════════════════════════════════════
// ÁREA DE SCROLL
// ═══════════════════════════════════════════════════════════════════════════
.stone-grid-content,
.stone-grid-wrapper {
    flex: 1 1 auto;
    overflow-y: auto !important;
    max-height: none !important;
    min-height: 400px;
    
    // Scrollbar personalizado
    scrollbar-width: thin;
    scrollbar-color: $stone-primary #f1f1f1;
    
    &::-webkit-scrollbar {
        width: 10px;
    }
    
    &::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 5px;
    }
    
    &::-webkit-scrollbar-thumb {
        background: $stone-primary;
        border-radius: 5px;
        
        &:hover {
            background: darken($stone-primary, 10%);
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// TABLA ANCHA
// ═══════════════════════════════════════════════════════════════════════════
.o_stone_table {
    width: 100%;
}

// ═══════════════════════════════════════════════════════════════════════════
// STONE CARDS - VISTA DE PLACAS
// ═══════════════════════════════════════════════════════════════════════════
.stone-card {
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 12px !important;
    overflow: hidden;
    
    &:hover {
        transform: translateY(-6px);
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18) !important;
    }
    
    // Card seleccionada
    &.border-primary {
        border-color: $stone-primary !important;
        box-shadow: 
            0 0 0 3px rgba($stone-primary, 0.25),
            0 8px 25px rgba($stone-primary, 0.2) !important;
        
        .card-body {
            background: linear-gradient(180deg, rgba($stone-primary, 0.05) 0%, transparent 100%);
        }
    }
    
    // Header con imagen
    .card-img-top-wrapper {
        position: relative;
        height: 140px;
        overflow: hidden;
        background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
    }
    
    // Badges sobre la imagen
    .stone-badge-overlay {
        position: absolute;
        z-index: 5;
    }
    
    // Footer compacto
    .card-footer {
        font-size: 10px;
        background: #fafafa;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// ANIMACIONES
// ═══════════════════════════════════════════════════════════════════════════
@keyframes pulse-selection {
    0% { 
        transform: scale(1); 
        box-shadow: 0 0 0 0 rgba($stone-primary, 0.4);
    }
    50% { 
        transform: scale(1.02); 
        box-shadow: 0 0 0 10px rgba($stone-primary, 0);
    }
    100% { 
        transform: scale(1); 
        box-shadow: 0 0 0 0 rgba($stone-primary, 0);
    }
}

.stone-card.border-primary {
    animation: pulse-selection 0.4s ease;
}

@keyframes fade-in-up {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.stone-card {
    animation: fade-in-up 0.3s ease forwards;
    
    @for $i from 1 through 20 {
        &:nth-child(#{$i}) {
            animation-delay: #{$i * 0.03}s;
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// BADGES Y ETIQUETAS
// ═══════════════════════════════════════════════════════════════════════════
.stone-card .badge {
    font-weight: 600;
    letter-spacing: 0.3px;
}

// Badge de M² destacado
.stone-qty-badge {
    font-size: 15px !important;
    font-weight: 700;
    padding: 6px 12px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

// ═══════════════════════════════════════════════════════════════════════════
// HEADER GRADIENT (Barra de filtros)
// ═══════════════════════════════════════════════════════════════════════════
.stone-filter-bar {
    background: $stone-gradient;
    
    input.form-control {
        border: none;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        
        &:focus {
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.3);
        }
    }
    
    .stone-stat-box {
        background: rgba(255, 255, 255, 0.15);
        border-radius: 8px;
        padding: 8px 16px;
        backdrop-filter: blur(4px);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// INFO BOXES DENTRO DE CARDS
// ═══════════════════════════════════════════════════════════════════════════
.stone-info-box {
    background: #f8f9fa;
    border-radius: 6px;
    padding: 6px 8px;
    text-align: center;
    
    .stone-info-label {
        font-size: 9px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #6c757d;
        margin-bottom: 2px;
    }
    
    .stone-info-value {
        font-size: 12px;
        font-weight: 600;
        color: #333;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// PLACEHOLDER DE IMAGEN
// ═══════════════════════════════════════════════════════════════════════════
.stone-img-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
    
    i {
        font-size: 48px;
        color: #ccc;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// FOOTER FIJO
// ═══════════════════════════════════════════════════════════════════════════
.stone-footer {
    background: linear-gradient(180deg, #2d3748 0%, #1a202c 100%);
    border-top: 3px solid $stone-primary;
}

// ═══════════════════════════════════════════════════════════════════════════
// DETALLES ESPECIALES (Warning)
// ═══════════════════════════════════════════════════════════════════════════
.stone-detail-warning {
    background: rgba(255, 193, 7, 0.1);
    border-left: 3px solid #ffc107;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 10px;
}

// ═══════════════════════════════════════════════════════════════════════════
// GRUPO HEADER (Bloque)
// ═══════════════════════════════════════════════════════════════════════════
.stone-group-header {
    position: sticky;
    top: 0;
    z-index: 10;
    background: white;
    padding: 12px 0;
    margin-bottom: 12px;
    border-bottom: 2px solid #e9ecef;
    
    .stone-group-title {
        font-size: 16px;
        font-weight: 700;
        color: #333;
        
        i {
            color: $stone-primary;
        }
    }
    
    .stone-group-total {
        font-size: 14px;
        font-weight: 600;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// RESPONSIVE
// ═══════════════════════════════════════════════════════════════════════════
@media (max-width: 768px) {
    .o_dialog:has(.o_stone_move_panel),
    .modal-dialog:has(.o_stone_move_panel) {
        width: 100vw !important;
        max-width: 100vw !important;
        height: 100vh !important;
        margin: 0 !important;
        border-radius: 0 !important;
    }
    
    .stone-card {
        margin-bottom: 12px;
        
        .card-body {
            padding: 10px !important;
        }
    }
    
    .stone-filter-bar {
        flex-direction: column;
        gap: 8px !important;
        
        input.form-control {
            width: 100% !important;
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// DARK MODE SUPPORT (Odoo 17+)
// ═══════════════════════════════════════════════════════════════════════════
.o_dark_mode {
    .stone-card {
        background: #2d3748;
        border-color: #4a5568;
        
        .card-body {
            color: #e2e8f0;
        }
        
        .stone-info-box {
            background: #4a5568;
            
            .stone-info-value {
                color: #e2e8f0;
            }
        }
    }
    
    .stone-group-header {
        background: #1a202c;
        border-color: #4a5568;
        
        .stone-group-title {
            color: #e2e8f0;
        }
    }
    
    .stone-grid-content {
        background: #1a202c;
        
        &::-webkit-scrollbar-track {
            background: #2d3748;
        }
    }
}```

## ./views/sale_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_order_form_stone_selection" model="ir.ui.view">
        <field name="name">sale.order.form.stone.selection</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            
            <!-- js_class necesaria para cargar nuestros assets, aunque usemos lógica estándar -->
            <xpath expr="//field[@name='order_line']/list" position="attributes">
                <attribute name="js_class">stone_order_line_list</attribute>
            </xpath>

            <!-- El Widget Mágico -->
            <xpath expr="//field[@name='order_line']/list/field[@name='product_id']" position="before">
                <field name="is_stone_expanded" 
                       widget="stone_expand_button" 
                       string=" " 
                       width="30px" 
                       nolabel="1"
                       class="p-0 text-center"/>
            </xpath>

            <!-- Campos de datos necesarios -->
            <xpath expr="//field[@name='order_line']/list/field[@name='product_id']" position="after">
                <field name="lot_ids" widget="many2many_tags" column_invisible="1"/>
            </xpath>

        </field>
    </record>
</odoo>```

## ./views/stock_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Vista personalizada para las operaciones detalladas del movimiento -->
    <record id="view_stock_move_operations_stone_selection" model="ir.ui.view">
        <field name="name">stock.move.operations.form.stone</field>
        <field name="model">stock.move</field>
        <field name="inherit_id" ref="stock.view_stock_move_operations"/>
        <field name="arch" type="xml">
            
            <!-- Reemplazamos el campo move_line_ids original con nuestro widget -->
            <xpath expr="//field[@name='move_line_ids']" position="replace">
                
                <!-- 
                    Usamos el widget="stone_move_grid" que definimos en JS.
                    Esto ocultará la lista estándar y mostrará tu Grilla Poderosa.
                -->
                <field name="move_line_ids" 
                       widget="stone_move_grid" 
                       context="{'default_product_id': product_id, 'default_location_id': location_id, 'default_location_dest_id': location_dest_id}"
                       readonly="state == 'done'">
                    <!-- Mantenemos el tree interno por si Odoo necesita fallback o estructura de datos -->
                    <list editable="bottom" create="0" delete="0">
                        <field name="lot_id"/>
                        <field name="quantity"/>
                        <field name="product_uom_id"/>
                    </list>
                </field>
                
            </xpath>

            <!-- 
               Opcional: Ocultar los botones de "Generate Serials" o "Import Lots" 
               si estorban, ya que usaremos la grilla 
            -->
            <xpath expr="//widget[@name='generate_serials']" position="attributes">
                <attribute name="invisible">1</attribute>
            </xpath>
            <xpath expr="//widget[@name='import_lots']" position="attributes">
                <attribute name="invisible">1</attribute>
            </xpath>

        </field>
    </record>
</odoo>```

