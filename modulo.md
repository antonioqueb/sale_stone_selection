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
            # stone_grid
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.xml',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.js',
            # stone_line_list
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.xml',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.js',
            # stone_move_grid
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
from . import stock_move
from . import stock_move_line```

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
        Método que prepara los datos para copiar líneas.
        NOTA: Puede recibir múltiples registros (NO es singleton).
        """
        if default is None:
            default = {}
        
        # Solo procesar individualmente si es singleton
        if len(self) == 1:
            _logger.info("=" * 80)
            _logger.info("[STONE COPY_DATA] INICIO - Línea ID: %s", self.id)
            _logger.info("[STONE COPY_DATA] self.lot_ids ANTES: %s (IDs: %s)", self.lot_ids, self.lot_ids.ids if self.lot_ids else [])
            _logger.info("[STONE COPY_DATA] default recibido: %s", default)
            _logger.info("[STONE COPY_DATA] Contexto: %s", self.env.context)
            
            # Verificar si lot_ids ya está en default
            if 'lot_ids' in default:
                _logger.info("[STONE COPY_DATA] lot_ids YA está en default: %s", default['lot_ids'])
            else:
                if self.lot_ids:
                    _logger.info("[STONE COPY_DATA] Agregando lot_ids a default: %s", self.lot_ids.ids)
                    default['lot_ids'] = [(6, 0, self.lot_ids.ids)]
                else:
                    _logger.info("[STONE COPY_DATA] NO hay lot_ids para copiar")
        else:
            _logger.info("[STONE COPY_DATA] Multi-registro: %s líneas, delegando a super()", len(self))
        
        result = super(SaleOrderLine, self).copy_data(default)
        
        if len(self) == 1:
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
        if len(self) == 1:
            _logger.info("=" * 80)
            _logger.info("[STONE LINE COPY] INICIO - Línea ID: %s", self.id)
            _logger.info("[STONE LINE COPY] lot_ids actuales: %s", self.lot_ids.ids if self.lot_ids else [])
            _logger.info("[STONE LINE COPY] default recibido: %s", default)
            _logger.info("[STONE LINE COPY] Contexto: %s", self.env.context)
        
        result = super(SaleOrderLine, self).copy(default)
        
        if len(self) == 1:
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
        Interceptar escritura para ver cambios en lot_ids y sincronizar Pickings.
        """
        # --- LOGGING PREVIO ---
        if 'lot_ids' in vals:
            _logger.info("=" * 80)
            _logger.info("[STONE LINE WRITE] Líneas IDs: %s", self.ids)
            _logger.info("[STONE LINE WRITE] lot_ids ANTES: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] lot_ids EN vals: %s", vals['lot_ids'])
            _logger.info("[STONE LINE WRITE] Contexto: %s", self.env.context)
        
        # 1. BLOQUEAR SYNC INVERSO (CORRECCIÓN CRÍTICA)
        # Añadimos 'skip_stone_sync_so' al contexto antes de llamar a super().
        # Esto evita que si Odoo crea asignaciones automáticas (FIFO) durante el write,
        # esas asignaciones sobrescriban nuestra selección en la Sale Order.
        ctx = dict(self.env.context, skip_stone_sync_so=True)

        # --- EJECUCIÓN SUPER ---
        result = super(SaleOrderLine, self.with_context(ctx)).write(vals)
        
        # --- SINCRONIZACIÓN BIDIRECCIONAL (SO -> PICKING) ---
        # Si cambiaron lot_ids, la orden no es nueva y no venimos del Picking (evitar bucle)
        # Usamos el contexto original self.env.context para respetar flags externos, 
        # pero ya protegimos el super() arriba.
        if 'lot_ids' in vals and not self.env.context.get('skip_stone_sync_picking'):
            for line in self:
                # Solo sincronizar si la orden ya generó movimientos
                if line.state in ['sale', 'done'] and line.move_ids:
                    _logger.info("[STONE SYNC] Detectado cambio en lotes SO para línea %s. Sincronizando Picking...", line.id)
                    line._sync_lots_to_picking_moves()

        # --- LOGGING POSTERIOR ---
        if 'lot_ids' in vals:
            _logger.info("[STONE LINE WRITE] lot_ids DESPUÉS: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] FIN")
            _logger.info("=" * 80)
        
        return result

    def _sync_lots_to_picking_moves(self):
        """
        Refleja los cambios de lotes de la SO hacia los movimientos de stock (Pickings).
        Maneja adiciones, eliminaciones y corrección de cantidades.
        """
        # Contexto para:
        # 1. skip_stone_sync_so: Evitar que el Picking intente escribir de vuelta a la SO (Loop Infinito)
        # 2. skip_picking_clean: Evitar que otros módulos borren lo que estamos haciendo
        # 3. skip_hold_validation: Permitir mover lotes aunque tengan reserva/hold
        ctx = dict(self.env.context, 
                   skip_stone_sync_so=True,
                   skip_picking_clean=True,
                   skip_hold_validation=True)

        target_lots = self.lot_ids
        
        # Iterar sobre movimientos asociados que no estén cancelados ni finalizados
        moves = self.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])
        
        for move in moves:
            # 1. Asegurar que la demanda del movimiento coincida con la suma de nuestros lotes
            # Esto evita que Odoo intente rellenar huecos con FIFO
            total_area = sum(target_lots.mapped(lambda l: self.env['stock.quant'].search([
                ('lot_id', '=', l.id),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0)
            ], limit=1).quantity or 0.0))

            if total_area > 0 and move.product_uom_qty != total_area:
                 _logger.info("[STONE SYNC] Ajustando demanda Move %s de %s a %s", move.id, move.product_uom_qty, total_area)
                 move.with_context(ctx).write({'product_uom_qty': total_area})

            picking = move.picking_id
            existing_move_lines = move.move_line_ids
            existing_lots = existing_move_lines.mapped('lot_id')

            # A. DETECTAR QUÉ BORRAR (Están en Picking pero NO en nuestra selección SO)
            # NOTA: Esto eliminará también los lotes "basura" que Odoo haya asignado por FIFO
            lots_to_remove = existing_lots - target_lots
            if lots_to_remove:
                lines_to_unlink = existing_move_lines.filtered(lambda ml: ml.lot_id in lots_to_remove)
                _logger.info("[STONE SYNC] Eliminando %s lotes del picking %s (Usuario o FIFO)", len(lines_to_unlink), picking.name)
                lines_to_unlink.with_context(ctx).unlink()

            # B. DETECTAR QUÉ AGREGAR (Están en SO pero no en Picking)
            lots_to_add = target_lots - existing_lots
            if lots_to_add:
                _logger.info("[STONE SYNC] Agregando %s lotes al picking %s", len(lots_to_add), picking.name)
                for lot in lots_to_add:
                    # 1. Buscar disponibilidad física real (donde esté el lote actualmente)
                    # Intentamos primero en la ubicación del movimiento o sus hijos
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', self.product_id.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    # 2. Fallback: Si no está ahí (ej. se movió), buscar en cualquier ubicación interna
                    if not quant:
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', lot.id),
                            ('product_id', '=', self.product_id.id),
                            ('location_id.usage', '=', 'internal'),
                            ('quantity', '>', 0)
                        ], limit=1)

                    if quant:
                        move_line_vals = {
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': self.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'lot_id': lot.id,
                            'location_id': quant.location_id.id, # Usar ubicación real del lote
                            'location_dest_id': move.location_dest_id.id,
                            'quantity': quant.quantity, # Cantidad total del quant
                        }
                        try:
                            self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        except Exception as e:
                            _logger.error("[STONE SYNC] Error creando move line para lote %s: %s", lot.name, str(e))
                    else:
                        _logger.warning("[STONE SYNC] No se pudo sincronizar lote %s: No stock físico encontrado", lot.name)

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
        _logger.info("=" * 80)

    def _get_all_sale_lots_with_qty(self):
        """
        Retorna TODOS los lotes de la venta con su cantidad,
        buscando en todos los moves/pickings + fallback a lot_ids.
        Para uso en reportes.
        """
        self.ensure_one()
        
        # 1. Buscar en TODOS los stock.move.line vinculados
        move_lines = self.env['stock.move.line'].search([
            ('move_id.sale_line_id', '=', self.id),
            ('lot_id', '!=', False),
        ])
        
        if move_lines:
            lot_data = {}
            for ml in move_lines:
                lot = ml.lot_id
                if lot.id not in lot_data:
                    lot_data[lot.id] = {'lot': lot, 'quantity': 0.0}
                lot_data[lot.id]['quantity'] += ml.quantity or ml.reserved_uom_qty or 0.0
            return list(lot_data.values())
        
        # 2. Fallback: lot_ids (pre-confirmación o sin moves aún)
        if self.lot_ids:
            result = []
            for lot in self.lot_ids:
                quant = self.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('product_id', '=', self.product_id.id),
                    ('location_id.usage', '=', 'internal'),
                    ('quantity', '>', 0)
                ], limit=1)
                result.append({
                    'lot': lot,
                    'quantity': quant.quantity if quant else (lot.x_alto * lot.x_ancho if lot.x_alto and lot.x_ancho else 0.0),
                })
            return result
        
        return []```

## ./models/sale_order.py
```py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Confirmación con asignación estricta de lotes seleccionados.
        CRÍTICO: Asigna el lote COMPLETO, no cantidades parciales.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE] ACTION_CONFIRM INICIO - Orden: %s", self.name)

        # =====================================================================
        # NUEVO: Bloquear doble confirmación
        # Caso 1: Esta misma orden ya está confirmada → redirigir a sí misma
        # Caso 2: Esta cotización ya generó una SO aparte → redirigir a esa SO
        # =====================================================================
        for order in self:
            # Caso 1: Ya está confirmada
            if order.state in ('sale', 'done'):
                _logger.info("[STONE] Orden %s ya confirmada (state=%s). Redirigiendo.", order.name, order.state)
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': order.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'name': _('Orden de Venta: %s') % order.name,
                }
            
            # Caso 2: Ya existe una SO confirmada que se originó de esta cotización
            existing_so = self.env['sale.order'].search([
                ('origin', '=', order.name),
                ('id', '!=', order.id),
                ('state', 'in', ('sale', 'done')),
            ], limit=1)
            
            if existing_so:
                _logger.info("[STONE] Cotización %s ya generó la SO %s. Redirigiendo.", order.name, existing_so.name)
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': existing_so.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'name': _('Orden de Venta: %s') % existing_so.name,
                }
        
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
        ctx = dict(self.env.context,
                   skip_picking_clean=True,
                   protected_lot_ids=all_protected_lot_ids,
                   is_stone_confirming=True,
                   skip_stone_sync_so=True)  # Evitar sync durante confirmación
        
        _logger.info("[STONE] Llamando a super() con skip_picking_clean=True...")
        
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
                        lines_to_remove.with_context(ctx).unlink()

            # B. Inyectar nuestros lotes con CANTIDAD COMPLETA
            for line in order.order_line:
                line_data = lines_lots_map.get(line.id)
                if not line_data:
                    continue
                    
                lots = self.env['stock.lot'].browse(line_data['lot_ids'])
                if lots:
                    self.with_context(ctx)._assign_stone_lots_to_picking(pickings, line, lots)
        
        # 4. Restaurar visualización en Sale Order (por si se perdió)
        for line_id, line_data in lines_lots_map.items():
            line = self.env['sale.order.line'].browse(line_id)
            if line.exists() and set(line.lot_ids.ids) != set(line_data['lot_ids']):
                line.with_context(ctx).write({'lot_ids': [(6, 0, line_data['lot_ids'])]})

        # =====================================================================
        # 5. NUEVO: Limpiar lot_ids de la COTIZACIÓN ORIGEN
        # 
        # Caso A: Odoo duplicó la cotización → la SO tiene origin = nombre de la cotización
        # Caso B: Odoo transformó la cotización (mismo registro) → no hay cotización aparte
        #
        # Buscamos por origin y si encontramos una cotización distinta, la limpiamos.
        # =====================================================================
        for order in self:
            if order.origin:
                source_orders = self.env['sale.order'].search([
                    ('name', '=', order.origin),
                    ('id', '!=', order.id),
                    ('state', 'in', ('draft', 'sent', 'cancel')),
                ], limit=1)
                
                if source_orders:
                    _logger.info("[STONE] Limpiando lot_ids de cotización origen %s", source_orders.name)
                    for source_line in source_orders.order_line.filtered(lambda l: l.lot_ids):
                        source_line.with_context(ctx).write({'lot_ids': [(5, 0, 0)]})
                        _logger.info("[STONE] ✓ Limpiado lot_ids de línea %s en cotización %s", 
                                    source_line.id, source_orders.name)
        
        _logger.info("[STONE] ACTION_CONFIRM FIN")
        _logger.info("=" * 80)
        return res

    def _assign_stone_lots_to_picking(self, pickings, sale_line, lots):
        """
        Asigna los lotes seleccionados al picking.
        CRÍTICO: Usa la CANTIDAD TOTAL del quant, no cantidades parciales.
        """
        product = sale_line.product_id
        if not lots:
            return

        ctx = dict(self.env.context, 
                   skip_stone_sync=True, 
                   skip_picking_clean=True,
                   skip_hold_validation=True,
                   skip_stone_sync_so=True)

        for picking in pickings:
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id 
                and m.state not in ['done', 'cancel']
            )
            
            for move in moves:
                existing_lot_ids = move.move_line_ids.mapped('lot_id').ids
                
                for lot in lots:
                    if lot.id in existing_lot_ids:
                        _logger.info("[STONE] Lote %s ya existe en move %s, verificando cantidad...", lot.name, move.id)
                        # Verificar si la cantidad es correcta
                        existing_line = move.move_line_ids.filtered(lambda ml: ml.lot_id.id == lot.id)
                        if existing_line:
                            quant = self.env['stock.quant'].search([
                                ('lot_id', '=', lot.id),
                                ('product_id', '=', product.id),
                                ('location_id', 'child_of', move.location_id.id),
                                ('quantity', '>', 0)
                            ], limit=1)
                            if quant and existing_line.quantity != quant.quantity:
                                _logger.info("[STONE] Corrigiendo cantidad de %s a %s", existing_line.quantity, quant.quantity)
                                existing_line.with_context(ctx).write({'quantity': quant.quantity})
                        continue
                    
                    # Buscar Stock Físico Total
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', product.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        # Fallback: buscar en cualquier ubicación interna
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', lot.id),
                            ('product_id', '=', product.id),
                            ('location_id.usage', '=', 'internal'),
                            ('quantity', '>', 0)
                        ], limit=1)
                    
                    if not quant:
                        _logger.warning("[STONE] Lote %s no encontrado físicamente", lot.name)
                        continue
                    
                    # CRÍTICO: USAR CANTIDAD TOTAL DEL QUANT (El lote completo)
                    qty_to_assign = quant.quantity
                    
                    _logger.info("[STONE] Asignando lote %s con cantidad COMPLETA: %s m²", lot.name, qty_to_assign)
                    
                    move_line_vals = {
                        'move_id': move.id,
                        'picking_id': picking.id,
                        'product_id': product.id,
                        'product_uom_id': move.product_uom.id,
                        'lot_id': lot.id,
                        'location_id': quant.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'quantity': qty_to_assign,
                    }
                    
                    try:
                        self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        _logger.info("[STONE] ✓ Asignado Lote %s (Qty: %s) a Picking %s", lot.name, qty_to_assign, picking.name)
                    except Exception as e:
                        _logger.error("[STONE] Error asignando lote %s: %s", lot.name, str(e))

    def copy_data(self, default=None):
        return super().copy_data(default)

    def copy(self, default=None):
        return super().copy(default)```

## ./models/stock_move_line.py
```py
# -*- coding: utf-8 -*-
from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear líneas en el Picking, sincronizar hacia la SO SOLO si la línea
        de venta tiene lotes seleccionados manualmente.
        """
        lines = super(StockMoveLine, self).create(vals_list)
        
        if (not self.env.context.get('skip_stone_sync_so') 
            and not self.env.context.get('is_stone_confirming')):
            # Solo sincronizar lines cuyo sale_line_id SÍ tiene lot_ids manuales
            lines_to_sync = lines.filtered(
                lambda ml: ml.move_id.sale_line_id and ml.move_id.sale_line_id.lot_ids
            )
            if lines_to_sync:
                lines_to_sync._sync_to_sale_order_line()
        
        return lines

    def write(self, vals):
        res = super(StockMoveLine, self).write(vals)
        
        if (('lot_id' in vals or 'quantity' in vals) 
            and not self.env.context.get('skip_stone_sync_so')):
            # Solo sincronizar si la SO line tiene lotes manuales
            lines_to_sync = self.filtered(
                lambda ml: ml.move_id.sale_line_id and ml.move_id.sale_line_id.lot_ids
            )
            if lines_to_sync:
                lines_to_sync._sync_to_sale_order_line()
        
        return res

    def unlink(self):
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        res = super(StockMoveLine, self).unlink()
        
        if (not self.env.context.get('skip_stone_sync_so') 
            and not self.env.context.get('is_stone_confirming')):
            # Solo sync para moves cuya SO line tiene lotes manuales
            moves_with_manual = moves_to_sync.filtered(
                lambda m: m.sale_line_id.lot_ids
            )
            if moves_with_manual:
                moves_with_manual._sync_stone_sale_lines()
        
        return res

    def _sync_to_sale_order_line(self):
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        if moves_to_sync:
            _logger.info("[STONE SYNC] Sincronizando %s movimientos hacia SO", len(moves_to_sync))
            moves_to_sync._sync_stone_sale_lines()```

## ./models/stock_move.py
```py
# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _recompute_state(self):
        res = super(StockMove, self)._recompute_state()
        if self.env.context.get('is_stone_confirming') or self.env.context.get('skip_stone_sync'):
            return res
        return res

    def _sync_stone_sale_lines(self):
        """
        Recalcula los lotes en la línea de venta basándose en las líneas del movimiento actual.
        Trigger: Picking -> SO
        """
        if self.env.context.get('is_stone_confirming'):
            _logger.info("[STONE SYNC] Saltando sync durante confirmación inicial")
            return

        for move in self:
            if not move.sale_line_id:
                continue
            
            if move.state in ['done', 'cancel']:
                _logger.info("[STONE SYNC] Movimiento %s ya finalizado, no sincronizando", move.id)
                continue
            
            sol = move.sale_line_id

            all_lot_ids = set()
            
            for sibling_move in sol.move_ids:
                if sibling_move.state == 'cancel':
                    continue
                
                for ml in sibling_move.move_line_ids:
                    if ml.lot_id:
                        all_lot_ids.add(ml.lot_id.id)
            
            pending_moves = sol.move_ids.filtered(
                lambda m: m.state in ('confirmed', 'waiting', 'partially_available')
                and not m.move_line_ids
            )
            if pending_moves:
                existing_so_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()
                accounted_lots = all_lot_ids.copy()
                unaccounted = existing_so_lots - accounted_lots
                if unaccounted:
                    _logger.info(
                        "[STONE SYNC] Preserving %d unaccounted lots from SO Line %s "
                        "for pending moves: %s",
                        len(unaccounted), sol.id, list(unaccounted)
                    )
                    all_lot_ids.update(unaccounted)
            
            existing_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()
            
            if all_lot_ids == existing_lots:
                _logger.info("[STONE SYNC] Sin cambios en lotes para SO Line %s", sol.id)
                continue
            
            _logger.info("[STONE SYNC] Picking %s -> SO Line %s", 
                        move.picking_id.name if move.picking_id else 'N/A', sol.id)
            _logger.info("[STONE SYNC] Lotes anteriores: %s", sorted(existing_lots))
            _logger.info("[STONE SYNC] Lotes nuevos: %s", sorted(all_lot_ids))
            
            try:
                sol.with_context(skip_stone_sync_picking=True).write({
                    'lot_ids': [(6, 0, list(all_lot_ids))]
                })
                _logger.info("[STONE SYNC] ✓ Actualizado SO Line %s con %s lotes", 
                             sol.id, len(all_lot_ids))
            except Exception as e:
                _logger.error("[STONE SYNC] Error actualizando SO Line: %s", str(e))

    def write(self, vals):
        res = super(StockMove, self).write(vals)
        
        if 'move_line_ids' in vals and not self.env.context.get('skip_stone_sync_so'):
            for move in self:
                if move.sale_line_id and move.state not in ['done', 'cancel']:
                    move._sync_stone_sale_lines()
        
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
    def _get_committed_lot_ids(self, product_id):
        """
        Retorna IDs de lotes que están comprometidos en órdenes de venta confirmadas.
        Estos lotes NO deben aparecer como seleccionables en cotizaciones.
        """
        # 1. Lotes en move_line_ids de pickings activos vinculados a ventas confirmadas
        committed_move_lines = self.env['stock.move.line'].search([
            ('product_id', '=', product_id),
            ('lot_id', '!=', False),
            ('state', 'not in', ['done', 'cancel']),
            ('move_id.sale_line_id', '!=', False),
            ('move_id.sale_line_id.order_id.state', 'in', ['sale', 'done']),
        ])
        committed_ids = set(committed_move_lines.mapped('lot_id').ids)
        
        # 2. También lotes en sale.order.line de órdenes confirmadas
        #    (caso borde: orden confirmada pero picking aún no generado)
        committed_sol = self.env['sale.order.line'].search([
            ('product_id', '=', product_id),
            ('lot_ids', '!=', False),
            ('order_id.state', 'in', ['sale', 'done']),
        ])
        for sol in committed_sol:
            committed_ids.update(sol.lot_ids.ids)
        
        return list(committed_ids)

    def _build_stone_domain(self, product_id, filters, safe_current_ids, excluded_lot_ids):
        """
        Helper interno para construir el dominio de búsqueda de placas.
        Reutilizado por search_stone_inventory_for_so y search_stone_inventory_for_so_paginated.
        """
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        if excluded_lot_ids:
            base_domain.append(('lot_id', 'not in', excluded_lot_ids))

        free_domain = [('reserved_quantity', '=', 0)]
        if 'x_tiene_hold' in self.env['stock.quant']._fields:
            free_domain.append(('x_tiene_hold', '=', False))

        if safe_current_ids:
            availability_domain = ['|', ('lot_id', 'in', safe_current_ids)] + ['&'] + free_domain
        else:
            availability_domain = free_domain

        domain = base_domain + availability_domain

        if filters.get('bloque'):
            domain.append(('lot_id.x_bloque', 'ilike', filters['bloque']))
        if filters.get('atado'):
            domain.append(('lot_id.x_atado', 'ilike', filters['atado']))
        if filters.get('lot_name'):
            domain.append(('lot_id.name', 'ilike', filters['lot_name']))
        if filters.get('alto_min'):
            try:
                domain.append(('lot_id.x_alto', '>=', float(filters['alto_min'])))
            except Exception:
                pass
        if filters.get('ancho_min'):
            try:
                domain.append(('lot_id.x_ancho', '>=', float(filters['ancho_min'])))
            except Exception:
                pass

        return domain

    def _build_lots_data(self, lot_ids):
        """
        Helper interno: lee todos los campos de los lotes de una sola vez.
        """
        lots_data = {}
        if not lot_ids:
            return lots_data

        lots = self.env['stock.lot'].browse(lot_ids)
        for lot in lots:
            x_proveedor_value = lot.x_proveedor if 'x_proveedor' in lot._fields else False
            if x_proveedor_value:
                field_type = lot._fields.get('x_proveedor')
                if field_type and field_type.type == 'many2one':
                    x_proveedor_display = x_proveedor_value.name if x_proveedor_value else ''
                else:
                    x_proveedor_display = str(x_proveedor_value) if x_proveedor_value else ''
            else:
                x_proveedor_display = ''

            lots_data[lot.id] = {
                'name': lot.name,
                'x_grosor': lot.x_grosor if 'x_grosor' in lot._fields else 0,
                'x_alto': lot.x_alto if 'x_alto' in lot._fields else 0,
                'x_ancho': lot.x_ancho if 'x_ancho' in lot._fields else 0,
                'x_peso': lot.x_peso if 'x_peso' in lot._fields else 0,
                'x_tipo': lot.x_tipo if 'x_tipo' in lot._fields else '',
                'x_numero_placa': lot.x_numero_placa if 'x_numero_placa' in lot._fields else '',
                'x_bloque': lot.x_bloque if 'x_bloque' in lot._fields else '',
                'x_atado': lot.x_atado if 'x_atado' in lot._fields else '',
                'x_grupo': lot.x_grupo if 'x_grupo' in lot._fields else '',
                'x_color': lot.x_color if 'x_color' in lot._fields else '',
                'x_pedimento': lot.x_pedimento if 'x_pedimento' in lot._fields else '',
                'x_contenedor': lot.x_contenedor if 'x_contenedor' in lot._fields else '',
                'x_referencia_proveedor': lot.x_referencia_proveedor if 'x_referencia_proveedor' in lot._fields else '',
                'x_proveedor': x_proveedor_display,
                'x_origen': lot.x_origen if 'x_origen' in lot._fields else '',
                'x_fotografia_principal': lot.x_fotografia_principal if 'x_fotografia_principal' in lot._fields else False,
                'x_tiene_fotografias': lot.x_tiene_fotografias if 'x_tiene_fotografias' in lot._fields else False,
                'x_cantidad_fotos': lot.x_cantidad_fotos if 'x_cantidad_fotos' in lot._fields else 0,
                'x_detalles_placa': lot.x_detalles_placa if 'x_detalles_placa' in lot._fields else '',
            }

        return lots_data

    def _quants_to_result(self, quants, lots_data):
        """
        Helper interno: convierte recordset de quants a lista de dicts serializables.
        """
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
                'x_grosor': lot_info.get('x_grosor', 0) or 0,
                'x_alto': lot_info.get('x_alto', 0) or 0,
                'x_ancho': lot_info.get('x_ancho', 0) or 0,
                'x_peso': lot_info.get('x_peso', 0) or 0,
                'x_tipo': lot_info.get('x_tipo', '') or '',
                'x_numero_placa': lot_info.get('x_numero_placa', '') or '',
                'x_bloque': lot_info.get('x_bloque', '') or '',
                'x_atado': lot_info.get('x_atado', '') or '',
                'x_grupo': lot_info.get('x_grupo', '') or '',
                'x_color': lot_info.get('x_color', '') or '',
                'x_pedimento': lot_info.get('x_pedimento', '') or '',
                'x_contenedor': lot_info.get('x_contenedor', '') or '',
                'x_referencia_proveedor': lot_info.get('x_referencia_proveedor', '') or '',
                'x_proveedor': lot_info.get('x_proveedor', '') or '',
                'x_origen': lot_info.get('x_origen', '') or '',
                'x_fotografia_principal': lot_info.get('x_fotografia_principal', False),
                'x_tiene_fotografias': lot_info.get('x_tiene_fotografias', False),
                'x_cantidad_fotos': lot_info.get('x_cantidad_fotos', 0) or 0,
                'x_detalles_placa': lot_info.get('x_detalles_placa', '') or '',
            })
        return result

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None):
        """
        Búsqueda de inventario para selección de piedra.
        Devuelve datos completos del lote incluyendo todos los campos personalizados.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE QUANT SEARCH] INICIO - product_id: %s, filters: %s", product_id, filters)

        if not filters:
            filters = {}

        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        committed_lot_ids = self._get_committed_lot_ids(int(product_id))
        excluded_lot_ids = [lid for lid in committed_lot_ids if lid not in safe_current_ids]
        _logger.info("[STONE QUANT SEARCH] Lotes comprometidos excluidos: %s", len(excluded_lot_ids))

        domain = self._build_stone_domain(product_id, filters, safe_current_ids, excluded_lot_ids)
        quants = self.search(domain, limit=300, order='lot_id')

        lot_ids = quants.mapped('lot_id').ids
        lots_data = self._build_lots_data(lot_ids)
        result = self._quants_to_result(quants, lots_data)

        _logger.info("[STONE QUANT SEARCH] Encontrados: %s quants (excluidos %s comprometidos)",
                     len(result), len(excluded_lot_ids))
        _logger.info("[STONE QUANT SEARCH] FIN")
        _logger.info("=" * 80)

        return result

    @api.model
    def search_stone_inventory_for_so_paginated(self, product_id, filters=None, current_lot_ids=None, page=0, page_size=35):
        """
        Versión paginada de search_stone_inventory_for_so.
        Retorna { items: [...], total: N } para soporte de infinite scroll en el popup.
        """
        if not filters:
            filters = {}

        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        committed_lot_ids = self._get_committed_lot_ids(int(product_id))
        excluded_lot_ids = [lid for lid in committed_lot_ids if lid not in safe_current_ids]

        domain = self._build_stone_domain(product_id, filters, safe_current_ids, excluded_lot_ids)

        # Contar total sin límite
        total = self.search_count(domain)

        # Página solicitada
        offset = int(page) * int(page_size)
        quants = self.search(domain, limit=int(page_size), offset=offset, order='lot_id')

        lot_ids = quants.mapped('lot_id').ids
        lots_data = self._build_lots_data(lot_ids)
        items = self._quants_to_result(quants, lots_data)

        _logger.info(
            "[STONE QUANT PAGINATED] product=%s page=%s/%s offset=%s size=%s total=%s got=%s",
            product_id, page, (total // int(page_size)), offset, page_size, total, len(items)
        )

        return {'items': items, 'total': total}```

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
import { Component, useState, onWillStart, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENTE PRINCIPAL: BOTÓN STONE
// El popup se renderiza como DOM puro inyectado en document.body para evitar
// problemas de contexto OWL al montar fuera del árbol principal.
// ═══════════════════════════════════════════════════════════════════════════════
export class StoneExpandButton extends Component {
    static template = "sale_stone_selection.StoneExpandButton";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this._detailsRow = null;
        this._popupRoot = null;
        this._popupKeyHandler = null;
        this._popupObserver = null;  // ← Referencia al IntersectionObserver del popup

        this.state = useState({
            isExpanded: false,
            selectedCount: 0,
        });

        onWillStart(() => this._updateCount());
        onWillUpdateProps((nextProps) => this._updateCount(nextProps));
        onWillUnmount(() => {
            this.removeDetailsRow();
            this.destroyPopup();
        });
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────

    _updateCount(props = this.props) {
        const ids = this.extractLotIds(props?.record?.data?.lot_ids);
        this.state.selectedCount = ids.length;
    }

    extractLotIds(rawLots) {
        if (!rawLots) return [];
        if (Array.isArray(rawLots)) return rawLots.filter((x) => typeof x === "number");
        if (rawLots.currentIds) return rawLots.currentIds;
        if (rawLots.resIds) return rawLots.resIds;
        if (rawLots.records) return rawLots.records.map((r) => r.resId || r.data?.id).filter(Boolean);
        return [];
    }

    getProductId() {
        const pd = this.props.record.data.product_id;
        if (!pd) return 0;
        if (Array.isArray(pd)) return pd[0];
        if (typeof pd === "number") return pd;
        if (pd.id) return pd.id;
        return 0;
    }

    getProductName() {
        const pd = this.props.record.data.product_id;
        if (!pd) return "";
        if (Array.isArray(pd)) return pd[1] || "";
        if (pd.display_name) return pd.display_name;
        return "";
    }

    getCurrentLotIds() {
        return this.extractLotIds(this.props.record.data.lot_ids);
    }

    // ─── Toggle principal ─────────────────────────────────────────────────────

    async handleToggle(ev) {
        ev.stopPropagation();

        if (this.state.isExpanded) {
            this.removeDetailsRow();
            this.state.isExpanded = false;
            return;
        }

        // Cerrar cualquier otro expandido
        document.querySelectorAll(".stone-selected-row").forEach((e) => e.remove());

        const tr = ev.currentTarget.closest("tr");
        if (!tr) return;

        this.state.isExpanded = true;
        await this.injectSelectedTable(tr);
    }

    // ─── Tabla de seleccionadas (inline bajo la fila) ─────────────────────────

    async injectSelectedTable(currentRow) {
        const newTr = document.createElement("tr");
        newTr.className = "stone-selected-row";

        const colCount = currentRow.querySelectorAll("td").length || 10;
        const td = document.createElement("td");
        td.colSpan = colCount;
        td.className = "stone-selected-cell";

        const container = document.createElement("div");
        container.className = "stone-selected-container";

        const header = document.createElement("div");
        header.className = "stone-selected-header";
        header.innerHTML = `
            <span class="stone-selected-title">
                <i class="fa fa-check-circle me-2"></i>
                Placas seleccionadas
                <span class="stone-sel-badge" id="stone-sel-badge">${this.getCurrentLotIds().length}</span>
            </span>
            <button class="stone-add-btn stone-add-btn-trigger">
                <i class="fa fa-plus me-1"></i> Agregar placa
            </button>
        `;

        const body = document.createElement("div");
        body.className = "stone-selected-body";

        container.appendChild(header);
        container.appendChild(body);
        td.appendChild(container);
        newTr.appendChild(td);
        currentRow.after(newTr);
        this._detailsRow = newTr;

        await this.renderSelectedTable(body, this.getCurrentLotIds());

        header.querySelector(".stone-add-btn-trigger").addEventListener("click", (e) => {
            e.stopPropagation();
            this.openPopup();
        });
    }

    async renderSelectedTable(container, lotIds) {
        if (!lotIds || lotIds.length === 0) {
            container.innerHTML = `
                <div class="stone-no-selection">
                    <i class="fa fa-info-circle me-2 text-muted"></i>
                    <span class="text-muted">Sin placas seleccionadas. Usa <strong>Agregar placa</strong> para comenzar.</span>
                </div>`;
            return;
        }

        container.innerHTML = `<div class="stone-table-loading"><i class="fa fa-circle-o-notch fa-spin me-2"></i> Cargando datos...</div>`;

        try {
            const [lotsData, quants] = await Promise.all([
                this.orm.searchRead(
                    "stock.lot",
                    [["id", "in", lotIds]],
                    ["name", "x_bloque", "x_atado", "x_alto", "x_ancho", "x_grosor", "x_tipo", "x_color"],
                    { limit: lotIds.length }
                ),
                this.orm.searchRead(
                    "stock.quant",
                    [
                        ["lot_id", "in", lotIds],
                        ["location_id.usage", "=", "internal"],
                        ["quantity", ">", 0],
                    ],
                    ["lot_id", "quantity"]
                ),
            ]);

            const qtyMap = {};
            for (const q of quants) {
                const lid = q.lot_id[0];
                qtyMap[lid] = (qtyMap[lid] || 0) + q.quantity;
            }

            const lotMap = {};
            for (const l of lotsData) lotMap[l.id] = l;

            let totalQty = 0;
            let html = `
                <table class="stone-sel-table">
                    <thead>
                        <tr>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Ancho</th>
                            <th class="col-num">Espesor</th>
                            <th class="col-num">M²</th>
                            <th>Tipo</th>
                            <th>Color</th>
                            <th class="col-act"></th>
                        </tr>
                    </thead>
                    <tbody>`;

            for (const lid of lotIds) {
                const lot = lotMap[lid];
                if (!lot) continue;
                const qty = qtyMap[lid] || 0;
                totalQty += qty;
                html += `
                    <tr>
                        <td class="cell-lot">${lot.name}</td>
                        <td>${lot.x_bloque || "-"}</td>
                        <td>${lot.x_atado || "-"}</td>
                        <td class="col-num">${lot.x_alto ? lot.x_alto.toFixed(0) : "-"}</td>
                        <td class="col-num">${lot.x_ancho ? lot.x_ancho.toFixed(0) : "-"}</td>
                        <td class="col-num">${lot.x_grosor || "-"}</td>
                        <td class="col-num fw-semibold">${qty.toFixed(2)}</td>
                        <td>${lot.x_tipo || "-"}</td>
                        <td>${lot.x_color || "-"}</td>
                        <td class="col-act">
                            <button class="stone-remove-btn" data-lot-id="${lid}" title="Quitar">
                                <i class="fa fa-times"></i>
                            </button>
                        </td>
                    </tr>`;
            }

            html += `
                    </tbody>
                    <tfoot>
                        <tr class="stone-total-row">
                            <td colspan="6" class="text-end fw-bold text-muted">Total:</td>
                            <td class="col-num fw-bold">${totalQty.toFixed(2)}</td>
                            <td colspan="3"></td>
                        </tr>
                    </tfoot>
                </table>`;

            container.innerHTML = html;

            container.querySelectorAll(".stone-remove-btn").forEach((btn) => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.removeLot(parseInt(btn.dataset.lotId));
                });
            });
        } catch (err) {
            console.error("[STONE] Error renderizando seleccionadas:", err);
            container.innerHTML = `<div class="text-danger p-2">Error: ${err.message}</div>`;
        }
    }

    async removeLot(lotId) {
        const newIds = this.getCurrentLotIds().filter((id) => id !== lotId);
        await this.props.record.update({ lot_ids: [[6, 0, newIds]] });
        this._updateCount();
        await this.refreshSelectedTable();
    }

    async refreshSelectedTable() {
        if (!this._detailsRow) return;
        const body = this._detailsRow.querySelector(".stone-selected-body");
        if (!body) return;
        const lots = this.getCurrentLotIds();
        const badge = this._detailsRow.querySelector(".stone-sel-badge");
        if (badge) badge.textContent = lots.length;
        await this.renderSelectedTable(body, lots);
    }

    removeDetailsRow() {
        if (this._detailsRow) {
            this._detailsRow.remove();
            this._detailsRow = null;
        }
    }

    // ─── POPUP (DOM puro en document.body) ────────────────────────────────────

    openPopup() {
        this.destroyPopup();
        const productId = this.getProductId();
        if (!productId) return;

        this._popupRoot = document.createElement("div");
        this._popupRoot.className = "stone-popup-root";
        document.body.appendChild(this._popupRoot);

        this._renderPopupDOM(productId);
    }

    _renderPopupDOM(productId) {
        const root = this._popupRoot;
        const PAGE_SIZE = 35;

        // Estado local del popup
        const state = {
            quants: [],
            totalCount: 0,
            hasMore: false,
            isLoading: false,
            isLoadingMore: false,
            page: 0,
            pendingIds: new Set(this.getCurrentLotIds()),
            filters: { lot_name: "", bloque: "", atado: "", alto_min: "", ancho_min: "" },
        };

        let searchTimeout = null;

        root.innerHTML = `
            <div class="stone-popup-overlay" id="stone-overlay">
                <div class="stone-popup-container">

                    <div class="stone-popup-header">
                        <div class="stone-popup-title">
                            <i class="fa fa-th me-2"></i>
                            Seleccionar Placas
                            <span class="stone-popup-subtitle">${this.getProductName() ? "— " + this.getProductName() : ""}</span>
                        </div>
                        <div class="stone-popup-header-actions">
                            <span class="stone-badge-selected">
                                <i class="fa fa-check-circle me-1"></i>
                                <span id="sp-badge-count">${state.pendingIds.size}</span> seleccionadas
                            </span>
                            <button class="stone-btn stone-btn-accent" id="sp-confirm-top">
                                <i class="fa fa-check me-1"></i> Confirmar
                            </button>
                            <button class="stone-btn stone-btn-ghost" id="sp-close">
                                <i class="fa fa-times"></i>
                            </button>
                        </div>
                    </div>

                    <div class="stone-popup-filters">
                        <div class="stone-filter-group">
                            <label>Lote</label>
                            <input type="text" class="stone-filter-input" id="sf-lot" placeholder="Buscar lote..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Bloque</label>
                            <input type="text" class="stone-filter-input" id="sf-bloque" placeholder="Bloque..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Atado</label>
                            <input type="text" class="stone-filter-input" id="sf-atado" placeholder="Atado..."/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Alto mín.</label>
                            <input type="number" class="stone-filter-input stone-filter-sm" id="sf-alto" placeholder="0"/>
                        </div>
                        <div class="stone-filter-group">
                            <label>Ancho mín.</label>
                            <input type="number" class="stone-filter-input stone-filter-sm" id="sf-ancho" placeholder="0"/>
                        </div>
                        <div class="stone-filter-spacer"></div>
                        <div class="stone-filter-stats">
                            <span id="sp-stat" class="stone-filter-stat-loading">
                                <i class="fa fa-circle-o-notch fa-spin me-1"></i> Buscando...
                            </span>
                        </div>
                    </div>

                    <div class="stone-popup-body" id="sp-body">
                        <div class="stone-empty-state">
                            <i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i>
                            <div class="stone-empty-text mt-2">Cargando inventario...</div>
                        </div>
                    </div>

                    <div class="stone-popup-footer">
                        <span class="stone-footer-info" id="sp-footer-info">—</span>
                        <div class="stone-footer-actions">
                            <button class="stone-btn stone-btn-outline" id="sp-cancel">Cancelar</button>
                            <button class="stone-btn stone-btn-primary-dark" id="sp-confirm-bottom">
                                <i class="fa fa-check me-1"></i> Agregar selección
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const overlay = root.querySelector("#stone-overlay");
        const body = root.querySelector("#sp-body");
        const stat = root.querySelector("#sp-stat");
        const footerInfo = root.querySelector("#sp-footer-info");
        const badgeCount = root.querySelector("#sp-badge-count");

        // ─── Utils ───────────────────────────────────────────────────────────
        const updateBadge = () => { badgeCount.textContent = state.pendingIds.size; };

        const updateStats = () => {
            stat.className = "stone-filter-stat-count";
            stat.innerHTML = `${state.totalCount} placas disponibles`;
            footerInfo.innerHTML = `Mostrando <strong>${state.quants.length}</strong> de <strong>${state.totalCount}</strong>`;
        };

        const renderTable = () => {
            if (state.quants.length === 0 && !state.isLoading) {
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-inbox fa-3x text-muted"></i>
                        <div class="stone-empty-text mt-2">No hay placas con estos filtros</div>
                    </div>`;
                updateStats();
                return;
            }

            // Construir HTML de la tabla
            let rows = "";
            for (const q of state.quants) {
                const lotId = q.lot_id ? q.lot_id[0] : 0;
                const lotName = q.lot_id ? q.lot_id[1] : "-";
                const loc = q.location_id ? q.location_id[1].split("/").pop() : "-";
                const sel = state.pendingIds.has(lotId);
                const reserved = q.reserved_quantity > 0;

                let statusBadge = `<span class="stone-tag stone-tag-free">Libre</span>`;
                if (sel) statusBadge = `<span class="stone-tag stone-tag-ok">Selec.</span>`;
                else if (reserved) statusBadge = `<span class="stone-tag stone-tag-warn">Reservado</span>`;

                rows += `
                    <tr class="${sel ? "row-sel" : ""}" data-lot-id="${lotId}">
                        <td class="col-chk">
                            <div class="stone-chkbox ${sel ? "checked" : ""}">
                                ${sel ? '<i class="fa fa-check"></i>' : ""}
                            </div>
                        </td>
                        <td class="cell-lot">${lotName}</td>
                        <td>${q.x_bloque || "-"}</td>
                        <td>${q.x_atado || "-"}</td>
                        <td class="col-num">${q.x_alto ? q.x_alto.toFixed(0) : "-"}</td>
                        <td class="col-num">${q.x_ancho ? q.x_ancho.toFixed(0) : "-"}</td>
                        <td class="col-num">${q.x_grosor || "-"}</td>
                        <td class="col-num fw-semibold">${q.quantity ? q.quantity.toFixed(2) : "-"}</td>
                        <td>${q.x_tipo || "-"}</td>
                        <td>${q.x_color || "-"}</td>
                        <td class="cell-loc">${loc}</td>
                        <td>${statusBadge}</td>
                    </tr>`;
            }

            const sentinel = `
                <div id="sp-sentinel" class="stone-scroll-sentinel">
                    ${state.isLoadingMore ? '<div class="stone-loading-more"><i class="fa fa-circle-o-notch fa-spin me-2"></i> Cargando más...</div>' : ""}
                    ${state.hasMore && !state.isLoadingMore ? '<div class="stone-scroll-hint"><i class="fa fa-chevron-down me-1"></i> Desplázate para cargar más</div>' : ""}
                </div>`;

            body.innerHTML = `
                <table class="stone-popup-table">
                    <thead>
                        <tr>
                            <th class="col-chk">✓</th>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="col-num">Alto</th>
                            <th class="col-num">Ancho</th>
                            <th class="col-num">Gros.</th>
                            <th class="col-num">M²</th>
                            <th>Tipo</th>
                            <th>Color</th>
                            <th>Ubicación</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                ${sentinel}`;

            updateStats();

            // Click en filas (toggle selección sin re-render completo)
            body.querySelectorAll("tr[data-lot-id]").forEach((tr) => {
                tr.style.cursor = "pointer";
                tr.addEventListener("click", () => {
                    const lotId = parseInt(tr.dataset.lotId);
                    if (!lotId) return;
                    if (state.pendingIds.has(lotId)) {
                        state.pendingIds.delete(lotId);
                    } else {
                        state.pendingIds.add(lotId);
                    }
                    const sel = state.pendingIds.has(lotId);
                    tr.className = sel ? "row-sel" : "";
                    const chk = tr.querySelector(".stone-chkbox");
                    if (chk) {
                        chk.className = "stone-chkbox" + (sel ? " checked" : "");
                        chk.innerHTML = sel ? '<i class="fa fa-check"></i>' : "";
                    }
                    const tag = tr.querySelector(".stone-tag");
                    if (tag) {
                        tag.className = sel ? "stone-tag stone-tag-ok" : "stone-tag stone-tag-free";
                        tag.textContent = sel ? "Selec." : "Libre";
                    }
                    updateBadge();
                });
            });

            // ── Infinite scroll: usar this._popupObserver (en scope del componente) ──
            if (this._popupObserver) {
                this._popupObserver.disconnect();
                this._popupObserver = null;
            }
            const sentinelEl = body.querySelector("#sp-sentinel");
            if (sentinelEl && state.hasMore) {
                this._popupObserver = new IntersectionObserver(
                    (entries) => {
                        if (entries[0].isIntersecting && state.hasMore && !state.isLoadingMore) {
                            loadPage(state.page + 1, false);
                        }
                    },
                    { root: body, rootMargin: "100px", threshold: 0.1 }
                );
                this._popupObserver.observe(sentinelEl);
            }
        };

        // ─── loadPage ────────────────────────────────────────────────────────
        const loadPage = async (page, reset) => {
            if (reset) {
                state.isLoading = true;
                state.quants = [];
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-circle-o-notch fa-spin fa-2x text-muted"></i>
                        <div class="stone-empty-text mt-2">Buscando...</div>
                    </div>`;
                stat.className = "stone-filter-stat-loading";
                stat.innerHTML = `<i class="fa fa-circle-o-notch fa-spin me-1"></i> Buscando...`;
            } else {
                state.isLoadingMore = true;
            }

            try {
                let result;
                try {
                    result = await this.orm.call(
                        "stock.quant",
                        "search_stone_inventory_for_so_paginated",
                        [],
                        {
                            product_id: productId,
                            filters: state.filters,
                            current_lot_ids: Array.from(state.pendingIds),
                            page,
                            page_size: PAGE_SIZE,
                        }
                    );
                } catch (_e) {
                    // Fallback al método original
                    const all = (await this.orm.call(
                        "stock.quant",
                        "search_stone_inventory_for_so",
                        [],
                        {
                            product_id: productId,
                            filters: state.filters,
                            current_lot_ids: Array.from(state.pendingIds),
                        }
                    )) || [];
                    result = {
                        items: all.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
                        total: all.length,
                    };
                }

                const items = result.items || [];
                if (reset || page === 0) {
                    state.quants = items;
                } else {
                    state.quants = [...state.quants, ...items];
                }
                state.totalCount = result.total || 0;
                state.page = page;
                state.hasMore = state.quants.length < state.totalCount;
            } catch (err) {
                console.error("[STONE POPUP] Error:", err);
                body.innerHTML = `
                    <div class="stone-empty-state">
                        <i class="fa fa-exclamation-triangle fa-2x text-danger"></i>
                        <div class="stone-empty-text mt-2 text-danger">Error: ${err.message}</div>
                    </div>`;
                return;
            } finally {
                state.isLoading = false;
                state.isLoadingMore = false;
            }

            renderTable();
        };

        // ─── Confirm / Close ─────────────────────────────────────────────────
        const doConfirm = async () => {
            this.destroyPopup();
            const newIds = Array.from(state.pendingIds);
            await this.props.record.update({ lot_ids: [[6, 0, newIds]] });
            this._updateCount();
            await this.refreshSelectedTable();
        };

        const doClose = () => this.destroyPopup();

        // ─── Event listeners ─────────────────────────────────────────────────
        root.querySelector("#sp-close").addEventListener("click", doClose);
        root.querySelector("#sp-cancel").addEventListener("click", doClose);
        root.querySelector("#sp-confirm-top").addEventListener("click", doConfirm);
        root.querySelector("#sp-confirm-bottom").addEventListener("click", doConfirm);
        overlay.addEventListener("click", (e) => { if (e.target === overlay) doClose(); });

        const onKeyDown = (e) => { if (e.key === "Escape") { doClose(); } };
        document.addEventListener("keydown", onKeyDown);
        this._popupKeyHandler = onKeyDown;

        // Filtros
        const bindFilter = (id, key) => {
            const input = root.querySelector(`#${id}`);
            if (!input) return;
            input.addEventListener("input", (e) => {
                state.filters[key] = e.target.value;
                if (searchTimeout) clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => loadPage(0, true), 350);
            });
        };
        bindFilter("sf-lot", "lot_name");
        bindFilter("sf-bloque", "bloque");
        bindFilter("sf-atado", "atado");
        bindFilter("sf-alto", "alto_min");
        bindFilter("sf-ancho", "ancho_min");

        // Carga inicial
        loadPage(0, true);
    }

    destroyPopup() {
        if (this._popupObserver) {
            this._popupObserver.disconnect();
            this._popupObserver = null;
        }
        if (this._popupKeyHandler) {
            document.removeEventListener("keydown", this._popupKeyHandler);
            this._popupKeyHandler = null;
        }
        if (this._popupRoot) {
            this._popupRoot.remove();
            this._popupRoot = null;
        }
    }
}

registry.category("fields").add("stone_expand_button", {
    component: StoneExpandButton,
    displayName: "Botón Selección Piedra",
});

export const stoneOrderLineListView = { ...listView };
registry.category("views").add("stone_order_line_list", stoneOrderLineListView);```

## ./static/src/components/stone_line_list/stone_line_list.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <!-- 
        Template del botón toggle.
        El popup se renderiza como DOM puro en document.body (ver stone_line_list.js),
        por lo que no hay template OWL para él aquí.
    -->
    <t t-name="sale_stone_selection.StoneExpandButton" owl="1">
        <div class="stone-field-wrapper" t-on-click="handleToggle">
            <button class="stone-toggle-btn" t-att-class="state.isExpanded ? 'active' : ''"
                    title="Ver/ocultar placas seleccionadas">
                <i class="fa fa-th-large" t-if="!state.isExpanded"/>
                <i class="fa fa-chevron-up" t-if="state.isExpanded"/>
                <span t-if="state.selectedCount > 0 and !state.isExpanded" 
                      class="stone-count-badge">
                    <t t-esc="state.selectedCount"/>
                </span>
            </button>
        </div>
    </t>
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
            assignedLots: [],
            filters: { lot_name: '', bloque: '', atado: '' },
            error: null
        });
        this.searchTimeout = null;

        onWillStart(async () => {
            await this.loadInventory();
        });

        onWillUpdateProps(async (nextProps) => {
            const oldId = this._extractId(this.props.record.data.product_id);
            const newId = this._extractId(nextProps.record.data.product_id);
            if (oldId !== newId) {
                await this.loadInventory(nextProps);
            }
        });
    }

    _extractId(field) {
        if (!field) return null;
        if (typeof field === 'number') return field;
        if (Array.isArray(field)) return field[0];
        if (typeof field === 'object' && field.id) return field.id;
        if (typeof field === 'object' && field[0]) return field[0];
        return null;
    }

    _extractIdName(field) {
        if (!field) return null;
        if (Array.isArray(field)) return field;
        if (typeof field === 'object' && field.id) {
            return [field.id, field.display_name || field.name || ''];
        }
        return null;
    }

    _getAssignedLotIds(props = this.props) {
        const lines = props.record.data.move_line_ids;
        const ids = [];
        if (lines && lines.records) {
            for (const line of lines.records) {
                const lotId = this._extractId(line.data.lot_id);
                if (lotId) ids.push(lotId);
            }
        }
        return ids;
    }

    _getAssignedLotsData(props = this.props) {
        const lines = props.record.data.move_line_ids;
        const lotsData = [];
        if (lines && lines.records) {
            for (const line of lines.records) {
                const lotIdName = this._extractIdName(line.data.lot_id);
                const locIdName = this._extractIdName(line.data.location_id);
                if (lotIdName && lotIdName[0]) {
                    lotsData.push({
                        id: `assigned_${lotIdName[0]}`,
                        lot_id: lotIdName,
                        quantity: line.data.quantity || 0,
                        reserved_quantity: line.data.quantity || 0,
                        location_id: locIdName || false,
                        x_bloque: '',
                        x_atado: '',
                        x_alto: 0,
                        x_ancho: 0,
                        x_grosor: 0,
                        x_tipo: '',
                        x_color: '',
                        x_origen: '',
                        x_pedimento: '',
                        x_detalles_placa: '',
                        _isAssigned: true
                    });
                }
            }
        }
        return lotsData;
    }

    async loadInventory(props = null) {
        const currentProps = props || this.props;

        if (!currentProps || !currentProps.record || !currentProps.record.data) {
            console.warn("No hay props/record disponible");
            this.state.isLoading = false;
            return;
        }

        const recordData = currentProps.record.data;
        const productId = this._extractId(recordData.product_id);

        this.state.isLoading = true;
        this.state.error = null;

        if (!productId) {
            this.state.quants = [];
            this.state.assignedLots = [];
            this.state.isLoading = false;
            return;
        }

        const assignedLotIds = this._getAssignedLotIds(currentProps);
        const assignedLotsData = this._getAssignedLotsData(currentProps);

        try {
            const quants = await this.orm.call('stock.quant', 'search_stone_inventory_for_so', [], {
                product_id: productId,
                filters: this.state.filters,
                current_lot_ids: assignedLotIds
            });

            const quantsMap = new Map();
            for (const q of (quants || [])) {
                if (q.lot_id) quantsMap.set(q.lot_id[0], q);
            }

            const enrichedQuants = (quants || []).map(q => ({
                ...q,
                _isAssigned: q.lot_id ? assignedLotIds.includes(q.lot_id[0]) : false
            }));

            for (const assigned of assignedLotsData) {
                const lotId = assigned.lot_id[0];
                if (!quantsMap.has(lotId)) {
                    try {
                        const lotData = await this.orm.read('stock.lot', [lotId], [
                            'name', 'x_bloque', 'x_atado', 'x_alto', 'x_ancho',
                            'x_grosor', 'x_tipo', 'x_color', 'x_origen',
                            'x_pedimento', 'x_detalles_placa'
                        ]);
                        if (lotData && lotData[0]) {
                            const lot = lotData[0];
                            enrichedQuants.unshift({
                                ...assigned,
                                lot_id: [lotId, lot.name],
                                x_bloque: lot.x_bloque || '',
                                x_atado: lot.x_atado || '',
                                x_alto: lot.x_alto || 0,
                                x_ancho: lot.x_ancho || 0,
                                x_grosor: lot.x_grosor || 0,
                                x_tipo: lot.x_tipo || '',
                                x_color: lot.x_color || '',
                                x_origen: lot.x_origen || '',
                                x_pedimento: lot.x_pedimento || '',
                                x_detalles_placa: lot.x_detalles_placa || '',
                                _isAssigned: true
                            });
                        }
                    } catch (e) {
                        enrichedQuants.unshift(assigned);
                    }
                }
            }

            this.state.quants = enrichedQuants;
            this.state.assignedLots = assignedLotIds;

        } catch (e) {
            console.error("Error en loadInventory:", e);
            this.state.error = e.message || "Error cargando datos";
            this.state.quants = assignedLotsData;
            this.state.assignedLots = assignedLotIds;
        } finally {
            this.state.isLoading = false;
        }
    }

    get allItems() {
        return [...this.state.quants].sort((a, b) => {
            if (a._isAssigned && !b._isAssigned) return -1;
            if (!a._isAssigned && b._isAssigned) return 1;
            const bla = a.x_bloque || 'zzz';
            const blb = b.x_bloque || 'zzz';
            return bla.localeCompare(blb);
        });
    }

    get selectedCount() {
        return this.state.assignedLots.length;
    }

    get selectedTotalArea() {
        let total = 0;
        for (const q of this.state.quants) {
            if (q._isAssigned) total += q.quantity || 0;
        }
        return total.toFixed(2);
    }

    isLotSelected(lotId) {
        return this.state.assignedLots.includes(lotId);
    }

    async _getFullLotQuantity(lotId, productId, locationId) {
        try {
            const quants = await this.orm.searchRead(
                'stock.quant',
                [
                    ['lot_id', '=', lotId],
                    ['product_id', '=', productId],
                    ['location_id', 'child_of', locationId],
                    ['quantity', '>', 0]
                ],
                ['quantity', 'location_id'],
                { limit: 1 }
            );

            if (quants && quants.length > 0) {
                return {
                    quantity: quants[0].quantity,
                    location_id: quants[0].location_id[0]
                };
            }

            // Fallback: cualquier ubicación interna
            const quantsFallback = await this.orm.searchRead(
                'stock.quant',
                [
                    ['lot_id', '=', lotId],
                    ['product_id', '=', productId],
                    ['location_id.usage', '=', 'internal'],
                    ['quantity', '>', 0]
                ],
                ['quantity', 'location_id'],
                { limit: 1 }
            );

            if (quantsFallback && quantsFallback.length > 0) {
                return {
                    quantity: quantsFallback[0].quantity,
                    location_id: quantsFallback[0].location_id[0]
                };
            }

            return null;
        } catch (e) {
            console.error("Error obteniendo cantidad del lote:", e);
            return null;
        }
    }

    async toggleLot(quant) {
        if (!quant.lot_id) return;

        const lotId = quant.lot_id[0];
        const isCurrentlySelected = this.isLotSelected(lotId);
        const recordData = this.props.record.data;
        const lines = recordData.move_line_ids;
        const productId = this._extractId(recordData.product_id);

        try {
            if (isCurrentlySelected) {
                // ── DESELECCIONAR ─────────────────────────────────────────────
                if (lines && lines.records) {
                    const lineRecord = lines.records.find(
                        line => this._extractId(line.data.lot_id) === lotId
                    );
                    if (lineRecord) {
                        await this.props.record.update({
                            move_line_ids: [[2, lineRecord.id, 0]]
                        });
                    }
                }
            } else {
                // ── SELECCIONAR ───────────────────────────────────────────────
                const locationId = this._extractId(recordData.location_id);
                const locationDestId = this._extractId(recordData.location_dest_id);

                let fullQty = quant.quantity;
                let sourceLocationId = quant.location_id ? quant.location_id[0] : locationId;

                if (productId && locationId) {
                    const realData = await this._getFullLotQuantity(lotId, productId, locationId);
                    if (realData) {
                        fullQty = realData.quantity;
                        sourceLocationId = realData.location_id;
                        console.log(`[STONE] Cantidad REAL del lote ${lotId}: ${fullQty} m²`);
                    }
                }

                const newLine = {
                    lot_id: lotId,
                    quantity: fullQty,
                    product_id: productId,
                    location_id: sourceLocationId || locationId,
                    location_dest_id: locationDestId,
                };

                await this.props.record.update({
                    move_line_ids: [[0, 0, newLine]]
                });
            }

            // Refrescar inventario para reflejar el nuevo estado
            await this.loadInventory();

        } catch (e) {
            console.error("[STONE] Error en toggleLot:", e);
            this.state.error = e.message || "Error al actualizar";
        }
    }

    onFilterChange(key, value) {
        this.state.filters[key] = value;
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => this.loadInventory(), 400);
    }

    async onRefresh() {
        await this.loadInventory();
    }
}

StoneMoveGridField.template = "sale_stone_selection.StoneMoveGridField";
StoneMoveGridField.props = { ...standardFieldProps };

registry.category("fields").add("stone_move_grid", {
    component: StoneMoveGridField,
    displayName: "Stone Move Grid",
});```

## ./static/src/components/stone_move_grid/stone_move_grid.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">
    <t t-name="sale_stone_selection.StoneMoveGridField" owl="1">
        <div class="o_stone_move_panel">
            
            <!-- HEADER -->
            <div class="stone-header">
                <div class="input-group input-group-sm" style="width: auto;">
                    <span class="input-group-text">Lote</span>
                    <input type="text" class="form-control" style="width:120px;" 
                           placeholder="Buscar..."
                           t-model="state.filters.lot_name" 
                           t-on-input="(e) => this.onFilterChange('lot_name', e.target.value)"/>
                </div>
                <div class="input-group input-group-sm" style="width: auto;">
                    <span class="input-group-text">Bloque</span>
                    <input type="text" class="form-control" style="width:100px;" 
                           t-model="state.filters.bloque" 
                           t-on-input="(e) => this.onFilterChange('bloque', e.target.value)"/>
                </div>
                <div class="input-group input-group-sm" style="width: auto;">
                    <span class="input-group-text">Atado</span>
                    <input type="text" class="form-control" style="width:80px;" 
                           t-model="state.filters.atado" 
                           t-on-input="(e) => this.onFilterChange('atado', e.target.value)"/>
                </div>
                
                <div class="ms-auto d-flex align-items-center gap-3">
                    <span class="text-muted">
                        <t t-esc="state.quants.length"/> disponibles
                    </span>
                    <span class="text-success fw-bold">
                        <t t-esc="selectedCount"/> seleccionadas
                    </span>
                    <span class="text-primary fw-bold">
                        <t t-esc="selectedTotalArea"/> m²
                    </span>
                    <button class="btn btn-sm btn-outline-secondary" t-on-click="onRefresh" title="Actualizar">
                        <i class="fa fa-refresh" t-att-class="state.isLoading ? 'fa-spin' : ''"/>
                    </button>
                </div>
            </div>

            <!-- BODY (SCROLLABLE) -->
            <div class="stone-body">
                
                <div t-if="state.isLoading" class="stone-empty">
                    <i class="fa fa-spinner fa-spin fa-2x text-muted"/>
                    <div class="mt-2 text-muted">Cargando...</div>
                </div>

                <div t-elif="state.error" class="stone-empty">
                    <i class="fa fa-exclamation-triangle fa-2x text-danger"/>
                    <div class="mt-2 text-danger"><t t-esc="state.error"/></div>
                </div>

                <div t-elif="state.quants.length === 0" class="stone-empty">
                    <i class="fa fa-inbox fa-2x text-muted"/>
                    <div class="mt-2 text-muted">No hay placas disponibles</div>
                </div>

                <table t-else="" class="stone-table">
                    <thead>
                        <tr>
                            <th class="col-check">✓</th>
                            <th>Lote</th>
                            <th>Bloque</th>
                            <th>Atado</th>
                            <th class="text-center">Alto</th>
                            <th class="text-center">Ancho</th>
                            <th class="text-center">Espesor</th>
                            <th class="text-end">M²</th>
                            <th>Tipo</th>
                            <th>Color</th>
                            <th>Ubicación</th>
                            <th>Origen</th>
                            <th>Pedimento</th>
                            <th>Notas</th>
                        </tr>
                    </thead>
                    <tbody>
                        <t t-foreach="allItems" t-as="q" t-key="q.id">
                            <t t-set="isSelected" t-value="isLotSelected(q.lot_id ? q.lot_id[0] : 0)"/>
                            <tr t-on-click="() => this.toggleLot(q)" 
                                t-att-class="isSelected ? 'row-selected' : ''">
                                
                                <td class="col-check">
                                    <!-- Pointer events none para que el click pase al TR -->
                                    <input type="checkbox" 
                                           class="form-check-input"
                                           style="pointer-events: none;"
                                           t-att-checked="isSelected"/>
                                </td>
                                <td class="fw-bold font-monospace">
                                    <t t-esc="q.lot_id ? q.lot_id[1] : '-'"/>
                                </td>
                                <td><t t-esc="q.x_bloque or '-'"/></td>
                                <td><t t-esc="q.x_atado or '-'"/></td>
                                <td class="text-center">
                                    <t t-esc="q.x_alto ? q.x_alto.toFixed(0) : '-'"/>
                                </td>
                                <td class="text-center">
                                    <t t-esc="q.x_ancho ? q.x_ancho.toFixed(0) : '-'"/>
                                </td>
                                <td class="text-center">
                                    <t t-esc="q.x_grosor or '-'"/>
                                </td>
                                <td class="text-end fw-bold">
                                    <t t-esc="q.quantity ? q.quantity.toFixed(2) : '0.00'"/>
                                </td>
                                <td><t t-esc="q.x_tipo or '-'"/></td>
                                <td><t t-esc="q.x_color or '-'"/></td>
                                <td class="text-muted">
                                    <t t-esc="(q.location_id and q.location_id[1]) ? q.location_id[1].split('/').pop() : '-'"/>
                                </td>
                                <td><t t-esc="q.x_origen or '-'"/></td>
                                <td class="font-monospace text-muted">
                                    <t t-esc="q.x_pedimento or '-'"/>
                                </td>
                                <td>
                                    <i t-if="q.x_detalles_placa" 
                                       class="fa fa-exclamation-triangle text-warning" 
                                       t-att-title="q.x_detalles_placa"/>
                                    <span t-else="" class="text-muted">-</span>
                                </td>
                            </tr>
                        </t>
                    </tbody>
                </table>
            </div>

            <!-- FOOTER -->
            <div class="stone-footer">
                <span class="text-muted">
                    <i class="fa fa-info-circle me-1"/>
                    Clic en fila para seleccionar/deseleccionar
                </span>
                <span>
                    <strong><t t-esc="selectedCount"/></strong> placas = 
                    <strong><t t-esc="selectedTotalArea"/></strong> m²
                </span>
            </div>
        </div>
    </t>
</templates>```

## ./static/src/scss/stone_styles.scss
```scss
// ═══════════════════════════════════════════════════════════════════════════
// STONE SELECTION — Estilos principales
// ═══════════════════════════════════════════════════════════════════════════

// Variables de diseño
$stone-primary: #2c5282;       // Azul profundo para piedra
$stone-primary-light: #3182ce;
$stone-accent: #68d391;        // Verde para seleccionados
$stone-danger: #fc8181;
$stone-warn: #f6ad55;
$stone-bg: #f7fafc;
$stone-border: #e2e8f0;
$stone-text: #2d3748;
$stone-muted: #718096;
$stone-radius: 8px;
$stone-radius-sm: 5px;

// ═══════════════════════════════════════════════════════════════════════════
// BOTÓN TOGGLE EN LA LISTA
// ═══════════════════════════════════════════════════════════════════════════
.stone-field-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
}

.stone-toggle-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: 1.5px solid $stone-border;
    border-radius: $stone-radius-sm;
    background: white;
    color: $stone-primary;
    cursor: pointer;
    transition: all 0.15s ease;
    position: relative;
    padding: 0;

    &:hover {
        border-color: $stone-primary-light;
        background: #ebf8ff;
        color: $stone-primary-light;
        transform: scale(1.08);
    }

    &.active {
        background: $stone-primary;
        border-color: $stone-primary;
        color: white;
    }

    i { font-size: 13px; }
}

.stone-count-badge {
    position: absolute;
    top: -6px;
    right: -6px;
    background: $stone-accent;
    color: #1a202c;
    font-size: 9px;
    font-weight: 700;
    min-width: 16px;
    height: 16px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 3px;
    line-height: 1;
    border: 1.5px solid white;
}

// ═══════════════════════════════════════════════════════════════════════════
// FILA DE SELECCIONADAS (inline en la lista)
// ═══════════════════════════════════════════════════════════════════════════
.stone-selected-row td.stone-selected-cell {
    padding: 0 !important;
    background: #f0f7ff;
    border-top: 2px solid $stone-primary;
    border-bottom: 2px solid $stone-border;
}

.stone-selected-container {
    background: white;
    border-radius: 0;
    overflow: hidden;
}

.stone-selected-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    background: $stone-bg;
    border-bottom: 1px solid $stone-border;
}

.stone-selected-title {
    font-size: 12px;
    font-weight: 600;
    color: $stone-primary;
    display: flex;
    align-items: center;

    i { color: $stone-accent; }
}

.stone-selected-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: $stone-primary;
    color: white;
    font-size: 10px;
    font-weight: 700;
    min-width: 18px;
    height: 18px;
    border-radius: 9px;
    padding: 0 4px;
    margin-left: 6px;
}

.stone-add-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 5px 12px;
    background: $stone-primary;
    color: white;
    border: none;
    border-radius: $stone-radius-sm;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;

    &:hover {
        background: $stone-primary-light;
    }

    i { font-size: 10px; }
}

.stone-selected-body {
    max-height: 280px;
    overflow-y: auto;
    overflow-x: auto;

    &::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    &::-webkit-scrollbar-thumb {
        background: #cbd5e0;
        border-radius: 3px;
    }
}

.stone-no-selection {
    padding: 16px 14px;
    font-size: 12px;
    color: $stone-muted;
    display: flex;
    align-items: center;
    gap: 6px;
}

.stone-table-loading {
    padding: 20px;
    text-align: center;
    color: $stone-muted;
    font-size: 12px;
}

// Tabla de seleccionadas (compacta)
.stone-sel-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11.5px;

    thead tr {
        background: #f8fafc;
    }

    th {
        padding: 6px 8px;
        text-align: left;
        font-weight: 600;
        font-size: 10.5px;
        text-transform: uppercase;
        color: $stone-muted;
        border-bottom: 1px solid $stone-border;
        white-space: nowrap;

        &.col-num { text-align: right; }
        &.col-act { text-align: center; width: 36px; }
    }

    tbody tr {
        transition: background 0.1s;

        &:hover {
            background: #f7fafc;
        }

        &:not(:last-child) td {
            border-bottom: 1px solid #f0f4f8;
        }
    }

    td {
        padding: 6px 8px;
        color: $stone-text;
        vertical-align: middle;

        &.col-num { text-align: right; font-variant-numeric: tabular-nums; }
        &.col-act { text-align: center; }
    }

    .cell-lot {
        font-family: 'Courier New', monospace;
        font-size: 11px;
        font-weight: 600;
        color: $stone-primary;
    }

    tfoot .stone-total-row {
        background: $stone-bg;

        td {
            padding: 7px 8px;
            border-top: 2px solid $stone-border;
            font-size: 12px;
        }
    }
}

.stone-remove-btn {
    width: 22px;
    height: 22px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid #fed7d7;
    border-radius: 4px;
    background: #fff5f5;
    color: #e53e3e;
    cursor: pointer;
    transition: all 0.12s;
    padding: 0;

    &:hover {
        background: #fc8181;
        border-color: #fc8181;
        color: white;
    }

    i { font-size: 10px; }
}

.fw-semibold { font-weight: 600; }

// ═══════════════════════════════════════════════════════════════════════════
// POPUP FULLSCREEN
// ═══════════════════════════════════════════════════════════════════════════
.stone-popup-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(2px);
    z-index: 10500;
    display: flex;
    align-items: stretch;
    justify-content: stretch;
    padding: 16px;
    box-sizing: border-box;
}

.stone-popup-container {
    background: white;
    border-radius: 12px;
    width: 100%;
    height: 100%;
    max-width: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    animation: stonePopupIn 0.2s ease;
}

@keyframes stonePopupIn {
    from {
        opacity: 0;
        transform: scale(0.97) translateY(8px);
    }
    to {
        opacity: 1;
        transform: scale(1) translateY(0);
    }
}

// Header del popup
.stone-popup-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    background: $stone-primary;
    color: white;
    flex: 0 0 auto;
}

.stone-popup-title {
    font-size: 15px;
    font-weight: 700;
    display: flex;
    align-items: center;

    i { font-size: 16px; }
}

.stone-popup-subtitle {
    font-size: 13px;
    font-weight: 400;
    opacity: 0.85;
    margin-left: 4px;
}

.stone-popup-header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}

.stone-badge-selected {
    background: rgba(255, 255, 255, 0.2);
    color: white;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 4px;
}

// Botones del popup
.stone-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 7px 14px;
    border-radius: $stone-radius-sm;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    border: none;

    i { font-size: 11px; }

    &.stone-btn-primary {
        background: $stone-accent;
        color: #1a202c;

        &:hover { background: darken(#68d391, 8%); }
    }

    &.stone-btn-ghost {
        background: rgba(255, 255, 255, 0.15);
        color: white;
        border: 1px solid rgba(255, 255, 255, 0.3);

        &:hover { background: rgba(255, 255, 255, 0.25); }
    }
}

// Filtros del popup
.stone-popup-filters {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    padding: 10px 16px;
    background: $stone-bg;
    border-bottom: 1px solid $stone-border;
    flex: 0 0 auto;
    flex-wrap: wrap;
}

.stone-filter-group {
    display: flex;
    flex-direction: column;
    gap: 3px;

    label {
        font-size: 9.5px;
        font-weight: 700;
        text-transform: uppercase;
        color: $stone-muted;
        letter-spacing: 0.03em;
    }
}

.stone-filter-input {
    padding: 5px 8px;
    border: 1.5px solid $stone-border;
    border-radius: $stone-radius-sm;
    font-size: 12px;
    width: 130px;
    color: $stone-text;
    transition: border-color 0.15s;
    background: white;

    &.stone-filter-sm { width: 70px; }

    &:focus {
        outline: none;
        border-color: $stone-primary-light;
        box-shadow: 0 0 0 2px rgba($stone-primary-light, 0.2);
    }

    &::placeholder { color: #a0aec0; }
}

.stone-filter-spacer {
    flex: 1;
}

.stone-filter-stats {
    display: flex;
    align-items: center;
    padding-bottom: 2px;
}

.stone-filter-stat-loading,
.stone-filter-stat-count {
    font-size: 11.5px;
    color: $stone-muted;
    display: flex;
    align-items: center;
    gap: 4px;
}

.stone-filter-stat-count {
    color: $stone-primary;
    font-weight: 600;
}

// Body del popup (scrolleable)
.stone-popup-body {
    flex: 1 1 auto;
    overflow-y: auto;
    overflow-x: auto;
    min-height: 0;
    background: white;
    position: relative;

    &::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    &::-webkit-scrollbar-thumb {
        background: #cbd5e0;
        border-radius: 4px;
    }
    &::-webkit-scrollbar-track {
        background: #f7fafc;
    }
}

.stone-empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 60%;
    min-height: 250px;
    color: #a0aec0;
    gap: 12px;

    i { font-size: 40px; }
}

.stone-empty-text {
    font-size: 14px;
    color: $stone-muted;
}

// Tabla del popup
.stone-popup-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 12px;

    thead {
        position: sticky;
        top: 0;
        z-index: 10;

        tr { background: $stone-bg; }

        th {
            padding: 9px 10px;
            text-align: left;
            font-size: 10.5px;
            font-weight: 700;
            text-transform: uppercase;
            color: $stone-muted;
            letter-spacing: 0.04em;
            border-bottom: 2px solid $stone-border;
            white-space: nowrap;
            background: $stone-bg;

            &.col-chk {
                width: 44px;
                text-align: center;
            }

            &.col-num {
                text-align: right;
                width: 60px;
            }
        }
    }

    tbody {
        tr {
            cursor: pointer;
            transition: background 0.08s;

            &:hover { background: #f0f7ff; }

            &.row-sel {
                background: #ebfaf1;

                &:hover { background: #d4f4e0; }

                td:first-child {
                    border-left: 3px solid $stone-accent;
                }
            }

            td {
                padding: 8px 10px;
                border-bottom: 1px solid #f0f4f8;
                vertical-align: middle;
                color: $stone-text;

                &.col-chk {
                    text-align: center;
                    width: 44px;
                }

                &.col-num {
                    text-align: right;
                    font-variant-numeric: tabular-nums;
                }

                &.cell-lot {
                    font-family: 'Courier New', monospace;
                    font-size: 11.5px;
                    font-weight: 700;
                    color: $stone-primary;
                }

                &.cell-loc {
                    color: $stone-muted;
                    font-size: 11px;
                }
            }
        }
    }
}

// Checkbox personalizado en popup
.stone-chkbox {
    width: 18px;
    height: 18px;
    border: 2px solid #cbd5e0;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto;
    transition: all 0.12s;
    background: white;

    i {
        font-size: 10px;
        color: white;
    }

    &.checked {
        background: $stone-accent;
        border-color: darken(#68d391, 10%);
    }
}

// Tags de estado
.stone-tag {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 600;
    white-space: nowrap;

    &.stone-tag-ok {
        background: #c6f6d5;
        color: #276749;
    }

    &.stone-tag-warn {
        background: #fefcbf;
        color: #744210;
    }

    &.stone-tag-free {
        background: #edf2f7;
        color: #718096;
        border: 1px solid #e2e8f0;
    }
}

// Sentinel de infinite scroll
.stone-scroll-sentinel {
    padding: 16px;
    text-align: center;
}

.stone-loading-more {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: $stone-muted;
    font-size: 12px;
    padding: 8px;
}

.stone-scroll-hint {
    color: #a0aec0;
    font-size: 11px;
    animation: hintBounce 2s infinite;
}

@keyframes hintBounce {
    0%, 100% { opacity: 0.5; transform: translateY(0); }
    50% { opacity: 1; transform: translateY(3px); }
}

// Footer del popup
.stone-popup-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    background: $stone-bg;
    border-top: 1px solid $stone-border;
    flex: 0 0 auto;
}

.stone-footer-info {
    font-size: 12px;
    color: $stone-muted;
}

.stone-footer-actions {
    display: flex;
    gap: 8px;
    align-items: center;

    .stone-btn {
        // Adaptar colores para el footer (fondo claro)
        &.stone-btn-ghost {
            background: white;
            color: $stone-muted;
            border: 1.5px solid $stone-border;

            &:hover {
                background: $stone-bg;
                color: $stone-text;
            }
        }

        &.stone-btn-primary {
            background: $stone-primary;
            color: white;

            &:hover { background: $stone-primary-light; }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MODAL FULLSCREEN: Stone Move Grid (para Picking)
// ═══════════════════════════════════════════════════════════════════════════
.o_dialog:has(.o_stone_move_panel),
.modal-dialog:has(.o_stone_move_panel) {
    max-width: 98vw !important;
    width: 98vw !important;
    height: 92vh !important;
    margin: 2vh auto !important;
    display: flex !important;
    flex-direction: column !important;
}

.o_dialog:has(.o_stone_move_panel) .modal-content,
.modal-dialog:has(.o_stone_move_panel) .modal-content {
    height: 100% !important;
    max-height: 100% !important;
    display: flex !important;
    flex-direction: column !important;
    overflow: hidden !important;
}

.o_dialog:has(.o_stone_move_panel) .modal-body,
.modal-dialog:has(.o_stone_move_panel) .modal-body {
    flex: 1 1 auto !important;
    padding: 0 !important;
    overflow: hidden !important;
    display: flex !important;
    flex-direction: column !important;
    min-height: 0 !important;
}

.o_stone_move_panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
    background: #fff;
    overflow: hidden;
}

.stone-header {
    flex: 0 0 auto;
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    padding: 10px 16px;
    background: $stone-bg;
    border-bottom: 1px solid $stone-border;
    align-items: center;
    z-index: 20;
}

.stone-body {
    flex: 1 1 auto;
    overflow-y: auto !important;
    overflow-x: auto;
    min-height: 0;
    background: #fff;
    position: relative;

    &::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    &::-webkit-scrollbar-thumb {
        background: #ced4da;
        border-radius: 4px;
    }
}

.stone-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 200px;
    color: #6c757d;
}

.stone-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 12px;

    thead {
        position: sticky;
        top: 0;
        z-index: 10;

        tr { background: $stone-bg; }

        th {
            position: sticky;
            top: 0;
            background: $stone-bg;
            padding: 10px 8px;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            color: #495057;
            border-bottom: 2px solid $stone-border;
            white-space: nowrap;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);

            &.col-check {
                width: 40px;
                text-align: center;
            }
        }
    }

    tbody {
        tr {
            cursor: pointer;
            transition: background-color 0.1s;

            &:hover { background-color: #f1f3f5; }

            &.row-selected {
                background-color: #ebfaf1;

                &:hover { background-color: #d4f4e0; }

                td:first-child { border-left: 3px solid #28a745; }
            }
        }

        td {
            padding: 8px;
            border-bottom: 1px solid #eee;
            vertical-align: middle;
            background-color: inherit;
        }

        td.col-check {
            width: 40px;
            text-align: center;
        }
    }

    .form-check-input {
        margin: 0;
        cursor: pointer;

        &:checked {
            background-color: #28a745;
            border-color: #28a745;
        }
    }
}

.stone-footer {
    flex: 0 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    background: $stone-bg;
    border-top: 1px solid $stone-border;
    font-size: 13px;
    z-index: 20;
}

// Legacy
.o_stone_toggle_btn {
    color: #495057 !important;
    &:hover { color: #212529 !important; }
}
.o_stone_details_row_tr td {
    background-color: $stone-bg;
    padding: 0 !important;
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

