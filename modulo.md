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
        CRÍTICO: Asigna el lote COMPLETO, no cantidades parciales.
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
        res = super(StockMove, self)._recompute_state()
        if self.env.context.get('is_stone_confirming') or self.env.context.get('skip_stone_sync'):
            return res
        return res

    def _sync_stone_sale_lines(self):
        """
        Recalcula los lotes en la línea de venta basándose en las líneas del movimiento actual.
        Trigger: Picking -> SO
        
        CRÍTICO: Esta sincronización asegura que cuando se cambian lotes en el Picking,
        la Orden de Venta refleje esos cambios.
        
        FIX BACKORDER: Al sincronizar, no solo miramos el move actual sino TODOS
        los moves de la SO line (incluyendo backorders) para no perder lotes pendientes.
        """
        # Evitamos sincronizar si estamos en medio de la confirmación inicial
        if self.env.context.get('is_stone_confirming'):
            _logger.info("[STONE SYNC] Saltando sync durante confirmación inicial")
            return

        for move in self:
            if not move.sale_line_id:
                continue
            
            # Solo sincronizar si el movimiento no está finalizado
            if move.state in ['done', 'cancel']:
                _logger.info("[STONE SYNC] Movimiento %s ya finalizado, no sincronizando", move.id)
                continue
            
            sol = move.sale_line_id
            
            # ══════════════════════════════════════════════════════════════
            # FIX: Recopilar lotes de TODOS los moves de la SO line,
            # no solo del move actual. Esto incluye:
            # - Lotes en moves activos (confirmed/assigned/partially_available)
            # - Lotes en moves done (ya entregados)
            # - Lotes en backorders pendientes
            # ══════════════════════════════════════════════════════════════
            all_lot_ids = set()
            
            for sibling_move in sol.move_ids:
                if sibling_move.state == 'cancel':
                    continue
                
                for ml in sibling_move.move_line_ids:
                    if ml.lot_id:
                        all_lot_ids.add(ml.lot_id.id)
            
            # También incluir lotes de moves pendientes (sin move_lines aún,
            # como backorders recién creados que aún no se reservaron)
            # Estos los recuperamos de las fuentes originales de la SO line
            # solo si el move está pendiente y no tiene lines
            pending_moves = sol.move_ids.filtered(
                lambda m: m.state in ('confirmed', 'waiting', 'partially_available')
                and not m.move_line_ids
            )
            if pending_moves:
                # Si hay moves pendientes sin lines, preservar los lotes
                # que están en la SO line y no están en ningún move done/assigned
                existing_so_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()
                # Los que ya están en move_lines de otros moves
                accounted_lots = all_lot_ids.copy()
                # Los que faltan = están en SO pero no en ningún move_line
                unaccounted = existing_so_lots - accounted_lots
                if unaccounted:
                    _logger.info(
                        "[STONE SYNC] Preserving %d unaccounted lots from SO Line %s "
                        "for pending moves: %s",
                        len(unaccounted), sol.id, list(unaccounted)
                    )
                    all_lot_ids.update(unaccounted)
            
            # Verificar si hay cambios reales
            existing_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()
            
            if all_lot_ids == existing_lots:
                _logger.info("[STONE SYNC] Sin cambios en lotes para SO Line %s", sol.id)
                continue
            
            _logger.info("[STONE SYNC] Picking %s -> SO Line %s", 
                        move.picking_id.name if move.picking_id else 'N/A', sol.id)
            _logger.info("[STONE SYNC] Lotes anteriores: %s", sorted(existing_lots))
            _logger.info("[STONE SYNC] Lotes nuevos: %s", sorted(all_lot_ids))
            
            # Actualizamos la SO evitando disparar la sincronización inversa
            try:
                sol.with_context(skip_stone_sync_picking=True).write({
                    'lot_ids': [(6, 0, list(all_lot_ids))]
                })
                _logger.info("[STONE SYNC] ✓ Actualizado SO Line %s con %s lotes", 
                             sol.id, len(all_lot_ids))
            except Exception as e:
                _logger.error("[STONE SYNC] Error actualizando SO Line: %s", str(e))

    def write(self, vals):
        """
        Interceptar cambios en move_line_ids para sincronizar hacia SO
        """
        res = super(StockMove, self).write(vals)
        
        # Si cambiaron las líneas de movimiento y no estamos en sync, disparar sync
        if 'move_line_ids' in vals and not self.env.context.get('skip_stone_sync_so'):
            for move in self:
                if move.sale_line_id and move.state not in ['done', 'cancel']:
                    move._sync_stone_sale_lines()
        
        return res```

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
        Al crear líneas en el Picking (desde la Grilla o manualmente), 
        sincronizar hacia la Orden de Venta.
        """
        lines = super(StockMoveLine, self).create(vals_list)
        
        # Sincronizar solo si no venimos de la confirmación inicial o sync inverso
        if not self.env.context.get('skip_stone_sync_so') and not self.env.context.get('is_stone_confirming'):
            lines._sync_to_sale_order_line()
        
        return lines

    def write(self, vals):
        """
        Al modificar líneas (ej. cambiar cantidad o lote), sincronizar.
        """
        res = super(StockMoveLine, self).write(vals)
        
        # Si cambió el lote o la cantidad, sincronizar hacia SO
        if ('lot_id' in vals or 'quantity' in vals) and not self.env.context.get('skip_stone_sync_so'):
            self._sync_to_sale_order_line()
        
        return res

    def unlink(self):
        """
        Al borrar líneas en el Picking, quitar los lotes de la Orden de Venta.
        """
        # Antes de borrar, identificamos qué moves/sale_lines se verán afectados
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        res = super(StockMoveLine, self).unlink()
        
        if not self.env.context.get('skip_stone_sync_so') and not self.env.context.get('is_stone_confirming'):
            moves_to_sync._sync_stone_sale_lines()
        
        return res

    def _sync_to_sale_order_line(self):
        """
        Helper para disparar la sincronización desde las líneas hacia SO.
        Solo sincroniza movimientos que tienen línea de venta asociada.
        """
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        if moves_to_sync:
            _logger.info("[STONE SYNC] Sincronizando %s movimientos hacia SO", len(moves_to_sync))
            moves_to_sync._sync_stone_sale_lines()```

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
                # Detectar tipo de campo x_proveedor (puede ser Many2one o Char)
                x_proveedor_value = lot.x_proveedor if 'x_proveedor' in lot._fields else False
                if x_proveedor_value:
                    field_type = lot._fields.get('x_proveedor')
                    if field_type and field_type.type == 'many2one':
                        x_proveedor_display = x_proveedor_value.name if x_proveedor_value else ''
                    else:
                        # Es Char o Selection
                        x_proveedor_display = str(x_proveedor_value) if x_proveedor_value else ''
                else:
                    x_proveedor_display = ''
                
                lots_data[lot.id] = {
                    'name': lot.name,
                    # Dimensiones
                    'x_grosor': lot.x_grosor if 'x_grosor' in lot._fields else 0,
                    'x_alto': lot.x_alto if 'x_alto' in lot._fields else 0,
                    'x_ancho': lot.x_ancho if 'x_ancho' in lot._fields else 0,
                    'x_peso': lot.x_peso if 'x_peso' in lot._fields else 0,
                    # Clasificación
                    'x_tipo': lot.x_tipo if 'x_tipo' in lot._fields else '',
                    'x_numero_placa': lot.x_numero_placa if 'x_numero_placa' in lot._fields else '',
                    'x_bloque': lot.x_bloque if 'x_bloque' in lot._fields else '',
                    'x_atado': lot.x_atado if 'x_atado' in lot._fields else '',
                    'x_grupo': lot.x_grupo if 'x_grupo' in lot._fields else '',
                    'x_color': lot.x_color if 'x_color' in lot._fields else '',
                    # Logística
                    'x_pedimento': lot.x_pedimento if 'x_pedimento' in lot._fields else '',
                    'x_contenedor': lot.x_contenedor if 'x_contenedor' in lot._fields else '',
                    'x_referencia_proveedor': lot.x_referencia_proveedor if 'x_referencia_proveedor' in lot._fields else '',
                    'x_proveedor': x_proveedor_display,
                    'x_origen': lot.x_origen if 'x_origen' in lot._fields else '',
                    # Fotografías
                    'x_fotografia_principal': lot.x_fotografia_principal if 'x_fotografia_principal' in lot._fields else False,
                    'x_tiene_fotografias': lot.x_tiene_fotografias if 'x_tiene_fotografias' in lot._fields else False,
                    'x_cantidad_fotos': lot.x_cantidad_fotos if 'x_cantidad_fotos' in lot._fields else 0,
                    # Detalles
                    'x_detalles_placa': lot.x_detalles_placa if 'x_detalles_placa' in lot._fields else '',
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
                if (lotId) {
                    ids.push(lotId);
                }
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
                if (q.lot_id) {
                    quantsMap.set(q.lot_id[0], q);
                }
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
            if (q._isAssigned) {
                total += q.quantity || 0;
            }
        }
        return total.toFixed(2);
    }

    isLotSelected(lotId) {
        return this.state.assignedLots.includes(lotId);
    }

    /**
     * CORREGIDO: Obtener cantidad TOTAL del lote desde el servidor
     * para asegurar que se asigne el lote completo
     */
    async _getFullLotQuantity(lotId, productId, locationId) {
        try {
            // Buscar el quant real del servidor para obtener cantidad exacta
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
            
            // Fallback: buscar en cualquier ubicación interna
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
                // ═══════════════════════════════════════════════════════════════
                // DESELECCIONAR - Eliminar línea del movimiento
                // ═══════════════════════════════════════════════════════════════
                if (lines && lines.records) {
                    const lineRecord = lines.records.find(
                        line => this._extractId(line.data.lot_id) === lotId
                    );
                    
                    if (lineRecord) {
                        console.log(`[STONE] Eliminando lote ${lotId} del picking`);
                        await this.props.record.update({
                            move_line_ids: [[2, lineRecord.id, 0]]
                        });
                    }
                }
            } else {
                // ═══════════════════════════════════════════════════════════════
                // SELECCIONAR - CRÍTICO: Obtener cantidad COMPLETA del lote
                // ═══════════════════════════════════════════════════════════════
                const locationId = this._extractId(recordData.location_id);
                const locationDestId = this._extractId(recordData.location_dest_id);
                
                // IMPORTANTE: Obtener la cantidad real del servidor, no confiar en el cache local
                let fullQty = quant.quantity;
                let sourceLocationId = quant.location_id ? quant.location_id[0] : locationId;
                
                if (productId && locationId) {
                    const realData = await this._getFullLotQuantity(lotId, productId, locationId);
                    if (realData) {
                        fullQty = realData.quantity;
                        sourceLocationId = realData.location_id;
                        console.log(`[STONE] Cantidad REAL del lote ${lotId}: ${fullQty} m²`);```

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
                            <th class="text-center">Grosor</th>
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
// MODAL FULLSCREEN - Forzando estructura Flex
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
    overflow: hidden !important; /* Evita scroll en el modal completo */
}

.o_dialog:has(.o_stone_move_panel) .modal-body,
.modal-dialog:has(.o_stone_move_panel) .modal-body {
    flex: 1 1 auto !important;
    padding: 0 !important;
    overflow: hidden !important; /* El scroll lo maneja el panel interno */
    display: flex !important;
    flex-direction: column !important;
    min-height: 0 !important;
}

// ═══════════════════════════════════════════════════════════════════════════
// PANEL PRINCIPAL
// ═══════════════════════════════════════════════════════════════════════════
.o_stone_move_panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
    background: #fff;
    overflow: hidden;
}

// ═══════════════════════════════════════════════════════════════════════════
// HEADER (Fijo)
// ═══════════════════════════════════════════════════════════════════════════
.stone-header {
    flex: 0 0 auto; /* No encoger ni crecer */
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    padding: 10px 16px;
    background: #f8f9fa;
    border-bottom: 1px solid #dee2e6;
    align-items: center;
    z-index: 20;
}

// ═══════════════════════════════════════════════════════════════════════════
// BODY - SCROLL (Aquí ocurre el desplazamiento)
// ═══════════════════════════════════════════════════════════════════════════
.stone-body {
    flex: 1 1 auto; /* Ocupa el espacio restante */
    overflow-y: auto !important; /* Scroll vertical activado */
    overflow-x: auto;
    min-height: 0;
    background: #fff;
    position: relative;
    
    /* Scrollbar estilizado (opcional) */
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

// ═══════════════════════════════════════════════════════════════════════════
// TABLA (Sticky Header)
// ═══════════════════════════════════════════════════════════════════════════
.stone-table {
    width: 100%;
    border-collapse: separate; /* Necesario para sticky */
    border-spacing: 0;
    font-size: 12px;
    
    thead {
        position: sticky;
        top: 0;
        z-index: 10;
        
        tr {
            background: #f8f9fa;
        }
        
        th {
            position: sticky;
            top: 0;
            background: #f8f9fa; /* Fondo opaco vital para sticky */
            padding: 10px 8px;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
            white-space: nowrap;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        
        th.col-check {
            width: 40px;
            text-align: center;
        }
    }
    
    tbody {
        tr {
            cursor: pointer;
            transition: background-color 0.1s;
            
            &:hover {
                background-color: #f1f3f5;
            }
            
            &.row-selected {
                background-color: #e8f5e9;
                
                &:hover {
                    background-color: #c8e6c9;
                }
                
                td:first-child {
                    border-left: 3px solid #28a745;
                }
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

// ═══════════════════════════════════════════════════════════════════════════
// FOOTER (Fijo)
// ═══════════════════════════════════════════════════════════════════════════
.stone-footer {
    flex: 0 0 auto; /* No encoger ni crecer */
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    background: #f8f9fa;
    border-top: 1px solid #dee2e6;
    font-size: 13px;
    z-index: 20;
}

// LEGACY
.o_stone_toggle_btn {
    color: #495057 !important;
    &:hover { 
        color: #212529 !important; 
    }
}
.o_stone_details_row_tr td {
    background-color: #f8f9fa;
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

