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
        
        FIX BACKORDER: Al sincronizar, no solo miramos el move actual sino TODOS
        los moves de la SO line (incluyendo backorders) para no perder lotes pendientes.
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
            
            sol = move.sale_line_id
            
            # ══════════════════════════════════════════════════════════════
            # FIX: Recopilar lotes de TODOS los moves de la SO line,
            # no solo del move actual. Esto incluye:
            # - Lotes en moves activos (confirmed/assigned/partially_available)
            # - Lotes en moves done (ya entregados)
            # - Lotes en backorders pendientes
            # ══════════════════════════════════════════════════════════════
            all_lot_ids = set()
            
            for sibling_move in sol.move_ids:
                if sibling_move.state == 'cancel':
                    continue
                
                for ml in sibling_move.move_line_ids:
                    if ml.lot_id:
                        all_lot_ids.add(ml.lot_id.id)
            
            # También incluir lotes de moves pendientes (sin move_lines aún,
            # como backorders recién creados que aún no se reservaron)
            # Estos los recuperamos de las fuentes originales de la SO line
            # solo si el move está pendiente y no tiene lines
            pending_moves = sol.move_ids.filtered(
                lambda m: m.state in ('confirmed', 'waiting', 'partially_available')
                and not m.move_line_ids
            )
            if pending_moves:
                # Si hay moves pendientes sin lines, preservar los lotes
                # que están en la SO line y no están en ningún move done/assigned
                existing_so_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()
                # Los que ya están en move_lines de otros moves
                accounted_lots = all_lot_ids.copy()
                # Los que faltan = están en SO pero no en ningún move_line
                unaccounted = existing_so_lots - accounted_lots
                if unaccounted:
                    _logger.info(
                        "[STONE SYNC] Preserving %d unaccounted lots from SO Line %s "
                        "for pending moves: %s",
                        len(unaccounted), sol.id, list(unaccounted)
                    )
                    all_lot_ids.update(unaccounted)
            
            # Verificar si hay cambios reales
            existing_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()
            
            if all_lot_ids == existing_lots:
                _logger.info("[STONE SYNC] Sin cambios en lotes para SO Line %s", sol.id)
                continue
            
            _logger.info("[STONE SYNC] Picking %s -> SO Line %s", 
                        move.picking_id.name if move.picking_id else 'N/A', sol.id)
            _logger.info("[STONE SYNC] Lotes anteriores: %s", sorted(existing_lots))
            _logger.info("[STONE SYNC] Lotes nuevos: %s", sorted(all_lot_ids))
            
            # Actualizamos la SO evitando disparar la sincronización inversa
            try:
                sol.with_context(skip_stone_sync_picking=True).write({
                    'lot_ids': [(6, 0, list(all_lot_ids))]
                })
                _logger.info("[STONE SYNC] ✓ Actualizado SO Line %s con %s lotes", 
                             sol.id, len(all_lot_ids))
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