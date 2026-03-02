# -*- coding: utf-8 -*-
from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear líneas en el Picking, sincronizar hacia la SO SOLO si la línea
        de venta tiene lotes seleccionados manualmente.
        """
        lines = super(StockMoveLine, self).create(vals_list)
        
        if (not self.env.context.get('skip_stone_sync_so') 
            and not self.env.context.get('is_stone_confirming')):
            # Solo sincronizar lines cuyo sale_line_id SÍ tiene lot_ids manuales
            lines_to_sync = lines.filtered(
                lambda ml: ml.move_id.sale_line_id and ml.move_id.sale_line_id.lot_ids
            )
            if lines_to_sync:
                lines_to_sync._sync_to_sale_order_line()
        
        return lines

    def write(self, vals):
        res = super(StockMoveLine, self).write(vals)
        
        if (('lot_id' in vals or 'quantity' in vals) 
            and not self.env.context.get('skip_stone_sync_so')):
            # Solo sincronizar si la SO line tiene lotes manuales
            lines_to_sync = self.filtered(
                lambda ml: ml.move_id.sale_line_id and ml.move_id.sale_line_id.lot_ids
            )
            if lines_to_sync:
                lines_to_sync._sync_to_sale_order_line()
        
        return res

    def unlink(self):
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        res = super(StockMoveLine, self).unlink()
        
        if (not self.env.context.get('skip_stone_sync_so') 
            and not self.env.context.get('is_stone_confirming')):
            # Solo sync para moves cuya SO line tiene lotes manuales
            moves_with_manual = moves_to_sync.filtered(
                lambda m: m.sale_line_id.lot_ids
            )
            if moves_with_manual:
                moves_with_manual._sync_stone_sale_lines()
        
        return res

    def _sync_to_sale_order_line(self):
        moves_to_sync = self.mapped('move_id').filtered(
            lambda m: m.sale_line_id and m.state not in ['done', 'cancel']
        )
        
        if moves_to_sync:
            _logger.info("[STONE SYNC] Sincronizando %s movimientos hacia SO", len(moves_to_sync))
            moves_to_sync._sync_stone_sale_lines()