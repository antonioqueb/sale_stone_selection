# -*- coding: utf-8 -*-
{
    'name': 'Stone Selection & Visual Sale Grid',
    'version': '17.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Selección visual agrupada de placas (piedra/mármol) en ventas',
    'description': """
        Módulo profesional para la gestión de ventas de piedra natural.
        
        Características:
        - Inyección de componente OWL en líneas de pedido.
        - Selección visual de lotes (placas) agrupadas por Bloque.
        - Cálculo automático de m² basado en selección.
        - Visualización de dimensiones, ubicación y tipo.
        - UX mejorada: Acordeón expandible sin popups intrusivos.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    'depends': ['sale_management', 'stock'],
    'data': [
        'views/sale_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_stone_selection/static/src/scss/stone_styles.scss',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.xml',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.js',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.xml',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
