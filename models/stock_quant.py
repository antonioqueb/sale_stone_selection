# -*- coding: utf-8 -*-
from collections import defaultdict

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
        delivered_qty = defaultdict(float)
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
                delivered_qty[(ml.move_id.sale_line_id.id, ml.lot_id.id)] += (
                    ml.quantity if 'quantity' in ml._fields
                    else getattr(ml, 'qty_done', 0.0)) or 0.0
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
                if qty is None:
                    qty = fisico
                # Lo ya entregado de ESA línea ya salió del físico: no
                # compromete el remanente (V/558 entregó 20 de 20665-2 y
                # seguía sumándolas, dejando el palet "lleno").
                sol_qty += max(
                    float(qty) - delivered_qty.get((sol.id, lot.id), 0.0), 0.0)
            comprometido = max(ml_qty, min(sol_qty, fisico))
            if comprometido >= fisico - 0.0001:
                fully.append(lot.id)
        return fully

    # Remanente menor a esto (2 decimales visibles) = residuo de redondeo,
    # no material vendible.
    SOM_STONE_FREE_EPS = 0.005

    @api.model
    def _som_stone_free_by_lot(self, product_id, lot_ids, company_ids=None,
                               exclude_sale_line_id=None):
        """Libre REAL por lote (formato/pieza): físico interno menos lo que
        OTROS documentos ya tomaron. Mismo criterio que
        stock.lot.hold.order.line._som_lot_free_qty:

            asignado = max(reserva nativa del quant,
                           move lines VIVAS de ventas confirmadas,
                           min(capturado en ventas confirmadas − entregado, físico))
            libre    = físico − asignado − retenido por holds activos

        `exclude_sale_line_id` = la línea que se está editando: su propia
        reserva/captura no se descuenta (está a punto de reemplazarse).
        Devuelve {lot_id: {'fisico': m², 'libre': m²}}."""
        lot_ids = [int(l) for l in (lot_ids or []) if l]
        if not lot_ids:
            return {}
        product_id = int(product_id)
        exclude_id = int(exclude_sale_line_id or 0) or None

        Quant = self.env['stock.quant'].sudo()
        qdom = [
            ('product_id', '=', product_id),
            ('lot_id', 'in', lot_ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ]
        if company_ids:
            qdom.append(('company_id', 'in', list(company_ids)))
        quants = Quant.search(qdom)

        fisico = defaultdict(float)
        reservado = defaultdict(float)
        retenido = defaultdict(float)
        has_hold = 'x_tiene_hold' in Quant._fields
        for q in quants:
            lid = q.lot_id.id
            fisico[lid] += q.quantity or 0.0
            reservado[lid] += q.reserved_quantity or 0.0
            if has_hold and q.x_tiene_hold and hasattr(q, 'som_hold_held_qty'):
                try:
                    retenido[lid] += q.som_hold_held_qty()
                except Exception:
                    retenido[lid] += q.quantity or 0.0

        Ml = self.env['stock.move.line'].sudo()
        qty_field = 'quantity' if 'quantity' in Ml._fields else 'qty_done'
        live_mls = Ml.search([
            ('product_id', '=', product_id),
            ('lot_id', 'in', lot_ids),
            ('state', 'not in', ('done', 'cancel')),
        ])
        asignado_so = defaultdict(float)
        for ml in live_mls:
            qty = getattr(ml, qty_field) or 0.0
            sol = ml.move_id.sale_line_id
            if exclude_id and sol.id == exclude_id:
                # Reserva de la propia línea: no cuenta en su contra.
                reservado[ml.lot_id.id] -= qty
                continue
            if sol and sol.order_id.state in ('sale', 'done'):
                asignado_so[ml.lot_id.id] += qty

        Sol = self.env['sale.order.line'].sudo()
        sols = Sol.search([
            ('product_id', '=', product_id),
            ('lot_ids', 'in', lot_ids),
            ('order_id.state', 'in', ('sale', 'done')),
        ])
        if exclude_id:
            sols = sols.filtered(lambda l: l.id != exclude_id)
        delivered = defaultdict(float)
        if sols:
            done_mls = Ml.search([
                ('product_id', '=', product_id),
                ('lot_id', 'in', lot_ids),
                ('state', '=', 'done'),
                ('location_dest_id.usage', '=', 'customer'),
                ('move_id.sale_line_id', 'in', sols.ids),
            ])
            for ml in done_mls:
                delivered[(ml.move_id.sale_line_id.id, ml.lot_id.id)] += (
                    getattr(ml, qty_field) or 0.0)
        asignado_sol = defaultdict(float)
        for sol in sols:
            bd = getattr(sol, 'x_lot_breakdown_json', None)
            for lot in sol.lot_ids:
                if lot.id not in fisico:
                    continue
                qty = None
                if bd and hasattr(sol, '_som_breakdown_qty_for_lot'):
                    qty = sol._som_breakdown_qty_for_lot(bd, lot)
                if qty is None:
                    # Sin desglose = lote tomado completo.
                    qty = fisico[lot.id]
                asignado_sol[lot.id] += max(
                    float(qty or 0.0) - delivered.get((sol.id, lot.id), 0.0), 0.0)

        out = {}
        for lid in lot_ids:
            f = fisico.get(lid, 0.0)
            asignado = max(
                max(reservado.get(lid, 0.0), 0.0),
                asignado_so.get(lid, 0.0),
                min(asignado_sol.get(lid, 0.0), f),
            )
            out[lid] = {
                'fisico': f,
                'libre': max(f - asignado - retenido.get(lid, 0.0), 0.0),
            }
        return out

    @api.model
    def _som_stone_partial_lot_ids(self, quants, lots_data):
        """Lotes formato/pieza presentes en los quants (los únicos donde el
        libre puede diferir del físico)."""
        out = []
        for q in quants:
            lid = q.lot_id.id if q.lot_id else False
            if not lid:
                continue
            tipo = str((lots_data.get(lid) or {}).get('x_tipo') or '').lower()
            if tipo in ('formato', 'pieza') and lid not in out:
                out.append(lid)
        return out

    @api.model
    def _som_stone_company_ids(self, filters=None):
        """Compañías que acota el selector visual. Si el llamador manda la
        compañía de la VENTA (filters['company_id']) se usa esa; si no, las
        compañías activas del usuario (mismo alcance que las ir.rule)."""
        company_id = (filters or {}).get('company_id')
        try:
            company_id = int(company_id or 0)
        except (TypeError, ValueError):
            company_id = 0
        if company_id:
            return [company_id]
        return self.env.companies.ids

    def _build_stone_domain(self, product_id, filters, safe_current_ids, excluded_lot_ids,
                            sale_line_id=None):
        company_ids = self._som_stone_company_ids(filters)
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
            ('company_id', 'in', company_ids),
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
            ('company_id', 'in', company_ids),
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
                ('company_id', 'in', company_ids),
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
            ('company_id', 'in', company_ids),
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

        # SOLO LO QUE REALMENTE QUEDA: un formato/pieza comprometido o
        # retenido en parte pasa al selector únicamente si su libre real
        # (físico − reservas/capturas de otros − holds) es mayor a cero.
        # Antes bastaba con estar anotado en una venta viva: pallets
        # completos con reserva nativa (o con residuo de redondeo de
        # empaque) salían como "Reserv." y confundían al vendedor.
        remainder_candidates = (
            (set(partial_hold_lot_ids) | set(partial_committed_ids))
            - set(safe_current_ids or []))
        if remainder_candidates:
            free_by_lot = self._som_stone_free_by_lot(
                product_id, list(remainder_candidates), company_ids, sale_line_id)
            with_remainder = {
                lid for lid, info in free_by_lot.items()
                if info.get('libre', 0.0) > self.SOM_STONE_FREE_EPS}
            partial_hold_lot_ids = [
                lid for lid in partial_hold_lot_ids if lid in with_remainder]
            partial_committed_ids = [
                lid for lid in partial_committed_ids if lid in with_remainder]

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

    def _quants_to_result(self, quants, lots_data, free_by_lot=None, keep_physical_lot_ids=None):
        """`quantity` = lo que el usuario puede tomar. Para formato/pieza es
        el LIBRE real del lote (repartido entre sus quants en orden); las
        placas son atómicas y conservan el físico. `physical_qty` siempre
        trae el físico del quant y `free_qty` lo libre que se le asignó."""
        free_by_lot = free_by_lot or {}
        keep_physical = set(keep_physical_lot_ids or [])
        remaining = {lid: info.get('libre', 0.0) for lid, info in free_by_lot.items()}
        result = []
        for q in quants:
            lot_id = q.lot_id.id if q.lot_id else False
            lot_info = lots_data.get(lot_id, {})
            physical = q.quantity or 0.0
            if lot_id in remaining and lot_id not in keep_physical:
                take = max(min(physical, remaining[lot_id]), 0.0)
                remaining[lot_id] -= take
                free_qty = round(take, 4)
            else:
                free_qty = physical
            result.append({
                'id': q.id,
                'lot_id': [lot_id, lot_info.get('name', '')] if lot_id else False,
                'location_id': [q.location_id.id, q.location_id.display_name] if q.location_id else False,
                'quantity': free_qty,
                'physical_qty': physical,
                'free_qty': free_qty,
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
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None, company_id=None,
                                      sale_line_id=None):
        _logger.info("[STONE QUANT SEARCH] INICIO - product_id: %s, filters: %s", product_id, filters)

        if not filters:
            filters = {}
        # company_id opcional = compañía de la VENTA que se está editando
        # (el selector la puede mandar); sin ella, compañías activas.
        if company_id:
            filters = dict(filters, company_id=company_id)

        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        committed_lot_ids = self._get_committed_lot_ids(int(product_id))
        excluded_lot_ids = [lid for lid in committed_lot_ids if lid not in safe_current_ids]

        domain = self._build_stone_domain(product_id, filters, safe_current_ids, excluded_lot_ids,
                                          sale_line_id=sale_line_id)
        quants = self.search(domain, limit=300, order='lot_id')

        lot_ids = quants.mapped('lot_id').ids
        lots_data = self._build_lots_data(lot_ids)
        free_by_lot, keep_physical = self._som_stone_free_for_result(
            product_id, filters, quants, lots_data, safe_current_ids, sale_line_id)
        result = self._quants_to_result(quants, lots_data, free_by_lot, keep_physical)

        _logger.info("[STONE QUANT SEARCH] Encontrados: %s quants", len(result))
        return result

    @api.model
    def _som_stone_free_for_result(self, product_id, filters, quants, lots_data,
                                   safe_current_ids, sale_line_id=None):
        """Mapa de libre por lote para los formato/pieza de la página. Sin
        `sale_line_id` (línea aún sin guardar) los lotes de la propia
        selección conservan el físico: no hay forma de separar su propia
        captura de la de terceros."""
        partial_ids = self._som_stone_partial_lot_ids(quants, lots_data)
        if not partial_ids:
            return {}, []
        company_ids = self._som_stone_company_ids(filters)
        free_by_lot = self._som_stone_free_by_lot(
            product_id, partial_ids, company_ids, sale_line_id)
        keep_physical = [] if sale_line_id else list(safe_current_ids or [])
        return free_by_lot, keep_physical

    @api.model
    def search_stone_inventory_for_so_paginated(self, product_id, filters=None, current_lot_ids=None, page=0, page_size=35, company_id=None,
                                                sale_line_id=None):
        if not filters:
            filters = {}
        if company_id:
            filters = dict(filters, company_id=company_id)

        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        committed_lot_ids = self._get_committed_lot_ids(int(product_id))
        excluded_lot_ids = [lid for lid in committed_lot_ids if lid not in safe_current_ids]

        domain = self._build_stone_domain(product_id, filters, safe_current_ids, excluded_lot_ids,
                                          sale_line_id=sale_line_id)

        total = self.search_count(domain)

        offset = int(page) * int(page_size)
        quants = self.search(domain, limit=int(page_size), offset=offset, order='lot_id')

        lot_ids = quants.mapped('lot_id').ids
        lots_data = self._build_lots_data(lot_ids)
        free_by_lot, keep_physical = self._som_stone_free_for_result(
            product_id, filters, quants, lots_data, safe_current_ids, sale_line_id)
        items = self._quants_to_result(quants, lots_data, free_by_lot, keep_physical)

        _logger.info(
            "[STONE QUANT PAGINATED] product=%s page=%s total=%s got=%s",
            product_id, page, total, len(items)
        )

        return {'items': items, 'total': total}