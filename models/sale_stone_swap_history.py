# -*- coding: utf-8 -*-
from odoo import models, fields


class SaleStoneSwapHistory(models.Model):
    """
    Registro inmutable de swaps de lotes ejecutados sobre líneas de venta.
    Permite reconstruir la cadena old → new para mostrar etiquetas en la UI
    aunque el lote viejo ya no esté en sale.order.line.lot_ids.
    """
    _name = 'sale.stone.swap.history'
    _description = 'Historial de Swap de Lotes en Selección de Piedra'
    _order = 'create_date desc, id desc'

    sale_line_id = fields.Many2one(
        'sale.order.line',
        string='Línea de Venta',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sale_order_id = fields.Many2one(
        related='sale_line_id.order_id',
        store=True,
        index=True,
    )
    old_lot_id = fields.Many2one(
        'stock.lot', string='Lote Reemplazado',
        required=True, index=True, ondelete='restrict',
    )
    new_lot_id = fields.Many2one(
        'stock.lot', string='Lote Nuevo',
        required=True, index=True, ondelete='restrict',
    )
    old_qty = fields.Float(string='Cantidad Anterior')
    new_qty = fields.Float(string='Cantidad Nueva')
    user_id = fields.Many2one(
        'res.users',
        string='Ejecutado por',
        default=lambda s: s.env.user,
    )