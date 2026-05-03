# -*- coding: utf-8 -*-

"""
Archivo conservado solo por compatibilidad histórica.

No importar este archivo desde models/__init__.py.

La integración con sale.swap.wizard debe vivir en sale_delivery_wizard,
porque sale.swap.wizard pertenece a ese módulo. Esto evita la dependencia
circular entre sale_stone_selection y sale_delivery_wizard.
"""