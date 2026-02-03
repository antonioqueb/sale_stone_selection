# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.stock_lot_dimensions.models.utils.picking_cleaner import PickingLotCleaner
except ImportError:
    PickingLotCleaner = None

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Confirmación con asignación estricta de lotes seleccionados.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE ORDER CONFIRM] INICIO - Orden(es): %s", self.mapped('name'))
        
        # 1. GUARDAR los lotes ANTES de confirmar
        lines_lots_map = {}
        for order in self:
            for line in order.order_line.filtered(lambda l: l.lot_ids):
                lines_lots_map[line.id] = line.lot_ids.ids.copy()
                _logger.info("[STONE] Guardando lotes línea %s: %s", line.id, lines_lots_map[line.id])
        
        # 2. Confirmar con contexto de protección TOTAL
        ctx = dict(self.env.context, 
                   is_stone_confirming=True, 
                   skip_stone_sync=True,
                   skip_back_sync=True)
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        
        # 3. Limpiar asignaciones automáticas FIFO
        self.with_context(ctx)._clear_auto_assigned_lots()
        
        # 4. Asignar nuestros lotes seleccionados
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
            if not pickings:
                continue

            for line in order.order_line:
                lot_ids = lines_lots_map.get(line.id, [])
                if not lot_ids:
                    continue
                    
                lots = self.env['stock.lot'].browse(lot_ids)
                _logger.info("[STONE] Asignando lotes %s a línea %s", lots.mapped('name'), line.id)
                self.with_context(ctx)._assign_stone_lots_to_picking(pickings, line, lots)
        
        # 5. RESTAURAR lot_ids en las líneas (por si algo los borró)
        for line_id, lot_ids in lines_lots_map.items():
            line = self.env['sale.order.line'].browse(line_id)
            if line.exists() and set(line.lot_ids.ids) != set(lot_ids):
                _logger.info("[STONE] Restaurando lot_ids en línea %s: %s", line_id, lot_ids)
                line.with_context(ctx).write({'lot_ids': [(6, 0, lot_ids)]})
        
        _logger.info("[STONE ORDER CONFIRM] FIN")
        _logger.info("=" * 80)
        return res

    def _clear_auto_assigned_lots(self):
        """Limpia las reservas automáticas FIFO de los pickings."""
        ctx = dict(self.env.context, skip_stone_sync=True, is_stone_confirming=True)
        
        for order in self:
            for picking in order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done']):
                for move in picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                    if move.move_line_ids:
                        _logger.info("[STONE] Limpiando %s move_lines de move %s", 
                                    len(move.move_line_ids), move.id)
                        move.move_line_ids.with_context(ctx).unlink()

    def _assign_stone_lots_to_picking(self, pickings, sale_line, lots):
        """
        Asigna los lotes seleccionados al picking.
        """
        product = sale_line.product_id
        if not lots:
            return

        ctx = dict(self.env.context, skip_stone_sync=True, is_stone_confirming=True)

        for picking in pickings:
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id 
                and m.state not in ['done', 'cancel']
            )
            
            if not moves:
                continue
            
            for move in moves:
                for lot in lots:
                    # Buscar quant
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

    # =========================================================================
    # Mantener los métodos de diagnóstico para copy
    # =========================================================================
    
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