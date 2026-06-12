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
 *  - Los toggles/checkbox (p.ej. 'Mandar a pedir', 'Asignar') sí guardan
 *    pronto: no pierden nada al recargar.
 *  - NO guarda mientras la UI de selección de placas está abierta (panel
 *    expandido, selector o visor de fotos): el guardado recarga el form y
 *    destruye ese DOM inyectado, cerrándole la selección al usuario a media
 *    edición/borrado. Las placas se persisten solas por ORM, no pierden nada.
 *
 * Se activa SOLO en el formulario de sale.order vía js_class="stone_autosave_form".
 * Usa únicamente API estable del record (.dirty / .resId / .save()).
 */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { useEffect, onMounted, onWillUnmount } from "@odoo/owl";

// Retraso base tras detectar cambios antes de intentar guardar (ms).
const AUTOSAVE_DELAY_MS = 3000;
// Tiempo mínimo sin teclear (y sin input de texto enfocado) requerido para
// guardar. Es lo que hace que "espere a que dejes de escribir".
const QUIET_MS = 6000;
// Selectores del DOM inyectado por la selección de placas (stone_line_list).
// Mientras exista alguno, el autosave se pospone: guardar recargaría el form
// y cerraría/reiniciaría la selección en curso.
const STONE_UI_OPEN_SELECTORS = [
    ".stone-popup-root",     // selector de placas (popup)
    ".stone-selected-row",   // panel expandido de lotes seleccionados
    ".stone-lightbox-root",  // visor de fotos del lote
];

export class StoneAutosaveFormController extends formView.Controller {
    setup() {
        super.setup();
        this.notification = useService("notification");
        this._autosaveTimer = null;
        this._autosaving = false;
        this._lastEditTs = 0;
        // Evita repetir el aviso de "cambio rechazado" en cada reintento; se
        // rearma cuando el usuario vuelve a editar.
        this._saveErrorNotified = false;

        // Registra actividad de tecleo para posponer el guardado.
        this._onUserActivity = () => {
            this._lastEditTs = Date.now();
            // Nueva edición: permite volver a avisar y reprograma el guardado
            // (tras una corrección de un valor rechazado, este es el disparador
            // que reintenta el guardado).
            this._saveErrorNotified = false;
            if (this._isRootDirty()) {
                this._scheduleAutosave(AUTOSAVE_DELAY_MS);
            }
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

    /**
     * ¿Está abierta la UI de selección de placas (popup, panel expandido o
     * lightbox)? Mientras lo esté no se guarda: el reload del guardado
     * destruiría ese DOM y le cerraría la selección al usuario, p.ej. al ir
     * borrando placas con la X.
     */
    _isStoneSelectionUiOpen() {
        return STONE_UI_OPEN_SELECTORS.some((sel) => document.querySelector(sel));
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
        // También espera a que se cierre la UI de selección de placas: las
        // placas ya se persisten solas por ORM y guardar el form a media
        // selección/borrado recargaría la vista y reiniciaría todo el ciclo.
        const sinceEdit = Date.now() - this._lastEditTs;
        if (this._isStoneSelectionUiOpen() || this._isTextEditingActive() || sinceEdit < QUIET_MS) {
            this._scheduleAutosave(QUIET_MS);
            return;
        }

        this._autosaving = true;
        let saveFailed = false;
        try {
            await this.model.root.save();
        } catch (error) {
            // El autosave no debe interrumpir la edición, pero SÍ debe avisar
            // cuando el SERVIDOR RECHAZA el cambio (p.ej. la regla de piso: la
            // cantidad no puede ser menor que lo asignado en placas). Antes este
            // error se tragaba en silencio y daba la falsa impresión de que el
            // valor inválido se había guardado.
            saveFailed = true;
            console.warn("[STONE AUTOSAVE] Guardado automático no aplicado:", error);
            if (!this._saveErrorNotified) {
                this._saveErrorNotified = true;
                this._notifySaveError(error);
            }
        } finally {
            this._autosaving = false;
            // Solo reprograma tras un guardado EXITOSO con cambios nuevos. Si
            // falló (p.ej. validación de piso), NO reintenta en bucle: espera a
            // que el usuario corrija el valor, lo cual dispara _onUserActivity y
            // reprograma el guardado.
            if (!saveFailed && !this._isRootNew() && this._isRootDirty()) {
                this._scheduleAutosave(AUTOSAVE_DELAY_MS);
            }
        }
    }

    /**
     * Muestra al usuario el motivo por el que el servidor rechazó el guardado
     * automático. Extrae el mensaje del servidor (UserError) de las formas
     * conocidas entre versiones de Odoo y cae a un mensaje genérico.
     */
    _notifySaveError(error) {
        let message =
            (error && error.data && error.data.message) ||
            (error && error.message && error.message.data && error.message.data.message) ||
            (error && typeof error.message === "string" ? error.message : "") ||
            "";

        message = (message || "").toString().trim();

        if (!message) {
            message = _t(
                "No se pudo guardar el cambio. Revisa la cantidad: no puede ser menor que lo asignado en placas."
            );
        }

        this.notification.add(message, {
            title: _t("Cambio no guardado"),
            type: "warning",
            sticky: false,
        });
    }
}

registry.category("views").add("stone_autosave_form", {
    ...formView,
    Controller: StoneAutosaveFormController,
});
