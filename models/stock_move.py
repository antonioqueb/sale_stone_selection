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

            # REGLA DE ORO (2026-08-07, pedida explícitamente): LAS ENTREGAS
            # MANDAN. Lo que viva en los pickings (pick/out) ES la selección:
            # los lotes presentes ahí se OFICIALIZAN en el selector visual,
            # incluidos los que el vendedor no había marcado. Si los pickings
            # no traen ningún lote, gana el selector (este sync no limpia
            # nada — la dirección selector→picking la lleva
            # _sync_lots_to_picking_moves).
            if not all_lot_ids:
                continue

            # EXCEPCIÓN A LA REGLA DE ORO: los lotes reservados EN TRÁNSITO
            # en un viaje ACTIVO no pueden estar en la entrega todavía (el
            # material va en el mar) — la entrega no manda sobre lo que aún
            # no llega. Sin esta preservación, validar la recepción de UN
            # embarque reemplazaba lot_ids con sus placas y SOLTABA la
            # reserva de las placas del OTRO embarque en camino (caso real:
            # V/131 perdió 41 placas de EMBARQUE/2026/0035 al recibir el
            # EMBARQUE/2026/0029).
            missing_lots = existing_lots - all_lot_ids
            if missing_lots and 'stock.transit.line' in self.env:
                in_transit = self.env['stock.transit.line'].sudo().search([
                    ('order_id', '=', sol.order_id.id),
                    ('product_id', '=', sol.product_id.id),
                    ('lot_id', 'in', list(missing_lots)),
                    ('allocation_status', '=', 'reserved'),
                    ('voyage_id.custom_status', 'not in', ['delivered', 'cancel']),
                ]).mapped('lot_id')
                if in_transit:
                    _logger.info(
                        "[STONE SYNC] Preservando %s lote(s) reservados en "
                        "tránsito activo (SO Line %s): %s",
                        len(in_transit), sol.id, in_transit.mapped('name'))
                    all_lot_ids.update(in_transit.ids)

            added = all_lot_ids - existing_lots
            if added:
                added_names = self.env['stock.lot'].browse(
                    list(added)).mapped('name')
                _logger.info(
                    "[STONE SYNC] Oficializando en el selector lotes "
                    "presentes en la ENTREGA (SO Line %s): %s",
                    sol.id, added_names)

            if all_lot_ids == existing_lots:
                continue

            _logger.info("[STONE SYNC] Picking %s -> SO Line %s",
                         move.picking_id.name if move.picking_id else 'N/A', sol.id)

            # SEMBRAR EL DESGLOSE de los lotes formato/pieza recién
            # oficializados: sin entrada en x_lot_breakdown_json, el lote se
            # interpretaba como COMPLETO en todos los consumidores (visual,
            # ratchet, re-sync a picking con reparto uniforme). La cantidad
            # sembrada es la de sus move lines en los pickings — exactamente
            # lo que la entrega dice.
            write_vals = {'lot_ids': [(6, 0, list(all_lot_ids))]}
            if added and 'x_lot_breakdown_json' in sol._fields:
                breakdown = dict(sol.x_lot_breakdown_json or {})
                changed_bd = False
                for lot_id in added:
                    lot = self.env['stock.lot'].browse(lot_id)
                    tipo = ''
                    if 'x_tipo' in lot._fields and lot.x_tipo:
                        tipo = str(lot.x_tipo).strip().lower()
                    if tipo not in ('formato', 'pieza'):
                        continue
                    if sol._som_breakdown_qty_for_lot(breakdown, lot) is not None:
                        continue
                    ml_qty = sum(
                        ml.quantity or 0.0
                        for ml in sol.move_ids.mapped('move_line_ids')
                        if ml.lot_id.id == lot_id
                        and ml.state not in ('cancel',)
                    )
                    if ml_qty > 0:
                        breakdown[str(lot_id)] = ml_qty
                        changed_bd = True
                if changed_bd:
                    write_vals['x_lot_breakdown_json'] = breakdown

            try:
                sol.with_context(skip_stone_sync_picking=True).write(write_vals)
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