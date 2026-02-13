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
        # NUEVO: Si la orden ya está confirmada, redirigir
        # =====================================================================
        for order in self:
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
        return super().copy(default)