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
        _logger.info("[STONE] ACTION_CONFIRM INICIO - Órdenes: %s", self.mapped('name'))
        
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
                _logger.info("[STONE] Guardando línea %s: lotes=%s", line.id, lot_ids)
        
        if not lines_lots_map:
            _logger.info("[STONE] No hay líneas con lotes, confirmación normal")
            return super().action_confirm()
        
        # 2. Confirmar con contexto que protege nuestros lotes
        ctx = dict(self.env.context,
                   skip_picking_clean=True,  # Evitar que el cleaner borre todo
                   protected_lot_ids=all_protected_lot_ids,
                   is_stone_confirming=True)
        
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        
        _logger.info("[STONE] Confirmación base completada")
        
        # 3. Limpiar SOLO los lotes NO protegidos y asignar los nuestros
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
            
            if not pickings:
                continue

            # Limpiar move_lines que NO son de nuestros lotes seleccionados
            for picking in pickings:
                for move in picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                    lines_to_remove = move.move_line_ids.filtered(
                        lambda ml: ml.lot_id.id not in all_protected_lot_ids
                    )
                    if lines_to_remove:
                        _logger.info("[STONE] Limpiando %s move_lines NO protegidas", len(lines_to_remove))
                        lines_to_remove.unlink()

            # Asignar nuestros lotes
            for line in order.order_line:
                line_data = lines_lots_map.get(line.id)
                if not line_data:
                    continue
                    
                lots = self.env['stock.lot'].browse(line_data['lot_ids'])
                _logger.info("[STONE] Asignando %s lotes a línea %s", len(lots), line.id)
                self.with_context(ctx)._assign_stone_lots_to_picking(pickings, line, lots)
        
        # 4. Restaurar lot_ids en las líneas
        for line_id, line_data in lines_lots_map.items():
            line = self.env['sale.order.line'].browse(line_id)
            if line.exists() and set(line.lot_ids.ids) != set(line_data['lot_ids']):
                _logger.info("[STONE] Restaurando lot_ids línea %s", line_id)
                line.with_context(ctx).write({'lot_ids': [(6, 0, line_data['lot_ids'])]})
        
        _logger.info("[STONE] ACTION_CONFIRM FIN")
        _logger.info("=" * 80)
        return res

    def _assign_stone_lots_to_picking(self, pickings, sale_line, lots):
        """Asigna los lotes seleccionados al picking."""
        product = sale_line.product_id
        if not lots:
            return

        ctx = dict(self.env.context, skip_stone_sync=True, skip_picking_clean=True)

        for picking in pickings:
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id 
                and m.state not in ['done', 'cancel']
            )
            
            if not moves:
                continue
            
            for move in moves:
                # Verificar qué lotes ya están asignados
                existing_lot_ids = move.move_line_ids.mapped('lot_id').ids
                
                for lot in lots:
                    # Si ya existe, no duplicar
                    if lot.id in existing_lot_ids:
                        _logger.info("[STONE] Lote %s ya asignado, omitiendo", lot.name)
                        continue
                    
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', product.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        _logger.warning("[STONE] Lote %s sin stock", lot.name)
                        continue
                    
                    available_qty = quant.quantity - quant.reserved_quantity
                    if available_qty <= 0:
                        _logger.warning("[STONE] Lote %s sin disponibilidad", lot.name)
                        continue
                    
                    move_line_vals = {
                        'move_id': move.id,
                        'picking_id': picking.id,
                        'product_id': product.id,
                        'product_uom_id': move.product_uom.id,
                        'lot_id': lot.id,
                        'location_id': quant.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'quantity': available_qty,
                    }
                    
                    try:
                        self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        _logger.info("[STONE] ✅ Move line creado: lote=%s, qty=%s", lot.name, available_qty)
                    except Exception as e:
                        _logger.error("[STONE] ❌ Error: %s", str(e))

    def copy_data(self, default=None):
        _logger.info("[STONE ORDER COPY_DATA] Orden: %s", self.name)
        return super().copy_data(default)

    def copy(self, default=None):
        _logger.info("[STONE ORDER COPY] Orden: %s", self.name)
        for line in self.order_line:
            _logger.info("[STONE ORDER COPY] Línea %s lot_ids: %s", line.id, line.lot_ids.ids)
        result = super().copy(default)
        for line in result.order_line:
            _logger.info("[STONE ORDER COPY] Nueva línea %s lot_ids: %s", line.id, line.lot_ids.ids)
        return result