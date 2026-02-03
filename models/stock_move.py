# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _recompute_state(self):
        """
        Detecta cambios en las reservas del Picking.
        """
        res = super(StockMove, self)._recompute_state()
        
        # NO sincronizar durante confirmación
        if self.env.context.get('is_stone_confirming'):
            return res
        if self.env.context.get('skip_stone_sync'):
            return res
            
        return res