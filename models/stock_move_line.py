# ./models/stock_move_line.py
# -*- coding: utf-8 -*-
from odoo import models, api, fields

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear líneas en el Picking (desde la Grilla o manualmente), 
        sincronizar hacia la Orden de Venta.
        """
        lines = super(StockMoveLine, self).create(vals_list)
        if not self.env.context.get('skip_stone_sync_so'):
            lines._sync_to_sale_order_line()
        return lines

    def unlink(self):
        """
        Al borrar líneas en el Picking, quitar los lotes de la Orden de Venta.
        """
        # Antes de borrar, identificamos qué moves/sale_lines se verán afectados
        moves_to_sync = self.mapped('move_id')
        res = super(StockMoveLine, self).unlink()
        
        if not self.env.context.get('skip_stone_sync_so'):
            moves_to_sync._sync_stone_sale_lines()
        return res

    def _sync_to_sale_order_line(self):
        """Helper para disparar la sincronización desde las líneas."""
        self.mapped('move_id')._sync_stone_sale_lines()