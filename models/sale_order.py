# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare
import json
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_is_quote_backup = fields.Boolean(
        string="Es Cotización Histórica",
        default=False,
        copy=False,
        help="Indica que esta orden es una copia de respaldo de la cotización original.",
    )

    def _stone_clear_quote_stock_selections_before_confirm(self):
        """
        Regla funcional crítica:
        En cotización NO debe existir selección de stock.

        Si por datos históricos, caché de navegador, API externa o una versión
        anterior del módulo una cotización trae lot_ids / breakdown, se eliminan
        antes de confirmar para que la orden confirmada nazca limpia.

        Después de confirmar, el usuario debe seleccionar lotes/cantidades desde
        la orden de venta ya confirmada.
        """
        for order in self.filtered(lambda o: o.state in ('draft', 'sent')):
            lines = order.order_line.filtered(
                lambda l: bool(l.lot_ids) or bool(l.x_lot_breakdown_json)
            )

            if not lines:
                continue

            _logger.warning(
                "[STONE] Cotización %s tenía selección de stock antes de confirmar. "
                "Se limpiarán %s línea(s) para evitar cantidades/lotes corruptos.",
                order.name,
                len(lines),
            )

            lines.with_context(
                skip_stone_sync_so=True,
                skip_stone_sync_picking=True,
                skip_picking_clean=True,
                allow_quote_lot_cleanup=True,
            ).write({
                'lot_ids': [(5, 0, 0)],
                'x_lot_breakdown_json': False,
            })

    def _stone_assert_no_transient_auto_lots_left(self):
        """
        Postcondición de seguridad para la confirmación sin selección manual.

        Durante action_confirm Odoo puede crear move lines con lote por reserva
        nativa. En este flujo se permiten solo como estado transitorio porque
        stock_lot_dimensions debe limpiarlas inmediatamente después de super().
        Si una línea con lote queda viva, se detiene la confirmación para no
        dejar una reserva física que el usuario no seleccionó.
        """
        StockMoveLine = self.env['stock.move.line'].sudo()
        qty_field = 'quantity' if 'quantity' in StockMoveLine._fields else 'qty_done'

        for order in self:
            pickings = order.picking_ids.filtered(
                lambda p: p.state not in ('done', 'cancel')
            )
            if not pickings:
                continue

            residual_lines = pickings.move_ids.move_line_ids.filtered(
                lambda ml:
                    ml.lot_id
                    and ml.move_id.state not in ('done', 'cancel')
                    and float(getattr(ml, qty_field, 0.0) or 0.0) > 0.0
            )

            if not residual_lines:
                continue

            details = []
            for line in residual_lines[:10]:
                details.append(
                    '%s / %s / %s / qty=%s' % (
                        line.picking_id.name if line.picking_id else 'Sin picking',
                        line.product_id.display_name if line.product_id else 'Sin producto',
                        line.lot_id.name if line.lot_id else 'Sin lote',
                        getattr(line, qty_field, 0.0) or 0.0,
                    )
                )

            _logger.error(
                "[STONE] La limpieza posterior a confirmación dejó %s move_line(s) "
                "con lote automático en la orden %s: %s",
                len(residual_lines),
                order.name,
                residual_lines.ids,
            )

            raise UserError(_(
                "La venta se confirmó en modo de autoasignación transitoria, "
                "pero quedaron lotes asignados automáticamente.\n\n"
                "La operación fue detenida para evitar una reserva física no seleccionada.\n\n"
                "Líneas detectadas:\n%s\n\n"
                "Revise la limpieza de pickings automáticos antes de reintentar."
            ) % '\n'.join(details))

    def action_confirm(self):
        """
        Confirmación con:
        1. Bloqueo funcional: una cotización NO puede confirmar selección de stock.
        2. Duplicación de cotización (backup) + cambio de folio a V.
        3. Asignación estricta de lotes SOLO si la orden ya venía en estado válido.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE] ACTION_CONFIRM INICIO - Orden: %s", self.name)

        # =====================================================================
        # BLOQUEAR DOBLE CONFIRMACIÓN
        # =====================================================================
        for order in self:
            if order.state in ('sale', 'done'):
                _logger.info("[STONE] Orden %s ya confirmada (state=%s). Redirigiendo.", order.name, order.state)
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': order.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'name': _('Orden de Venta: %s') % order.name,
                }

            existing_so = self.env['sale.order'].search([
                ('origin', '=', order.name),
                ('id', '!=', order.id),
                ('state', 'in', ('sale', 'done')),
            ], limit=1)

            if existing_so:
                _logger.info("[STONE] Cotización %s ya generó la SO %s. Redirigiendo.", order.name, existing_so.name)
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': existing_so.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'name': _('Orden de Venta: %s') % existing_so.name,
                }

            if order.x_is_quote_backup:
                _logger.info("[STONE] Orden %s es backup de cotización. No se puede confirmar.", order.name)
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': order.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'name': _('Cotización: %s') % order.name,
                }

        # =====================================================================
        # 0. REGLA NUEVA: limpiar selección de stock en cotizaciones
        # =====================================================================
        self._stone_clear_quote_stock_selections_before_confirm()

        # =====================================================================
        # 1. GUARDAR los lotes ANTES de cualquier operación
        #    Nota: después de limpiar cotizaciones, esto normalmente estará vacío.
        # =====================================================================
        lines_lots_map = {}
        all_protected_lot_ids = []

        for order in self:
            for line in order.order_line.filtered(lambda l: l.lot_ids):
                lot_ids = line.lot_ids.ids.copy()

                breakdown = {}
                if line.x_lot_breakdown_json:
                    try:
                        if isinstance(line.x_lot_breakdown_json, str):
                            breakdown = json.loads(line.x_lot_breakdown_json)
                        elif isinstance(line.x_lot_breakdown_json, dict):
                            breakdown = line.x_lot_breakdown_json
                    except (json.JSONDecodeError, TypeError):
                        breakdown = {}

                lines_lots_map[line.id] = {
                    'lot_ids': lot_ids,
                    'product_id': line.product_id.id,
                    'breakdown': breakdown,
                }
                all_protected_lot_ids.extend(lot_ids)
                _logger.info(
                    "[STONE] Protegiendo para línea %s: %s lotes, breakdown: %s",
                    line.id,
                    len(lot_ids),
                    breakdown,
                )

        has_stone_lots = bool(lines_lots_map)

        # =====================================================================
        # 2. DUPLICACIÓN: Crear backup de cotización + renombrar a V
        # =====================================================================
        for order in self:
            if order.state in ['draft', 'sent'] and not order.x_is_quote_backup:
                current_cot_name = order.name

                new_ov_name = self.env['ir.sequence'].next_by_code('sale.order.confirmed')
                if not new_ov_name:
                    new_ov_name = current_cot_name.replace('COT/', 'V/')
                    _logger.warning(
                        "[STONE] Secuencia 'sale.order.confirmed' no encontrada. "
                        "Usando fallback: %s", new_ov_name
                    )

                _logger.info(
                    "[STONE] Duplicando cotización %s → backup, renombrando a %s",
                    current_cot_name,
                    new_ov_name,
                )

                copy_defaults = {
                    'name': current_cot_name,
                    'state': 'draft',
                    'origin': 'Convertido a %s' % new_ov_name,
                    'x_is_quote_backup': True,
                    'date_order': fields.Datetime.now(),
                }

                if has_stone_lots:
                    copy_defaults['order_line'] = False

                backup_quote = order.copy(default=copy_defaults)

                if has_stone_lots and not backup_quote.order_line:
                    for line in order.order_line:
                        line_defaults = {
                            'order_id': backup_quote.id,
                            'lot_ids': [(5, 0, 0)],
                            'x_lot_breakdown_json': False,
                        }
                        line.copy(default=line_defaults)

                _logger.info(
                    "[STONE] Backup creado: %s (ID: %s, x_is_quote_backup=True)",
                    backup_quote.name,
                    backup_quote.id,
                )

                order.name = new_ov_name
                order.origin = current_cot_name

                _logger.info("[STONE] Orden renombrada: %s → %s", current_cot_name, new_ov_name)

        # =====================================================================
        # 3. CONFIRMAR: Llamar a super() con o sin protección de lotes
        # =====================================================================
        if not has_stone_lots:
            transient_ctx = dict(
                self.env.context,
                # Odoo puede autoasignar lotes durante super().action_confirm().
                # En este flujo esos lotes son basura transitoria: stock_lot_dimensions
                # los limpia inmediatamente después de confirmar. Por eso se evita
                # que las validaciones funcionales bloqueen antes de la limpieza.
                stone_transient_auto_assign=True,
                skip_duplicate_lot_validation=True,
                skip_hold_validation=True,
                skip_picking_clean=False,
            )

            _logger.info(
                "[STONE] Sin lotes seleccionados. Confirmando con autoasignación "
                "transitoria tolerada y limpieza posterior obligatoria."
            )
            res = super(SaleOrder, self.with_context(transient_ctx)).action_confirm()
            self.with_context(transient_ctx)._stone_assert_no_transient_auto_lots_left()
            _logger.info("[STONE] ACTION_CONFIRM FIN")
            _logger.info("=" * 80)
            return res

        ctx = dict(
            self.env.context,
            skip_picking_clean=True,
            protected_lot_ids=all_protected_lot_ids,
            is_stone_confirming=True,
            skip_stone_sync_so=True,
        )

        _logger.info("[STONE] Llamando a super() con skip_picking_clean=True...")
        res = super(SaleOrder, self.with_context(ctx)).action_confirm()
        _logger.info("[STONE] Retorno de super(). Iniciando asignación forzada.")

        # =====================================================================
        # 4. ASIGNACIÓN FORZADA de lotes
        # =====================================================================
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])

            if not pickings:
                _logger.warning("[STONE] No se generaron pickings para la orden %s", order.name)
                continue

            for picking in pickings:
                for move in picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                    all_lot_lines = move.move_line_ids.filtered(lambda ml: ml.lot_id)
                    if all_lot_lines:
                        _logger.info(
                            "[STONE] Eliminando %s move_lines existentes para recrear con ubicación correcta",
                            len(all_lot_lines),
                        )
                        all_lot_lines.with_context(ctx).unlink()

            for line in order.order_line:
                line_data = lines_lots_map.get(line.id)
                if not line_data:
                    continue

                lots = self.env['stock.lot'].browse(line_data['lot_ids'])
                if lots:
                    self.with_context(ctx)._assign_stone_lots_to_picking(
                        pickings,
                        line,
                        lots,
                        line_data.get('breakdown', {}),
                    )

        # 5. Restaurar visualización en Sale Order
        for line_id, line_data in lines_lots_map.items():
            line = self.env['sale.order.line'].browse(line_id)
            if line.exists() and set(line.lot_ids.ids) != set(line_data['lot_ids']):
                line.with_context(ctx).write({'lot_ids': [(6, 0, line_data['lot_ids'])]})

        # =====================================================================
        # 6. Limpiar lot_ids de la COTIZACIÓN BACKUP
        # =====================================================================
        for order in self:
            if order.origin:
                source_orders = self.env['sale.order'].search([
                    ('name', '=', order.origin),
                    ('id', '!=', order.id),
                    ('state', 'in', ('draft', 'sent', 'cancel')),
                ], limit=1)

                if source_orders:
                    _logger.info("[STONE] Limpiando lot_ids de cotización origen %s", source_orders.name)
                    for source_line in source_orders.order_line.filtered(lambda l: l.lot_ids):
                        source_line.with_context(ctx).write({
                            'lot_ids': [(5, 0, 0)],
                            'x_lot_breakdown_json': False,
                        })
                        _logger.info(
                            "[STONE] ✓ Limpiado lot_ids de línea %s en cotización %s",
                            source_line.id,
                            source_orders.name,
                        )

        _logger.info("[STONE] ACTION_CONFIRM FIN")
        _logger.info("=" * 80)
        return res

    def _get_lot_qty_for_line(self, sale_line, lot, breakdown=None):
        tipo = 'placa'
        if hasattr(lot, 'x_tipo') and lot.x_tipo:
            tipo = str(lot.x_tipo).lower()

        is_partial_type = (tipo in ('formato', 'pieza'))

        if not is_partial_type:
            return None, 'full_quant'

        if not breakdown:
            breakdown = {}
            if sale_line.x_lot_breakdown_json:
                try:
                    if isinstance(sale_line.x_lot_breakdown_json, str):
                        breakdown = json.loads(sale_line.x_lot_breakdown_json)
                    elif isinstance(sale_line.x_lot_breakdown_json, dict):
                        breakdown = sale_line.x_lot_breakdown_json
                except (json.JSONDecodeError, TypeError):
                    breakdown = {}

        lot_id_str = str(lot.id)
        if lot_id_str in breakdown:
            qty = float(breakdown[lot_id_str])
            _logger.info(
                "[STONE] Lote %s tipo=%s: usando breakdown → qty=%s",
                lot.name,
                tipo,
                qty,
            )
            return qty, 'breakdown'

        if hasattr(sale_line, 'x_selected_lots') and sale_line.x_selected_lots:
            for quant in sale_line.x_selected_lots:
                if quant.lot_id.id == lot.id and str(quant.id) in breakdown:
                    qty = float(breakdown[str(quant.id)])
                    _logger.info(
                        "[STONE] Lote %s tipo=%s: usando breakdown quant_id=%s → qty=%s",
                        lot.name,
                        tipo,
                        quant.id,
                        qty,
                    )
                    return qty, 'breakdown'

        num_lots = len(sale_line.lot_ids) if sale_line.lot_ids else 1
        if num_lots > 0 and sale_line.product_uom_qty > 0:
            _logger.info(
                "[STONE] Lote %s tipo=%s: sin breakdown, usando sale_line qty=%s / %s lotes",
                lot.name,
                tipo,
                sale_line.product_uom_qty,
                num_lots,
            )
            return None, 'sale_qty_split'

        return None, 'full_quant'

    def _stone_move_line_qty_vals(self, qty):
        StockMoveLine = self.env['stock.move.line']
        if 'quantity' in StockMoveLine._fields:
            return {'quantity': qty}
        if 'reserved_uom_qty' in StockMoveLine._fields:
            return {'reserved_uom_qty': qty}
        if 'qty_done' in StockMoveLine._fields:
            return {'qty_done': qty}
        return {}

    def _stone_get_lot_quants_for_assignment(self, product, lot, source_location=None):
        Quant = self.env['stock.quant']

        base_domain = [
            ('lot_id', '=', lot.id),
            ('product_id', '=', product.id),
            ('quantity', '>', 0),
        ]

        quants = Quant.browse()

        if source_location:
            quants = Quant.search(
                base_domain + [('location_id', 'child_of', source_location.id)],
                order='quantity desc, location_id, id',
            )

        if not quants:
            quants = Quant.search(
                base_domain + [('location_id.usage', '=', 'internal')],
                order='quantity desc, location_id, id',
            )

        return quants

    def _stone_get_lot_physical_qty(self, quants):
        return sum((q.quantity or 0.0) for q in quants)

    def _stone_build_quant_splits(self, quants, qty):
        qty = float(qty or 0.0)
        if qty <= 0 or not quants:
            return []

        positive_quants = quants.filtered(lambda q: (q.quantity or 0.0) > 0)

        for quant in positive_quants:
            if (quant.quantity or 0.0) >= qty:
                return [(quant, qty)]

        remaining = qty
        splits = []

        for quant in positive_quants:
            if remaining <= 0:
                break

            take_qty = min(remaining, quant.quantity or 0.0)
            if take_qty <= 0:
                continue

            splits.append((quant, take_qty))
            remaining -= take_qty

        return splits

    def _stone_unlink_existing_lot_move_lines(self, move, lot, ctx):
        existing_lines = move.move_line_ids.filtered(lambda ml: ml.lot_id == lot)
        if existing_lines:
            _logger.info(
                "[STONE] Eliminando %s move_line(s) previas del lote %s en move %s para recrear cantidad exacta.",
                len(existing_lines),
                lot.name,
                move.id,
            )
            existing_lines.with_context(ctx).unlink()

    def _stone_create_lot_move_lines(self, move, lot, qty, product, quants, ctx):
        StockMoveLine = self.env['stock.move.line']
        created_lines = StockMoveLine.browse()
        splits = self._stone_build_quant_splits(quants, qty)

        for quant, split_qty in splits:
            vals = {
                'move_id': move.id,
                'picking_id': move.picking_id.id if move.picking_id else False,
                'product_id': product.id,
                'product_uom_id': move.product_uom.id,
                'lot_id': lot.id,
                'location_id': quant.location_id.id,
                'location_dest_id': move.location_dest_id.id,
            }
            vals.update(self._stone_move_line_qty_vals(split_qty))

            if quant.package_id and 'package_id' in StockMoveLine._fields:
                vals['package_id'] = quant.package_id.id
            if quant.owner_id and 'owner_id' in StockMoveLine._fields:
                vals['owner_id'] = quant.owner_id.id

            created_lines |= StockMoveLine.with_context(ctx).create(vals)

            _logger.info(
                "[STONE] ✓ Move line creada lote=%s qty=%.6f ubicación=%s picking=%s",
                lot.name,
                split_qty,
                quant.location_id.display_name,
                move.picking_id.name if move.picking_id else 'N/A',
            )

        return created_lines

    def _assign_stone_lots_to_picking(self, pickings, sale_line, lots, breakdown=None):
        product = sale_line.product_id
        if not lots:
            return

        if not breakdown:
            breakdown = {}

        ctx = dict(
            self.env.context,
            skip_stone_sync=True,
            skip_picking_clean=True,
            skip_hold_validation=True,
            skip_stone_sync_so=True,
        )

        rounding = product.uom_id.rounding or 0.00001

        for picking in pickings:
            moves = picking.move_ids.filtered(
                lambda m: m.product_id.id == product.id and m.state not in ['done', 'cancel']
            )

            for move in moves:
                total_for_move = 0.0

                for lot in lots:
                    partial_qty, qty_source = self._get_lot_qty_for_line(
                        sale_line,
                        lot,
                        breakdown,
                    )

                    quants = self._stone_get_lot_quants_for_assignment(
                        product=product,
                        lot=lot,
                        source_location=move.location_id,
                    )

                    if not quants:
                        _logger.warning(
                            "[STONE] Lote %s no encontrado físicamente para producto %s.",
                            lot.name,
                            product.display_name,
                        )
                        continue

                    physical_qty = self._stone_get_lot_physical_qty(quants)

                    if qty_source == 'full_quant':
                        qty_to_assign = physical_qty
                    elif qty_source == 'breakdown' and partial_qty is not None:
                        qty_to_assign = partial_qty
                    elif qty_source == 'sale_qty_split':
                        num_lots = len(lots)
                        qty_to_assign = (
                            sale_line.product_uom_qty / num_lots
                            if num_lots > 0 else physical_qty
                        )
                    else:
                        qty_to_assign = physical_qty

                    if float_compare(qty_to_assign, physical_qty, precision_rounding=rounding) > 0:
                        _logger.warning(
                            "[STONE] Lote %s solicitado %.6f pero solo existe físicamente %.6f. Se usará %.6f.",
                            lot.name,
                            qty_to_assign,
                            physical_qty,
                            physical_qty,
                        )
                        qty_to_assign = physical_qty

                    if float_compare(qty_to_assign, 0, precision_rounding=rounding) <= 0:
                        continue

                    self._stone_unlink_existing_lot_move_lines(move, lot, ctx)

                    _logger.info(
                        "[STONE] Asignando lote %s qty=%.6f (source=%s, tipo=%s, físico_total=%.6f, quants=%s)",
                        lot.name,
                        qty_to_assign,
                        qty_source,
                        lot.x_tipo if hasattr(lot, 'x_tipo') else 'placa',
                        physical_qty,
                        len(quants),
                    )

                    self._stone_create_lot_move_lines(
                        move=move,
                        lot=lot,
                        qty=qty_to_assign,
                        product=product,
                        quants=quants,
                        ctx=ctx,
                    )
                    total_for_move += qty_to_assign

                if float_compare(total_for_move, 0, precision_rounding=rounding) > 0:
                    if float_compare(
                        move.product_uom_qty,
                        total_for_move,
                        precision_rounding=rounding,
                    ) != 0:
                        _logger.info(
                            "[STONE] Ajustando demanda del move %s de %.6f a %.6f para respetar selección exacta.",
                            move.id,
                            move.product_uom_qty,
                            total_for_move,
                        )
                        move.with_context(ctx).write({'product_uom_qty': total_for_move})

    def copy_data(self, default=None):
        return super().copy_data(default)

    def copy(self, default=None):
        return super().copy(default)