# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _recompute_state(self):
        """
        Detecta cambios en las reservas del Picking y actualiza la Orden de Venta.
        """
        res = super(StockMove, self)._recompute_state()
        
        # PROTECCIÓN CRÍTICA:
        # 1. Durante confirmación inicial (is_stone_confirming)
        # 2. Si ya estamos en una sincronización (skip_back_sync)  
        # 3. Si estamos en el proceso de limpieza de pickings (skip_stone_sync)
        if self.env.context.get('is_stone_confirming'):
            return res
            
        if self.env.context.get('skip_back_sync'):
            return res
            
        if self.env.context.get('skip_stone_sync'):
            return res

        # Solo sincronizar si NO estamos en proceso de asignación
        # y si el picking ya está en un estado estable
        for move in self:
            if move.picking_id and move.picking_id.state in ('assigned', 'done'):
                self._sync_lots_back_to_so()
                break
            
        return res

    def _sync_lots_back_to_so(self):
        """
        Sincroniza stock.move.line -> sale.order.line.lot_ids
        SOLO cuando el usuario modifica manualmente el picking.
        """
        # Verificar contexto de protección
        if self.env.context.get('is_stone_confirming'):
            return
        if self.env.context.get('skip_stone_sync'):
            return
            
        for move in self:
            if not move.sale_line_id:
                continue
            if not move.picking_type_id or move.picking_type_id.code != 'outgoing':
                continue
            
            # Solo sincronizar si el picking está completamente asignado
            if move.picking_id.state not in ('assigned', 'done'):
                continue
                
            current_reservation_lots = move.move_line_ids.mapped('lot_id')
            so_lots = move.sale_line_id.lot_ids
            
            if set(current_reservation_lots.ids) != set(so_lots.ids):
                _logger.info("[STONE] Sincronizando Picking %s -> SO %s", 
                            move.picking_id.name, move.sale_line_id.order_id.name)
                move.sale_line_id.with_context(skip_stock_sync=True).write({
                    'lot_ids': [(6, 0, current_reservation_lots.ids)]
                })