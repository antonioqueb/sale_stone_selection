# -*- coding: utf-8 -*-
from odoo import models, fields, api
import json
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

    x_lot_breakdown_json = fields.Json(
        string="Desglose de Cantidades por Lote",
        copy=True,
        help="JSON con {lot_id: qty} para formatos y piezas. "
             "Para placas no se usa (se toma el quant completo).",
    )

    # =========================================================================
    # DIAGNÓSTICO
    # =========================================================================

    def copy_data(self, default=None):
        if default is None:
            default = {}
        if len(self) == 1:
            _logger.info("[STONE COPY_DATA] Línea ID: %s, lot_ids: %s, breakdown: %s",
                         self.id, self.lot_ids.ids, self.x_lot_breakdown_json)
            if 'lot_ids' not in default and self.lot_ids:
                default['lot_ids'] = [(6, 0, self.lot_ids.ids)]
            if 'x_lot_breakdown_json' not in default and self.x_lot_breakdown_json:
                default['x_lot_breakdown_json'] = self.x_lot_breakdown_json
        return super(SaleOrderLine, self).copy_data(default)

    def copy(self, default=None):
        if len(self) == 1:
            _logger.info("[STONE LINE COPY] Línea ID: %s, lot_ids: %s", self.id, self.lot_ids.ids)
        result = super(SaleOrderLine, self).copy(default)
        if len(self) == 1:
            _logger.info("[STONE LINE COPY] Nueva línea ID: %s, lot_ids: %s",
                         result.id, result.lot_ids.ids if result else [])
        return result

    @api.model_create_multi
    def create(self, vals_list):
        for idx, vals in enumerate(vals_list):
            if 'lot_ids' in vals or 'x_lot_breakdown_json' in vals:
                _logger.info("[STONE LINE CREATE] vals[%s] lot_ids: %s, breakdown: %s",
                             idx, vals.get('lot_ids'), vals.get('x_lot_breakdown_json'))
        result = super(SaleOrderLine, self).create(vals_list)
        return result

    def write(self, vals):
        if 'lot_ids' in vals or 'x_lot_breakdown_json' in vals:
            _logger.info("[STONE LINE WRITE] Líneas IDs: %s", self.ids)
            if 'lot_ids' in vals:
                _logger.info("[STONE LINE WRITE] lot_ids EN vals: %s", vals['lot_ids'])
            if 'x_lot_breakdown_json' in vals:
                _logger.info("[STONE LINE WRITE] breakdown EN vals: %s", vals['x_lot_breakdown_json'])

        ctx = dict(self.env.context, skip_stone_sync_so=True)
        result = super(SaleOrderLine, self.with_context(ctx)).write(vals)

        if 'lot_ids' in vals and not self.env.context.get('skip_stone_sync_picking'):
            for line in self:
                if line.state in ['sale', 'done'] and line.move_ids:
                    _logger.info("[STONE SYNC] Detectado cambio en lotes SO para línea %s. Sincronizando Picking...", line.id)
                    line._sync_lots_to_picking_moves()

        return result

    def _sync_lots_to_picking_moves(self):
        """
        Refleja los cambios de lotes de la SO hacia los movimientos de stock (Pickings).
        Maneja adiciones, eliminaciones y corrección de cantidades.
        Respeta x_lot_breakdown_json para cantidades parciales.
        """
        ctx = dict(self.env.context,
                   skip_stone_sync_so=True,
                   skip_picking_clean=True,
                   skip_hold_validation=True)

        target_lots = self.lot_ids

        # Leer breakdown
        breakdown = {}
        if self.x_lot_breakdown_json:
            try:
                if isinstance(self.x_lot_breakdown_json, str):
                    breakdown = json.loads(self.x_lot_breakdown_json)
                elif isinstance(self.x_lot_breakdown_json, dict):
                    breakdown = self.x_lot_breakdown_json
            except (json.JSONDecodeError, TypeError):
                breakdown = {}

        moves = self.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])

        for move in moves:
            # Calcular total esperado según tipo de cada lote
            total_qty = 0.0
            for lot in target_lots:
                tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'
                lot_id_str = str(lot.id)
                if tipo in ('formato', 'pieza') and lot_id_str in breakdown:
                    total_qty += float(breakdown[lot_id_str])
                else:
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('location_id.usage', '=', 'internal'),
                        ('quantity', '>', 0)
                    ], limit=1)
                    total_qty += quant.quantity if quant else 0.0

            if total_qty > 0 and move.product_uom_qty != total_qty:
                _logger.info("[STONE SYNC] Ajustando demanda Move %s de %s a %s",
                             move.id, move.product_uom_qty, total_qty)
                move.with_context(ctx).write({'product_uom_qty': total_qty})

            picking = move.picking_id
            existing_move_lines = move.move_line_ids
            existing_lots = existing_move_lines.mapped('lot_id')

            # A. BORRAR lotes que ya no están en selección
            lots_to_remove = existing_lots - target_lots
            if lots_to_remove:
                lines_to_unlink = existing_move_lines.filtered(lambda ml: ml.lot_id in lots_to_remove)
                _logger.info("[STONE SYNC] Eliminando %s lotes del picking %s", len(lines_to_unlink), picking.name)
                lines_to_unlink.with_context(ctx).unlink()

            # B. AGREGAR lotes nuevos
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
                        tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'
                        lot_id_str = str(lot.id)
                        if tipo in ('formato', 'pieza') and lot_id_str in breakdown:
                            qty = min(float(breakdown[lot_id_str]), quant.quantity)
                        else:
                            qty = quant.quantity

                        move_line_vals = {
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': self.product_id.id,
                            'product_uom_id': move.product_uom.id,
                            'lot_id': lot.id,
                            'location_id': quant.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                            'quantity': qty,
                        }
                        try:
                            self.env['stock.move.line'].with_context(ctx).create(move_line_vals)
                        except Exception as e:
                            _logger.error("[STONE SYNC] Error creando move line para lote %s: %s", lot.name, str(e))
                    else:
                        _logger.warning("[STONE SYNC] No se pudo sincronizar lote %s: No stock físico encontrado", lot.name)

            # C. CORREGIR cantidades de lotes existentes que cambiaron en breakdown
            for lot in (target_lots & existing_lots):
                tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'
                lot_id_str = str(lot.id)
                if tipo in ('formato', 'pieza') and lot_id_str in breakdown:
                    expected_qty = float(breakdown[lot_id_str])
                    existing_line = existing_move_lines.filtered(lambda ml: ml.lot_id.id == lot.id)
                    if existing_line and existing_line[0].quantity != expected_qty:
                        _logger.info("[STONE SYNC] Corrigiendo qty lote %s de %s a %s",
                                     lot.name, existing_line[0].quantity, expected_qty)
                        existing_line[0].with_context(ctx).write({'quantity': expected_qty})

    def read(self, fields=None, load='_classic_read'):
        result = super(SaleOrderLine, self).read(fields, load)
        if fields and 'lot_ids' in fields:
            _logger.info("[STONE LINE READ] IDs: %s, fields: %s", self.ids, fields)
        return result

    @api.onchange('lot_ids', 'x_lot_breakdown_json')
    def _onchange_lot_ids(self):
        """
        Actualiza la cantidad de la línea al seleccionar placas.
        - Placas: suma de quants completos
        - Formatos: suma de m² del breakdown
        - Piezas: suma de piezas del breakdown
        """
        if not self.lot_ids:
            return

        breakdown = {}
        if self.x_lot_breakdown_json:
            try:
                if isinstance(self.x_lot_breakdown_json, str):
                    breakdown = json.loads(self.x_lot_breakdown_json)
                elif isinstance(self.x_lot_breakdown_json, dict):
                    breakdown = self.x_lot_breakdown_json
            except (json.JSONDecodeError, TypeError):
                breakdown = {}

        total_qty = 0.0
        for lot in self.lot_ids:
            tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'
            lot_id_str = str(lot.id)

            if tipo in ('formato', 'pieza') and lot_id_str in breakdown:
                total_qty += float(breakdown[lot_id_str])
            else:
                # Placa o sin breakdown: usar quant completo
                quant = self.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('location_id.usage', '=', 'internal'),
                    ('quantity', '>', 0)
                ], limit=1)
                total_qty += quant.quantity if quant else 0.0

        if total_qty > 0:
            self.product_uom_qty = total_qty
            _logger.info("[STONE ONCHANGE] product_uom_qty actualizado a: %s", total_qty)

    def _get_all_sale_lots_with_qty(self):
        """
        Retorna TODOS los lotes de la venta con su cantidad,
        buscando en todos los moves/pickings + fallback a lot_ids.
        Para uso en reportes.
        """
        self.ensure_one()

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

        if self.lot_ids:
            breakdown = {}
            if self.x_lot_breakdown_json:
                try:
                    if isinstance(self.x_lot_breakdown_json, str):
                        breakdown = json.loads(self.x_lot_breakdown_json)
                    elif isinstance(self.x_lot_breakdown_json, dict):
                        breakdown = self.x_lot_breakdown_json
                except (json.JSONDecodeError, TypeError):
                    breakdown = {}

            result = []
            for lot in self.lot_ids:
                tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'
                lot_id_str = str(lot.id)

                if tipo in ('formato', 'pieza') and lot_id_str in breakdown:
                    qty = float(breakdown[lot_id_str])
                else:
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('product_id', '=', self.product_id.id),
                        ('location_id.usage', '=', 'internal'),
                        ('quantity', '>', 0)
                    ], limit=1)
                    qty = quant.quantity if quant else (lot.x_alto * lot.x_ancho if lot.x_alto and lot.x_ancho else 0.0)

                result.append({
                    'lot': lot,
                    'quantity': qty,
                })
            return result

        return []