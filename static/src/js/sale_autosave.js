/** @odoo-module */
/**
 * Autosave del formulario de la orden de venta.
 *
 * Evita tener que pulsar "Guardar" tras cada cambio: cuando el registro queda
 * "sucio" (cualquier campo confirmado: producto, cantidad, booleanos como
 * 'Mandar a pedir'/'Por Asignar', etc.) se guarda solo, con un pequeño retraso
 * para agrupar cambios seguidos.
 *
 * Se activa SOLO en el formulario de sale.order vía js_class="stone_autosave_form"
 * (no afecta a otros modelos). Usa únicamente API estable del record
 * (.dirty / .resId / .save()).
 */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { useEffect } from "@odoo/owl";

// Retraso tras el último cambio confirmado antes de guardar (ms).
const AUTOSAVE_DELAY_MS = 800;

export class StoneAutosaveFormController extends formView.Controller {
    setup() {
        super.setup();
        this._autosaveTimer = null;
        this._autosaving = false;

        // Reacciona a que el registro raíz pase a "sucio".
        useEffect(
            () => {
                if (this._isRootDirty()) {
                    this._scheduleAutosave();
                }
            },
            () => {
                const root = this.model.root;
                // Se leen ambas variantes para suscribirse a la reactiva real
                // (el nombre del getter cambió entre versiones de Odoo).
                return [root && root.dirty, root && root.isDirty];
            }
        );
    }

    _isRootDirty() {
        const root = this.model.root;
        if (!root) {
            return false;
        }
        return !!(root.dirty ?? root.isDirty);
    }

    _isRootNew() {
        const root = this.model.root;
        // Sin resId el registro aún no existe en BD: no autoguardar para no
        // disparar validaciones de un registro a medio crear.
        return !root || !root.resId;
    }

    _scheduleAutosave() {
        if (this._autosaveTimer) {
            clearTimeout(this._autosaveTimer);
        }
        this._autosaveTimer = setTimeout(() => {
            this._autosaveTimer = null;
            this._runAutosave();
        }, AUTOSAVE_DELAY_MS);
    }

    async _runAutosave() {
        if (this._autosaving || this._isRootNew() || !this._isRootDirty()) {
            return;
        }

        this._autosaving = true;
        try {
            await this.model.root.save();
        } catch (error) {
            // No interrumpimos la edición si el autosave falla (p.ej. validación
            // momentánea). El guardado manual sigue disponible.
            console.warn("[STONE AUTOSAVE] Guardado automático no aplicado:", error);
        } finally {
            this._autosaving = false;
            // Si llegaron cambios nuevos durante el guardado, reprogramar.
            if (!this._isRootNew() && this._isRootDirty()) {
                this._scheduleAutosave();
            }
        }
    }
}

registry.category("views").add("stone_autosave_form", {
    ...formView,
    Controller: StoneAutosaveFormController,
});
