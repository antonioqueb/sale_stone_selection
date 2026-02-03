# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

# Intentamos importar el Cleaner igual que en el módulo de Carrito
try:
    from odoo.addons.stock_lot_dimensions.models.utils.picking_cleaner import PickingLotCleaner
except ImportError:
    PickingLotCleaner = None

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Lógica robusta de confirmación:
        1. Confirmación estándar (Odoo genera Pickings y reserva FIFO).
        2. Limpieza de reservas automáticas (usando PickingLotCleaner).
        3. Asignación forzada de los lotes seleccionados visualmente.
        """
        # 1. Ejecutar confirmación estándar
        res = super(SaleOrder, self).action_confirm()
        
        # 2. Limpieza de reservas automáticas (Critico para evitar mezcla de lotes)
        self._clear_auto_assigned_lots()
        
        # 3. Asignación Estricta de Lotes Seleccionados
        for order in self:
            lines_with_stone = order.order_line.filtered(lambda l: l.lot_ids)
            if not lines_with_stone:
                continue

            pickings = order.picking_ids.filtered(
                lambda p: p.state not in ['cancel', 'done']
            )
            
            if not pickings:
                continue

            _logger.info(f"[STONE] Asignando lotes seleccionados para Orden {order.name}")
            for line in lines_with_stone:
                order._assign_stone_lots_strict(pickings, line)
        
        return res

    def _clear_auto_assigned_lots(self):
        """Limpia las reservas que Odoo hizo automáticamente por FIFO."""
        if PickingLotCleaner:
            _logger.info("[STONE] Ejecutando PickingLotCleaner...")
            cleaner = PickingLotCleaner(self.env)
            for order in self:
                if order.picking_ids:
                    cleaner.clear_pickings_lots(order.picking_ids)
        else:
            _logger.warning("[STONE] PickingLotCleaner no disponible. La limpieza podría ser incompleta.")

    def _assign_stone_lots_strict(self, pickings, line):
        """
        Crea las líneas de movimiento (stock.move.line) para los lotes seleccionados.
        """
        product = line.product_id
        selected_lots = line.lot_ids
        
        if not selected_lots:
            return

        for picking in pickings:
            moves = picking.move_ids.filtered(lambda m: m.product_id.id == product.id)
            
            for move in moves:
                # Nos aseguramos que esté limpio (por si el Cleaner falló o no existe)
                if move.move_line_ids:
                    move.move_line_ids.unlink()
                
                remaining_demand = move.product_uom_qty
                
                for lot in selected_lots:
                    if remaining_demand <= 0:
                        break
                        
                    # Buscar el stock físico real
                    # 1. Prioridad: Ubicación del movimiento
                    # 2. Fallback: Cualquier ubicación interna
                    domain = [
                        ('lot_id', '=', lot.id),
                        ('quantity', '>', 0),
                        ('location_id.usage', '=', 'internal')
                    ]
                    
                    quant = self.env['stock.quant'].search(
                        domain + [('location_id', 'child_of', move.location_id.id)], 
                        limit=1, 
                        order='quantity desc'
                    )
                    
                    if not quant:
                        quant = self.env['stock.quant'].search(domain, limit=1, order='quantity desc')
                    
                    if not quant:
                        _logger.warning(f"[STONE] Lote {lot.name} seleccionado pero sin stock físico.")
                        continue

                    # Reservar
                    qty_to_reserve = min(quant.quantity, remaining_demand)
                    
                    if qty_to_reserve <= 0:
                        continue

                    try:
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': product.id,
                            'lot_id': lot.id,
                            'quantity': qty_to_reserve,
                            'location_id': quant.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                            'product_uom_id': product.uom_id.id,
                        })
                        
                        remaining_demand -= qty_to_reserve
                        _logger.info(f"[STONE] Reservado {lot.name} ({qty_to_reserve}) en {picking.name}")
                        
                    except Exception as e:
                        _logger.error(f"[STONE] Error reservando lote {lot.name}: {e}")