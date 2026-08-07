# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
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
    # Reglas de selección
    # =========================================================================

    def _stone_can_select_lots(self):
        """
        Regla funcional:
        La selección de stock solo está permitida en órdenes confirmadas.
        En cotización solo se capturan cantidades comerciales.
        """
        self.ensure_one()
        return self.state in ('sale', 'done')

    @api.model
    def _stone_vals_target_order_is_unconfirmed(self, vals):
        order_id = vals.get('order_id')
        if not order_id:
            return False

        if isinstance(order_id, int):
            order = self.env['sale.order'].browse(order_id)
        else:
            return False

        return order.exists() and order.state not in ('sale', 'done')

    @api.model
    def _stone_sanitize_quote_selection_vals(self, vals):
        clean_vals = dict(vals)

        if 'lot_ids' in clean_vals:
            clean_vals['lot_ids'] = [(5, 0, 0)]

        if 'x_lot_breakdown_json' in clean_vals:
            clean_vals['x_lot_breakdown_json'] = False

        return clean_vals

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

    def _stone_line_get_lot_quants(self, lot, move=None):
        source_location = move.location_id if move and move.location_id else False

        if self.order_id and hasattr(self.order_id, '_stone_get_lot_quants_for_assignment'):
            return self.order_id._stone_get_lot_quants_for_assignment(
                product=self.product_id,
                lot=lot,
                source_location=source_location,
            )

        Quant = self.env['stock.quant']
        base_domain = [
            ('lot_id', '=', lot.id),
            ('product_id', '=', self.product_id.id),
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

    def _stone_line_get_lot_physical_qty(self, lot, move=None):
        quants = self._stone_line_get_lot_quants(lot, move=move)
        if self.order_id and hasattr(self.order_id, '_stone_get_lot_physical_qty'):
            return self.order_id._stone_get_lot_physical_qty(quants)
        return sum((q.quantity or 0.0) for q in quants)

    def _stone_line_move_line_qty(self, move_line):
        if not move_line:
            return 0.0
        if 'quantity' in move_line._fields:
            return move_line.quantity or 0.0
        if 'reserved_uom_qty' in move_line._fields:
            return move_line.reserved_uom_qty or 0.0
        if 'qty_done' in move_line._fields:
            return move_line.qty_done or 0.0
        return 0.0

    def _stone_line_expected_qty_for_lot(self, lot, breakdown, move=None):
        tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'
        lot_id_str = str(lot.id)
        quants = self._stone_line_get_lot_quants(lot, move=move)
        physical_qty = sum((q.quantity or 0.0) for q in quants)

        if tipo in ('formato', 'pieza'):
            if lot_id_str in breakdown:
                expected_qty = float(breakdown[lot_id_str] or 0.0)
            else:
                # El breakdown puede venir con claves de quant.id (flujo del
                # carrito) en lugar de lot.id — mismo criterio que
                # _get_lot_qty_for_line en la confirmación.
                expected_qty = None
                if hasattr(self, 'x_selected_lots') and self.x_selected_lots:
                    for quant in self.x_selected_lots:
                        if quant.lot_id.id == lot.id and str(quant.id) in breakdown:
                            expected_qty = float(breakdown[str(quant.id)] or 0.0)
                            break

                if expected_qty is None:
                    # Formato/pieza SIN desglose: repartir lo vendido entre los
                    # lotes de la línea (como hace la confirmación) en lugar de
                    # reservar la placa física COMPLETA. Antes, vender 2 m² de
                    # un formato podía dejar la entrega con demanda de 15 m².
                    num_lots = len(self.lot_ids) if self.lot_ids else 1
                    if num_lots > 0 and (self.product_uom_qty or 0.0) > 0:
                        expected_qty = min(
                            (self.product_uom_qty or 0.0) / num_lots,
                            physical_qty,
                        )
                    else:
                        expected_qty = physical_qty
        else:
            expected_qty = physical_qty

        if expected_qty > physical_qty > 0:
            _logger.warning(
                "[STONE SYNC] Lote %s solicitado %.6f pero físico total %.6f. Se usará físico total.",
                lot.name,
                expected_qty,
                physical_qty,
            )
            expected_qty = physical_qty

        return expected_qty, physical_qty, tipo, quants

    def _stone_line_create_exact_move_lines(self, move, lot, qty, quants, ctx):
        if qty <= 0:
            return self.env['stock.move.line'].browse()

        if self.order_id and hasattr(self.order_id, '_stone_create_lot_move_lines'):
            return self.order_id._stone_create_lot_move_lines(
                move=move,
                lot=lot,
                qty=qty,
                product=self.product_id,
                quants=quants,
                ctx=ctx,
            )

        StockMoveLine = self.env['stock.move.line']
        created = StockMoveLine.browse()
        remaining = qty

        for quant in quants.filtered(lambda q: (q.quantity or 0.0) > 0):
            if remaining <= 0:
                break
            take_qty = min(remaining, quant.quantity or 0.0)
            vals = {
                'move_id': move.id,
                'picking_id': move.picking_id.id if move.picking_id else False,
                'product_id': self.product_id.id,
                'product_uom_id': move.product_uom.id,
                'lot_id': lot.id,
                'location_id': quant.location_id.id,
                'location_dest_id': move.location_dest_id.id,
            }
            if 'quantity' in StockMoveLine._fields:
                vals['quantity'] = take_qty
            elif 'reserved_uom_qty' in StockMoveLine._fields:
                vals['reserved_uom_qty'] = take_qty
            elif 'qty_done' in StockMoveLine._fields:
                vals['qty_done'] = take_qty
            created |= StockMoveLine.with_context(ctx).create(vals)
            remaining -= take_qty

        return created

    # =========================================================================
    # DIAGNÓSTICO / CREATE / WRITE
    # =========================================================================

    def copy_data(self, default=None):
        if default is None:
            default = {}

        if len(self) == 1:
            _logger.info(
                "[STONE COPY_DATA] Línea ID: %s, state=%s, lot_ids=%s, breakdown=%s",
                self.id,
                self.state,
                self.lot_ids.ids,
                self.x_lot_breakdown_json,
            )

            if not self._stone_can_select_lots():
                default['lot_ids'] = [(5, 0, 0)]
                default['x_lot_breakdown_json'] = False
            else:
                if 'lot_ids' not in default and self.lot_ids:
                    default['lot_ids'] = [(6, 0, self.lot_ids.ids)]
                if 'x_lot_breakdown_json' not in default and self.x_lot_breakdown_json:
                    default['x_lot_breakdown_json'] = self.x_lot_breakdown_json

        return super(SaleOrderLine, self).copy_data(default)

    def copy(self, default=None):
        if len(self) == 1:
            _logger.info(
                "[STONE LINE COPY] Línea ID: %s, state=%s, lot_ids=%s",
                self.id,
                self.state,
                self.lot_ids.ids,
            )
        result = super(SaleOrderLine, self).copy(default)
        if len(self) == 1:
            _logger.info(
                "[STONE LINE COPY] Nueva línea ID: %s, lot_ids=%s",
                result.id,
                result.lot_ids.ids if result else [],
            )
        return result

    @api.model_create_multi
    def create(self, vals_list):
        clean_vals_list = []

        for idx, vals in enumerate(vals_list):
            vals_to_create = vals

            if (
                ('lot_ids' in vals or 'x_lot_breakdown_json' in vals)
                and self._stone_vals_target_order_is_unconfirmed(vals)
            ):
                _logger.warning(
                    "[STONE LINE CREATE] Se intentó crear selección de stock en cotización. "
                    "Se limpiará. vals[%s] lot_ids=%s breakdown=%s",
                    idx,
                    vals.get('lot_ids'),
                    vals.get('x_lot_breakdown_json'),
                )
                vals_to_create = self._stone_sanitize_quote_selection_vals(vals)

            elif 'lot_ids' in vals or 'x_lot_breakdown_json' in vals:
                _logger.info(
                    "[STONE LINE CREATE] vals[%s] lot_ids=%s breakdown=%s",
                    idx,
                    vals.get('lot_ids'),
                    vals.get('x_lot_breakdown_json'),
                )

            clean_vals_list.append(vals_to_create)

        return super(SaleOrderLine, self).create(clean_vals_list)

    def _stone_validate_lot_holds(self):
        """Un lote con HOLD activo de OTRO cliente no puede quedar asignado a
        la línea. Corre dentro del write, con candado FOR UPDATE sobre los
        quants: dos operaciones simultáneas sobre el mismo lote se serializan
        y la segunda ve el hold ya confirmado. Lotes sin quant interno (aún en
        tránsito) no se tocan: su control vive en la torre de control."""
        Quant = self.env['stock.quant'].sudo()
        for line in self:
            if not line.lot_ids:
                continue
            company = line.company_id or self.env.company
            quants = Quant.search([
                ('lot_id', 'in', line.lot_ids.ids),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
                ('company_id', '=', company.id),
            ])
            if not quants:
                continue
            self.env.cr.execute(
                "SELECT id FROM stock_quant WHERE id IN %s FOR UPDATE",
                [tuple(quants.ids)],
            )
            quants.invalidate_recordset()
            order_partner = line.order_id.partner_id
            for quant in quants:
                hold = quant.x_hold_activo_id if quant.x_tiene_hold else False
                if (hold and hold.partner_id and order_partner
                        and hold.partner_id.commercial_partner_id
                        != order_partner.commercial_partner_id):
                    raise UserError(_(
                        'El lote %(lot)s está APARTADO para %(partner)s y no '
                        'puede asignarse a este pedido. Si el apartado ya no '
                        'aplica, cancélalo primero.',
                        lot=quant.lot_id.name,
                        partner=hold.partner_id.name,
                    ))

    def write(self, vals):
        vals = dict(vals or {})

        has_selection_vals = any(
            key in vals for key in ('lot_ids', 'x_lot_breakdown_json')
        )

        if has_selection_vals:
            _logger.info("[STONE LINE WRITE] Líneas IDs: %s", self.ids)
            if 'lot_ids' in vals:
                _logger.info("[STONE LINE WRITE] lot_ids EN vals: %s", vals['lot_ids'])
            if 'x_lot_breakdown_json' in vals:
                _logger.info("[STONE LINE WRITE] breakdown EN vals: %s", vals['x_lot_breakdown_json'])

            # REGLA CENTRAL (alcance LOCAL de este módulo):
            # Dentro de ESTE write, seleccionar/desasignar placas NO aplica el
            # product_uom_qty que venga en el mismo vals: la cantidad tecleada en
            # paralelo a un cambio de lotes se descarta y se conserva la solicitada.
            #
            # OJO: esto NO significa que la cantidad nunca cambie por las placas.
            # 'stock_transit_allocation' (que depende de este módulo, por lo que su
            # write envuelve a este) aplica DESPUÉS la regla de PISO/RATCHET: si lo
            # asignado supera lo solicitado, sube product_uom_qty a lo asignado
            # ('la asignada manda cuando es más'), y nunca permite cobrar menos de
            # lo asignado. Ese ajuste corre como un write anidado solo con
            # product_uom_qty (sin lot_ids), así que este pop no lo afecta.
            if (
                'product_uom_qty' in vals
                and not self.env.context.get('allow_stone_selection_update_qty')
            ):
                _logger.info(
                    "[STONE LINE WRITE] Ignorando product_uom_qty=%s porque vino junto con selección de lotes. "
                    "La cantidad solicitada se conserva (el piso/ratchet de tránsito la ajustará si aplica).",
                    vals.get('product_uom_qty'),
                )
                vals.pop('product_uom_qty', None)

        ctx = dict(self.env.context, skip_stone_sync_so=True)

        if has_selection_vals:
            blocked_lines = self.filtered(lambda l: not l._stone_can_select_lots())
            allowed_lines = self - blocked_lines

            result = True

            if blocked_lines:
                clean_vals = self._stone_sanitize_quote_selection_vals(vals)
                _logger.warning(
                    "[STONE LINE WRITE] Bloqueada selección de stock en línea(s) no confirmadas: %s. "
                    "Se limpiarán lot_ids/breakdown.",
                    blocked_lines.ids,
                )
                result = super(
                    SaleOrderLine,
                    blocked_lines.with_context(ctx)
                ).write(clean_vals) and result

            if allowed_lines:
                result = super(
                    SaleOrderLine,
                    allowed_lines.with_context(ctx)
                ).write(vals) and result
                # Revalidación EN la transacción: si un lote recién asignado
                # tiene hold activo de OTRO cliente (creado un segundo antes
                # por otra operación), el write completo se revierte.
                if not self.env.context.get('skip_hold_validation'):
                    allowed_lines._stone_validate_lot_holds()

        else:
            result = super(SaleOrderLine, self.with_context(ctx)).write(vals)

        if (
            any(k in vals for k in ('lot_ids', 'x_lot_breakdown_json'))
            and not self.env.context.get('skip_stone_sync_picking')
        ):
            for line in self:
                if line.state in ['sale', 'done'] and line.move_ids:
                    _logger.info(
                        "[STONE SYNC] Detectado cambio en lotes SO para línea %s. Sincronizando Picking...",
                        line.id,
                    )
                    line._sync_lots_to_picking_moves()

        return result

    def _sync_lots_to_picking_moves(self):
        ctx = dict(
            self.env.context,
            skip_stone_sync_so=True,
            skip_picking_clean=True,
            skip_hold_validation=True,
        )

        for sale_line in self:
            if not sale_line._stone_can_select_lots():
                _logger.warning(
                    "[STONE SYNC] Se ignoró sincronización de lotes en línea no confirmada %s.",
                    sale_line.id,
                )
                continue

            target_lots = sale_line.lot_ids
            breakdown = sale_line._parse_breakdown_dict()

            moves = sale_line.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'])

            for move in moves:
                picking = move.picking_id
                expected_by_lot = {}
                total_qty = 0.0

                for lot in target_lots:
                    expected_qty, physical_qty, tipo, quants = sale_line._stone_line_expected_qty_for_lot(
                        lot,
                        breakdown,
                        move=move,
                    )
                    expected_by_lot[lot.id] = {
                        'qty': expected_qty,
                        'physical_qty': physical_qty,
                        'tipo': tipo,
                        'quants': quants,
                    }
                    total_qty += expected_qty

                if total_qty > 0 and abs((move.product_uom_qty or 0.0) - total_qty) > 0.0001:
                    _logger.info(
                        "[STONE SYNC] Ajustando demanda Move %s de %s a %s",
                        move.id,
                        move.product_uom_qty,
                        total_qty,
                    )
                    move.with_context(ctx).write({'product_uom_qty': total_qty})

                existing_move_lines = move.move_line_ids
                existing_lots = existing_move_lines.mapped('lot_id')

                lots_to_remove = existing_lots - target_lots
                if lots_to_remove:
                    lines_to_unlink = existing_move_lines.filtered(lambda ml: ml.lot_id in lots_to_remove)
                    _logger.info(
                        "[STONE SYNC] Eliminando %s lote(s) del picking %s",
                        len(lines_to_unlink),
                        picking.name if picking else 'N/A',
                    )
                    lines_to_unlink.with_context(ctx).unlink()

                lots_to_add = target_lots - existing_lots
                if lots_to_add:
                    _logger.info(
                        "[STONE SYNC] Agregando %s lote(s) al picking %s",
                        len(lots_to_add),
                        picking.name if picking else 'N/A',
                    )
                    for lot in lots_to_add:
                        data = expected_by_lot.get(lot.id) or {}
                        qty = data.get('qty') or 0.0
                        quants = data.get('quants') or sale_line._stone_line_get_lot_quants(lot, move=move)

                        if not quants:
                            _logger.warning(
                                "[STONE SYNC] No se pudo sincronizar lote %s: no hay stock físico encontrado.",
                                lot.name,
                            )
                            continue

                        if qty <= 0:
                            continue

                        sale_line._stone_line_create_exact_move_lines(move, lot, qty, quants, ctx)

                for lot in (target_lots & existing_lots):
                    existing_lines = move.move_line_ids.filtered(lambda ml: ml.lot_id.id == lot.id)
                    data = expected_by_lot.get(lot.id) or {}
                    expected_qty = data.get('qty') or 0.0
                    quants = data.get('quants') or sale_line._stone_line_get_lot_quants(lot, move=move)

                    if not existing_lines:
                        if expected_qty > 0 and quants:
                            sale_line._stone_line_create_exact_move_lines(move, lot, expected_qty, quants, ctx)
                        continue

                    current_qty = sum(sale_line._stone_line_move_line_qty(ml) for ml in existing_lines)
                    valid_location_ids = set(quants.mapped('location_id').ids) if quants else set()
                    current_location_ids = set(existing_lines.mapped('location_id').ids)

                    needs_rebuild = abs(current_qty - expected_qty) > 0.0001
                    if valid_location_ids and (current_location_ids - valid_location_ids):
                        needs_rebuild = True

                    if not needs_rebuild:
                        continue

                    _logger.info(
                        "[STONE SYNC] Reconstruyendo lote %s en move %s: actual %.6f → esperado %.6f",
                        lot.name,
                        move.id,
                        current_qty,
                        expected_qty,
                    )
                    existing_lines.with_context(ctx).unlink()

                    if expected_qty > 0 and quants:
                        sale_line._stone_line_create_exact_move_lines(
                            move,
                            lot,
                            expected_qty,
                            quants,
                            ctx,
                        )

    def read(self, fields=None, load='_classic_read'):
        result = super(SaleOrderLine, self).read(fields, load)
        if fields and 'lot_ids' in fields:
            _logger.info("[STONE LINE READ] IDs: %s, fields: %s", self.ids, fields)
        return result

    @api.onchange('lot_ids', 'x_lot_breakdown_json')
    def _onchange_lot_ids(self):
        if not self._stone_can_select_lots():
            if self.lot_ids or self.x_lot_breakdown_json:
                self.lot_ids = False
                self.x_lot_breakdown_json = False
                return {
                    'warning': {
                        'title': _('Selección de stock bloqueada'),
                        'message': _(
                            'Solo puedes seleccionar lotes/placas cuando la cotización '
                            'ya fue confirmada como orden de venta. En cotización captura '
                            'únicamente la cantidad solicitada.'
                        ),
                    }
                }
            return

        # REGLA CENTRAL (alcance LOCAL de este módulo):
        # En el onchange de este módulo la selección de placas no recalcula
        # product_uom_qty; queda como cantidad solicitada / demanda comercial.
        #
        # El ajuste real lo hace 'stock_transit_allocation' al guardar (write):
        # piso/ratchet que sube la solicitada a lo asignado cuando es más y nunca
        # deja cobrar menos de lo asignado. Aquí no se toca para no pelear con
        # esa derivación.
        return
    
    def _som_cap_lot_breakdown_to_line(self, items):
        """El desglose por lote de una línea JAMÁS muestra más que lo
        vendido: sin breakdown, el fallback era el stock FÍSICO del lote
        (p. ej. 'Lote × 1000' en una venta de 600). Se recorta en orden
        greedy y se descartan los que quedan en cero."""
        limit = self.product_uom_qty or 0.0
        if limit <= 0 or not items:
            return items
        running = 0.0
        capped = []
        for item in items:
            allowed = max(min(item.get('quantity', 0.0), limit - running), 0.0)
            running += allowed
            if allowed > 0.0001:
                item = dict(item, quantity=allowed)
                capped.append(item)
        return capped or items[:1]

    def _som_breakdown_qty_for_lot(self, breakdown, lot):
        """Cantidad asignada del lote en el desglose. El breakdown del
        carrito puede venir con llave de LOT o de QUANT — se buscan ambas
        (mismo criterio que _stone_line_expected_qty_for_lot)."""
        if not breakdown:
            return None
        val = breakdown.get(str(lot.id))
        if val is not None:
            return float(val)
        if 'x_selected_lots' in self._fields and self.x_selected_lots:
            for quant in self.x_selected_lots:
                if quant.lot_id.id == lot.id and str(quant.id) in breakdown:
                    return float(breakdown[str(quant.id)])
        return None

    def _get_all_sale_lots_with_qty(self):
        self.ensure_one()

        if not self._stone_can_select_lots():
            return []

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
                lot_data[lot.id]['quantity'] += self._stone_line_move_line_qty(ml)
            return self._som_cap_lot_breakdown_to_line(list(lot_data.values()))

        if self.lot_ids:
            breakdown = self._parse_breakdown_dict()

            result = []
            for lot in self.lot_ids:
                tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'

                bqty = (self._som_breakdown_qty_for_lot(breakdown, lot)
                        if tipo in ('formato', 'pieza') else None)
                if bqty is not None:
                    qty = bqty
                else:
                    physical_qty = self._stone_line_get_lot_physical_qty(lot)
                    qty = physical_qty if physical_qty else (
                        lot.x_alto * lot.x_ancho
                        if lot.x_alto and lot.x_ancho
                        else 0.0
                    )

                result.append({
                    'lot': lot,
                    'quantity': qty,
                })
            return self._som_cap_lot_breakdown_to_line(result)

        # Piezas/formatos vendidos desde el carrito: la selección vive en
        # x_selected_lots (+ x_lot_breakdown_json, del módulo del carrito) y
        # puede no estar sincronizada a lot_ids porque sin reserva forzada de
        # lote tampoco hay move lines con lote. Sin este fallback, el reporte
        # detalle no mostraba el desglose de lotes de productos tipo pieza.
        if 'x_selected_lots' in self._fields and self.x_selected_lots:
            breakdown = self._parse_breakdown_dict()
            result = []
            seen_lot_ids = set()
            for quant in self.x_selected_lots:
                lot = quant.lot_id
                if not lot or lot.id in seen_lot_ids:
                    continue
                seen_lot_ids.add(lot.id)
                tipo = str(lot.x_tipo).lower() if lot.x_tipo else 'placa'
                lot_id_str = str(lot.id)

                bqty = None
                if tipo in ('formato', 'pieza'):
                    if lot_id_str in breakdown:
                        bqty = float(breakdown[lot_id_str])
                    elif str(quant.id) in breakdown:
                        bqty = float(breakdown[str(quant.id)])
                if bqty is not None:
                    qty = bqty
                else:
                    qty = quant.quantity or (
                        lot.x_alto * lot.x_ancho
                        if lot.x_alto and lot.x_ancho
                        else 0.0
                    )

                result.append({
                    'lot': lot,
                    'quantity': qty,
                })
            return self._som_cap_lot_breakdown_to_line(result)

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
        self.ensure_one()

        if not self._stone_can_select_lots():
            return []

        breakdown = self._parse_breakdown_dict()
        current_lot_ids = list(self.lot_ids.ids)

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

        all_lot_ids = list(current_lot_ids) + [
            lid for lid in ghost_lot_ids if lid not in current_lot_ids
        ]

        if not all_lot_ids:
            return []

        Lot = self.env['stock.lot']
        lots = Lot.browse(all_lot_ids)
        lots_map = {l.id: l for l in lots if l.exists()}

        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', all_lot_ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ])
        qty_map = {}
        loc_map = {}
        for q in quants:
            qty_map[q.lot_id.id] = qty_map.get(q.lot_id.id, 0.0) + q.quantity
            if q.lot_id.id not in loc_map and q.location_id:
                # Ubicación RECORTADA: último padre / último hijo, para que
                # la columna no se coma la tabla con la ruta completa.
                parts = [p for p in (q.location_id.complete_name
                                     or q.location_id.display_name
                                     or '').split('/') if p]
                loc_map[q.lot_id.id] = '/'.join(parts[-2:]) if parts else ''

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

            badges = []
            is_locked = False

            if d:
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
                'location': loc_map.get(lot_id, ''),
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