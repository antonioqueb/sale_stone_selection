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
        if self.env.context.get('is_stone_confirming'):
            _logger.info("[STONE SYNC] Saltando sync durante confirmación inicial")
            return

        for move in self:
            if not move.sale_line_id:
                continue
            
            if move.state in ['done', 'cancel']:
                _logger.info("[STONE SYNC] Movimiento %s ya finalizado, no sincronizando", move.id)
                continue
            
            sol = move.sale_line_id

            all_lot_ids = set()
            
            for sibling_move in sol.move_ids:
                if sibling_move.state == 'cancel':
                    continue
                
                for ml in sibling_move.move_line_ids:
                    if ml.lot_id:
                        all_lot_ids.add(ml.lot_id.id)
            
            pending_moves = sol.move_ids.filtered(
                lambda m: m.state in ('confirmed', 'waiting', 'partially_available')
                and not m.move_line_ids
            )
            if pending_moves:
                existing_so_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()
                accounted_lots = all_lot_ids.copy()
                unaccounted = existing_so_lots - accounted_lots
                if unaccounted:
                    _logger.info(
                        "[STONE SYNC] Preserving %d unaccounted lots from SO Line %s "
                        "for pending moves: %s",
                        len(unaccounted), sol.id, list(unaccounted)
                    )
                    all_lot_ids.update(unaccounted)
            
            existing_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()
            
            if all_lot_ids == existing_lots:
                _logger.info("[STONE SYNC] Sin cambios en lotes para SO Line %s", sol.id)
                continue
            
            _logger.info("[STONE SYNC] Picking %s -> SO Line %s", 
                        move.picking_id.name if move.picking_id else 'N/A', sol.id)
            _logger.info("[STONE SYNC] Lotes anteriores: %s", sorted(existing_lots))
            _logger.info("[STONE SYNC] Lotes nuevos: %s", sorted(all_lot_ids))
            
            try:
                sol.with_context(skip_stone_sync_picking=True).write({
                    'lot_ids': [(6, 0, list(all_lot_ids))]
                })
                _logger.info("[STONE SYNC] ✓ Actualizado SO Line %s con %s lotes", 
                             sol.id, len(all_lot_ids))
            except Exception as e:
                _logger.error("[STONE SYNC] Error actualizando SO Line: %s", str(e))

    def write(self, vals):
        res = super(StockMove, self).write(vals)
        
        if 'move_line_ids' in vals and not self.env.context.get('skip_stone_sync_so'):
            for move in self:
                if move.sale_line_id and move.state not in ['done', 'cancel']:
                    move._sync_stone_sale_lines()
        
        return res