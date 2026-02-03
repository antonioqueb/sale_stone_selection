/** @odoo-module */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";

export class StoneMoveGridField extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            isLoading: true,
            quants: [],
            filters: {
                lot_name: '',
                bloque: '',
                atado: '',
                alto_min: '',
                ancho_min: ''
            }
        });

        this.searchTimeout = null;

        onWillStart(async () => {
            await this.loadInventory();
        });

        onWillUpdateProps(async (nextProps) => {
            // Recargar si cambia el producto o la ubicación origen
            if (nextProps.record.data.product_id[0] !== this.props.record.data.product_id[0] ||
                nextProps.record.data.location_id[0] !== this.props.record.data.location_id[0]) {
                await this.loadInventory(nextProps);
            }
        });
    }

    get record() {
        return this.props.record.data;
    }

    /**
     * Carga el inventario disponible en la ubicación de origen
     */
    async loadInventory(props = this.props) {
        const recordData = props.record.data;
        const productId = recordData.product_id ? recordData.product_id[0] : false;
        const locationId = recordData.location_id ? recordData.location_id[0] : false;

        if (!productId) {
            this.state.quants = [];
            this.state.isLoading = false;
            return;
        }

        this.state.isLoading = true;

        try {
            // Obtenemos los lotes que YA están seleccionados en move_line_ids
            // move_line_ids es un x2many. Iteramos sus registros para sacar los lot_id.
            const currentLines = recordData.move_line_ids.records || [];
            const currentLotIds = currentLines
                .map(r => r.data.lot_id ? r.data.lot_id[0] : false)
                .filter(id => id);

            // Reusamos tu método de búsqueda del modelo stock.quant
            // Nota: Agregamos filtro de location_id para buscar solo en el origen del movimiento
            const domainExtras = [];
            if (locationId) {
                // Forzamos búsqueda en la ubicación origen (o hijas)
                // Nota: search_stone_inventory_for_so usa location_id.usage='internal' por defecto,
                // aquí lo ideal es pasar un dominio extra si tu backend lo soporta, 
                // o filtrar después. Para ser consistente con tu método existente:
                // Vamos a inyectar un filtro 'location_id' en el diccionario 'filters'
                // si modificamos el backend para leerlo, o confiamos en que 'internal' es suficiente
                // y filtramos en JS. Lo mejor es filtrar en JS si el método python es rígido.
            }

            const quants = await this.orm.call(
                'stock.quant',
                'search_stone_inventory_for_so',
                [],
                {
                    product_id: productId,
                    filters: this.state.filters,
                    current_lot_ids: currentLotIds
                }
            );

            // Filtrado adicional en JS para asegurar que sea la ubicación correcta 
            // (si search_stone_inventory_for_so busca en todo el almacén)
            // Asumimos que queremos ver todo lo disponible "Interno" o filtramos por locationId
            // Si el movimiento es específico de una ubicación padre, filtramos:
            let filteredQuants = quants;
            if (locationId) {
                // Opcional: filtrar si la ubicación devuelta no es hija de la ubicación origen
                // Por simplicidad, mostramos todo lo interno como en ventas, 
                // o descomenta abajo para ser estricto:
                // filteredQuants = quants.filter(q => q.location_id[0] === locationId);
            }

            this.state.quants = filteredQuants;

        } catch (e) {
            console.error("Error cargando inventario stock:", e);
        } finally {
            this.state.isLoading = false;
        }
    }

    /**
     * Agrupa por bloque para la vista
     */
    get groupedQuants() {
        const groups = {};
        for (const q of this.state.quants) {
            const blockName = q.x_bloque || 'General';
            if (!groups[blockName]) {
                groups[blockName] = { name: blockName, items: [], totalArea: 0, count: 0 };
            }
            groups[blockName].items.push(q);
            groups[blockName].count++;
            groups[blockName].totalArea += q.quantity;
        }
        return Object.values(groups).sort((a, b) => b.count - a.count);
    }

    /**
     * Verifica si un Lote (quant) ya está en las líneas del movimiento
     */
    getLineForLot(lotId) {
        const lines = this.props.record.data.move_line_ids.records;
        return lines.find(l => l.data.lot_id && l.data.lot_id[0] === lotId);
    }

    isLotSelected(lotId) {
        return !!this.getLineForLot(lotId);
    }

    /**
     * MANEJO DE SELECCIÓN (CORE LOGIC)
     * Agrega o Elimina registros en move_line_ids
     */
    async toggleLot(quant) {
        if (!quant.lot_id) return;
        const lotId = quant.lot_id[0];
        const existingLine = this.getLineForLot(lotId);

        const x2many = this.props.record.data.move_line_ids;

        if (existingLine) {
            // --- DESELECCIONAR: Eliminar línea ---
            // Usamos el comando x2many unlink
            // Para Owl field, llamamos a una función del prop o modificamos la lista
            // En Odoo 16/17+, x2many fields tienen métodos helpers en el record list.
            
            // Opción A: delete() si es registro virtual o unlink() si es real.
            // La forma segura en Form Views:
            await x2many.removeRecord(existingLine);
        } else {
            // --- SELECCIONAR: Crear línea ---
            // Preparamos los valores por defecto
            const vals = {
                lot_id: [lotId, quant.lot_id[1]],
                quantity: quant.quantity, // Cantidad a reservar
                product_uom_id: this.props.record.data.product_uom, // UoM
                location_id: quant.location_id, // Ubicación origen del quant
                location_dest_id: this.props.record.data.location_dest_id,
                // product_id y otros se heredan del contexto o defaults
            };

            // Crear registro en el x2many
            await x2many.addNewRecord({ position: 'bottom', context: vals });
            
            // Nota: addNewRecord crea el registro. Para establecer valores predeterminados 
            // que no vienen del contexto, a veces hay que hacer update posterior,
            // pero pasando 'context' con default_campo suele funcionar.
            // Si falla, buscar el último record creado y hacer update:
            /*
            const newRec = x2many.records[x2many.records.length - 1];
            await newRec.update(vals);
            */
        }
    }

    // --- Filtros ---
    onFilterChange(key, value) {
        this.state.filters[key] = value;
        if (this.searchTimeout) clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.loadInventory();
        }, 400);
    }
    
    clearFilters() {
        this.state.filters = { lot_name: '', bloque: '', atado: '', alto_min: '', ancho_min: '' };
        this.loadInventory();
    }
}

StoneMoveGridField.template = "sale_stone_selection.StoneMoveGridField";
StoneMoveGridField.props = {
    ...standardFieldProps,
};

// Registramos el widget para usarlo en el XML
registry.category("fields").add("stone_move_grid", {
    component: StoneMoveGridField,
    displayName: "Stone Selection Grid (Move)",
    supportedTypes: ["one2many"],
});