# -*- coding: utf-8 -*-
from odoo import models, api

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None):
        """
        Método usado por el JS 'stone_line_list.js' para llenar el grid.
        Devuelve lotes disponibles + lotes que ya tienes seleccionados.
        """
        if not filters:
            filters = {}
        
        # Normalizar IDs actuales para la consulta
        safe_current_ids = []
        if current_lot_ids:
            if isinstance(current_lot_ids, list):
                safe_current_ids = [x for x in current_lot_ids if isinstance(x, int)]

        # 1. Dominio Base: Producto correcto y en ubicación interna con stock positivo
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        # 2. Dominio de Disponibilidad
        # Queremos mostrar lotes que:
        # A) No estén reservados y no tengan Hold (si usas el módulo de apartados)
        # B) O que sean los lotes que YO mismo seleccioné (safe_current_ids)
        
        free_domain = [('reserved_quantity', '=', 0)]
        if hasattr(self, 'x_tiene_hold'):
            free_domain.append(('x_tiene_hold', '=', False))

        if safe_current_ids:
            # Lógica: (Es mío) OR (Está libre)
            availability_domain = ['|', ('lot_id', 'in', safe_current_ids)] + ['&'] + free_domain
        else:
            availability_domain = free_domain
            
        domain = base_domain + availability_domain

        # 3. Filtros del Buscador Visual (Bloque, Atado, Dimensiones, etc.)
        if filters.get('bloque'):
            domain.append(('x_bloque', 'ilike', filters['bloque']))
        if filters.get('atado'):
            domain.append(('x_atado', 'ilike', filters['atado']))
        if filters.get('lot_name'):
            domain.append(('lot_id.name', 'ilike', filters['lot_name']))
        
        if filters.get('alto_min'):
            try: domain.append(('x_alto', '>=', float(filters['alto_min'])))
            except: pass
        if filters.get('ancho_min'):
            try: domain.append(('x_ancho', '>=', float(filters['ancho_min'])))
            except: pass

        # Campos a leer (asegúrate de que los x_ existan en tu BD)
        fields_to_read = [
            'lot_id', 'location_id', 'quantity', 'reserved_quantity',
            'x_bloque', 'x_alto', 'x_ancho', 'x_atado', 'x_grosor', 'x_tipo'
        ]
        
        quants = self.search_read(domain, fields_to_read, limit=300, order='x_bloque, lot_id')
        return quants