# -*- coding: utf-8 -*-
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class SaleSwapWizard(models.TransientModel):
    """
    Hook para registrar cada swap exitoso en sale.stone.swap.history.
    De esta manera la UI de selección de placas puede mostrar el lote
    reemplazado tachado y el reemplazo con etiqueta, sin tocar
    sale_delivery_wizard.
    """
    _inherit = 'sale.swap.wizard'

    def action_confirm_swap(self):
        try:
            pairs = self._collect_swap_pairs()
        except Exception as exc:
            _logger.warning(
                "[STONE SWAP HISTORY] No se pudieron recolectar pares: %s", exc
            )
            pairs = []

        result = super().action_confirm_swap()

        if pairs:
            History = self.env['sale.stone.swap.history']
            for vals in pairs:
                try:
                    History.create(vals)
                except Exception as exc:
                    _logger.warning(
                        "[STONE SWAP HISTORY] Error registrando swap %s: %s",
                        vals, exc,
                    )

        return result

    def _collect_swap_pairs(self):
        self.ensure_one()
        pairs = []

        lines = self._get_swap_lines_from_widget_selections()
        if not lines:
            lines = self._get_swap_lines_from_db_lines()

        for data in lines:
            move_line = data.get('move_line')
            old_lot = data.get('origin_lot')
            new_lot = data.get('target_lot')

            if not move_line or not old_lot or not new_lot:
                continue
            if old_lot.id == new_lot.id:
                continue

            sale_line = data.get('sale_line') or (
                move_line.move_id.sale_line_id if move_line.move_id else False
            )
            if not sale_line:
                continue

            pairs.append({
                'sale_line_id': sale_line.id,
                'old_lot_id': old_lot.id,
                'new_lot_id': new_lot.id,
                'old_qty': data.get('qty', 0.0) or 0.0,
                'new_qty': (
                    data.get('target_qty', 0.0)
                    or data.get('qty', 0.0)
                    or 0.0
                ),
            })

        return pairs