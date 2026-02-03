# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Sobrescribimos confirmar para imponer la selección visual sobre la lógica FIFO de Odoo.
        """
        # 1. Ejecutar confirmación estándar de Odoo (Genera Pickings y reservas FIFO)
        res = super(SaleOrder, self).action_confirm()
        
        # 2. Corregir las reservas inmediatamente
        for order in self:
            # Buscar líneas que tengan selección manual de placas (lot_ids no vacío)
            lines_with_stone = order.order_line.filtered(lambda l: l.lot_ids)
            if not lines_with_stone:
                continue

            # Obtener los albaranes generados que no estén cancelados
            pickings = order.picking_ids.filtered(
                lambda p: p.state not in ['cancel', 'done']
            )
            
            if not pickings:
                continue

            _logger.info(f"[STONE] Aplicando reserva estricta para Orden {order.name}")
            
            # Aplicar la lógica de asignación forzada línea por línea
            for line in lines_with_stone:
                order._assign_stone_lots_strict(pickings, line)
        
        return res

    def _assign_stone_lots_strict(self, pickings, line):
        """
        Elimina las reservas automáticas y asigna LOS LOTES SELECCIONADOS VISUALMENTE.
        """
        product = line.product_id
        selected_lots = line.lot_ids  # Estos son los lotes que seleccionaste en el grid visual
        
        if not selected_lots:
            return

        for picking in pickings:
            # Buscar movimientos asociados a este producto en el picking
            moves = picking.move_ids.filtered(lambda m: m.product_id.id == product.id)
            
            for move in moves:
                # ---------------------------------------------------------
                # PASO 1: LIMPIEZA (Borrón y cuenta nueva)
                # Eliminamos lo que Odoo reservó automáticamente (FIFO)
                # ---------------------------------------------------------
                if move.move_line_ids:
                    _logger.info(f"[STONE] Limpiando reservas automáticas en movimiento {move.id}")
                    move.move_line_ids.unlink()
                
                # ---------------------------------------------------------
                # PASO 2: ASIGNACIÓN MANUAL (Respetar Grid Visual)
                # ---------------------------------------------------------
                remaining_demand = move.product_uom_qty
                
                for lot in selected_lots:
                    if remaining_demand <= 0:
                        break
                        
                    # Buscar dónde está físicamente este lote AHORA MISMO.
                    # Priorizamos buscar en la ubicación del movimiento, pero si no está ahí
                    # (ej. movimiento entre almacenes), buscamos en cualquier interna.
                    domain = [
                        ('lot_id', '=', lot.id),
                        ('quantity', '>', 0),
                        ('location_id.usage', '=', 'internal')
                    ]
                    
                    # Intento 1: Ubicación hija del movimiento
                    quant = self.env['stock.quant'].search(
                        domain + [('location_id', 'child_of', move.location_id.id)], 
                        limit=1, 
                        order='quantity desc'
                    )
                    
                    # Intento 2: Cualquier ubicación interna (Fallback)
                    if not quant:
                        quant = self.env['stock.quant'].search(domain, limit=1, order='quantity desc')
                    
                    if not quant:
                        _logger.warning(f"[STONE] El lote {lot.name} fue seleccionado pero no tiene stock físico disponible.")
                        continue

                    # Cantidad a reservar: Todo lo que tenga el lote o lo que falte de demanda
                    qty_to_reserve = min(quant.quantity, remaining_demand)
                    
                    if qty_to_reserve <= 0:
                        continue

                    try:
                        # CREAR LA RESERVA EXPLÍCITA
                        # Esto hace que aparezca en "Operaciones Detalladas" del Picking
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': product.id,
                            'lot_id': lot.id,
                            'quantity': qty_to_reserve, 
                            'location_id': quant.location_id.id, # Ubicación REAL del lote
                            'location_dest_id': move.location_dest_id.id,
                            'product_uom_id': product.uom_id.id,
                        })
                        
                        remaining_demand -= qty_to_reserve
                        _logger.info(f"[STONE] Reservado Lote {lot.name} ({qty_to_reserve}) en Movimiento {move.id}")
                        
                    except Exception as e:
                        _logger.error(f"[STONE] Error creando reserva para lote {lot.name}: {str(e)}")