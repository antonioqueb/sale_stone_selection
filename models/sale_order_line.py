# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Almacena la selección visual
    # CAMBIO: Se cambia copy=False a copy=True para permitir que la selección
    # persista al duplicar la cotización hacia la orden de venta.
    lot_ids = fields.Many2many(
        'stock.lot',
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=True
    )

    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """ Actualiza la cantidad (m2) de la línea al seleccionar placas """
        if not self.lot_ids:
            return

        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])

        total_qty = sum(quants.mapped('quantity'))
        
        if total_qty > 0:
            self.product_uom_qty = total_qty