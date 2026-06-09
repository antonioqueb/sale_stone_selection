# -*- coding: utf-8 -*-
{
    'name': 'Stone Selection & Visual Sale Grid',
    'version': '19.0.1.4.2',
    'category': 'Sales/Sales',
    'summary': 'Selección visual de placas con reserva estricta y estatus de entrega',
    'description': """
        - Selección visual (Grid) en líneas de venta.
        - Reserva estricta de lotes seleccionados (Bypass FIFO).
        - Integración con stock_lot_dimensions para limpieza de asignaciones automáticas.
        - Estatus de entrega/devolución/swap por lote, visible en lista inline y popup.

        Importante:
        Este módulo NO depende de sale_delivery_wizard para evitar dependencia circular.
        La integración específica con entregas/swap se conecta desde sale_delivery_wizard.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    'depends': [
        'sale_management',
        'stock',
        'stock_lot_dimensions',
        'inventory_shopping_cart',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_views.xml',
        'views/stock_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_stone_selection/static/src/js/sale_autosave.js',
            'sale_stone_selection/static/src/scss/stone_styles.scss',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.xml',
            'sale_stone_selection/static/src/components/stone_grid/stone_grid.js',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.xml',
            'sale_stone_selection/static/src/components/stone_line_list/stone_line_list.js',
            'sale_stone_selection/static/src/components/stone_move_grid/stone_move_grid.xml',
            'sale_stone_selection/static/src/components/stone_move_grid/stone_move_grid.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'OPL-1',
}