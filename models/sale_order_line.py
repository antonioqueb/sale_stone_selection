# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    lot_ids = fields.Many2many(
        'stock.lot',
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
        copy=True
    )

    is_stone_expanded = fields.Boolean("Detalles Desplegados", default=False)

    def copy_data(self, default=None):
        if default is None:
            default = {}
        
        if len(self) == 1:
            _logger.info("[STONE COPY_DATA] Línea ID: %s, lot_ids: %s", self.id, self.lot_ids.ids if self.lot_ids else [])
            if 'lot_ids' not in default and self.lot_ids:
                default['lot_ids'] = [(6, 0, self.lot_ids.ids)]
        
        return super(SaleOrderLine, self).copy_data(default)

    def copy(self, default=None):
        if len(self) == 1:
            _logger.info("[STONE LINE COPY] Línea ID: %s, lot_ids: %s", self.id, self.lot_ids.ids if self.lot_ids else [])
        
        result = super(SaleOrderLine, self).copy(default)
        
        if len(self) == 1:
            _logger.info("[STONE LINE COPY] Nueva línea ID: %s, lot_ids: %s", 
                        result.id if result else None, 
                        result.lot_ids.ids if result and result.lot_ids else [])
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info("[STONE LINE CREATE] Creando %s línea(s)", len(vals_list))
        for idx, vals in enumerate(vals_list):
            if 'lot_ids' in vals:
                _logger.info("[STONE LINE CREATE] vals[%s] lot_ids: %s", idx, vals['lot_ids'])
        
        result = super(SaleOrderLine, self).create(vals_list)
        
        for line in result:
            if line.lot_ids:
                _logger.info("[STONE LINE CREATE] Línea %s -> lot_ids: %s", line.id, line.lot_ids.ids)
        
        return result

    def write(self, vals):
        if 'lot_ids' in vals:
            _logger.info("[STONE LINE WRITE] Líneas IDs: %s", self.ids)
            _logger.info("[STONE LINE WRITE] lot_ids ANTES: %s", {l.id: l.lot_ids.ids for l in self})
            _logger.info("[STONE LINE WRITE] lot_ids EN vals: %s", vals['lot_ids'])
        
        # Bloquear sync inverso durante write
        ctx = dict(self.env.context, skip_stone_sync_so=True)
        result = super(SaleOrderLine, self.with_context(ctx)).write(vals)
        
        # Sincronización SO -> Picking
        # NUEVO: NO sincronizar si estamos en confirmación (is_stone_confirming)
        # porque la limpieza de lot_ids post-confirm NO debe borrar los move_lines del picking
        if ('lot_ids' in vals 
            and not self.env.context.get('skip_stone_sync_picking')
            and not self.env.context.get('is_stone_confirming')):
            for line in self:
                if line.state in ['sale', 'done'] and line.move_ids:
                    _logger.info("[STONE SYNC] Detectado cambio en lotes SO para línea %s. Sincronizando Picking...", line.id)
                    line._sync_lots_to_picking_moves()

        if 'lot_ids' in vals:
            _logger.info("[STONE LINE WRITE] lot_ids DESPUÉS: %s", {l.id: l.lot_ids.ids for l in self})
        
        return result

    def _sync_lots_to_picking_moves(self):
        """
        Refleja los cambios de lotes de la SO hacia los movimientos de stock (Pickings).
        """
        ctx = dict(self.env.context, 
                   skip_stone_sync_so=True,
                   skip_picking_clean=True,
                   skip_hold_validation=True)

        target_lots = self.lot_ids
        
        moves = self.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])
        
        for move in moves:
            total_area = sum(target_lots.mapped(lambda l: self.env['stock.quant'].search([
                ('lot_id', '=', l.id),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0)
            ], limit=1).quantity or 0.0))

            if total_area > 0 and move.product_uom_qty != total_area:
                 _logger.info("[STONE SYNC] Ajustando demanda Move %s de %s a %s", move.id, move.product_uom_qty, total_area)
                 move.with_context(ctx).write({'product_uom_qty': total_area})

            picking = move.picking_id
            existing_move_lines = move.move_line_ids
            existing_lots = existing_move_lines.mapped('lot_id')

            lots_to_remove = existing_lots - target_lots
            if lots_to_remove:
                lines_to_unlink = existing_move_lines.filtered(lambda ml: ml.lot_id in lots_to_remove)
                _logger.info("[STONE SYNC] Eliminando %s lotes del picking %s", len(lines_to_unlink), picking.name)
                lines_to_unlink.with_context(ctx).unlink()

            lots_to_add = target_lots - existing_lots
            if lots_to_add:
                _logger.info("[STONE SYNC] Agregando %s lotes al picking %s", len(lots_to_add), picking.name)
                for lot in lots_to_add:
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', self.product_id.id),
                        ('location_id', 'child_of', move.location_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if not quant:
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', lot.id),
                            ('product_id', '=', self.product_id.id),
                            ('location_id.usage', '=', 'internal'),
                            ('quantity', '>', 0)
                        ], limit=1)

                    if quant:
                        move_line_vals = {
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': self.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'lot_id': lot.id,
                            'location_id': quant.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                            'quantity': quant.quantity,
                        }
                        try:
                            self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        except Exception as e:
                            _logger.error("[STONE SYNC] Error creando move line para lote %s: %s", lot.name, str(e))
                    else:
                        _logger.warning("[STONE SYNC] No se pudo sincronizar lote %s: No stock físico encontrado", lot.name)

    def read(self, fields=None, load='_classic_read'):
        result = super(SaleOrderLine, self).read(fields, load)
        if fields and 'lot_ids' in fields:
            _logger.info("[STONE LINE READ] IDs: %s", self.ids)
        return result

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        """Actualiza la cantidad (m2) de la línea al seleccionar placas"""
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

    def _get_all_sale_lots_with_qty(self):
        """
        Retorna TODOS los lotes de la venta con su cantidad.
        ACTUALIZADO: Busca primero en move_line_ids (post-confirmación),
        luego en lot_ids (pre-confirmación).
        """
        self.ensure_one()
        
        # 1. Buscar en TODOS los stock.move.line vinculados
        move_lines = self.env['stock.move.line'].search([
            ('move_id.sale_line_id', '=', self.id),
            ('lot_id', '!=', False),
        ])
        
        if move_lines:
            lot_data = {}
            for ml in move_lines:
                lot = ml.lot_id
                if lot.id not in lot_data:
                    lot_data[lot.id] = {'lot': lot, 'quantity': 0.0}
                lot_data[lot.id]['quantity'] += ml.quantity or ml.reserved_uom_qty or 0.0
            return list(lot_data.values())
        
        # 2. Fallback: lot_ids (pre-confirmación)
        if self.lot_ids:
            result = []
            for lot in self.lot_ids:
                quant = self.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('product_id', '=', self.product_id.id),
                    ('location_id.usage', '=', 'internal'),
                    ('quantity', '>', 0)
                ], limit=1)
                result.append({
                    'lot': lot,
                    'quantity': quant.quantity if quant else (lot.x_alto * lot.x_ancho if lot.x_alto and lot.x_ancho else 0.0),
                })
            return result
        
        return []