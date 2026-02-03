# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Este campo guarda los IDs de los lotes que seleccionas en el Grid JS.
    # Es fundamental para que el backend sepa qué reservar.
    lot_ids = fields.Many2many(
        'stock.lot',
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=False
    )

    # Campo auxiliar para el estado del botón (expandido/colapsado)
    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """ 
        Cuando seleccionas placas en el grid JS, esto calcula 
        automáticamente los m2 totales y actualiza la cantidad de la línea.
        """
        if not self.lot_ids:
            return

        # Sumar la cantidad disponible en stock de los lotes seleccionados
        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])

        total_qty = sum(quants.mapped('quantity'))
        
        # Actualizar cantidad solo si encontramos stock válido
        if total_qty > 0:
            self.product_uom_qty = total_qty