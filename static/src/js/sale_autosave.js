/** @odoo-module */
/**
 * Autosave del formulario de la orden de venta.
 *
 * Evita tener que pulsar "Guardar" tras cada cambio. Reglas pensadas para NO
 * interrumpir la edición:
 *  - Espera a que el usuario deje de escribir unos segundos (debounce desde la
 *    última tecla).
 *  - NO guarda mientras hay un campo de texto enfocado (así el reload posterior
 *    al guardado no cierra el input en el que estás).
 *  - Los toggles/checkbox (p.ej. 'Mandar a pedir', 'Por Asignar') sí guardan
 *    pronto: no pierden nada al recargar.
 *
 * Se activa SOLO en el formulario de sale.order vía js_class="stone_autosave_form".
 * Usa únicamente API estable del record (.dirty / .resId / .save()).
 */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { useEffect, onMounted, onWillUnmount } from "@odoo/owl";

// Retraso base tras detectar cambios antes de intentar guardar (ms).
const AUTOSAVE_DELAY_MS = 1500;
// Tiempo mínimo sin teclear (y sin input de texto enfocado) requerido para
// guardar. Es lo que hace que "espere a que dejes de escribir".
const QUIET_MS = 3000;

export class StoneAutosaveFormController extends formView.Controller {
    setup() {
        super.setup();
        this._autosaveTimer = null;
        this._autosaving = false;
        this._lastEditTs = 0;

        // Registra actividad de tecleo para posponer el guardado.
        this._onUserActivity = () => {
            this._lastEditTs = Date.now();
        };

        onMounted(() => {
            document.addEventListener("input", this._onUserActivity, true);
            document.addEventListener("keydown", this._onUserActivity, true);
        });

        onWillUnmount(() => {
            document.removeEventListener("input", this._onUserActivity, true);
            document.removeEventListener("keydown", this._onUserActivity, true);
            if (this._autosaveTimer) {
                clearTimeout(this._autosaveTimer);
                this._autosaveTimer = null;
            }
        });

        // Reacciona a que el registro raíz pase a "sucio".
        useEffect(
            () => {
                if (this._isRootDirty()) {
                    this._scheduleAutosave(AUTOSAVE_DELAY_MS);
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
        return !!(root && (root.dirty ?? root.isDirty));
    }

    _isRootNew() {
        const root = this.model.root;
        // Sin resId el registro aún no existe en BD: no autoguardar para no
        // disparar validaciones de un registro a medio crear.
        return !root || !root.resId;
    }

    /**
     * ¿Hay un campo de TEXTO enfocado? Solo esos pierden al recargar; los
     * checkbox/radio/toggle no, así que no bloquean el autosave.
     */
    _isTextEditingActive() {
        const el = document.activeElement;
        if (!el) {
            return false;
        }
        if (el.isContentEditable) {
            return true;
        }
        const tag = (el.tagName || "").toLowerCase();
        if (tag === "textarea") {
            return true;
        }
        if (tag === "input") {
            const type = (el.type || "text").toLowerCase();
            return !["checkbox", "radio", "button", "submit", "reset"].includes(type);
        }
        return false;
    }

    _scheduleAutosave(delay) {
        if (this._autosaveTimer) {
            clearTimeout(this._autosaveTimer);
        }
        this._autosaveTimer = setTimeout(() => {
            this._autosaveTimer = null;
            this._runAutosave();
        }, delay);
    }

    async _runAutosave() {
        if (this._autosaving || this._isRootNew() || !this._isRootDirty()) {
            return;
        }

        // Espera a que el usuario deje de escribir y a que ningún campo de texto
        // esté enfocado (evita que el reload del guardado cierre el input).
        const sinceEdit = Date.now() - this._lastEditTs;
        if (this._isTextEditingActive() || sinceEdit < QUIET_MS) {
            this._scheduleAutosave(QUIET_MS);
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
                this._scheduleAutosave(AUTOSAVE_DELAY_MS);
            }
        }
    }
}

registry.category("views").add("stone_autosave_form", {
    ...formView,
    Controller: StoneAutosaveFormController,
});
