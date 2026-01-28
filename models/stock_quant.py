# -*- coding: utf-8 -*-
from odoo import models, api

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def search_stone_inventory_for_so(self, product_id, filters=None, current_lot_ids=None):
        """
        Búsqueda especializada:
        1. Filtra por dimensiones y texto.
        2. Excluye material en Hold o Reservado (Comprometido).
        3. EXCEPCIÓN: Incluye siempre los lotes que ya están en 'current_lot_ids' 
           (para que no desaparezcan de la vista si ya los reservó esta orden).
        """
        if not filters:
            filters = {}
        
        # Asegurar lista de IDs actuales
        if not current_lot_ids:
            current_lot_ids = []
        elif isinstance(current_lot_ids, str):
            # Manejo defensivo por si llega como string raro
            current_lot_ids = []

        # --- DOMINIO BASE ---
        # Stock interno y cantidad positiva
        base_domain = [
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)
        ]

        # --- LÓGICA DE DISPONIBILIDAD (NO Comprometido / NO Hold) ---
        # Un lote es visible si:
        # (No tiene reserva Y No tiene Hold) O (Es uno de los lotes ya seleccionados en esta línea)
        
        availability_domain = [
            '&', ('reserved_quantity', '=', 0), # No comprometido
            ('id', '>', 0) # Placeholder para concatenar
        ]
        
        # Verificar si existe el campo hold (del otro módulo)
        if hasattr(self, 'x_tiene_hold'):
            availability_domain = [
                '&', ('reserved_quantity', '=', 0),
                ('x_tiene_hold', '=', False)
            ]

        # Aplicar lógica OR: (Disponible) OR (Ya seleccionado por mí)
        if current_lot_ids:
            # Buscamos el quant asociado a los lotes seleccionados para incluirlos
            # Nota: current_lot_ids son IDs de stock.lot, aqui buscamos stock.quant
            domain = base_domain + ['|', ('lot_id', 'in', current_lot_ids)] + availability_domain
        else:
            domain = base_domain + availability_domain

        # --- FILTROS DE TEXTO ---
        if filters.get('bloque'):
            domain.append(('x_bloque', 'ilike', filters['bloque']))
        
        if filters.get('atado'):
            domain.append(('x_atado', 'ilike', filters['atado']))
            
        if filters.get('contenedor'):
            domain.append(('x_contenedor', 'ilike', filters['contenedor']))
            
        if filters.get('pedimento'):
            domain.append(('x_pedimento', 'ilike', filters['pedimento']))
            
        if filters.get('lot_name'):
            domain.append(('lot_id.name', 'ilike', filters['lot_name']))

        # --- FILTROS NUMÉRICOS (NUEVOS) ---
        # Alto Mínimo
        if filters.get('alto_min'):
            try:
                val = float(filters['alto_min'])
                domain.append(('x_alto', '>=', val))
            except (ValueError, TypeError):
                pass

        # Ancho Mínimo
        if filters.get('ancho_min'):
            try:
                val = float(filters['ancho_min'])
                domain.append(('x_ancho', '>=', val))
            except (ValueError, TypeError):
                pass
                
        # Grosor
        if filters.get('grosor'):
            try:
                val = float(filters['grosor'])
                domain.append(('x_grosor', '>=', val - 0.1))
                domain.append(('x_grosor', '<=', val + 0.1))
            except (ValueError, TypeError):
                pass

        # Campos a leer
        fields = [
            'lot_id', 'location_id', 'quantity', 'reserved_quantity',
            'x_bloque', 'x_alto', 'x_ancho', 
            'x_atado', 'x_contenedor', 'x_grosor'
        ]
        
        # Si existe el campo hold, leerlo para mostrar estatus visual si se requiere
        if hasattr(self, 'x_tiene_hold'):
            fields.append('x_tiene_hold')

        quants = self.search_read(domain, fields, limit=200, order='x_bloque, lot_id')
        
        return quants