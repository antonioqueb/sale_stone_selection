# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
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
    # Helpers
    # =========================================================================

    def _parse_breakdown_dict(self):
        self.ensure_one()
        raw = self.x_lot_breakdown_json
        if not raw:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

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
        ctx = dict(self.env.context,
                   skip_stone_sync_so=True,
                   skip_picking_clean=True,
                   skip_hold_validation=True)

        target_lots = self.lot_ids
        breakdown = self._parse_breakdown_dict()

        moves = self.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])

        for move in moves:
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

            for lot in (target_lots & existing_lots):
                existing_line = existing_move_lines.filtered(lambda ml: ml.lot_id.id == lot.id)
                if not existing_line:
                    continue

                real_quant = self.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('product_id', '=', self.product_id.id),
                    ('location_id', 'child_of', move.location_id.id),
                    ('quantity', '>', 0),
                ], limit=1)

                update_vals = {}
                if real_quant and existing_line[0].location_id.id != real_quant.location_id.id:
                    _logger.warning(
                        "[STONE SYNC] Corrigiendo location_id de %s → %s en move_line %s (lote %s)",
                        existing_line[0].location_id.display_name,
                        real_quant.location_id.display_name,
                        existing_line[0].id,
                        lot.name,
                    )
                    update_vals['location_id'] = real_quant.location_id.id

                tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'
                lot_id_str = str(lot.id)
                if tipo in ('formato', 'pieza') and lot_id_str in breakdown:
                    expected_qty = float(breakdown[lot_id_str])
                    if existing_line[0].quantity != expected_qty:
                        _logger.info("[STONE SYNC] Corrigiendo qty lote %s de %s a %s",
                                     lot.name, existing_line[0].quantity, expected_qty)
                        update_vals['quantity'] = expected_qty

                if update_vals:
                    existing_line[0].with_context(ctx).write(update_vals)

    def read(self, fields=None, load='_classic_read'):
        result = super(SaleOrderLine, self).read(fields, load)
        if fields and 'lot_ids' in fields:
            _logger.info("[STONE LINE READ] IDs: %s, fields: %s", self.ids, fields)
        return result

    @api.onchange('lot_ids', 'x_lot_breakdown_json')
    def _onchange_lot_ids(self):
        if not self.lot_ids:
            return

        breakdown = self._parse_breakdown_dict()

        total_qty = 0.0
        for lot in self.lot_ids:
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

        if total_qty > 0:
            self.product_uom_qty = total_qty
            _logger.info("[STONE ONCHANGE] product_uom_qty actualizado a: %s", total_qty)

    def _get_all_sale_lots_with_qty(self):
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
            breakdown = self._parse_breakdown_dict()

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

    # =========================================================================
    # API NUEVA: Estatus de entrega completo por lote
    # =========================================================================

    def _stone_safe_get(self, record, attr, default=None):
        try:
            if hasattr(record, attr):
                val = getattr(record, attr)
                return val if val is not None and val is not False else default
        except Exception:
            pass
        return default

    def get_stone_lots_full_status(self):
        """
        Retorna lista completa de lotes a mostrar en la UI de selección,
        incluyendo:
        - Lotes actualmente seleccionados (sale_order_line.lot_ids)
        - Lotes 'ghost' que fueron reemplazados por swap (ya no en lot_ids)

        Cada item incluye datos del lote, cantidad disponible vs mostrada,
        badges de estatus (entregado/devuelto/reentregado/swap) y flag is_locked
        que el frontend usa para deshabilitar quitar/editar cantidad.
        """
        self.ensure_one()

        breakdown = self._parse_breakdown_dict()
        current_lot_ids = list(self.lot_ids.ids)

        # ────────────────────────────────────────────────────────
        # 1) Documentos de delivery relacionados a la línea
        # ────────────────────────────────────────────────────────
        Doc = self.env['sale.delivery.document']
        docs = Doc.search([
            ('sale_order_id', '=', self.order_id.id),
            ('state', 'in', ('prepared', 'confirmed')),
        ])

        info = {}

        def get_info(lot_id):
            if lot_id not in info:
                info[lot_id] = {
                    'qty_delivered': 0.0,
                    'qty_returned': 0.0,
                    'qty_redelivered_confirmed': 0.0,
                    'qty_redelivered_pending': 0.0,
                    'qty_pick_ticket': 0.0,
                    'remissions': [],
                    'returns': [],
                    'redeliveries_confirmed': [],
                    'redeliveries_pending': [],
                    'pick_tickets': [],
                    'swap_replaced_by': [],
                    'swap_replacement_of': [],
                }
            return info[lot_id]

        for doc in docs:
            for dl in doc.line_ids:
                if dl.sale_line_id != self or not dl.lot_id:
                    continue
                lot_id = dl.lot_id.id
                d = get_info(lot_id)
                qty = dl.qty_done or dl.qty_selected or 0.0

                if doc.document_type == 'remission' and doc.state == 'confirmed':
                    d['qty_delivered'] += qty
                    ref = doc.remission_number or doc.name or ''
                    if ref and ref not in d['remissions']:
                        d['remissions'].append(ref)
                elif doc.document_type == 'return' and doc.state == 'confirmed':
                    qty_r = dl.qty_returned or qty
                    d['qty_returned'] += qty_r
                    ref = doc.name or ''
                    if ref and ref not in d['returns']:
                        d['returns'].append(ref)
                elif doc.document_type == 'redelivery':
                    if doc.state == 'confirmed':
                        d['qty_redelivered_confirmed'] += qty
                        ref = doc.remission_number or doc.name or ''
                        if ref and ref not in d['redeliveries_confirmed']:
                            d['redeliveries_confirmed'].append(ref)
                    else:
                        d['qty_redelivered_pending'] += dl.qty_selected or qty
                        ref = doc.name or ''
                        if ref and ref not in d['redeliveries_pending']:
                            d['redeliveries_pending'].append(ref)
                elif doc.document_type == 'pick_ticket' and doc.state == 'prepared':
                    d['qty_pick_ticket'] += dl.qty_selected or 0.0
                    ref = doc.name or ''
                    if ref and ref not in d['pick_tickets']:
                        d['pick_tickets'].append(ref)

        # ────────────────────────────────────────────────────────
        # 2) Swap history
        # ────────────────────────────────────────────────────────
        ghost_lot_ids = []
        try:
            swaps = self.env['sale.stone.swap.history'].search([
                ('sale_line_id', '=', self.id),
            ], order='create_date asc, id asc')

            for sw in swaps:
                old = sw.old_lot_id
                new = sw.new_lot_id
                if not old or not new:
                    continue
                get_info(old.id)['swap_replaced_by'].append(
                    {'lot_id': new.id, 'lot_name': new.name or ''}
                )
                get_info(new.id)['swap_replacement_of'].append(
                    {'lot_id': old.id, 'lot_name': old.name or ''}
                )
                if old.id not in current_lot_ids and old.id not in ghost_lot_ids:
                    ghost_lot_ids.append(old.id)
        except Exception as exc:
            _logger.warning(
                "[STONE STATUS] No se pudo cargar swap history: %s", exc
            )

        # ────────────────────────────────────────────────────────
        # 3) Construir lista completa de IDs a retornar
        # ────────────────────────────────────────────────────────
        all_lot_ids = list(current_lot_ids) + [
            lid for lid in ghost_lot_ids if lid not in current_lot_ids
        ]

        if not all_lot_ids:
            return []

        Lot = self.env['stock.lot']
        lots = Lot.browse(all_lot_ids)
        lots_map = {l.id: l for l in lots if l.exists()}

        # ────────────────────────────────────────────────────────
        # 4) Quants para cantidad disponible
        # ────────────────────────────────────────────────────────
        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', all_lot_ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ])
        qty_map = {}
        for q in quants:
            qty_map[q.lot_id.id] = qty_map.get(q.lot_id.id, 0.0) + q.quantity

        # ────────────────────────────────────────────────────────
        # 5) Build resultado
        # ────────────────────────────────────────────────────────
        result = []
        for lot_id in all_lot_ids:
            lot = lots_map.get(lot_id)
            if not lot:
                continue

            d = info.get(lot_id)
            is_ghost = lot_id in ghost_lot_ids and lot_id not in current_lot_ids
            tipo = (lot.x_tipo or 'placa').lower() if self._stone_safe_get(lot, 'x_tipo') else 'placa'
            available_qty = qty_map.get(lot_id, 0.0)

            if is_ghost:
                displayed_qty = 0.0
            elif tipo in ('formato', 'pieza') and str(lot_id) in breakdown:
                displayed_qty = float(breakdown[str(lot_id)])
            else:
                displayed_qty = available_qty

            # ─── Badges de estatus (orden de prioridad visual) ───
            badges = []
            is_locked = False

            if d:
                # SWAP primero (visualmente más importante)
                for sw in d['swap_replaced_by']:
                    badges.append({
                        'type': 'swap_replaced',
                        'label': _('Reemplazado por %s') % sw['lot_name'],
                        'icon': 'fa-exchange',
                    })
                    is_locked = True
                for sw in d['swap_replacement_of']:
                    badges.append({
                        'type': 'swap_replacement',
                        'label': _('Reemplazo de %s') % sw['lot_name'],
                        'icon': 'fa-refresh',
                    })

                if d['qty_delivered'] > 0:
                    for ref in d['remissions']:
                        badges.append({
                            'type': 'delivered',
                            'label': _('Entregado · %s') % ref,
                            'icon': 'fa-check-circle',
                        })
                    is_locked = True

                if d['qty_returned'] > 0:
                    for ref in d['returns']:
                        badges.append({
                            'type': 'returned',
                            'label': _('Devuelto · %s') % ref,
                            'icon': 'fa-undo',
                        })
                    is_locked = True

                if d['qty_redelivered_confirmed'] > 0:
                    for ref in d['redeliveries_confirmed']:
                        badges.append({
                            'type': 'redelivered',
                            'label': _('Reentregado · %s') % ref,
                            'icon': 'fa-share',
                        })
                    is_locked = True

                if d['qty_redelivered_pending'] > 0:
                    for ref in d['redeliveries_pending']:
                        badges.append({
                            'type': 'redelivery_pending',
                            'label': _('Reentrega Pendiente · %s') % ref,
                            'icon': 'fa-hourglass-half',
                        })
                    is_locked = True

                if d['qty_pick_ticket'] > 0:
                    for ref in d['pick_tickets']:
                        badges.append({
                            'type': 'pick_ticket',
                            'label': _('En Pick Ticket · %s') % ref,
                            'icon': 'fa-clipboard',
                        })
                    is_locked = True

            if not badges and not is_ghost:
                badges.append({
                    'type': 'pending',
                    'label': _('Pendiente'),
                    'icon': 'fa-clock-o',
                })

            result.append({
                'lot_id': lot_id,
                'lot_name': lot.name or '',
                'product_id': self.product_id.id,
                'available_qty': available_qty,
                'displayed_qty': displayed_qty,
                'tipo': tipo,
                'x_bloque': self._stone_safe_get(lot, 'x_bloque', '') or '',
                'x_atado': self._stone_safe_get(lot, 'x_atado', '') or '',
                'x_alto': self._stone_safe_get(lot, 'x_alto', 0) or 0,
                'x_ancho': self._stone_safe_get(lot, 'x_ancho', 0) or 0,
                'x_grosor': self._stone_safe_get(lot, 'x_grosor', 0) or 0,
                'x_color': self._stone_safe_get(lot, 'x_color', '') or '',
                'x_fotografia_principal': self._stone_safe_get(lot, 'x_fotografia_principal', False) or False,
                'x_cantidad_fotos': self._stone_safe_get(lot, 'x_cantidad_fotos', 0) or 0,
                'status_badges': badges,
                'is_locked': is_locked,
                'is_ghost': is_ghost,
                'qty_delivered': d['qty_delivered'] if d else 0.0,
                'qty_returned': d['qty_returned'] if d else 0.0,
                'qty_redelivered': (
                    (d['qty_redelivered_confirmed'] + d['qty_redelivered_pending'])
                    if d else 0.0
                ),
            })

        return result