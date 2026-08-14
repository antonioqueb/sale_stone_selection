# -*- coding: utf-8 -*-
from odoo import models, api
import logging
_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _get_committed_lot_ids(self, product_id):
        """
        Retorna IDs de lotes que están comprometidos en órdenes de venta confirmadas.
        """
        committed_move_lines = self.env['stock.move.line'].search([
            ('product_id', '=', product_id),
            ('lot_id', '!=', False),
            ('state', 'not in', ['done', 'cancel']),
            ('move_id.sale_line_id', '!=', False),
            ('move_id.sale_line_id.order_id.state', 'in', ['sale', 'done']),
        ])
        committed_ids = set(committed_move_lines.mapped('lot_id').ids)

        committed_sol = self.env['sale.order.line'].search([
            ('product_id', '=', product_id),
            ('lot_ids', '!=', False),
            ('order_id.state', 'in', ['sale', 'done']),
        ])
        # ENTREGADO NO COMPROMETE (2026-08-14): lot_ids conserva los lotes
        # oficializados aunque la línea YA se entregó. Si ese material
        # regresó por devolución, está físicamente disponible y debe ser
        # elegible otra vez (venta, reclasificación, taller). Comprometido
        # = pendiente de entregar: se descuentan los lotes con salida DONE
        # a cliente de SU MISMA línea (si otra orden abierta los tiene,
        # esa orden los sigue comprometiendo por su cuenta).
        sol_lot_ids = set()
        for sol in committed_sol:
            sol_lot_ids.update(sol.lot_ids.ids)
        delivered_by_line = {}
        if sol_lot_ids:
            done_mls = self.env['stock.move.line'].sudo().search([
                ('product_id', '=', product_id),
                ('lot_id', 'in', list(sol_lot_ids)),
                ('state', '=', 'done'),
                ('location_dest_id.usage', '=', 'customer'),
                ('move_id.sale_line_id', 'in', committed_sol.ids),
            ])
            for ml in done_mls:
                delivered_by_line.setdefault(
                    ml.move_id.sale_line_id.id, set()).add(ml.lot_id.id)
        for sol in committed_sol:
            delivered = delivered_by_line.get(sol.id, set())
            committed_ids.update(
                lid for lid in sol.lot_ids.ids if lid not in delivered)

        # PARCIALIDADES (2026-08-11): el validador de duplicados ya es
        # partial-aware para FORMATO/PIEZA, así que aquí solo se excluyen
        # los lotes COMPLETAMENTE comprometidos:
        # - PLACAS: atómicas — cualquier compromiso las excluye completas.
        # - FORMATO/PIEZA: excluidos solo si lo comprometido (máx entre move
        #   lines vivas y capturas en órdenes) cubre todo el físico; con
        #   remanente siguen seleccionables (el caller los pasa al
        #   passthrough para librar los filtros de reserva/hold).
        if not committed_ids:
            return []
        fully = []
        for lot in self.env['stock.lot'].browse(list(committed_ids)):
            tipo = str(getattr(lot, 'x_tipo', '') or '').lower()
            if tipo not in ('formato', 'pieza'):
                fully.append(lot.id)
                continue
            quants = self.env['stock.quant'].sudo().search([
                ('lot_id', '=', lot.id),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
            ])
            fisico = sum(quants.mapped('quantity'))
            ml_qty = 0.0
            for ml in committed_move_lines:
                if ml.lot_id.id == lot.id:
                    ml_qty += (ml.quantity if 'quantity' in ml._fields
                               else getattr(ml, 'qty_done', 0.0)) or 0.0
            sol_qty = 0.0
            for sol in committed_sol:
                if lot.id not in sol.lot_ids.ids:
                    continue
                qty = None
                if hasattr(sol, '_som_breakdown_qty_for_lot'):
                    bd = getattr(sol, 'x_lot_breakdown_json', None)
                    if bd:
                        qty = sol._som_breakdown_qty_for_lot(bd, lot)
                sol_qty += float(qty) if qty is not None else fisico
            comprometido = max(ml_qty, min(sol_qty, fisico))
            if comprometido >= fisico - 0.0001:
                fully.append(lot.id)
        return fully

    def _build_stone_domain(self, product_id, filters, safe_current_ids, excluded_lot_ids):
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        if excluded_lot_ids:
            base_domain.append(('lot_id', 'not in', excluded_lot_ids))

        free_domain = [('reserved_quantity', '=', 0)]
        if 'x_tiene_hold' in self.env['stock.quant']._fields:
            free_domain.append(('x_tiene_hold', '=', False))

        # Placas retenidas SOLO por un traslado interno de carrito/escáner
        # ABIERTO (reserva DÉBIL de reacomodo de ubicación) siguen siendo
        # vendibles: esa reserva se libera sola al confirmar la venta, así
        # que no deben desaparecer del selector.
        weak_lines = self.env['stock.move.line'].sudo().search([
            ('product_id', '=', int(product_id)),
            ('lot_id', '!=', False),
            ('state', 'in', ('assigned', 'partially_available')),
            ('picking_id.picking_type_code', '=', 'internal'),
            ('picking_id.origin', '=like', 'Carrito - %'),
            ('picking_id.state', 'not in', ('done', 'cancel')),
        ])
        weak_lot_ids = [
            lid for lid in weak_lines.mapped('lot_id').ids
            if lid not in (excluded_lot_ids or [])
        ]

        # APARTADO PARCIAL: un formato/pieza con hold que solo retiene su
        # parcialidad sigue siendo vendible por el REMANENTE — pasa al
        # selector (la validación de holds y los topes cuidan la cantidad).
        partial_hold_lot_ids = []
        if 'x_tiene_hold' in self.env['stock.quant']._fields:
            held_quants = self.env['stock.quant'].sudo().search([
                ('product_id', '=', int(product_id)),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
                ('x_tiene_hold', '=', True),
                ('lot_id.x_tipo', 'in', ('formato', 'pieza')),
            ])
            partial_hold_lot_ids = [
                q.lot_id.id for q in held_quants
                if q.lot_id
                and q.lot_id.id not in (excluded_lot_ids or [])
                and q.som_hold_free_qty() > 0.0001
            ]

        # Comprometidos PARCIALES (formato/pieza con remanente): pueden
        # traer reserva nativa — pasan al passthrough para ser visibles.
        partial_committed_ids = []
        Sol = self.env['sale.order.line'].sudo()
        sols_live = Sol.search([
            ('product_id', '=', int(product_id)),
            ('lot_ids', '!=', False),
            ('order_id.state', 'in', ['sale', 'done']),
        ])
        seen_partial = set()
        for sol in sols_live:
            for lot in sol.lot_ids:
                if lot.id in seen_partial or lot.id in (excluded_lot_ids or []):
                    continue
                tipo = str(getattr(lot, 'x_tipo', '') or '').lower()
                if tipo in ('formato', 'pieza'):
                    seen_partial.add(lot.id)
                    partial_committed_ids.append(lot.id)

        passthrough_ids = list(
            set(safe_current_ids or [])
            | set(weak_lot_ids)
            | set(partial_hold_lot_ids)
            | set(partial_committed_ids))

        if passthrough_ids:
            availability_domain = (
                ['|', ('lot_id', 'in', passthrough_ids)]
                + ['&'] * (len(free_domain) - 1)
                + free_domain
            )
        else:
            availability_domain = free_domain

        domain = base_domain + availability_domain

        if filters.get('bloque'):
            domain.append(('lot_id.x_bloque', 'ilike', filters['bloque']))
        if filters.get('atado'):
            domain.append(('lot_id.x_atado', 'ilike', filters['atado']))
        if filters.get('lot_name'):
            domain.append(('lot_id.name', 'ilike', filters['lot_name']))
        if filters.get('alto_min'):
            try:
                domain.append(('lot_id.x_alto', '>=', float(filters['alto_min'])))
            except Exception:
                pass
        if filters.get('ancho_min'):
            try:
                domain.append(('lot_id.x_ancho', '>=', float(filters['ancho_min'])))
            except Exception:
                pass
        if filters.get('tipo'):
            domain.append(('lot_id.x_tipo', '=', filters['tipo']))

        return domain

    def _build_lots_data(self, lot_ids):
        lots_data = {}
        if not lot_ids:
            return lots_data

        lots = self.env['stock.lot'].browse(lot_ids)
        for lot in lots:
            x_proveedor_value = lot.x_proveedor if 'x_proveedor' in lot._fields else False
            if x_proveedor_value:
                field_type = lot._fields.get('x_proveedor')
                if field_type and field_type.type == 'many2one':
                    x_proveedor_display = x_proveedor_value.name if x_proveedor_value else ''
                else:
                    x_proveedor_display = str(x_proveedor_value) if x_proveedor_value else ''
            else:
                x_proveedor_display = ''

            lots_data[lot.id] = {
                'name': lot.name,
                'x_grosor': lot.x_grosor if 'x_grosor' in lot._fields else 0,
                'x_alto': lot.x_alto if 'x_alto' in lot._fields else 0,
                'x_ancho': lot.x_ancho if 'x_ancho' in lot._fields else 0,
                'x_peso': lot.x_peso if 'x_peso' in lot._fields else 0,
                'x_tipo': lot.x_tipo if 'x_tipo' in lot._fields else '',
                'x_numero_placa': lot.x_numero_placa if 'x_numero_placa' in lot._fields else '',
                'x_bloque': lot.x_bloque if 'x_bloque' in lot._fields else '',
                'x_atado': lot.x_atado if 'x_atado' in lot._fields else '',
                'x_grupo': lot.x_grupo if 'x_grupo' in lot._fields else '',
                'x_color': lot.x_color if 'x_color' in lot._fields else '',
                'x_pedimento': lot.x_pedimento if 'x_pedimento' in lot._fields else '',
                'x_contenedor': lot.x_contenedor if 'x_contenedor' in lot._fields else '',
                'x_referencia_proveedor': lot.x_referencia_proveedor if 'x_referencia_proveedor' in lot._fields else '',
                'x_proveedor': x_proveedor_display,
                'x_origen': lot.x_origen if 'x_origen' in lot._fields else '',
                'x_fotografia_principal': lot.x_fotografia_principal if 'x_fotografia_principal' in lot._fields else False,
                'x_tiene_fotografias': lot.x_tiene_fotografias if 'x_tiene_fotografias' in lot._fields else False,
                'x_cantidad_fotos': lot.x_cantidad_fotos if 'x_cantidad_fotos' in lot._fields else 0,
                'x_detalles_placa': lot.x_detalles_placa if 'x_detalles_placa' in lot._fields else '',
            }

        return lots_data

    def _quants_to_result(self, quants, lots_data):
        result = []
        for q in quants:
            lot_id = q.lot_id.id if q.lot_id else False
            lot_info = lots_data.get(lot_id, {})
            result.append({
                'id': q.id,
                'lot_id': [lot_id, lot_info.get('name', '')] if lot_id else False,
                'location_id': [q.location_id.id, q.location_id.display_name] if q.location_id else False,
                'quantity': q.quantity,
                'reserved_quantity': q.reserved_quantity,
                'x_grosor': lot_info.get('x_grosor', 0) or 0,
                'x_alto': lot_info.get('x_alto', 0) or 0,
                'x_ancho': lot_info.get('x_ancho', 0) or 0,
                'x_peso': lot_info.get('x_peso', 0) or 0,
                'x_tipo': lot_info.get('x_tipo', '') or '',
                'x_numero_placa': lot_info.get('x_numero_placa', '') or '',
                'x_bloque': lot_info.get('x_bloque', '') or '',
                'x_atado': lot_info.get('x_atado', '') or '',
                'x_grupo': lot_info.get('x_grupo', '') or '',
                'x_color': lot_info.get('x_color', '') or '',
                'x_pedimento': lot_info.get('x_pedimento', '') or '',
                'x_contenedor': lot_info.get('x_contenedor', '') or '',
                'x_referencia_proveedor': lot_info.get('x_referencia_proveedor', '') or '',
                'x_proveedor': lot_info.get('x_proveedor', '') or '',
                'x_origen': lot_info.get('x_origen', '') or '',
                'x_fotografia_principal': lot_info.get('x_fotografia_principal', False),
                'x_tiene_fotografias': lot_info.get('x_tiene_fotografias', False),
                'x_cantidad_fotos': lot_info.get('x_cantidad_fotos', 0) or 0,
                'x_detalles_placa': lot_info.get('x_detalles_placa', '') or '',
            })
        return result

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None):
        _logger.info("[STONE QUANT SEARCH] INICIO - product_id: %s, filters: %s", product_id, filters)

        if not filters:
            filters = {}

        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        committed_lot_ids = self._get_committed_lot_ids(int(product_id))
        excluded_lot_ids = [lid for lid in committed_lot_ids if lid not in safe_current_ids]

        domain = self._build_stone_domain(product_id, filters, safe_current_ids, excluded_lot_ids)
        quants = self.search(domain, limit=300, order='lot_id')

        lot_ids = quants.mapped('lot_id').ids
        lots_data = self._build_lots_data(lot_ids)
        result = self._quants_to_result(quants, lots_data)

        _logger.info("[STONE QUANT SEARCH] Encontrados: %s quants", len(result))
        return result

    @api.model
    def search_stone_inventory_for_so_paginated(self, product_id, filters=None, current_lot_ids=None, page=0, page_size=35):
        if not filters:
            filters = {}

        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        committed_lot_ids = self._get_committed_lot_ids(int(product_id))
        excluded_lot_ids = [lid for lid in committed_lot_ids if lid not in safe_current_ids]

        domain = self._build_stone_domain(product_id, filters, safe_current_ids, excluded_lot_ids)

        total = self.search_count(domain)

        offset = int(page) * int(page_size)
        quants = self.search(domain, limit=int(page_size), offset=offset, order='lot_id')

        lot_ids = quants.mapped('lot_id').ids
        lots_data = self._build_lots_data(lot_ids)
        items = self._quants_to_result(quants, lots_data)

        _logger.info(
            "[STONE QUANT PAGINATED] product=%s page=%s total=%s got=%s",
            product_id, page, total, len(items)
        )

        return {'items': items, 'total': total}