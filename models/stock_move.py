# ./models/stock_move.py
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
        # Evitamos sincronizar si estamos en medio de la confirmación inicial
        if self.env.context.get('is_stone_confirming'):
            return

        for move in self:
            if not move.sale_line_id:
                continue
            
            # Obtenemos todos los lotes asignados actualmente en el movimiento
            current_move_lots = move.move_line_ids.mapped('lot_id')
            
            # Actualizamos la SO evitando disparar la sincronización inversa
            # Usamos skip_stone_sync_picking para que la SO no intente escribir de vuelta al Picking
            move.sale_line_id.with_context(skip_stone_sync_picking=True).write({
                'lot_ids': [(6, 0, current_move_lots.ids)]
            })
            _logger.info("[STONE SYNC] Picking %s -> SO Line %s: %s lotes", 
                         move.picking_id.name, move.sale_line_id.id, len(current_move_lots))