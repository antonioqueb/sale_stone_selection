# -*- coding: utf-8 -*-
"""Branding SOM en los correos de venta.

Los templates nativos son noupdate: un <record> que los sobrescriba se
SALTA en el -u. Por eso los cuerpos viven como archivos HTML del módulo
y este helper los ESCRIBE en cada actualización vía <function>.
"""
import logging

from odoo import api, models
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

_TEMPLATES = {
    'sale.mail_template_sale_confirmation': {
        'file': 'sale_stone_selection/data/mail_bodies/confirmation.html',
        'subject': (
            "Tu pedido {{ object.name or '' }} está confirmado"),
    },
    'sale.email_template_edi_sale': {
        'file': 'sale_stone_selection/data/mail_bodies/quotation.html',
        'subject': (
            "Tu {{ object.state in ('draft', 'sent') and 'cotización' "
            "or 'pedido' }} {{ object.name or '' }} ya está disponible"),
    },
}


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    @api.model
    def _som_apply_sale_mail_branding(self):
        for xmlid, spec in _TEMPLATES.items():
            template = self.env.ref(xmlid, raise_if_not_found=False)
            if not template:
                _logger.warning('[SOM MAIL] Template %s no existe.', xmlid)
                continue
            try:
                with file_open(spec['file'], 'r') as f:
                    body = f.read()
            except Exception:
                _logger.exception('[SOM MAIL] Sin cuerpo para %s.', xmlid)
                continue
            # body_html y subject son traducibles: si solo se escribe el
            # idioma base, los partners en español siguen recibiendo la
            # traducción nativa fea. Se escribe en TODOS los idiomas.
            langs = self.env['res.lang'].search([]).mapped('code')
            for lang in langs:
                template.sudo().with_context(lang=lang).write({
                    'subject': spec['subject'],
                    'body_html': body,
                })
            _logger.info(
                '[SOM MAIL] Branding aplicado a %s (%s).',
                xmlid, ', '.join(langs))
        return True
