# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
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
        if self.env.context.get('is_stone_confirming'):
            _logger.info("[STONE SYNC] Saltando sync durante confirmación inicial")
            return

        for move in self:
            if not move.sale_line_id:
                continue

            if move.state in ['done', 'cancel']:
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
                    all_lot_ids.update(unaccounted)

            existing_lots = set(sol.lot_ids.ids) if sol.lot_ids else set()

            # LA ASIGNACIÓN ES 100% DEL VENDEDOR: el sync refleja el estado de
            # los lotes YA elegidos (quitas, reemplazos vía swap), pero JAMÁS
            # agrega lotes nuevos. Una reserva nativa FIFO en cualquier picking
            # de la cadena NO es una asignación y no debe "oficializarse" aquí.
            auto_added = all_lot_ids - existing_lots
            if auto_added:
                added_names = self.env['stock.lot'].browse(
                    list(auto_added)).mapped('name')
                _logger.warning(
                    "[STONE SYNC] Ignorando lotes NO asignados por el vendedor "
                    "(reserva automática detectada) en SO Line %s: %s",
                    sol.id, added_names)
                all_lot_ids -= auto_added

            if all_lot_ids == existing_lots:
                continue

            _logger.info("[STONE SYNC] Picking %s -> SO Line %s",
                         move.picking_id.name if move.picking_id else 'N/A', sol.id)

            try:
                sol.with_context(skip_stone_sync_picking=True).write({
                    'lot_ids': [(6, 0, list(all_lot_ids))]
                })
                _logger.info("[STONE SYNC] ✓ Actualizado SO Line %s con %s lotes",
                             sol.id, len(all_lot_ids))
            except UserError:
                # Error de negocio (validador de holds, tope de stock…): debe
                # LLEGAR al usuario. Tragarlo dejaba picking y línea de venta
                # divergentes en silencio — justo lo que este sync evita.
                raise
            except Exception:
                _logger.exception(
                    "[STONE SYNC] Error inesperado actualizando SO Line %s",
                    sol.id,
                )
                raise UserError(_(
                    'No se pudo sincronizar los lotes del picking con la línea '
                    'de venta %s. Revisa el registro del servidor.'
                ) % sol.id)

    def write(self, vals):
        res = super(StockMove, self).write(vals)

        if 'move_line_ids' in vals and not self.env.context.get('skip_stone_sync_so'):
            for move in self:
                if move.sale_line_id and move.state not in ['done', 'cancel']:
                    move._sync_stone_sale_lines()

        return res