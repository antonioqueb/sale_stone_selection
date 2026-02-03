# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Lógica alineada con 'Inventory Shopping Cart':
        1. Ejecuta la confirmación estándar (Odoo reserva FIFO/LIFO por defecto).
        2. Inmediatamente limpiamos esas reservas automáticas.
        3. Forzamos la reserva de los lotes seleccionados manualmente.
        """
        res = super(SaleOrder, self).action_confirm()
        
        # Iterar sobre las líneas que tienen placas seleccionadas
        for order in self:
            # Filtramos líneas que tienen lotes seleccionados manualmente
            lines_with_stone = order.order_line.filtered(lambda l: l.lot_ids)
            if not lines_with_stone:
                continue

            # Obtener los pickings generados (albaranes) activos
            pickings = order.picking_ids.filtered(
                lambda p: p.state not in ['cancel', 'done']
            )
            
            # Aplicar la lógica de re-asignación (igual que en el carrito)
            for line in lines_with_stone:
                order._assign_stone_lots(pickings, line)
        
        return res

    def _assign_stone_lots(self, pickings, line):
        """
        Asigna los lotes específicos (lot_ids) de la línea de venta a los movimientos de stock.
        Lógica portada de 'shopping_cart.py' -> '_assign_specific_lots'.
        """
        product = line.product_id
        selected_lots = line.lot_ids  # Recordset de stock.lot
        
        for picking in pickings:
            # Buscar movimientos del producto de esta línea
            moves = picking.move_ids.filtered(lambda m: m.product_id.id == product.id)
            
            for move in moves:
                # 1. LIMPIEZA: Eliminar lo que Odoo reservó automáticamente
                # Esto soluciona el problema de "lotes aleatorios"
                if move.move_line_ids:
                    move.move_line_ids.unlink()
                
                remaining_demand = move.product_uom_qty
                
                # 2. ASIGNACIÓN: Crear líneas de movimiento manuales
                for lot in selected_lots:
                    if remaining_demand <= 0:
                        break
                        
                    # Buscar el quant para obtener la cantidad real disponible y ubicación exacta
                    # Priorizamos buscar en la ubicación del movimiento
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1, order='quantity desc')
                    
                    if not quant:
                        # Fallback: buscar en cualquier ubicación interna si no está en la ruta estándar
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', lot.id),
                            ('location_id.usage', '=', 'internal'),
                            ('quantity', '>', 0)
                        ], limit=1)
                    
                    if not quant:
                        continue

                    # Tomar todo lo disponible del lote o lo que falte por cubrir
                    qty_to_use = quant.quantity
                    qty_to_reserve = min(qty_to_use, remaining_demand)
                    
                    if qty_to_reserve <= 0:
                        continue

                    # Crear la reserva explícita
                    self.env['stock.move.line'].create({
                        'move_id': move.id,
                        'picking_id': picking.id,
                        'product_id': product.id,
                        'lot_id': lot.id,
                        'quantity': qty_to_reserve, # Odoo 17/18/19 usa 'quantity'
                        'location_id': quant.location_id.id, # Ubicación REAL del lote
                        'location_dest_id': move.location_dest_id.id,
                        'product_uom_id': product.uom_id.id,
                    })
                    
                    remaining_demand -= qty_to_reserve