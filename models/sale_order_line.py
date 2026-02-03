# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Almacena la selección visual
    # copy=True es importante, pero a veces insuficiente sin copy_data explícito
    lot_ids = fields.Many2many(
        'stock.lot',
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=True
    )

    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    def copy_data(self, default=None):
        """
        Sobrescribimos copy_data para asegurar que los lotes seleccionados
        se trasladen al duplicar la línea (ej. al duplicar la Cotización).
        """
        if default is None:
            default = {}
        
        # Si no se ha especificado explícitamente qué hacer con lot_ids en el default,
        # forzamos la copia de los IDs actuales.
        if 'lot_ids' not in default and self.lot_ids:
            _logger.info(f"[STONE] Duplicando línea {self.id} - Copiando {len(self.lot_ids)} placas: {self.lot_ids.ids}")
            default['lot_ids'] = [(6, 0, self.lot_ids.ids)]
        
        return super(SaleOrderLine, self).copy_data(default)

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """ Actualiza la cantidad (m2) de la línea al seleccionar placas """
        # Log para depuración
        if self.lot_ids:
            _logger.info(f"[STONE] _onchange_lot_ids en línea (ID: {self._origin.id or 'New'}): {self.lot_ids.ids}")
        
        if not self.lot_ids:
            return

        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])

        total_qty = sum(quants.mapped('quantity'))
        
        if total_qty > 0:
            # Si el usuario selecciona placas, actualizamos la cantidad
            _logger.info(f"[STONE] Actualizando cantidad a {total_qty} basado en selección.")
            self.product_uom_qty = total_qty