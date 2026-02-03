# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    lot_ids = fields.Many2many(
        'stock.lot',
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=False
    )

    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """ 
        Recalcula la cantidad de la línea (product_uom_qty) 
        basada en la suma de los lotes seleccionados.
        """
        if not self.lot_ids:
            return

        # Buscamos quants en ubicaciones internas para sumar la cantidad real
        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', self.lot_ids.ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ])

        total_qty = sum(quants.mapped('quantity'))
        
        # Solo actualizamos si encontramos stock, para evitar poner 0 accidentalmente
        if total_qty > 0:
            self.product_uom_qty = total_qty

    # -------------------------------------------------------------------------
    # NOTA TÉCNICA:
    # La lógica de sincronización de stock (_action_launch_stock_rule y _sync...)
    # ha sido eliminada de aquí.
    #
    # Ahora la reserva se maneja centralizadamente en:
    # models/sale_order.py -> action_confirm()
    #
    # Esto evita conflictos con la reserva automática de Odoo y garantiza
    # que se respeten los lotes seleccionados, igual que en el módulo de Carrito.
    # -------------------------------------------------------------------------