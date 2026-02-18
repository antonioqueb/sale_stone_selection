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
        Estos lotes NO deben aparecer como seleccionables en cotizaciones.
        """
        # 1. Lotes en move_line_ids de pickings activos vinculados a ventas confirmadas
        committed_move_lines = self.env['stock.move.line'].search([
            ('product_id', '=', product_id),
            ('lot_id', '!=', False),
            ('state', 'not in', ['done', 'cancel']),
            ('move_id.sale_line_id', '!=', False),
            ('move_id.sale_line_id.order_id.state', 'in', ['sale', 'done']),
        ])
        committed_ids = set(committed_move_lines.mapped('lot_id').ids)
        
        # 2. También lotes en sale.order.line de órdenes confirmadas
        #    (caso borde: orden confirmada pero picking aún no generado)
        committed_sol = self.env['sale.order.line'].search([
            ('product_id', '=', product_id),
            ('lot_ids', '!=', False),
            ('order_id.state', 'in', ['sale', 'done']),
        ])
        for sol in committed_sol:
            committed_ids.update(sol.lot_ids.ids)
        
        return list(committed_ids)

    def _build_stone_domain(self, product_id, filters, safe_current_ids, excluded_lot_ids):
        """
        Helper interno para construir el dominio de búsqueda de placas.
        Reutilizado por search_stone_inventory_for_so y search_stone_inventory_for_so_paginated.
        """
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

        if safe_current_ids:
            availability_domain = ['|', ('lot_id', 'in', safe_current_ids)] + ['&'] + free_domain
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

        return domain

    def _build_lots_data(self, lot_ids):
        """
        Helper interno: lee todos los campos de los lotes de una sola vez.
        """
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
        """
        Helper interno: convierte recordset de quants a lista de dicts serializables.
        """
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
        """
        Búsqueda de inventario para selección de piedra.
        Devuelve datos completos del lote incluyendo todos los campos personalizados.
        """
        _logger.info("=" * 80)
        _logger.info("[STONE QUANT SEARCH] INICIO - product_id: %s, filters: %s", product_id, filters)

        if not filters:
            filters = {}

        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        committed_lot_ids = self._get_committed_lot_ids(int(product_id))
        excluded_lot_ids = [lid for lid in committed_lot_ids if lid not in safe_current_ids]
        _logger.info("[STONE QUANT SEARCH] Lotes comprometidos excluidos: %s", len(excluded_lot_ids))

        domain = self._build_stone_domain(product_id, filters, safe_current_ids, excluded_lot_ids)
        quants = self.search(domain, limit=300, order='lot_id')

        lot_ids = quants.mapped('lot_id').ids
        lots_data = self._build_lots_data(lot_ids)
        result = self._quants_to_result(quants, lots_data)

        _logger.info("[STONE QUANT SEARCH] Encontrados: %s quants (excluidos %s comprometidos)",
                     len(result), len(excluded_lot_ids))
        _logger.info("[STONE QUANT SEARCH] FIN")
        _logger.info("=" * 80)

        return result

    @api.model
    def search_stone_inventory_for_so_paginated(self, product_id, filters=None, current_lot_ids=None, page=0, page_size=35):
        """
        Versión paginada de search_stone_inventory_for_so.
        Retorna { items: [...], total: N } para soporte de infinite scroll en el popup.
        """
        if not filters:
            filters = {}

        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        committed_lot_ids = self._get_committed_lot_ids(int(product_id))
        excluded_lot_ids = [lid for lid in committed_lot_ids if lid not in safe_current_ids]

        domain = self._build_stone_domain(product_id, filters, safe_current_ids, excluded_lot_ids)

        # Contar total sin límite
        total = self.search_count(domain)

        # Página solicitada
        offset = int(page) * int(page_size)
        quants = self.search(domain, limit=int(page_size), offset=offset, order='lot_id')

        lot_ids = quants.mapped('lot_id').ids
        lots_data = self._build_lots_data(lot_ids)
        items = self._quants_to_result(quants, lots_data)

        _logger.info(
            "[STONE QUANT PAGINATED] product=%s page=%s/%s offset=%s size=%s total=%s got=%s",
            product_id, page, (total // int(page_size)), offset, page_size, total, len(items)
        )

        return {'items': items, 'total': total}