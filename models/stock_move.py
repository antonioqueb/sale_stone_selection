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
            
            # Obtenemos todos los lotes asignados actualmente en el movimiento
            current_move_lots = move.move_line_ids.filtered(
                lambda ml: ml.lot_id
            ).mapped('lot_id')
            
            # Verificar si hay cambios reales
            existing_lots = move.sale_line_id.lot_ids
            
            if set(current_move_lots.ids) == set(existing_lots.ids):
                _logger.info("[STONE SYNC] Sin cambios en lotes para SO Line %s", move.sale_line_id.id)
                continue
            
            _logger.info("[STONE SYNC] Picking %s -> SO Line %s", move.picking_id.name, move.sale_line_id.id)
            _logger.info("[STONE SYNC] Lotes anteriores: %s", existing_lots.ids)
            _logger.info("[STONE SYNC] Lotes nuevos: %s", current_move_lots.ids)
            
            # Actualizamos la SO evitando disparar la sincronización inversa
            try:
                move.sale_line_id.with_context(skip_stone_sync_picking=True).write({
                    'lot_ids': [(6, 0, current_move_lots.ids)]
                })
                _logger.info("[STONE SYNC] ✓ Actualizado SO Line %s con %s lotes", 
                             move.sale_line_id.id, len(current_move_lots))
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
        
        return res