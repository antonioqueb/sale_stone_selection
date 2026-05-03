# -*- coding: utf-8 -*-

from . import sale_order
from . import sale_order_line
from . import stock_quant
from . import stock_move
from . import stock_move_line
from . import sale_stone_swap_history

# IMPORTANTE:
# No importar sale_swap_wizard aquí.
# Ese archivo hereda de sale.swap.wizard, modelo definido por sale_delivery_wizard.
# Importarlo desde sale_stone_selection crea dependencia circular:
# sale_stone_selection -> sale_delivery_wizard -> sale_stone_selection.